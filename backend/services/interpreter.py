"""
Interpreter: Rohdaten + Frage → professionelle Antwort in natürlicher Sprache.
Nutzt Gemini Pro für gehobene Textqualität.
"""
import re

from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GEMINI_PRO_MODEL, MAX_ROWS_FOR_INTERPRETATION

_client = genai.Client(api_key=GEMINI_API_KEY)


def _rows_to_text(columns: list[str], rows: list[list], max_rows: int = MAX_ROWS_FOR_INTERPRETATION) -> str:
    """Wandle Tabelle in kompakten Text um (max max_rows Zeilen)."""
    if not columns or not rows:
        return "(Keine Daten)"
    header = " | ".join(columns)
    separator = "-" * len(header)
    lines = [header, separator]
    for row in rows[:max_rows]:
        lines.append(" | ".join(str(v) if v is not None else "–" for v in row))
    if len(rows) > max_rows:
        lines.append(f"... ({len(rows) - max_rows} weitere Zeilen)")
    return "\n".join(lines)


_TEMPORAL_FILTER = re.compile(
    r"date\s*\(|strftime|julianday|NOW\(\)|'now'|\b(monat|monatlich|jahr|woche|zeitraum|periode|quartal)\b",
    re.IGNORECASE,
)
_NEGATION_QUERY = re.compile(
    r"\bNOT\s+IN\b|\bNOT\s+EXISTS\b|\bEXCEPT\b|\bLEFT\s+JOIN\b.+\bIS\s+NULL\b",
    re.IGNORECASE | re.DOTALL,
)
_CORE_TABLE_FILTER = re.compile(
    r"\bWHERE\b.+\b(aktiv|status|enabled|active)\b",
    re.IGNORECASE | re.DOTALL,
)


def _classify_empty_result(question: str, sql: str) -> str:
    """
    Klassifiziert warum eine Query 0 Zeilen liefert:
    - VALIDE_LEER: NOT IN / NOT EXISTS / EXCEPT → logische Abwesenheit
    - DATEN_FEHLEN: Zeitfilter oder spezifischer Datensatz gesucht
    - UNPLAUSIBEL: Filter auf Statusspalte einer Kerntabelle → verdächtiges Ergebnis
    """
    if _NEGATION_QUERY.search(sql):
        return "VALIDE_LEER"
    if _CORE_TABLE_FILTER.search(sql):
        return "UNPLAUSIBEL"
    if _TEMPORAL_FILTER.search(sql):
        return "DATEN_FEHLEN"
    return "DATEN_FEHLEN"


def _check_duplicate_values(columns: list[str], rows: list[list]) -> str | None:
    """
    Erkennt verdächtige identische numerische Werte in einer aggregierten Ergebnisspalte.
    Wenn ≥3 verschiedene Entitäten exakt denselben Wert haben, ist das ein Warnsignal
    für einen möglichen JOIN-Fehler (z.B. Umsatz mehrfach gezählt).
    """
    if len(rows) < 3 or len(columns) < 2:
        return None

    # Letzte numerische Spalte prüfen (typisch: aggregierter Wert)
    for col_idx in range(len(columns) - 1, 0, -1):
        vals = []
        for row in rows:
            if col_idx >= len(row):
                continue
            v = row[col_idx]
            try:
                vals.append(float(str(v).replace(",", ".")))
            except (ValueError, TypeError):
                break
        else:
            if len(vals) < 3:
                continue
            # Zähle wie oft der häufigste Wert vorkommt
            from collections import Counter
            counts = Counter(vals)
            most_common_val, most_common_count = counts.most_common(1)[0]
            if most_common_count >= 3 and most_common_count >= len(vals) * 0.4:
                return (
                    f"ACHTUNG: {most_common_count} verschiedene Einträge haben exakt denselben Wert "
                    f"({most_common_val}) in Spalte '{columns[col_idx]}'. "
                    f"Das kann auf einen JOIN-Fehler hinweisen (z.B. Werte werden mehrfach gezählt). "
                    f"Weise in deiner Antwort explizit auf diese Auffälligkeit hin."
                )
    return None


