# DataChat

Standalone-Webanwendung zum Hochladen von Datenbankdateien und Abfragen in natürlicher Sprache (Deutsch). Das Tool generiert SQL, führt es aus und liefert professionelle Antworten mit Tabellen und Charts.

---

## Was ist DataChat?

DataChat ist kein SaaS-Produkt und kein BI-Tool. Es ist ein **lokales Analyse-Interface** für strukturierte Daten:

- Datei hochladen (CSV, Excel, SQLite, SQL-Dump)
- Auf Deutsch fragen: *"Welche Kunden haben im letzten Jahr mehr als 5 Bestellungen aufgegeben?"*
- Antwort als Text + SQL + Tabelle + Chart

Die KI übernimmt die SQL-Generierung vollständig. Der Nutzer braucht keine SQL-Kenntnisse.

---

## Aktueller Stand (März 2026)

Das System ist funktionsfähig und wurde über mehrere Evaluierungsrunden mit Northwind-Daten und eigenen Testdatenbanken optimiert. Die zuletzt gemessenen Scores lagen bei **8.3–8.8 / 10** über 25 Testfragen.

**Was gut funktioniert:**
- Komplexe JOINs über mehrere Tabellen (Northwind-style)
- Window-Funktionen (RANK, DENSE_RANK) für Top-N-pro-Gruppe-Analysen
- Korrekte Aggregationsebene (Auftragsebene vs. Positionsebene)
- Leere Ergebnisse werden klassifiziert statt ignoriert (VALIDE_LEER / DATEN_FEHLEN / UNPLAUSIBEL)
- Formatierte Zahlen (Währungssymbole, Tausendertrennzeichen) werden vor CAST bereinigt
- Datumsformate werden automatisch erkannt (DD.MM.YYYY, YYYY-MM-DD, MM/DD/YYYY)
- Reservierte Schlüsselwörter als Tabellennamen (z.B. `order`) werden automatisch gequotet

**Bekannte Schwächen / offene Punkte:**
- SDK-Migration: Codebase nutzt noch `google.generativeai` — Migration zu `google.genai` ausstehend (FutureWarning)
- Keine Authentifizierung — nur für lokale/interne Nutzung gedacht
- Session-Daten liegen im RAM (kein Persistenz-Layer) — Neustart löscht alle Sessions
- Dateilimit: 20 MB

---

## Tech Stack

| Schicht | Technologie |
|---|---|
| Backend | Python 3.13, FastAPI, Uvicorn |
| KI — SQL-Generierung | Gemini Flash (google-genai) |
| KI — Antwort-Interpretation | Gemini Pro (google-genai) |
| Datenbank (Runtime) | SQLite in-memory (pro Session) |
| Datenbank-Parsing | pandas, openpyxl |
| Frontend | React 18, TypeScript, Vite |
| Charts | Recharts |
| Styling | Tailwind CSS, Custom CSS (Dark Theme) |

---

## Projektstruktur

```
DataChat/
├── backend/
│   ├── main.py                  # FastAPI App, CORS
│   ├── config.py                # API-Keys, Modellnamen
│   ├── requirements.txt
│   ├── routes/
│   │   ├── upload.py            # POST /api/upload
│   │   └── query.py             # POST /api/query
│   └── services/
│       ├── parser.py            # Datei → SQLite-Schema
│       ├── sql_agent.py         # Frage → SQL → Ausführung
│       ├── interpreter.py       # Daten → natürliche Antwort
│       ├── chart.py             # Chart-Typ-Erkennung
│       └── session.py           # In-Memory Session-Verwaltung
└── frontend/
    ├── index.html
    ├── src/
    │   ├── App.tsx
    │   ├── main.tsx
    │   ├── types.ts
    │   ├── index.css            # Dark Theme, CSS-Variablen
    │   ├── api/client.ts        # Axios-Wrapper
    │   └── components/
    │       ├── UploadZone.tsx
    │       ├── SchemaInfo.tsx
    │       ├── ChatInput.tsx
    │       └── AnswerCard.tsx
    └── package.json
```

---

## Setup

### Voraussetzungen

- Python 3.9+
- Node.js 18+
- Gemini API Key (von Google AI Studio)

### Backend starten

```bash
cd backend
pip install -r requirements.txt

# API-Key setzen (oder in .env hinterlegen)
export GEMINI_API_KEY=your_key_here

uvicorn main:app --port 8090 --reload
```

### Frontend starten

```bash
cd frontend
npm install
npm run dev
# Läuft auf http://localhost:5173
```

### Umgebungsvariablen (`backend/.env`)

```
GEMINI_API_KEY=your_key_here
```

---

## Architektur-Überblick

### Request-Flow

```
Datei-Upload
    → parser.py: Datei lesen, Tabellen erkennen, Schema generieren
    → SQLite in-memory DB aufbauen
    → Session mit Schema-Description speichern

Frage stellen
    → sql_agent.py: Schema + Frage → Gemini Flash → SQL
    → apply_sqlite_compat(): deterministische SQL-Korrekturen
    → SQL ausführen → (columns, rows, error)
    → Bei Fehler: 1 Retry mit Fehlermeldung an LLM
    → interpreter.py: Daten + Frage → Gemini Pro → Antwort-Text
    → chart.py: Chart-Typ aus Spaltenstruktur ableiten
    → Antwort zurück an Frontend
```

### Schema-Description

Der Kern der SQL-Qualität liegt in `parser.py`. Die Schema-Description ist kein simples `CREATE TABLE` — sie enthält:

