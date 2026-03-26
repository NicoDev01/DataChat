"""
Parse CSV / Excel / SQLite .db / SQL-dump uploads into:
  1. schema_sql         — CREATE TABLE + INSERT statements for SQLite
  2. schema_description — compact structure + sample values for LLM context
"""
import io
import re
import sqlite3
import tempfile
import os
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _infer_sql_type(series: pd.Series) -> str:
    dtype = str(series.dtype)
    if "int" in dtype:
        return "INTEGER"
    if "float" in dtype:
        return "REAL"
    # Heuristik: Wenn >80% der nicht-leeren Werte numerisch sind → REAL
    clean = series.dropna()
    clean = clean[clean.astype(str).str.strip() != ""]
    if len(clean) > 0:
        numeric_count = 0
        for v in clean:
            try:
                float(str(v).replace(",", "."))
                numeric_count += 1
            except (ValueError, TypeError):
                pass
        if numeric_count / len(clean) >= 0.8:
            return "REAL"
    return "TEXT"


def _sanitize_name(name: str) -> str:
    clean = re.sub(r"[^\w]", "_", str(name).strip().lower())
    clean = re.sub(r"_+", "_", clean).strip("_")
    return clean or "col"


_DATE_COL_PATTERN = re.compile(
    r'\b(datum|date|lieferdatum|bestelldatum|created|updated|timestamp|zeit|time|'
    r'von|bis|start|end|geburtstag|birthday)\b',
    re.IGNORECASE
)

_DATE_FORMAT_PATTERNS = [
    (re.compile(r'^\d{4}-\d{2}-\d{2}'), 'YYYY-MM-DD'),
    (re.compile(r'^\d{2}\.\d{2}\.\d{4}'), 'DD.MM.YYYY'),
    (re.compile(r'^\d{2}/\d{2}/\d{4}'), 'MM/DD/YYYY'),
    (re.compile(r'^\d{4}/\d{2}/\d{2}'), 'YYYY/MM/DD'),
]


# ---------------------------------------------------------------------------
# Column semantics analysis
# ---------------------------------------------------------------------------

# Muster die auf eine Ordinalskala hinweisen (nur Spaltennamen-Heuristik,
# keinerlei domänenspezifische Werte hardcoded)
_ORDINAL_COL_HINTS = re.compile(
    r'\b(klasse|class|stufe|level|grad|grade|rang|rank|priorit|priority|'
    r'kategorie|category|phase|tier|stage|schritt|step|note|score|bewertung|rating)\b',
    re.IGNORECASE
)


def _infer_ordinal_order(col_name: str, unique_vals: list[str]) -> list[str] | None:
    """
    Erkennt automatisch ob eine Spalte eine Ordinalskala enthält und gibt die sortierte
    Reihenfolge zurück — vollständig datengetrieben, ohne domänenspezifische Hardcodes.

    Erkennungsstrategien:
    1. Alle Werte sind reine Integers → numerisch sortiert
    2. Werte folgen Muster: gemeinsames Präfix + aufsteigende Zahl (z.B. 'Klasse 1','Klasse 2')
    3. Werte folgen Muster: Buchstabe+Zahl (z.B. 'RC1','RC2','A1','B2') → sortiert nach Buchstabe, dann Zahl
    4. Spaltennamen-Hint (klasse, level, stufe, ...) + wenige Werte → Werte alphabetisch/numerisch sortiert
    """
    if not unique_vals:
        return None

    # Strategie 1: Alle Werte sind reine Ganzzahlen
    try:
        nums = [int(v.strip()) for v in unique_vals]
        if len(set(nums)) == len(nums):  # keine Duplikate
            return [str(n) for n in sorted(nums)]
    except ValueError:
        pass

    # Strategie 2: Gemeinsames Präfix + Nummer (z.B. 'Klasse 1', 'Klasse 2', 'Level 3')
    prefix_num = re.compile(r'^(.+?)[\s\-_]?(\d+)$')
    matches = [prefix_num.match(v.strip()) for v in unique_vals]
    if all(matches):
        prefixes = {m.group(1).strip().lower() for m in matches}  # type: ignore
        if len(prefixes) == 1:  # alle haben denselben Präfix
            sorted_vals = sorted(unique_vals, key=lambda v: int(prefix_num.match(v.strip()).group(2)))  # type: ignore
            return sorted_vals

    # Strategie 3: Buchstabe(n) + Zahl + optionale Buchstaben (z.B. 'RC1','RC1N','RC2','A1','B2')
    letter_num = re.compile(r'^([A-Za-z]+)(\d+)([A-Za-z]*)$')
    matches3 = [letter_num.match(v.strip()) for v in unique_vals]
    if all(matches3):
        sorted_vals = sorted(unique_vals, key=lambda v: (
            letter_num.match(v.strip()).group(1),  # type: ignore
            int(letter_num.match(v.strip()).group(2)),  # type: ignore
            letter_num.match(v.strip()).group(3)  # type: ignore  suffix z.B. 'N'
        ))
        return sorted_vals

    # Strategie 4: Spaltennamen-Hint + wenige Werte (≤10) → sortiert ausgeben
    if _ORDINAL_COL_HINTS.search(col_name) and len(unique_vals) <= 10:
        # Versuche numerisch zu sortieren (auch bei gemischten Strings wie 'RC1N', 'RC2')
        def _sort_key(v: str):
            nums = re.findall(r'\d+', v)
            return (re.sub(r'\d', '', v).lower(), int(nums[0]) if nums else 0)
        return sorted(unique_vals, key=_sort_key)

    return None


