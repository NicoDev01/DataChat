"""
Chart-Typ-Erkennung: Analysiert Spalten und Zeilen regelbasiert (kein LLM).
Gibt chart-Konfiguration für Recharts zurück.
"""
from __future__ import annotations
import re


_DATE_PATTERNS = re.compile(
    r'\b(datum|date|monat|month|jahr|year|quartal|quarter|periode|period|zeit|time|woche|week)\b',
    re.IGNORECASE
)
_NUM_TYPES = ("INTEGER", "REAL", "NUMERIC", "FLOAT", "DOUBLE")

# Spalten die analytische Hilfswerte enthalten und nicht direkt visualisiert werden sollen
_AUXILIARY_COL_PATTERNS = re.compile(
    r'(kum|cum|kumulativ|cumulative|prozent|percent|pct|anteil|quote|änderung|aenderung|change|delta|diff|rang|rank|z_score)',
    re.IGNORECASE
)

# Identifier-Spalten die keine Messwerte sind
_ID_COL_PATTERNS = re.compile(
    r'(^id$|_id$|^nr$|^nummer$|^number$|^code$|^key$)',
    re.IGNORECASE
)


def _is_numeric(value) -> bool:
    if value is None:
        return False
    try:
        float(str(value).replace(",", "."))
        return True
    except ValueError:
        return False


def _classify_columns(columns: list[str], rows: list[list]) -> tuple[list[int], list[int]]:
    """
    Gibt (text_indices, num_indices) zurück basierend auf Inhalt der ersten Zeilen.
    """
    if not rows:
        return list(range(len(columns))), []

    text_idx: list[int] = []
    num_idx: list[int] = []

    for i, col in enumerate(columns):
        # Prüfe ob Mehrheit der Werte numerisch ist
        sample = [rows[r][i] for r in range(min(5, len(rows))) if i < len(rows[r])]
        numeric_count = sum(1 for v in sample if _is_numeric(v))
        if numeric_count >= max(1, len(sample) * 0.6):
            num_idx.append(i)
        else:
            text_idx.append(i)

    return text_idx, num_idx


def detect(columns: list[str], rows: list[list]) -> dict:
    """
    Analysiert Daten und gibt Chart-Konfiguration zurück.

    Rückgabeformat:
    {
        "type": "bar" | "line" | "pie" | "none",
        "data": [...],       # Liste von Dicts {x_key: val, y_key: val}
        "x_key": "spalte",
        "y_keys": ["wert1"],
    }
    """
    if not columns or not rows or len(rows) < 2:
        return {"type": "none", "data": [], "x_key": "", "y_keys": []}

    text_idx, num_idx = _classify_columns(columns, rows)

    if not text_idx or not num_idx:
        return {"type": "none", "data": [], "x_key": "", "y_keys": []}

    x_idx = text_idx[0]
    x_key = columns[x_idx]

    # Auxiliary-Spalten (Prozente, kumulative Werte, Ränge, Deltas) aus Chart ausschließen
    primary_num_idx = [i for i in num_idx if not _AUXILIARY_COL_PATTERNS.search(columns[i])]
    if primary_num_idx:
        num_idx = primary_num_idx

    # ID/Identifier-Spalten ausschließen — keine Messwerte
    non_id_idx = [i for i in num_idx if not _ID_COL_PATTERNS.search(columns[i])]
    if non_id_idx:
        num_idx = non_id_idx

    # Skalenmismatch: Wenn mehrere numerische Spalten vorhanden, nur die mit ähnlicher Größenordnung behalten
    # Referenz: die Spalte mit dem höchsten Durchschnittswert
    if len(num_idx) > 1:
        def _col_avg(col_i: int) -> float:
            vals = []
            for r in range(min(10, len(rows))):
                try:
                    v = float(str(rows[r][col_i]).replace(",", "."))
                    vals.append(abs(v))
                except (ValueError, TypeError):
                    pass
            return sum(vals) / len(vals) if vals else 0

        avgs = {i: _col_avg(i) for i in num_idx}
        max_avg = max(avgs.values()) if avgs else 0
        if max_avg > 0:
            # Behalte nur Spalten deren Durchschnitt nicht mehr als Faktor 20 unter dem Maximum liegt
            compatible_idx = [i for i in num_idx if avgs[i] >= max_avg / 20]
            if compatible_idx:
                num_idx = compatible_idx

    y_keys = [columns[i] for i in num_idx]

    # Daten strukturieren für Recharts
    data = []
    for row in rows[:50]:  # max 50 Datenpunkte im Chart
        point: dict = {x_key: str(row[x_idx]) if x_idx < len(row) else ""}
        for i in num_idx:
            if i < len(row):
                try:
                    point[columns[i]] = float(str(row[i]).replace(",", "."))
                except (ValueError, TypeError):
                    point[columns[i]] = 0
        data.append(point)

    # Chart-Typ wählen
    is_date_col = bool(_DATE_PATTERNS.search(x_key))
    row_count = len(rows)

    if is_date_col:
        chart_type = "line"
    elif row_count <= 6 and len(y_keys) == 1:
        chart_type = "pie"
    elif len(y_keys) > 1:
        chart_type = "bar"  # Grouped bar
    else:
        chart_type = "bar"

    return {
        "type": chart_type,
        "data": data,
        "x_key": x_key,
        "y_keys": y_keys,
    }
