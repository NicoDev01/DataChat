"""POST /api/query — Frage → SQL → Antwort + Chart + Tabelle."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.session import get_session
from services.sql_agent import run_query
from services.interpreter import interpret
from services.chart import detect

router = APIRouter(prefix="/api", tags=["query"])


class QueryRequest(BaseModel):
    session_id: str
    question: str


@router.post("/query")
async def query(req: QueryRequest):
    if not req.question.strip():
        raise HTTPException(400, "Frage darf nicht leer sein.")

    session = get_session(req.session_id)
    if not session:
        raise HTTPException(404, "Session nicht gefunden. Bitte Datei erneut hochladen.")
    if not session.conn:
        raise HTTPException(500, "Datenbankverbindung nicht verfügbar.")

    # 1. SQL generieren + ausführen
    sql, columns, rows, error = run_query(
        session.conn,
        session.schema_description,
        req.question,
        session.successful_queries,
    )

    if error:
        return {
            "success": False,
            "error": error,
            "sql": sql,
            "answer": "Die Abfrage konnte leider nicht ausgeführt werden.",
            "chart": {"type": "none", "data": [], "x_key": "", "y_keys": []},
            "table": {"columns": [], "rows": []},
        }

    # Erfolgreiche Query für zukünftige Few-Shot Examples speichern (max. 10)
    session.successful_queries.append({"question": req.question, "sql": sql})
    if len(session.successful_queries) > 10:
        session.successful_queries.pop(0)

    # 2. Professionelle Antwort generieren
    answer = interpret(req.question, sql, columns, rows)

    # 3. Chart-Konfiguration bestimmen
    chart = detect(columns, rows)

    return {
        "success": True,
        "error": None,
        "sql": sql,
        "answer": answer,
        "chart": chart,
        "table": {
            "columns": columns,
            "rows": rows[:200],  # max 200 Zeilen im Frontend
        },
    }
