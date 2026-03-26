# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DataChat is a full-stack web app that lets users upload tabular data files and query them in natural language. The backend converts questions into SQLite SQL via Gemini AI, executes the queries, and returns answers, charts, and table data. The frontend renders results in a chat-like interface.

## Commands

### Backend (Python/FastAPI)

```bash
cd backend
# Install dependencies (requires Python 3.11+)
pip install fastapi uvicorn python-dotenv pandas openpyxl google-genai

# Run dev server (port 8090)
uvicorn main:app --reload --port 8090
```

### Frontend (React/Vite)

```bash
cd frontend
npm install
npm run dev        # dev server on port 5173
npm run build      # tsc + vite build
npm run preview    # preview production build
```

## Architecture

### Request Flow

1. **Upload**: `POST /api/upload` — user uploads a file (CSV, XLSX, XLS, DB, SQL)
2. `services/parser.py` parses it into a SQLite in-memory DB + a rich `schema_description` string
3. A `Session` object (in-memory dict, keyed by UUID) stores the SQLite connection and schema info
4. **Query**: `POST /api/query` — user sends `{session_id, question}`
5. `services/sql_agent.py` calls **Gemini Flash** to generate SQL, applies SQLite compatibility fixes (`apply_sqlite_compat`), executes it, and retries once on error or suspicious results
6. `services/interpreter.py` calls **Gemini Pro** to produce a natural-language answer from the results
7. `services/chart.py` uses rule-based logic (no LLM) to pick chart type (bar/line/pie/none) and format data for Recharts
8. Response returns `{success, sql, answer, chart, table}` — table capped at 200 rows, chart at 50 points

### Backend Structure

```
backend/
  main.py                  # FastAPI app, CORS config, router registration
  config.py                # Loads .env: GEMINI_API_KEY, GEMINI_FLASH_MODEL, GEMINI_PRO_MODEL
  routes/
    upload.py              # POST /api/upload
    query.py               # POST /api/query
  services/
    session.py             # In-memory session store (dict[str, Session])
    parser.py              # File parsing: CSV/XLSX → DataFrames → SQLite schema + description
    sql_agent.py           # NL→SQL via Gemini Flash, SQLite compat layer, retry logic
    interpreter.py         # SQL results → NL answer via Gemini Pro
    chart.py               # Rule-based chart type detection
```

### Frontend Structure

```
frontend/src/
  App.tsx                  # Root: upload state, query history, sticky input bar
  api/client.ts            # axios wrappers for /api/upload and /api/query
  types.ts                 # UploadResponse, QueryResponse, ChartConfig interfaces
  components/
    UploadZone.tsx         # Drag-and-drop file upload
    SchemaInfo.tsx         # Displays table/row count and schema after upload
    ChatInput.tsx          # Sticky bottom text input
    AnswerCard.tsx         # Renders answer text, Recharts chart, collapsible table, SQL viewer
```

### Key Design Decisions

**Schema description** — `parser.py` generates a rich text description of the uploaded data that is injected into every SQL generation prompt. It includes column types, sample values, date formats, currency/number formatting hints, ordinal scales, and auto-detected JOIN relationships with mandatory JOIN syntax. This is the primary mechanism for SQL accuracy.

**Two Gemini models** — Flash (faster/cheaper) generates SQL; Pro (higher quality) writes the natural-language interpretation. Both model names are configurable in `.env`.

**SQLite compatibility layer** — `apply_sqlite_compat()` in `sql_agent.py` deterministically rewrites LLM-generated SQL to be SQLite-compatible (ILIKE→LIKE, STDDEV→manual, TRUE/FALSE→1/0, reserved table name quoting, etc.) before execution.

**Sessions are in-memory only** — no persistence. Restarting the backend loses all sessions. The SQLite DB lives entirely in memory attached to the session object.

**Frontend API base URL** is hardcoded in `frontend/src/api/client.ts` as `http://localhost:8090/api`.

## Configuration

Backend requires `backend/.env`:
```
GEMINI_API_KEY=...
GEMINI_PRO_MODEL=gemini-3.1-pro-preview
GEMINI_FLASH_MODEL=gemini-3.1-flash-lite-preview
```

Supported upload formats: `.csv`, `.xlsx`, `.xls`, `.db`, `.sqlite`, `.sql` (max 20 MB).