def _analyze_column_semantics(col_name: str, series: pd.Series, sql_type: str) -> dict:
    """
    Analysiert eine Spalte tiefergehend und gibt semantische Hinweise zurück:
    - mixed_type: TEXT-Spalte enthält sowohl Zahlen als auch echte Strings
    - dirty_numeric: TEXT-Spalte mit numerischen Werten plus Schmutz (%, Einheiten)
    - ordinal: bekannte Ordinalskala mit definierter Reihenfolge
    - domain: alle eindeutigen Werte wenn ≤12 und TEXT
    """
    result: dict = {}
    clean = series.dropna()
    clean = clean[clean.astype(str).str.strip() != ""]
    if clean.empty:
        return result

    str_vals = clean.astype(str)
    unique_vals = str_vals.unique().tolist()

    # Ordinal-Erkennung: vollständig datengetrieben, keine hardcoded Werte
    if sql_type == "TEXT" and 2 <= len(unique_vals) <= 20:
        ordinal_order = _infer_ordinal_order(col_name, unique_vals)
        if ordinal_order:
            result['ordinal'] = ordinal_order

    if sql_type == "TEXT":
        numeric_count = 0
        dirty_count = 0  # Zahl + Schmutz wie "19%", "50 EUR"
        pure_text_count = 0
        for v in str_vals:
            v = v.strip()
            try:
                float(v.replace(',', '.'))
                numeric_count += 1
            except ValueError:
                # Versuch nach Stripping von Suffix/Prefix
                stripped = re.sub(r'[%€$₹£\s]', '', v).replace(',', '.')
                try:
                    float(stripped)
                    dirty_count += 1
                except ValueError:
                    pure_text_count += 1

        total = len(str_vals)
        num_ratio = (numeric_count + dirty_count) / total if total else 0
        text_ratio = pure_text_count / total if total else 0

        if num_ratio >= 0.5 and text_ratio >= 0.1:
            result['mixed_type'] = True
        if dirty_count > 0 and numeric_count + dirty_count >= total * 0.5:
            result['dirty_numeric'] = True

        # Wertedomäne für kategorische Spalten
        if not result.get('mixed_type') and not result.get('dirty_numeric'):
            if len(unique_vals) <= 12:
                result['domain'] = unique_vals[:12]

    return result


_CURRENCY_SYMBOLS = re.compile(r'[₹$€£¥₩₽¢]')
_THOUSANDS_SEP = re.compile(r'^\d{1,3}(,\d{3})+(\.\d+)?$')


def _detect_numeric_format(series: pd.Series) -> str | None:
    """
    Erkennt ob eine TEXT-Spalte formatierte Zahlen enthält.
    Gibt einen Hinweis-String zurück, z.B. 'formatted_number:currency+thousands'
    oder None wenn keine Formatierung erkannt.
    """
    clean = series.dropna()
    clean = clean[clean.astype(str).str.strip() != ""]
    if clean.empty:
        return None
    sample = clean.astype(str).head(10)
    has_currency = sum(1 for v in sample if _CURRENCY_SYMBOLS.search(v))
    has_thousands = sum(1 for v in sample if _THOUSANDS_SEP.match(v.strip()))
    # Strip currency symbols then check if numeric
    def _is_numeric_after_strip(v: str) -> bool:
        cleaned = _CURRENCY_SYMBOLS.sub('', v).replace(',', '').replace(' ', '').strip()
        try:
            float(cleaned)
            return True
        except ValueError:
            return False
    numeric_after_strip = sum(1 for v in sample if _is_numeric_after_strip(v))
    if numeric_after_strip < max(1, len(sample) * 0.6):
        return None
    parts = []
    if has_currency >= max(1, len(sample) * 0.6):
        # Detect which symbols
        symbols_found = set()
        for v in sample:
            for ch in v:
                if _CURRENCY_SYMBOLS.match(ch):
                    symbols_found.add(ch)
        parts.append(f"Währungssymbol({''.join(sorted(symbols_found))})")
    if has_thousands >= max(1, len(sample) * 0.6):
        parts.append("Tausendertrennzeichen(,)")
    return ", ".join(parts) if parts else None


