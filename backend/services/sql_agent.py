"""
SQL Agent: Natürliche Sprache → SQL → SQLite-Ausführung.
Gibt (sql, columns, rows, error) zurück.
"""
import re
import sqlite3

from google import genai

from config import GEMINI_API_KEY, GEMINI_FLASH_MODEL

_client = genai.Client(api_key=GEMINI_API_KEY)


# ---------------------------------------------------------------------------
# SQLite compatibility layer (deterministisch, kein LLM nötig)
# ---------------------------------------------------------------------------

def apply_sqlite_compat(sql: str) -> str:
    fixed = sql

    # ILIKE -> LIKE
    fixed = re.sub(r'\bILIKE\b', 'LIKE', fixed, flags=re.IGNORECASE)

    # WITH ROLLUP / CUBE
    for clause in ("WITH ROLLUP", "WITH CUBE", "GROUPING SETS"):
        fixed = re.sub(re.escape(clause) + r'[^;]*', '', fixed, flags=re.IGNORECASE)

    # LIMIT x,y -> LIMIT y OFFSET x
    m = re.search(r'\bLIMIT\s+(\d+)\s*,\s*(\d+)', fixed, re.IGNORECASE)
    if m:
        fixed = fixed[:m.start()] + f"LIMIT {m.group(2)} OFFSET {m.group(1)}" + fixed[m.end():]

    # TRUE/FALSE -> 1/0
    fixed = re.sub(r'\bTRUE\b', '1', fixed, flags=re.IGNORECASE)
    fixed = re.sub(r'\bFALSE\b', '0', fixed, flags=re.IGNORECASE)

    # STDDEV/VARIANCE -> manual calculation
    def _replace_stat_fn(match: re.Match) -> str:
        col = match.group(1).strip()
        variance_expr = f"(AVG(({col})*({col})) - AVG({col})*AVG({col}))"
        fn = match.group(0).split("(")[0].upper().rstrip()
        if any(s in fn for s in ("STDDEV", "STDEV")):
            return f"SQRT({variance_expr})"
        return variance_expr

    for stat_fn in ("VARIANCE", "VAR_POP", "VAR_SAMP", "STDDEV", "STDDEV_POP",
                    "STDDEV_SAMP", "STD", "STDEV", "STDEV_POP", "STDEV_SAMP"):
        pattern = rf'\b{stat_fn}\s*\(([^)]+)\)'
        fixed = re.sub(pattern, _replace_stat_fn, fixed, flags=re.IGNORECASE)

    # MEDIAN -> AVG fallback
    fixed = re.sub(
        r'\bMEDIAN\s*\(([^)]+)\)',
        lambda m: f"AVG({m.group(1).strip()})",
        fixed, flags=re.IGNORECASE
    )

    # PERCENTILE_CONT/DISC -> AVG approximation
    fixed = re.sub(
        r'\bPERCENTILE_(?:CONT|DISC)\s*\([^)]+\)\s*WITHIN\s+GROUP\s*\([^)]+\)',
        lambda m: "AVG(col)",
        fixed, flags=re.IGNORECASE
    )

    # Multi-statement: keep only first
    if ';' in fixed:
        stmts = [s.strip() for s in fixed.split(';') if s.strip()]
        if len(stmts) > 1:
            fixed = stmts[0]

    # FILTER(WHERE ...) -> CASE WHEN
    def _replace_filter(m: re.Match) -> str:
        agg = m.group(1).strip()
        condition = m.group(2).strip()
        inner = re.match(r'(\w+)\s*\((.*)\)', agg)
        if inner:
            fn, col = inner.group(1).upper(), inner.group(2).strip()
            if fn == 'COUNT':
                return f"COUNT(CASE WHEN {condition} THEN 1 END)"
            return f"{fn}(CASE WHEN {condition} THEN {col} END)"
        return agg
    fixed = re.sub(
        r'(\w+\s*\([^)]*\))\s+FILTER\s*\(\s*WHERE\s+([^)]+)\)',
        _replace_filter, fixed, flags=re.IGNORECASE
    )

    # NTILE without OVER
    fixed = re.sub(
        r'\bNTILE\s*\(\s*(\d+)\s*\)(?!\s*OVER)',
        r'NTILE(\1) OVER (ORDER BY rowid)',
        fixed, flags=re.IGNORECASE
    )

    # Reservierte Schlüsselwörter als Tabellennamen automatisch quoten
    _RESERVED = r'\b(order|group|select|where|having|index|table|by|check|default|exists|'  \
                r'references|transaction|union|values|view)\b'

    # BUG-FIX: "order.col" → "order".col  (LLM quoted Tabelle+Spalte zusammen)
    fixed = re.sub(
        r'"(' + _RESERVED[3:-3] + r')\.([^"]+)"',
        lambda m: f'"{m.group(1)}".{m.group(2)}',
        fixed,
        flags=re.IGNORECASE
    )

    # table.col → "table".col (nur wenn nicht schon gequotet)
    def _quote_reserved_prefix(m: re.Match) -> str:
        word = m.group(1)
        full = m.group(0)
        start = m.start()
        if start > 0 and fixed[start - 1] == '"':
            return full
        return f'"{word}".'
    fixed = re.sub(
        _RESERVED + r'\.',
        _quote_reserved_prefix,
        fixed,
        flags=re.IGNORECASE
    )
    # FROM/JOIN word → FROM/JOIN "word"
    def _quote_reserved_table(m: re.Match) -> str:
        keyword = m.group(1)   # FROM or JOIN
        word    = m.group(2)   # reserved table name
        return f'{keyword} "{word}"'
    fixed = re.sub(
        r'\b(FROM|JOIN)\s+(' + _RESERVED[3:-3] + r')\b(?!\s*\()',
        _quote_reserved_table,
        fixed,
        flags=re.IGNORECASE
    )

    return fixed


