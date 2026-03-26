"""In-memory Session Store — ein Eintrag pro Upload."""
import uuid
import sqlite3
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Session:
    session_id: str
    schema_sql: str = ""
    schema_description: str = ""
    table_names: list = field(default_factory=list)
    table_count: int = 0
    row_count: int = 0
    conn: Optional[sqlite3.Connection] = None
    successful_queries: list = field(default_factory=list)  # [{question, sql}, ...]


_sessions: dict[str, Session] = {}


def create_session() -> Session:
    sid = str(uuid.uuid4())
    session = Session(session_id=sid)
    _sessions[sid] = session
    return session


def get_session(session_id: str) -> Optional[Session]:
    return _sessions.get(session_id)


def delete_session(session_id: str) -> None:
    if session_id in _sessions:
        s = _sessions[session_id]
        if s.conn:
            try:
                s.conn.close()
            except Exception:
                pass
        del _sessions[session_id]
