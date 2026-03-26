"""POST /api/upload — Datei hochladen und SQLite-Session anlegen."""
import pathlib
import sqlite3

from fastapi import APIRouter, HTTPException, UploadFile, File

from services.session import create_session
from services.parser import parse_upload

router = APIRouter(prefix="/api", tags=["upload"])

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".db", ".sqlite", ".sql"}


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    ext = pathlib.Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            f"Nicht unterstütztes Format '{ext}'. Erlaubt: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    file_bytes = await file.read()
    if len(file_bytes) > 20 * 1024 * 1024:  # 20 MB
        raise HTTPException(400, "Datei zu groß (max. 20 MB)")

    try:
        parsed = parse_upload(file_bytes, file.filename)
    except Exception as e:
        raise HTTPException(400, f"Fehler beim Einlesen der Datei: {e}")

    # SQLite in-memory DB aufbauen
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(parsed["schema_sql"])
        conn.commit()
        conn.execute("PRAGMA query_only = ON")
    except Exception as e:
        raise HTTPException(500, f"Fehler beim Aufbauen der Datenbank: {e}")

    session = create_session()
    session.schema_sql = parsed["schema_sql"]
    session.schema_description = parsed["schema_description"]
    session.table_names = parsed["table_names"]
    session.table_count = parsed["table_count"]
    session.row_count = parsed["row_count"]
    session.conn = conn

    return {
        "session_id": session.session_id,
        "filename": file.filename,
        "table_count": session.table_count,
        "row_count": session.row_count,
        "table_names": session.table_names,
        "schema_description": session.schema_description,
    }