def _detect_date_format(series: pd.Series) -> str | None:
    """Erkennt das Datumsformat einer Spalte anhand der ersten nicht-leeren Werte."""
    clean = series.dropna()
    clean = clean[clean.astype(str).str.strip() != ""]
    if clean.empty:
        return None
    sample = clean.astype(str).head(5)
    for pat, fmt in _DATE_FORMAT_PATTERNS:
        matches = sum(1 for v in sample if pat.match(v.strip()))
        if matches >= max(1, len(sample) * 0.6):
            return fmt
    return None


def _sample_values(series: pd.Series, max_vals: int = 4) -> str:
    """Return compact example values string for schema description."""
    clean = series.dropna()
    clean = clean[clean.astype(str).str.strip() != ""]
    if clean.empty:
        return ""
    dtype = str(series.dtype)
    if "int" in dtype or "float" in dtype:
        lo, hi = clean.min(), clean.max()
        return f"{lo}" if lo == hi else f"{lo}–{hi}"
    unique_vals = clean.astype(str).unique()
    short = [v for v in unique_vals if len(v) <= 30]
    sample = short[:max_vals]
    return ", ".join(f"'{v}'" for v in sample)


# ---------------------------------------------------------------------------
# JOIN relationship inference
# ---------------------------------------------------------------------------