_WRITE_STMT = re.compile(
    r'^\s*(?:DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE|CREATE|REPLACE|MERGE)\b',
    re.IGNORECASE
)


def _validate_sql(sql: str) -> None:
    """Verhindert destruktive SQL-Statements. Nur SELECT/WITH erlaubt."""
    clean = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
    clean = re.sub(r'--[^\n]*', '', clean).strip()
    if _WRITE_STMT.match(clean):
        stmt = clean.split()[0].upper()
        raise ValueError(f"Unerlaubte SQL-Operation '{stmt}'. Nur SELECT-Abfragen sind erlaubt.")


def _extract_sql(text: str) -> str:
    """Extrahiere SQL aus LLM-Antwort (Fences oder direkt)."""
    m = re.search(r'```(?:sql)?\s*(.*?)```', text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Bare SELECT/WITH
    m = re.search(r'((?:WITH|SELECT)\b.*)', text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return text.strip()


def _call_gemini(system_prompt: str, user_prompt: str) -> str:
    from google.genai import types
    response = _client.models.generate_content(
        model=GEMINI_FLASH_MODEL,
        contents=user_prompt,
        config=types.GenerateContentConfig(system_instruction=system_prompt),
    )
    return response.text or ""


def _execute(conn: sqlite3.Connection, sql: str) -> tuple[list[str], list[list], str | None]:
    try:
        cur = conn.execute(sql)
        columns = [d[0] for d in (cur.description or [])]
        rows = [list(r) for r in cur.fetchall()]
        return columns, rows, None
    except Exception as e:
        return [], [], str(e)


def _build_few_shot_block(successful_queries: list) -> str:
    """Baut einen Few-Shot-Block aus den letzten erfolgreichen Queries der Session."""
    if not successful_queries:
        return ""
    examples = successful_queries[-3:]  # Maximal 3 aktuellste
    lines = ["\n\nBewährte SQL-Beispiele aus dieser Datenbank (Muster übernehmen):"]
    for ex in examples:
        lines.append(f"Frage: {ex['question']}\nSQL: {ex['sql']}")
    return "\n".join(lines)


def run_query(
    conn: sqlite3.Connection,
    schema_description: str,
    question: str,
    successful_queries: list | None = None,
) -> tuple[str, list[str], list[list], str | None]:
    """
    Haupteintrittspunkt: Frage → SQL → Ausführung.
    Gibt (sql, columns, rows, error) zurück.
    Bei Fehler: 1 Retry mit Fehlermeldung.
    """
    system_prompt = (
        "Du bist ein SQL-Experte. Generiere ausschliesslich SQLite-kompatibles SQL. "
        "Antworte NUR mit der SQL-Abfrage, ohne Erklärungen, ohne Markdown. "
        "Erlaubte Statements: ausschließlich SELECT (inkl. WITH/CTE). "
        "NIEMALS DROP, DELETE, UPDATE, INSERT, ALTER, TRUNCATE, CREATE oder REPLACE generieren.\n"
        "JOIN-Regeln: Das Schema enthält unter 'VERPFLICHTENDE JOIN-SYNTAX' die exakten JOIN-Ausdrücke. "
        "KOPIERE diese exakt in deine Query — ersetze sie NICHT durch eigene Formulierungen. "
        "Verwende NIEMALS rowid wenn im Schema eine id-Spalte als Ziel angegeben ist. "
        "Verknüpfe Tabellen NIEMALS über Textspalten wie artikelnummer, kundennummer, code. "
        "Standard-LIMIT: Wenn die Frage nicht explizit 'alle' verlangt, begrenze das Ergebnis auf LIMIT 20.\n"
        "Typ-Mismatches: Wenn das Schema 'ACHTUNG Typ-Mismatches' enthält:\n"
        "  - Bei 'TYP-MISMATCH (CAST möglich)': verwende den angegebenen CAST-Ausdruck exakt.\n"
        "  - Bei 'SCHLÜSSEL-MISMATCH': CAST hilft nicht — verwende ausschließlich den rowid-basierten JOIN. "
        "Versuche NIEMALS einen CAST wenn SCHLÜSSEL-MISMATCH dokumentiert ist.\n"
        "Wichtig: Spalten mit Typ REAL oder INTEGER sind direkt numerisch verwendbar. "
        "Nur bei Spalten mit Typ TEXT, die Zahlen enthalten könnten, CAST(spalte AS REAL) verwenden. "
        "Für Sortierung und Vergleiche numerischer Werte immer den deklarierten Typ beachten.\n"
        "Formatierte Zahlen: Wenn das Schema 'enthält Währungssymbol(...) → REPLACE vor CAST nötig' oder "
        "'enthält Tausendertrennzeichen(,) → REPLACE vor CAST nötig' angibt, "
        "MUSS bei JEDER numerischen Operation dieser Spalte zuerst bereinigt werden: "
        "CAST(REPLACE(REPLACE(spalte, 'SYMBOL', ''), ',', '') AS REAL). "
        "Das gilt auch für Vergleiche (WHERE), Aggregationen (AVG, MAX) und Sortierungen (ORDER BY).\n"
        "MIXED-TYPE Spalten: Wenn das Schema 'MIXED-TYPE' angibt, verwende immer "
        "CASE WHEN spalte GLOB '[0-9]*' THEN CAST(spalte AS REAL) ELSE NULL END statt direktem CAST.\n"
        "ORDINAL-Spalten: Wenn das Schema 'ORDINAL-Skala: A < B < C' angibt, "
        "nutze für Vergleiche ein CASE-Mapping statt String-Vergleich: "
        "CASE spalte WHEN 'A' THEN 1 WHEN 'B' THEN 2 WHEN 'C' THEN 3 END >= CASE 'Zielwert' WHEN 'A' THEN 1 ... END.\n"
        "Preisfelder: Wenn der Nutzer 'Preis', 'kostet' oder 'Verkaufspreis' sagt ohne Spezifikation, "
        "verwende listenpreis_netto. Nur bei expliziter Nennung: 'Einkaufspreis' → einkaufspreis_netto, "
        "'Aktionspreis' → aktionspreis_netto.\n"
        "Geldbeträge: Bei allen Berechnungen mit Preisen, Umsätzen, Margen oder Beträgen immer ROUND(..., 2) verwenden. "
        "Niemals rohe Floating-Point-Werte ausgeben.\n"
        "LIMIT: Verwende LIMIT 1 nur bei Fragen nach genau EINEM Ergebnis (z.B. 'das teuerste', 'der beste', 'der höchste'). "
        "Bei Fragen nach Verteilung, Vergleich, Zusammenhang oder Verhältnis (z.B. 'pro Kunde', 'je Kategorie', 'im Vergleich') "
        "zeige ALLE relevanten Einträge ohne LIMIT oder mit LIMIT 10.\n"
        "Berechnete Metriken: Jede Kennzahl, nach der sortiert oder gefiltert wird (z.B. Marge, Verhältnis, Score), "
        "MUSS auch als benannte Spalte im SELECT stehen — nicht nur in ORDER BY oder WHERE. "
        "Beispiel: SELECT ..., ROUND(AVG(a) / AVG(b), 4) AS verhaeltnis ... ORDER BY verhaeltnis DESC.\n"
        "Aggregationsebene: Bei Begriffen wie 'Bestellwert', 'Auftragswert', 'Warenkorbgröße' oder 'durchschnittlicher Umsatz pro Kunde/Auftrag' "
        "immer zuerst auf Auftragsebene aggregieren (SUM pro Auftrag in Subquery), dann auf der nächsten Ebene mitteln. "
        "Niemals direkt über Einzelpositionen mitteln wenn Auftragsebene gemeint ist. "
        "Beispiel: SELECT AVG(order_total) FROM (SELECT SUM(menge*preis) AS order_total FROM positionen GROUP BY auftrags_id).\n"
        "Primärschlüssel-Namen: Der Primärschlüssel einer Tabelle heißt fast immer 'id', nicht 'productid', 'customerid', 'employeeid' o.ä. "
        "Diese langen Formen sind Fremdschlüssel in Kindtabellen (z.B. orderdetail.productid, order.customerid). "
        "In der Elterntabelle selbst heißt der PK schlicht 'id': product.id, customer.id, employee.id. "
        "Falsch: JOIN product p ON od.productid = p.productid. Richtig: JOIN product p ON od.productid = p.id. "
        "Wenn das Schema 'VERPFLICHTENDE JOIN-SYNTAX' enthält, diese exakt verwenden.\n"
        "Territorien vs. Lieferort: 'Territorium einer Bestellung' oder 'Bestellregion' bedeutet die Lieferadresse "
        "(order.shipcity, order.shipregion, order.shipcountry) — NICHT die Vertriebsterritorien des Mitarbeiters "
        "(employeeterritory). employeeterritory beschreibt Zuständigkeitsbereiche von Mitarbeitern, "
        "nicht den Lieferort einer konkreten Bestellung.\n"
        "NOT IN Verbot: Verwende NIEMALS 'NOT IN (SELECT ...)' — das liefert immer leer wenn die Subquery auch nur einen NULL-Wert enthält. "
        "Verwende stattdessen immer: NOT EXISTS (SELECT 1 FROM ... WHERE ...) "
        "oder: LEFT JOIN ... ON ... WHERE ziel.id IS NULL.\n"
        "Self-JOIN Hierarchien: Bei hierarchischen Self-JOINs (z.B. Mitarbeiter → Vorgesetzter via reportsto) "
        "NIEMALS OR-Bedingungen im JOIN verwenden die einen Datensatz mit sich selbst verknüpfen. "
        "Korrektes Muster: JOIN employee manager ON mitarbeiter.reportsto = manager.id. "
        "Kein: ON ... OR mitarbeiter.id = manager.id.\n"
        "Division-Sicherheit: Bei jeder Division durch eine aggregierte Zahl (COUNT, SUM) immer NULLIF verwenden: "
        "CAST(zaehler AS REAL) / NULLIF(nenner, 0). "
        "Bei Quoten mit NULL-Werten (z.B. Verspätungsquote mit shippeddate IS NULL): "
        "Nenner nur über tatsächlich vorhandene Werte berechnen: NULLIF(SUM(CASE WHEN col IS NOT NULL THEN 1 END), 0).\n"
        "Duplikate: Wenn eine Query Artikel, Kunden oder Lieferanten mehrfach zeigen würde (weil mehrere Positionen verknüpft sind), "
        "überlege ob eine Aggregation (AVG, MIN/MAX der Kennzahl) sinnvoller ist als Einzelzeilen. "
        "Verwende GROUP BY auf der sinnvollen Entitätsebene statt jeden JOIN-Match einzeln auszugeben.\n"
        "Semantische Filter: Wenn nach einer semantischen Kategorie gefiltert wird (z.B. 'Eilaufträge', 'hochwertige Produkte', 'kritische Lagermengen'), "
        "prüfe alle Werte der Spalte im Schema auf semantische Zugehörigkeit — nicht nur auf exakten Wortlaut. "
        "Verwende OR-Bedingungen oder LIKE-Pattern um alle semantisch passenden Werte einzuschließen.\n"
        "Kontextwerte: Bei MIN/MAX/Spanne-Berechnungen füge die Einzelwerte (MIN und MAX) als zusätzliche Spalten hinzu. "
        "Bei Kreuztabellen füge eine Gesamtsummen-Zeile oder -Spalte hinzu wenn es die Lesbarkeit verbessert.\n"
        "Datumspalten: Das Schema gibt das Format jeder Datumsspalte an (z.B. 'Format DD.MM.YYYY'). "
        "Wenn eine Spalte gemischte Formate enthält, verwende einen CASE-Parser der alle Formate abdeckt: "
        "CASE "
        "WHEN col LIKE '__.__.____ %' OR col LIKE '__.__.____' THEN date(substr(col,7,4)||'-'||substr(col,4,2)||'-'||substr(col,1,2)) "
        "WHEN col LIKE '__/__/____ %' OR col LIKE '__/____/____' THEN date(substr(col,7,4)||'-'||substr(col,1,2)||'-'||substr(col,4,2)) "
        "ELSE date(col) END. "
        "Wenn das Format eindeutig aus dem Schema bekannt ist, verwende nur den passenden Branch.\n"
        "Top-N Ranking: Bei Fragen nach 'Top X', 'beste N', 'schlechteste N' oder 'höchste/niedrigste N' "
        "verwende ORDER BY ... DESC/ASC LIMIT N — kein RANK() OVER wenn nicht explizit nach Rang-Spalte gefragt. "
        "Beispiel: SELECT produkt, SUM(umsatz) AS gesamt FROM verkäufe GROUP BY produkt ORDER BY gesamt DESC LIMIT 5.\n"
        "YoY/MoM-Vergleiche: Für Jahres- oder Monatsvergleiche verwende das CTE-Muster mit Self-Join: "
        "WITH perioden AS (SELECT <datum_extraktion> AS periode, SUM(wert) AS gesamt FROM tabelle GROUP BY periode) "
        "SELECT curr.periode, curr.gesamt, prev.gesamt AS vorperiode, "
        "ROUND((curr.gesamt - prev.gesamt) * 100.0 / NULLIF(prev.gesamt, 0), 1) AS veraenderung_pct "
        "FROM perioden curr LEFT JOIN perioden prev ON curr.periode = prev.periode + 1 ORDER BY curr.periode. "
        "Beachte dabei das dokumentierte Datumsformat der Spalte für die Extraktion "
        "(z.B. substr(col,7,4) für DD.MM.YYYY, strftime('%Y', col) für ISO-Format).\n"
        "Rollende Durchschnitte: Bei Fragen nach 'gleitendem Durchschnitt', 'rollend', 'geglättet' oder 'Trend' "
        "aggregiere zuerst auf Tagesebene in einem CTE, dann wende AVG() OVER (ROWS BETWEEN N PRECEDING AND CURRENT ROW) an: "
        "WITH daily AS (SELECT date(datum_col) AS tag, SUM(wert) AS tageswert FROM tabelle GROUP BY tag) "
        "SELECT tag, tageswert, ROUND(AVG(tageswert) OVER (ORDER BY tag ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2) "
        "AS rollend_7d FROM daily ORDER BY tag.\n"
        "Pareto / 80-20-Regel: Bei Fragen nach 'wichtigsten', '80/20', 'Pareto' oder 'welche X machen den meisten Umsatz': "
        "Gruppiere nach dem Objekt, summiere die Kennzahl, berechne kumulative Prozente per Window-Function und klassifiziere: "
        "WITH kum AS (SELECT obj, SUM(wert) AS gesamt, "
        "SUM(SUM(wert)) OVER (ORDER BY SUM(wert) DESC) * 100.0 / NULLIF(SUM(SUM(wert)) OVER (), 0) AS kum_pct "
        "FROM tabelle GROUP BY obj) "
        "SELECT *, CASE WHEN kum_pct <= 80 THEN 'A' WHEN kum_pct <= 95 THEN 'B' ELSE 'C' END AS klasse FROM kum ORDER BY gesamt DESC.\n"
        "ABC-Analyse: Bei expliziter ABC-Frage dasselbe Muster wie Pareto — A=0–80%, B=80–95%, C=95–100% kumulierter Anteil. "
        "Immer alle drei Klassen im Ergebnis ausgeben.\n"
        "Z-Score / Ausreißer / Anomalien: SQLite hat kein STDEV() — verwende die manuelle Formel: "
        "WITH stats AS (SELECT AVG(col) AS mean, "
        "SQRT(AVG(col*col) - AVG(col)*AVG(col)) AS std FROM tabelle), "
        "scored AS (SELECT t.*, (col - mean) / NULLIF(std, 0) AS z_score FROM tabelle t, stats) "
        "SELECT * FROM scored WHERE ABS(z_score) > 2.5 ORDER BY ABS(z_score) DESC. "
        "Bei Fragen nach 'Ausreißer', 'Anomalie', 'Spike', 'extrem' oder 'ungewöhnlich' dieses Muster verwenden. "
        "Fallback bei leerem Ergebnis: Wenn WHERE ABS(z_score) > 2.5 keine Zeilen liefert, "
        "entferne die WHERE-Bedingung und zeige die Top-5 nach ABS(z_score) DESC — "
        "so sieht der User immer die relativ auffälligsten Werte, auch wenn keine echten Ausreißer existieren. "
        "Füge in diesem Fall eine Spalte 'hinweis' mit dem Wert 'kein echter Ausreißer (Z<2.5)' hinzu.\n"
        "Soft-Delete: Wenn eine Tabelle eine Spalte 'deleted_at' hat, füge automatisch 'AND tabelle.deleted_at IS NULL' "
        "in alle WHERE-Bedingungen ein — es sei denn, die Frage fragt explizit nach gelöschten Einträgen.\n"
        "Zeitreferenz: Wenn die Frage relative Zeitangaben verwendet ('letzte 6 Monate', 'letztes Jahr', 'aktuell'), "
        "verwende NIEMALS date('now') als Referenz ohne vorher zu prüfen ob die Daten aktuell sind. "
        "Baue stattdessen eine Subquery: SELECT MAX(datumsspalte) FROM tabelle als Referenzpunkt. "
        "Beispiel: statt WHERE orderdate >= date('now', '-6 months') schreibe "
        "WHERE orderdate >= date((SELECT MAX(orderdate) FROM \"order\"), '-6 months'). "
        "Das gilt besonders bei historischen Datenbanken wo MAX(datum) weit in der Vergangenheit liegt.\n"
        "Entitätsnamen: Bei Fragen die mit 'Welche Kunden', 'Welche Mitarbeiter', 'Welche Lieferanten' beginnen, "
        "stelle sicher dass der Name (companyname, name, contactname o.ä.) immer im SELECT steht.\n"
        "Namensformatierung: Bei Personen (Mitarbeiter, Kontakte) immer Vorname zuerst: "
        "firstname || ' ' || lastname AS name. NIEMALS lastname || ' ' || firstname.\n"
        "Reservierte Schlüsselwörter als Tabellennamen: Tabellen wie 'order', 'group', 'select', 'index' "
        "MÜSSEN im FROM/JOIN immer gequotet UND sofort mit einem Alias versehen werden. "
        "Danach NUR noch den Alias verwenden — niemals mehr den Tabellennamen in Spaltenreferenzen, "
        "Funktionsaufrufen oder WHERE-Bedingungen. "
        "Falsch: FROM order ... julianday(order.shippeddate). "
        "Richtig: FROM \"order\" o ... julianday(o.shippeddate). "
        "KRITISCH beim Quoting: Nur den Tabellennamen allein quoten — niemals Tabelle und Spalte zusammen. "
        "FALSCH: \"order.employeeid\" — das macht 'order.employeeid' zu einem String-Literal! "
        "RICHTIG: \"order\".employeeid oder Alias o.employeeid. "
        "Diese Regel gilt in FROM, JOIN, ON-Bedingungen, CTEs und Subqueries — überall ohne Ausnahme.\n"
        "Spalten-Aliase: Wenn im SELECT mehrere Tabellen Spalten mit gleichem Namen haben "
        "(z.B. supplier.companyname und shipper.companyname, beide heißen 'companyname'), "
        "MUSS jede Spalte einen eindeutigen AS-Alias erhalten: "
        "supplier.companyname AS supplier_name, shipper.companyname AS shipper_name. "
        "Gilt für alle JOIN-Queries mit potenziell gleichen Spaltennamen.\n"
        "Bei analytischen oder konzeptuellen Fragen (z.B. 'Wie würde ich X entwickeln?', 'Was ist der beste Ansatz für Y?'): "
        "Generiere eine SQL-Abfrage, die die relevanten Rohdaten aus der Datenbank holt, "
        "die für die Beantwortung benötigt werden — z.B. Kennzahlen, Verteilungen, Korrelationsgrundlagen. "
        "Kein Modellbau in SQL, sondern Datenextraktion als Grundlage.\n\n"
        "Mehrstufige Fragen: Bei Fragen der Form 'Wer ist der stärkste X ... und mit welchem Y ...' oder "
        "'Welcher X macht am meisten ... und was/wer ist dabei ...': "
        "NIEMALS nur das beste Paar (X+Y) per LIMIT 1 ausgeben — das liefert den falschen Winner wenn Y verteilt ist. "
        "Korrektes Muster: Zuerst den Winner über alle Y aggregieren (primäres Ranking per CTE), "
        "dann den sekundären Drill-down nur für diesen Winner: "
        "WITH primary_rank AS (SELECT x_id, SUM(wert) AS gesamt_total FROM tabelle GROUP BY x_id), "
        "winner AS (SELECT x_id, gesamt_total FROM primary_rank ORDER BY gesamt_total DESC LIMIT 1) "
        "SELECT x.name, winner.gesamt_total, y.name, SUM(wert) AS kennzahl FROM tabelle "
        "JOIN winner ON tabelle.x_id = winner.x_id JOIN x ON ... JOIN y ON ... "
        "GROUP BY y_id ORDER BY kennzahl DESC LIMIT 1. "
        "WICHTIG: Den Gesamt-Winner-Wert (gesamt_total) immer mit in den finalen SELECT aufnehmen — "
        "der User soll sowohl den Gesamtwert des Winners als auch den Drill-down-Wert sehen.\n"
        "Performance-Schutz: Bei Queries ohne natürliches LIMIT (z.B. keine Top-N-Frage, kein Aggregat das eine Zeile liefert) "
        "und bei großen Tabellen füge LIMIT 5000 als Sicherheitsnetz hinzu. "
        "Ausnahme: Der User fragt explizit nach 'alle', 'gesamt' oder einem vollständigen Export.\n\n"
        f"{schema_description}"
        + _build_few_shot_block(successful_queries or [])
    )

    # Erster Versuch
    raw = _call_gemini(system_prompt, question)
    sql = _extract_sql(raw)
    sql = apply_sqlite_compat(sql)
    try:
        _validate_sql(sql)
    except ValueError as e:
        return sql, [], [], str(e)
    columns, rows, error = _execute(conn, sql)

    if error:
        # Gezielter Hinweis bei Syntax-Fehlern mit reservierten Schlüsselwörtern
        syntax_hint = ""
        error_lower = error.lower()
        if "syntax" in error_lower or "near" in error_lower:
            syntax_hint = (
                "HINWEIS: Häufige Ursache für Syntax-Fehler — reservierte Schlüsselwörter als Tabellennamen. "
                "Prüfe ob Tabellen wie 'order', 'group', 'select', 'where', 'index' in der Query vorkommen "
                "und quote sie mit doppelten Anführungszeichen: FROM \"order\" o, JOIN \"order\" o ON ...\n\n"
            )
        retry_prompt = (
            f"Frage: {question}\n\n"
            f"Deine fehlerhafte SQL:\n{sql}\n\n"
            f"SQLite-Fehler: {error}\n\n"
            f"{syntax_hint}"
            f"Korrigiere die SQL. Antworte NUR mit der korrigierten SQL."
        )
        raw2 = _call_gemini(system_prompt, retry_prompt)
        sql2 = _extract_sql(raw2)
        sql2 = apply_sqlite_compat(sql2)
        try:
            _validate_sql(sql2)
        except ValueError as e:
            return sql2, [], [], str(e)
        columns2, rows2, error2 = _execute(conn, sql2)
        if not error2:
            return sql2, columns2, rows2, None
        return sql2, [], [], error2

    # Leeres Ergebnis das verdächtig wirkt (z.B. Filter auf Statusspalte einer Kerntabelle)
    if not rows and _is_unplausible_empty(sql):
        retry_prompt = (
            f"Frage: {question}\n\n"
            f"Deine SQL:\n{sql}\n\n"
            f"Das Ergebnis hat 0 Zeilen, obwohl das unwahrscheinlich wirkt. "
            f"Mögliche Ursachen: Filter auf eine Statusspalte mit falschem Wert, "
            f"zu restriktive WHERE-Bedingung, oder Spalte existiert nicht mit diesem Wert. "
            f"Das Schema enthält folgende Tabellen und Spalten:\n{schema_description}\n\n"
            f"Schlage basierend auf dem Schema eine konkrete Filter-Lockerung vor und setze sie direkt um. "
            f"Antworte NUR mit der korrigierten SQL."
        )
        raw2 = _call_gemini(system_prompt, retry_prompt)
        sql2 = _extract_sql(raw2)
        sql2 = apply_sqlite_compat(sql2)
        try:
            _validate_sql(sql2)
        except ValueError:
            return sql, columns, rows, None
        columns2, rows2, error2 = _execute(conn, sql2)
        if not error2 and rows2:
            return sql2, columns2, rows2, None

    # Validierungsschritt: Prüfe ob Ergebnis verdächtig ist
    quality_issue = _check_result_quality(columns, rows)
    if quality_issue:
        retry_prompt = (
            f"Frage: {question}\n\n"
            f"Deine SQL:\n{sql}\n\n"
            f"Das Ergebnis ist verdächtig: {quality_issue}\n"
            f"Überarbeite die SQL um das Problem zu beheben. "
            f"Antworte NUR mit der korrigierten SQL."
        )
        raw2 = _call_gemini(system_prompt, retry_prompt)
        sql2 = _extract_sql(raw2)
        sql2 = apply_sqlite_compat(sql2)
        try:
            _validate_sql(sql2)
        except ValueError:
            return sql, columns, rows, None  # Behalte Original bei Guardrail-Verletzung
        columns2, rows2, error2 = _execute(conn, sql2)
        # Nur übernehmen wenn besser als Original
        if not error2 and rows2:
            quality_issue2 = _check_result_quality(columns2, rows2)
            if not quality_issue2:
                return sql2, columns2, rows2, None

    return sql, columns, rows, None


_CORE_TABLE_FILTER = re.compile(
    r'\bWHERE\b.+\b(aktiv|status|enabled|active)\b',
    re.IGNORECASE | re.DOTALL,
)
_NEGATION_QUERY = re.compile(
    r'\bNOT\s+IN\b|\bNOT\s+EXISTS\b|\bEXCEPT\b|\bLEFT\s+JOIN\b.+\bIS\s+NULL\b',
    re.IGNORECASE | re.DOTALL,
)


def _is_unplausible_empty(sql: str) -> bool:
    """Gibt True zurück wenn ein leeres Ergebnis verdächtig ist (z.B. Filter auf Statusspalte)."""
    if _NEGATION_QUERY.search(sql):
        return False  # Logisch leer — kein Retry nötig
    return bool(_CORE_TABLE_FILTER.search(sql))


def _check_result_quality(columns: list[str], rows: list[list]) -> str | None:
    """
    Prüft ob ein SQL-Ergebnis verdächtig ist.
    Gibt einen Beschreibungs-String zurück wenn ein Problem erkannt wurde, sonst None.
    """
    if not rows or not columns:
        return None

    # Prüfe berechnete/numerische Spalten auf NULL-Anteil
    for col_idx, col_name in enumerate(columns):
        col_vals = [row[col_idx] for row in rows if col_idx < len(row)]
        if not col_vals:
            continue
        null_count = sum(1 for v in col_vals if v is None or str(v).strip() in ('', 'None', 'NULL'))
        null_ratio = null_count / len(col_vals)
        if null_ratio > 0.5:
            return (
                f"Spalte '{col_name}' hat {null_ratio:.0%} NULL-Werte. "
                f"Möglicherweise fehlender REPLACE/CAST bei formatierten Zahlen oder MIXED-TYPE Spalte."
            )

    return None