def interpret(
    question: str,
    sql: str,
    columns: list[str],
    rows: list[list],
) -> str:
    """
    Generiere eine professionelle Antwort auf die Frage basierend auf den SQL-Ergebnissen.
    Gibt leere Strings zurück wenn keine Daten vorhanden.
    """
    if not rows:
        empty_hint = _classify_empty_result(question, sql)
        system_prompt_empty = (
            "Du bist ein professioneller Datenanalyst. "
            "Eine SQL-Abfrage hat 0 Zeilen zurückgegeben. "
            "Interpretiere das Ergebnis passend zum angegebenen Kontext:\n"
            "- VALIDE_LEER: Die Query ist korrekt, es gibt schlicht keine passenden Daten. "
            "Formuliere die Abwesenheit als positive Aussage (z.B. 'Alle X erfüllen Y bereits').\n"
            "- DATEN_FEHLEN: Die gefragten Daten existieren möglicherweise nicht oder der Zeitraum ist leer. "
            "Weise transparent darauf hin, dass keine Einträge für diesen Zeitraum/Filter vorliegen.\n"
            "- UNPLAUSIBEL: Das Ergebnis wirkt unrealistisch für ein produktives System "
            "(z.B. 0 aktive Datensätze in einer Kerntabelle). "
            "Formuliere die Antwort und ergänze einen Hinweis, dass dies auf ein Datenproblem hindeuten könnte.\n"
            "Antworte auf Deutsch, 1-3 Sätze, direkt zur Sache."
        )
        response = _client.models.generate_content(
            model=GEMINI_PRO_MODEL,
            contents=f"Kontext: {empty_hint}\n\nFrage: {question}\n\nSQL:\n{sql}\n\nDas Ergebnis hat 0 Zeilen.",
            config=types.GenerateContentConfig(system_instruction=system_prompt_empty),
        )
        return (response.text or "").strip()

    table_text = _rows_to_text(columns, rows)
    n = len(rows)
    plausibility_hint = _check_duplicate_values(columns, rows)

    system_prompt = (
        "Du bist ein professioneller Datenanalyst. "
        "Du erhältst eine Frage, die zugehörige SQL-Abfrage und deren Ergebnisse. "
        "WICHTIG: Deine Antwort darf AUSSCHLIESSLICH auf den gelieferten SQL-Ergebnissen basieren. "
        "Erfinde keine Berechnungen, Formeln oder Werte, die nicht in den Daten stehen. "
        "Nenne konkrete Zahlen direkt aus der Ergebnistabelle — niemals selbst berechnete Werte. "
        "Extrapolationsverbot: Schlussfolgere NIEMALS auf Zeilen oder Werte die nicht in der Ergebnistabelle sichtbar sind. "
        "Wenn das Ergebnis nur 1 Zeile zeigt, beschreibe nur diese eine Zeile — keine Annahmen über andere Zeilen. "
        "Wenn Daten durch LIMIT abgeschnitten sind, weise darauf hin statt zu extrapolieren. "
        "Falls die SQL-Ergebnisse die Frage nur teilweise beantworten, weise explizit darauf hin. "
        "Einleitungssatz: Beginne mit einem einzigen kurzen Satz der erklärt welche Daten ausgewertet wurden — "
        "z.B. 'Ich habe alle Bestellungen aus 2024 nach Region ausgewertet.' oder "
        "'Ich habe die Top-Produkte nach Gesamtumsatz analysiert.' "
        "Dann folgt direkt die eigentliche Antwort ohne weitere Einleitung. "
        "Prozentuale Anteile: Wenn das Ergebnis eine Gruppierung mit ≥2 Zeilen und einer numerischen Kennzahl enthält, "
        "berechne und nenne den prozentualen Anteil der relevanten Gruppen am Gesamtwert — "
        "z.B. 'Die Top-3-Regionen machen zusammen 67 % des Umsatzes aus.' "
        "Nur wenn die Gesamtsumme aus den Ergebnisdaten ableitbar ist — erfinde keine Werte. "
        "Schlussfolgerung: Wenn die Frage einen Vergleich, eine Klassifikation oder eine Schlussfolgerung verlangt, "
        "beende die Antwort mit einer expliziten Aussage dazu — nicht nur Zahlen nennen, sondern interpretieren. "
        "Beispiel: Bei 'Wie unterscheiden sich X und Y?' nicht nur X=5 und Y=3 nennen, sondern 'X ist 67% höher als Y'. "
        "Bei 'ABC-Analyse' die Werte in A/B/C klassifizieren (A=0–80%, B=80–95%, C=95–100% kumulierter Anteil). "
        "Formuliere auf Deutsch, klar und präzise, 2-5 Sätze. "
        "Kein 'Basierend auf den Daten...' — komm direkt zur Antwort."
    )

    plausibility_block = (
        f"\nPLAUSIBILITÄTS-HINWEIS: {plausibility_hint}\n"
        if plausibility_hint else ""
    )
    user_prompt = (
        f"Frage: {question}\n\n"
        f"Ausgeführte SQL:\n{sql}\n\n"
        f"SQL-Ergebnis ({n} Zeile{'n' if n != 1 else ''}):\n"
        f"{table_text}\n"
        f"{plausibility_block}\n"
        f"Beantworte die Frage ausschließlich anhand der obigen Ergebnisse."
    )

    response = _client.models.generate_content(
        model=GEMINI_PRO_MODEL,
        contents=user_prompt,
        config=types.GenerateContentConfig(system_instruction=system_prompt),
    )
    return (response.text or "").strip()