def _infer_join_relationships(tables: dict[str, dict]) -> tuple[list[str], list[str]]:
    """
    Erkennt automatisch JOIN-Beziehungen zwischen Tabellen.

    Strategie (Priorität absteigend):
    1. Semantischer FK: Spalte col in Tabelle A existiert auch in Tabelle B mit gleichen Werten
       → JOIN A.col = B.col  (z.B. order.customerid = customer.customerid)
    2. Numerischer FK mit _id-Suffix oder id-Suffix → rowid-basierter JOIN
       (z.B. artikel_id → artikel.rowid)
    3. Typ-Mismatch Erkennung: INTEGER vs TEXT mit Präfix-Pattern

    tables: {table_name: {"columns": [(col_name, sql_type)], "sample_values": {col: [values]}}}
    Gibt (relationships, type_warnings) zurück.
    """
    relationships: list[str] = []
    type_warnings: list[str] = []
    table_names = list(tables.keys())

    # Baue Index: Tabellenname → {Spaltenname → Typ}
    col_type_index: dict[str, dict[str, str]] = {
        tbl: {c[0]: c[1].upper() for c in info["columns"]}
        for tbl, info in tables.items()
    }

    # Bereits gefundene Beziehungen (verhindert Duplikate)
    seen: set[str] = set()

    # ---------------------------------------------------------------------------
    # Strategie 1: Semantischer FK — gleiche Spalte in zwei Tabellen mit übereinstimmenden Werten
    # z.B. order.customerid → customer.customerid (beide TEXT 'VINET' etc.)
    # ---------------------------------------------------------------------------
    for tbl_name, tbl_info in tables.items():
        for col_name, col_type in tbl_info["columns"]:
            # Spalten die typisch FK-Namen haben: endet auf "id" (mit oder ohne Unterstrich)
            col_lower = col_name.lower()
            is_id_col = col_lower.endswith("_id") or (col_lower.endswith("id") and len(col_lower) > 2)
            if not is_id_col:
                continue

            src_vals = set(
                str(v) for v in tbl_info["sample_values"].get(col_name, [])
                if v is not None and str(v).strip()
            )
            if not src_vals:
                continue

            for other_tbl in table_names:
                if other_tbl == tbl_name:
                    continue
                # Zieltabelle muss dieselbe Spalte haben
                if col_name not in col_type_index.get(other_tbl, {}):
                    continue
                target_vals = set(
                    str(v) for v in tables[other_tbl]["sample_values"].get(col_name, [])
                    if v is not None and str(v).strip()
                )
                if not target_vals:
                    continue
                # Werte müssen übereinstimmen (min. 1 gemeinsamer Wert)
                if src_vals & target_vals:
                    key = f"{tbl_name}.{col_name}={other_tbl}.{col_name}"
                    rev_key = f"{other_tbl}.{col_name}={tbl_name}.{col_name}"
                    if key not in seen and rev_key not in seen:
                        seen.add(key)
                        relationships.append(
                            f"JOIN {other_tbl} ON {tbl_name}.{col_name} = {other_tbl}.{col_name}"
                        )

    # ---------------------------------------------------------------------------
    # Strategie 1b: XYZid → Tabelle XYZ, Spalte "id"
    # z.B. order.customerid → customer.id, orderdetail.orderid → order.id
    # ---------------------------------------------------------------------------
    for tbl_name, tbl_info in tables.items():
        for col_name, col_type in tbl_info["columns"]:
            col_lower = col_name.lower()
            # Muss auf "id" enden aber NICHT "_id" (das ist Strategie 2)
            if not col_lower.endswith("id") or col_lower.endswith("_id"):
                continue
            if col_lower == "id":
                continue
            # Prefix extrahieren: "customerid" → "customer", "orderid" → "order"
            prefix = col_lower[:-2]  # strip "id"
            if len(prefix) < 3:
                continue

            # Suche Zieltabelle die "id"-Spalte hat und deren Name mit prefix übereinstimmt
            for other_tbl in table_names:
                if other_tbl == tbl_name:
                    continue
                other_lower = other_tbl.lower()
                # Name-Match: "customer" == "customer", "order" == "order" etc.
                name_match = (
                    other_lower == prefix or
                    other_lower.startswith(prefix) or
                    prefix.startswith(other_lower) or
                    (len(prefix) >= 4 and other_lower[:len(prefix)] == prefix)
                )
                if not name_match:
                    continue
                # Zieltabelle muss "id"-Spalte haben
                target_cols = col_type_index.get(other_tbl, {})
                if "id" not in target_cols:
                    continue
                # Werte müssen übereinstimmen
                src_vals = set(
                    str(v) for v in tbl_info["sample_values"].get(col_name, [])
                    if v is not None and str(v).strip()
                )
                tgt_vals = set(
                    str(v) for v in tables[other_tbl]["sample_values"].get("id", [])
                    if v is not None and str(v).strip()
                )
                if not src_vals or not tgt_vals:
                    # Kein Value-Check möglich — name_match reicht
                    pass
                elif not (src_vals & tgt_vals):
                    continue

                key = f"{tbl_name}.{col_name}={other_tbl}.id"
                rev = f"{other_tbl}.id={tbl_name}.{col_name}"
                if key not in seen and rev not in seen:
                    seen.add(key)
                    relationships.append(f"JOIN {other_tbl} ON {tbl_name}.{col_name} = {other_tbl}.id")
                break

    # ---------------------------------------------------------------------------
    # Strategie 2: Numerischer FK mit _id-Suffix → rowid (nur wenn nicht schon via Str. 1 gefunden)
    # ---------------------------------------------------------------------------
    for tbl_name, tbl_info in tables.items():
        for col_name, col_type in tbl_info["columns"]:
            if not col_name.lower().endswith("_id"):
                continue
            if col_type.upper() not in ("INTEGER", "REAL", "NUMERIC", ""):
                continue

            # Integer-Werte dieser Spalte
            raw_vals = tbl_info["sample_values"].get(col_name, [])
            int_vals: set[int] = set()
            for v in raw_vals:
                try:
                    int_vals.add(int(float(str(v))))
                except (ValueError, TypeError):
                    pass
            if not int_vals:
                continue

            # Kandidaten-Tabelle aus Spaltenname ableiten
            # z.B. "kunden_id" → "kunden", "artikel_id" → "artikel"
            prefix = col_name[:-3].rstrip("_").lower()  # strip "_id"

            best_match: str | None = None
            for other_tbl in table_names:
                if other_tbl == tbl_name:
                    continue
                other_lower = other_tbl.lower()
                prefix_lower = prefix.lower()

                # Matching-Strategien (von präzise zu fuzzy):
                # 1. Exakt: "kunden_id" → "kunden"
                # 2. Tabelle beginnt mit Prefix: "kunden_id" → "kundendaten"
                # 3. Prefix beginnt mit Tabelle: "kunden_id" → "kund"
                # 4. Tabelle enthält Prefix: "auftrags_id" → "auftraege" (beide enthalten "auftrag")
                # 5. Prefix enthält Tabellenname (ohne Plural-Endung)
                def _share_stem(a: str, b: str) -> bool:
                    min_len = min(len(a), len(b), 5)
                    return min_len >= 4 and a[:min_len] == b[:min_len]

                name_match = (
                    prefix_lower == other_lower or
                    other_lower.startswith(prefix_lower) or
                    prefix_lower.startswith(other_lower) or
                    _share_stem(prefix_lower, other_lower) or
                    # z.B. "serie" in "produktserien", "lager" in "lagerbestand"
                    (len(prefix_lower) >= 4 and prefix_lower in other_lower)
                )
                if not name_match:
                    continue

                # Prüfe ob die int_vals im rowid-Bereich der anderen Tabelle liegen
                other_row_count = tables[other_tbl].get("row_count", 0)
                if other_row_count > 0 and max(int_vals) <= other_row_count:
                    best_match = other_tbl
                    break
                elif other_row_count == 0:
                    # Kein row_count bekannt — name_match reicht
                    best_match = other_tbl
                    break

            if best_match:
                # Wenn diese Beziehung schon via semantischen FK (Strategie 1) gefunden — überspringen
                sem_key = f"{tbl_name}.{col_name}={best_match}.{col_name}"
                sem_rev = f"{best_match}.{col_name}={tbl_name}.{col_name}"
                if sem_key in seen or sem_rev in seen:
                    continue

                # Value-Matching: Prüfe ob die INTEGER-Werte der FK-Spalte direkt auf
                # die Werte einer ID-Spalte in der Zieltabelle matchen,
                # oder ob nur rowid-basierter JOIN korrekt ist.
                target_cols = col_type_index.get(best_match, {})
                matching_col_in_target = col_name  # z.B. "serie_id"
                join_expr = f"JOIN {best_match} ON {tbl_name}.{col_name} = {best_match}.rowid"  # Default

                if matching_col_in_target in target_cols:
                    target_type = target_cols[matching_col_in_target]
                    target_sample_vals = set(
                        str(v) for v in tables[best_match]["sample_values"].get(matching_col_in_target, [])
                        if v is not None
                    )
                    # Prüfe ob die Integer-Werte als String in den Zielwerten vorkommen
                    int_as_str = {str(v) for v in int_vals}
                    direct_cast_works = bool(int_as_str & target_sample_vals)

                    if target_type.upper() not in ("INTEGER", "REAL", "NUMERIC") and target_sample_vals:
                        if direct_cast_works:
                            # CAST funktioniert (z.B. '1','2','3' sind in target)
                            join_expr = (
                                f"JOIN {best_match} ON CAST({tbl_name}.{col_name} AS TEXT) = "
                                f"{best_match}.{matching_col_in_target}"
                            )
                            type_warnings.append(
                                f"TYP-MISMATCH (CAST möglich): {tbl_name}.{col_name} (INTEGER) "
                                f"→ {best_match}.{matching_col_in_target} (TEXT) — "
                                f"verwende: CAST({tbl_name}.{col_name} AS TEXT) = {best_match}.{matching_col_in_target}"
                            )
                        else:
                            # CAST hilft nicht — Werte sind grundlegend verschieden (z.B. 1 vs 'F001')
                            join_expr = f"JOIN {best_match} ON {tbl_name}.{col_name} = {best_match}.rowid"
                            type_warnings.append(
                                f"SCHLÜSSEL-MISMATCH: {tbl_name}.{col_name} (INTEGER, z.B. "
                                f"{sorted(int_vals)[:3]}) passt nicht zu "
                                f"{best_match}.{matching_col_in_target} (TEXT, z.B. "
                                f"{sorted(target_sample_vals)[:3]}) — "
                                f"CAST hilft nicht. Verwende {tbl_name}.{col_name} = {best_match}.rowid"
                            )

                relationships.append(join_expr)

    return relationships, type_warnings