- Spaltentypen inkl. erkannter Semantik (ORDINAL, MIXED-TYPE, Datum-Format)
- Numerische Besonderheiten (Währungssymbol, Tausendertrennzeichen)
- Verpflichtende JOIN-Syntax in direkter SQL-Form (`JOIN shipper ON "order".shipvia = shipper.id`)
- FK-Beziehungen über drei Strategien erkannt:
  - Str.1: Gleicher Spaltenname in beiden Tabellen mit wertbasiertem Match
  - Str.1b: `XYZid`-Spalte → Tabelle `XYZ` mit `id`-Spalte (Northwind-Pattern)
  - Str.2: Numerischer `_id`-Suffix → rowid-Fallback

### SQL-Compat-Layer (`apply_sqlite_compat`)

Deterministisch, kein LLM, läuft immer:

- `ILIKE` → `LIKE`
- `WITH ROLLUP/CUBE` entfernen
- `LIMIT x,y` → `LIMIT y OFFSET x`
- `TRUE/FALSE` → `1/0`
- `STDDEV/VARIANCE` → manuelle Berechnung
- `MEDIAN` → `AVG`-Fallback
- `FILTER(WHERE ...)` → `CASE WHEN`
- Reservierte Schlüsselwörter automatisch quoten (`order` → `"order"`)
- Bug-Fix: `"order.col"` (falsch gequotet) → `"order".col`

---

## KI-Konfiguration

### Modelle (`config.py`)

```python
GEMINI_FLASH_MODEL = "gemini-2.5-flash-preview"   # SQL-Generierung
GEMINI_PRO_MODEL   = "gemini-2.5-pro-preview"     # Antwort-Interpretation
```

### System-Prompt-Regeln (sql_agent.py)

Die SQL-Qualität wird durch ca. 25 explizite Prompt-Regeln gesteuert, iterativ aus Evaluierungsrunden entwickelt. Wichtigste Kategorien:

| Kategorie | Regel |
|---|---|
| JOINs | Verpflichtende JOIN-Syntax aus Schema exakt kopieren |
| Primärschlüssel | PK heißt `id`, nicht `productid`/`customerid` |
| Quoting | Tabellennamen allein quoten, nie `"table.col"` |
| Spalten-Aliase | Bei gleichnamigen Spalten aus verschiedenen Tabellen immer `AS` |
| NOT IN | Verboten — stattdessen `NOT EXISTS` oder `LEFT JOIN ... IS NULL` |
| Aggregation | Auftragsebene vor Mittelwertbildung (Subquery-first) |
| Zeitreferenz | `MAX(datum)` statt `date('now')` bei historischen Daten |
| Soft-Delete | `deleted_at IS NULL` automatisch hinzufügen |
| Division | Immer `NULLIF` im Nenner |

### Interpreter-Qualität (`interpreter.py`)

- Leere Ergebnisse werden klassifiziert, bevor der Interpreter antwortet
- Plausibilitäts-Check: Wenn ≥40% der Zeilen denselben Aggregatwert haben → Hinweis auf möglichen JOIN-Multiplikationsfehler
- Antwort-Stil: 2–5 Sätze, Business-Report-Ton, immer Schlussfolgerung

---

## Unterstützte Dateiformate

| Format | Verarbeitung |
|---|---|
| `.csv` | pandas, Encoding-Erkennung, Trennzeichen-Erkennung |
| `.xlsx` / `.xls` | openpyxl / xlrd via pandas |
| `.db` / `.sqlite` | Direktes Einlesen als SQLite |
| `.sql` | Schema + INSERT-Statements als Script ausführen |

Limit: 20 MB pro Datei.

---

## Bekannte Stolpersteine

**Northwind-Datenbank:**
- Tabelle heißt `order` (reserviertes SQL-Schlüsselwort) → immer `"order"` quoten
- PK ist `id`, FK in Kindtabellen ist `orderid`/`customerid` etc. — der Prompt erklärt das explizit

**JOIN-Erkennung:**
- Funktioniert zuverlässig für Standard-Patterns
- Edge Case: Wenn FK-Spaltenname und PK-Spaltenname gar keine gemeinsame Basis haben, wird kein JOIN erkannt → manuell im Schema nachpflegen möglich

**Formatierte Zahlen:**
- `parser.py` erkennt Währungssymbole und Tausendertrennzeichen in Stichproben
- Wenn weniger als 30% der Werte das Symbol enthalten, wird es nicht erkannt

---

## Entwicklung fortsetzen

### Nächste sinnvolle Schritte

1. **SDK-Migration**: `google.generativeai` → `google.genai` (FutureWarning aktiv, API funktioniert noch)
2. **Session-Persistenz**: Sessions überleben aktuell keinen Server-Neustart — SQLite-Datei als Session-Store
3. **Multi-File-Support**: Mehrere Dateien in einer Session verknüpfen
4. **Streaming**: Antwort-Text per SSE streamen statt auf vollständige Antwort warten
5. **Chart-Auswahl**: Nutzer kann Chart-Typ manuell überschreiben

### Evaluierung

Neue SQL-Qualität testen:
- 5 Fragen pro Kategorie (JOINs, Aggregation, Filter, Zeitreihen, Ranking)
- Jede Frage mit SQL-Note (0–5) und Antwort-Note (0–5) bewerten
- Fehler direkt als neue Prompt-Regel in `sql_agent.py` eintragen

### Wo was liegt (Kurzreferenz)

| Aufgabe | Datei |
|---|---|
| Prompt-Regeln ändern | `backend/services/sql_agent.py` → `run_query()` |
| JOIN-Erkennung verbessern | `backend/services/parser.py` → `_infer_join_relationships()` |
| Leere-Ergebnis-Klassifikation | `backend/services/interpreter.py` → `_classify_empty_result()` |
| Chart-Logik | `backend/services/chart.py` |
| Modellnamen | `backend/config.py` |
| Frontend-Design | `frontend/src/index.css`, `frontend/src/App.tsx` |
| Neue Komponente | `frontend/src/components/` |
