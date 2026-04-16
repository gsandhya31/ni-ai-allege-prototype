"""Case persistence: each email becomes a case row in SQLite.

Stores the full pipeline result as JSON plus a few indexed columns.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import CASES_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    allege_id TEXT PRIMARY KEY,
    source_file TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT NOT NULL,
    assigned_to TEXT,
    is_allege INTEGER NOT NULL,
    classification_confidence REAL,
    payload_json TEXT NOT NULL,
    draft_body TEXT,
    draft_template TEXT,
    sent_at TEXT,
    sent_path TEXT,
    resolution_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status);
CREATE INDEX IF NOT EXISTS idx_cases_assigned ON cases(assigned_to);
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(CASES_DB)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    with _conn() as c:
        c.executescript(SCHEMA)


def upsert_case(
    allege_id: str,
    source_file: str,
    is_allege: bool,
    classification_confidence: float,
    payload: Dict[str, Any],
    assigned_to: Optional[str] = "Gopi",
    status: str = "Open",
    draft_body: Optional[str] = None,
    draft_template: Optional[str] = None,
) -> None:
    now = _now()
    with _conn() as c:
        row = c.execute("SELECT allege_id FROM cases WHERE allege_id = ?", (allege_id,)).fetchone()
        if row:
            c.execute(
                """UPDATE cases SET
                    updated_at=?, status=?, assigned_to=?, is_allege=?,
                    classification_confidence=?, payload_json=?, draft_body=?, draft_template=?
                WHERE allege_id=?""",
                (
                    now,
                    status,
                    assigned_to,
                    1 if is_allege else 0,
                    classification_confidence,
                    json.dumps(payload),
                    draft_body,
                    draft_template,
                    allege_id,
                ),
            )
        else:
            c.execute(
                """INSERT INTO cases
                (allege_id, source_file, created_at, updated_at, status, assigned_to,
                 is_allege, classification_confidence, payload_json, draft_body, draft_template)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    allege_id,
                    source_file,
                    now,
                    now,
                    status,
                    assigned_to,
                    1 if is_allege else 0,
                    classification_confidence,
                    json.dumps(payload),
                    draft_body,
                    draft_template,
                ),
            )


def get_case(allege_id: str) -> Optional[Dict[str, Any]]:
    with _conn() as c:
        row = c.execute("SELECT * FROM cases WHERE allege_id=?", (allege_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["payload"] = json.loads(d.pop("payload_json"))
    return d


def list_cases(analyst_filter: Optional[str] = None, include_non_alleges: bool = True) -> List[Dict[str, Any]]:
    query = "SELECT * FROM cases"
    params: List[Any] = []
    clauses: List[str] = []
    if analyst_filter:
        clauses.append("(assigned_to = ? OR assigned_to IS NULL)")
        params.append(analyst_filter)
    if not include_non_alleges:
        clauses.append("is_allege = 1")
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY created_at DESC"
    with _conn() as c:
        rows = c.execute(query, tuple(params)).fetchall()
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["payload"] = json.loads(d.pop("payload_json"))
        out.append(d)
    return out


def update_status(allege_id: str, status: str, note: Optional[str] = None) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE cases SET status=?, resolution_note=?, updated_at=? WHERE allege_id=?",
            (status, note, _now(), allege_id),
        )


def mark_sent(allege_id: str, sent_path: str) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE cases SET sent_at=?, sent_path=?, updated_at=? WHERE allege_id=?",
            (_now(), sent_path, _now(), allege_id),
        )


def reset_all_cases() -> int:
    with _conn() as c:
        cur = c.execute("DELETE FROM cases")
        return cur.rowcount