def _sample_values(series: pd.Series, max_vals: int = 4) -> str:
    """Return compact example values string for schema description."""
    clean = series.dropna()
    clean = clean[clean.astype(str).str.strip() != ""]
    if clean.empty:
        return ""
    dtype = str(series.dtype)
    if "int" in dtype or "float" in dtype:
        lo, hi = clean.min(), clean.max()
        return f"{lo}" if lo == hi else f"{lo}–{hi}"
    unique_vals = clean.astype(str).unique()
    short = [v for v in unique_vals if len(v) <= 30]
    sample = short[:max_vals]
    return ", ".join(f"'{v}'" for v in sample)


def _parse_dataframes(sheets: dict[str, pd.DataFrame]) -> dict:
    schema_sql_parts: list[str] = []
    description_lines = ["Datenbank-Tabellen:"]
    table_names: list[str] = []
    total_rows = 0
    # Für JOIN-Erkennung: alle Tabellen-Metadaten sammeln
    tables_meta: dict[str, dict] = {}

    for table_name, df in sheets.items():
        if df.empty:
            continue
        df.columns = [_sanitize_name(c) for c in df.columns]
        df = df.dropna(axis=1, how="all")
        col_types = {col: _infer_sql_type(df[col]) for col in df.columns}
        df = df.fillna("")

        table_names.append(table_name)
        total_rows += len(df)

        # Sample-Werte für JOIN-Erkennung sammeln
        sample_vals: dict[str, list] = {}
        for col in df.columns:
            sample_vals[col] = df[col].dropna().head(20).tolist()
        tables_meta[table_name] = {
            "columns": [(col, col_types[col]) for col in df.columns],
            "sample_values": sample_vals,
            "row_count": len(df),
        }

        col_defs = ["id INTEGER PRIMARY KEY AUTOINCREMENT"]
        col_desc_parts: list[str] = []
        for col in df.columns:
            sql_type = col_types[col]
            col_defs.append(f"{col} {sql_type}")
            samples = _sample_values(df[col])
            # Datumsformat erkennen für TEXT-Spalten mit Datumsnamen
            date_fmt = None
            if sql_type == "TEXT" and _DATE_COL_PATTERN.search(col):
                date_fmt = _detect_date_format(df[col])
            # Formatierte Zahlen erkennen (Währung, Tausendertrennzeichen)
            num_fmt = None
            if sql_type == "TEXT" and not date_fmt:
                num_fmt = _detect_numeric_format(df[col])
            # Semantische Analyse
            semantics = _analyze_column_semantics(col, df[col], sql_type)

            hints = []
            if date_fmt:
                hints.append(f"Format {date_fmt}")
            if num_fmt:
                hints.append(f"enthält {num_fmt} → REPLACE vor CAST nötig")
            if semantics.get('mixed_type'):
                hints.append("MIXED-TYPE: enthält Zahlen und Text → CASE WHEN col GLOB '[0-9]*' THEN CAST(col AS REAL) ELSE NULL END")
            if semantics.get('dirty_numeric'):
                hints.append("dirty-numeric: enthält Zahlen mit Einheiten/Symbolen → defensiver CAST nötig")
            if semantics.get('ordinal'):
                order_str = ' < '.join(semantics['ordinal'])
                hints.append(f"ORDINAL-Skala: {order_str}")
            if semantics.get('domain') and not hints:
                domain_str = ', '.join(f"'{v}'" for v in semantics['domain'])
                hints.append(f"Werte: [{domain_str}]")

            hint_str = "; ".join(hints)
            if hint_str and samples:
                col_desc_parts.append(f"{col} ({sql_type}, {hint_str}, z.B. {samples})")
            elif hint_str:
                col_desc_parts.append(f"{col} ({sql_type}, {hint_str})")
            elif samples:
                col_desc_parts.append(f"{col} ({sql_type}, z.B. {samples})")
            else:
                col_desc_parts.append(f"{col} ({sql_type})")

        create_stmt = (
            f"CREATE TABLE {table_name} (\n    "
            + ",\n    ".join(col_defs)
            + "\n);"
        )

        insert_rows = df.head(500)
        col_names = ", ".join(df.columns)
        value_rows: list[str] = []
        for _, row in insert_rows.iterrows():
            vals: list[str] = []
            for col in df.columns:
                v = row[col]
                if v == "" or pd.isna(v):
                    vals.append("NULL")
                elif col_types[col] in ("INTEGER", "REAL"):
                    try:
                        vals.append(str(float(str(v).replace(",", "."))))
                    except (ValueError, TypeError):
                        vals.append("NULL")
                else:
                    vals.append(f"'{str(v).replace(chr(39), chr(39)*2)}'")
            value_rows.append(f"({', '.join(vals)})")

        insert_stmt = (
            f"INSERT INTO {table_name} ({col_names}) VALUES\n    "
            + ",\n    ".join(value_rows)
            + ";"
        )

        schema_sql_parts.append(create_stmt)
        schema_sql_parts.append(insert_stmt)
        description_lines.append(f"- {table_name} ({', '.join(col_desc_parts)})")

    # JOIN-Beziehungen erkennen und an Schema anhängen
    if len(tables_meta) > 1:
        joins, type_warnings = _infer_join_relationships(tables_meta)
        if joins:
            description_lines.append(
                "\nVERPFLICHTENDE JOIN-SYNTAX (exakt so verwenden — kein rowid wenn id-Spalte existiert):\n"
                + "\n".join(f"  {j}" for j in joins)
            )
        if type_warnings:
            description_lines.append(
                "\nACHTUNG Typ-Mismatches beim JOIN:\n"
                + "\n".join(f"  {w}" for w in type_warnings)
            )

    return {
        "schema_sql": "\n\n".join(schema_sql_parts),
        "schema_description": "\n".join(description_lines),
        "table_names": table_names,
        "table_count": len(table_names),
        "row_count": total_rows,
    }


def _parse_sqlite_db(file_bytes: bytes) -> dict:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    try:
        tmp.write(file_bytes)
        tmp.close()
        conn = sqlite3.connect(tmp.name)

        tables = [
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        if not tables:
            raise ValueError("Keine Tabellen in der SQLite-Datenbank gefunden.")

        schema_sql_parts: list[str] = []
        description_lines = ["Datenbank-Tabellen:"]
        total_rows = 0
        tables_meta: dict[str, dict] = {}

        for tbl in tables:
            create_sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (tbl,)
            ).fetchone()[0]
            schema_sql_parts.append(create_sql + ";")

            rows = conn.execute(f'SELECT * FROM "{tbl}" LIMIT 500').fetchall()
            col_info = conn.execute(f'PRAGMA table_info("{tbl}")').fetchall()
            col_names = [c[1] for c in col_info]
            col_types = {c[1]: c[2].upper() for c in col_info}

            tbl_row_count = conn.execute(f'SELECT COUNT(*) FROM "{tbl}"').fetchone()[0]
            # Sample-Werte für JOIN-Erkennung
            sample_vals_meta: dict[str, list] = {}
            for c in col_info:
                try:
                    sv = conn.execute(
                        f'SELECT "{c[1]}" FROM "{tbl}" WHERE "{c[1]}" IS NOT NULL LIMIT 20'
                    ).fetchall()
                    sample_vals_meta[_sanitize_name(c[1])] = [r[0] for r in sv]
                except Exception:
                    pass
            tables_meta[_sanitize_name(tbl)] = {
                "columns": [(_sanitize_name(c[1]), c[2] or "TEXT") for c in col_info],
                "sample_values": sample_vals_meta,
                "row_count": tbl_row_count,
            }

            if rows:
                col_list = ", ".join(f'"{c}"' for c in col_names)
                value_rows: list[str] = []
                for row in rows:
                    vals: list[str] = []
                    for col, v in zip(col_names, row):
                        if v is None:
                            vals.append("NULL")
                        elif col_types.get(col, "TEXT") in ("INTEGER", "REAL", "NUMERIC"):
                            vals.append(str(v))
                        else:
                            vals.append(f"'{str(v).replace(chr(39), chr(39)*2)}'")
                    value_rows.append(f"({', '.join(vals)})")
                schema_sql_parts.append(
                    f'INSERT INTO "{tbl}" ({col_list}) VALUES\n    '
                    + ",\n    ".join(value_rows) + ";"
                )

            total_rows += tbl_row_count

            col_desc_parts: list[str] = []
            for c in col_info:
                cname = _sanitize_name(c[1])
                ctype = c[2] or "TEXT"
                if cname.lower() == "id" and len(col_info) > 1:
                    continue
                try:
                    sample_rows = conn.execute(
                        f'SELECT DISTINCT "{c[1]}" FROM "{tbl}" '
                        f'WHERE "{c[1]}" IS NOT NULL LIMIT 4'
                    ).fetchall()
                    vals2 = [str(r[0]) for r in sample_rows if r[0] is not None and str(r[0]).strip()]
                    if ctype.upper() in ("INTEGER", "REAL", "NUMERIC") and len(vals2) >= 2:
                        nums = sorted(float(v) for v in vals2 if v.replace(".", "", 1).lstrip("-").isdigit())
                        sample_str = f"{nums[0]}–{nums[-1]}" if nums else ""
                    elif vals2:
                        short = [v for v in vals2 if len(v) <= 25][:4]
                        sample_str = ", ".join(f"'{v}'" for v in short)
                    else:
                        sample_str = ""
                    s_series = pd.Series(vals2)
                    # Datumsformat erkennen
                    date_fmt = None
                    if ctype.upper() in ("TEXT", "") and _DATE_COL_PATTERN.search(cname):
                        date_fmt = _detect_date_format(s_series)
                    # Formatierte Zahlen erkennen
                    num_fmt = None
                    if ctype.upper() in ("TEXT", "") and not date_fmt:
                        num_fmt = _detect_numeric_format(s_series)
                    # Semantische Analyse
                    semantics = _analyze_column_semantics(cname, s_series, ctype)
                    hints = []
                    if date_fmt:
                        hints.append(f"Format {date_fmt}")
                    if num_fmt:
                        hints.append(f"enthält {num_fmt} → REPLACE vor CAST nötig")
                    if semantics.get('mixed_type'):
                        hints.append("MIXED-TYPE: enthält Zahlen und Text → CASE WHEN col GLOB '[0-9]*' THEN CAST(col AS REAL) ELSE NULL END")
                    if semantics.get('dirty_numeric'):
                        hints.append("dirty-numeric: enthält Zahlen mit Einheiten/Symbolen → defensiver CAST nötig")
                    if semantics.get('ordinal'):
                        order_str = ' < '.join(semantics['ordinal'])
                        hints.append(f"ORDINAL-Skala: {order_str}")
                    if semantics.get('domain') and not hints:
                        domain_str = ', '.join(f"'{v}'" for v in semantics['domain'])
                        hints.append(f"Werte: [{domain_str}]")
                    hint_str = "; ".join(hints)
                    if hint_str and sample_str:
                        col_desc_parts.append(f"{cname} ({ctype}, {hint_str}, z.B. {sample_str})")
                    elif hint_str:
                        col_desc_parts.append(f"{cname} ({ctype}, {hint_str})")
                    elif sample_str:
                        col_desc_parts.append(f"{cname} ({ctype}, z.B. {sample_str})")
                    else:
                        col_desc_parts.append(f"{cname} ({ctype})")
                except Exception:
                    col_desc_parts.append(f"{cname} ({ctype})")

            description_lines.append(f"- {_sanitize_name(tbl)} ({', '.join(col_desc_parts)})")

        # JOIN-Beziehungen erkennen
        if len(tables_meta) > 1:
            joins, type_warnings = _infer_join_relationships(tables_meta)
            if joins:
                description_lines.append(
                    "\nVERPFLICHTENDE JOIN-SYNTAX (exakt so verwenden — kein rowid wenn id-Spalte existiert):\n"
                    + "\n".join(f"  {j}" for j in joins)
                )
            if type_warnings:
                description_lines.append(
                    "\nACHTUNG Typ-Mismatches beim JOIN:\n"
                    + "\n".join(f"  {w}" for w in type_warnings)
                )

        conn.close()
    finally:
        os.unlink(tmp.name)

    return {
        "schema_sql": "\n\n".join(schema_sql_parts),
        "schema_description": "\n".join(description_lines),
        "table_names": [_sanitize_name(t) for t in tables],
        "table_count": len(tables),
        "row_count": total_rows,
    }


def _parse_sql_dump(sql_text: str) -> dict:
    create_pattern = re.compile(
        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`]?(\w+)["`]?\s*\(([^;]+)\)',
        re.IGNORECASE | re.DOTALL,
    )
    table_names: list[str] = []
    description_lines = ["Datenbank-Tabellen:"]

    for m in create_pattern.finditer(sql_text):
        tbl = _sanitize_name(m.group(1))
        body = m.group(2)
        col_desc_parts: list[str] = []
        for line in body.splitlines():
            line = line.strip().rstrip(",")
            if not line or re.match(
                r'(?:PRIMARY\s+KEY|UNIQUE|INDEX|KEY|CONSTRAINT|FOREIGN|CHECK)\b',
                line, re.IGNORECASE
            ):
                continue
            col_match = re.match(r'["`]?(\w+)["`]?\s+(\w+)', line)
            if col_match:
                col_name = _sanitize_name(col_match.group(1))
                raw_type = col_match.group(2).upper()
                if raw_type in ("INT", "INTEGER", "BIGINT", "SMALLINT", "TINYINT", "MEDIUMINT"):
                    sql_type = "INTEGER"
                elif raw_type in ("FLOAT", "DOUBLE", "DECIMAL", "NUMERIC", "REAL"):
                    sql_type = "REAL"
                else:
                    sql_type = "TEXT"
                col_desc_parts.append(f"{col_name} ({sql_type})")
        if col_desc_parts:
            table_names.append(tbl)
            description_lines.append(f"- {tbl} ({', '.join(col_desc_parts)})")

    total_rows = len(re.findall(r'\bINSERT\b', sql_text, re.IGNORECASE))
    if not table_names:
        raise ValueError("Keine CREATE TABLE Statements in der SQL-Datei gefunden.")

    # Normalize for SQLite
    normalized = sql_text
    for pat, repl in [
        (r'\bENGINE\s*=\s*\w+', ''), (r'\bDEFAULT\s+CHARSET\s*=\s*\w+', ''),
        (r'\bCHARACTER\s+SET\s+\w+', ''), (r'\bCOLLATE\s+\w+', ''),
        (r'\bAUTO_INCREMENT\s*=?\s*\d*', ''), (r'\bUNSIGNED\b', ''),
        (r'\bNOT\s+NULL\b', ''), (r'\bDEFAULT\s+NULL\b', ''),
        (r"\bDEFAULT\s+'[^']*'", ''), (r'\bDEFAULT\s+\d+', ''),
        (r'\bCOMMENT\s+\'[^\']*\'', ''),
        (r'\b(?:VAR)?CHAR\s*\(\d+\)', 'TEXT'), (r'\b(?:TINY|MEDIUM|LONG)?TEXT\b', 'TEXT'),
        (r'\bTINYINT\s*\(\d+\)', 'INTEGER'), (r'\bINT\s*\(\d+\)', 'INTEGER'),
        (r'\bDECIMAL\s*\(\d+(?:,\d+)?\)', 'REAL'),
        (r"\bENUM\s*\([^)]+\)", 'TEXT'), (r"\bSET\s*\([^)]+\)", 'TEXT'),
        (r',?\s*(?:PRIMARY\s+)?KEY\s+[^,\)]+', ''),
        (r',?\s*(?:UNIQUE\s+)?INDEX\s+[^,\)]+', ''),
        (r',?\s*CONSTRAINT\s+[^,\)]+', ''), (r',\s*\)', ')'),
        (r'^\s*(?:SET|USE|LOCK|UNLOCK)[^\n;]*[;\n]', ''),
    ]:
        normalized = re.sub(pat, repl, normalized, flags=re.IGNORECASE | re.MULTILINE)
    normalized = normalized.replace('`', '"')

    return {
        "schema_sql": normalized,
        "schema_description": "\n".join(description_lines),
        "table_names": table_names,
        "table_count": len(table_names),
        "row_count": total_rows,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_upload(file_bytes: bytes, filename: str) -> dict:
    """Parse any supported file format into schema_sql + schema_description."""
    ext = Path(filename).suffix.lower()

    if ext == ".sql":
        return _parse_sql_dump(file_bytes.decode("utf-8", errors="replace"))
    if ext in (".db", ".sqlite"):
        return _parse_sqlite_db(file_bytes)
    if ext == ".csv":
        df = pd.read_csv(io.BytesIO(file_bytes), sep=None, engine="python")
        table_name = _sanitize_name(Path(filename).stem)
        return _parse_dataframes({table_name: df})
    if ext in (".xlsx", ".xls"):
        xf = pd.ExcelFile(io.BytesIO(file_bytes))
        sheets: dict[str, pd.DataFrame] = {}
        seen: dict[str, int] = {}
        for sheet in xf.sheet_names:
            name = _sanitize_name(sheet)
            if name in seen:
                seen[name] += 1
                name = f"{name}_{seen[name]}"
            else:
                seen[name] = 1
            sheets[name] = xf.parse(sheet)
        return _parse_dataframes(sheets)

    raise ValueError(f"Nicht unterstütztes Dateiformat: {ext}. Bitte .csv, .xlsx, .xls, .db oder .sql verwenden.")
