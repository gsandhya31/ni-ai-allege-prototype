"""SQLite append-only audit log.

Every tool action and every human action gets a row. Seed entries (imported
from samples/seed_audit.json on first run) are preserved across demo resets;
live entries are wiped by the reset button.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import AUDIT_DB, SAMPLES_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    actor TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    allege_id TEXT,
    action TEXT NOT NULL,
    details TEXT,
    ai_recommended_action TEXT,
    followed_ai_recommendation INTEGER,
    seed INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_allege ON audit(allege_id);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(AUDIT_DB)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    with _conn() as c:
        c.executescript(SCHEMA)
    # Seed if empty
    seed_file = SAMPLES_DIR / "seed_audit.json"
    if not seed_file.exists():
        return
    with _conn() as c:
        row = c.execute("SELECT COUNT(*) AS n FROM audit WHERE seed=1").fetchone()
        if row["n"] > 0:
            return
        with open(seed_file) as f:
            seed_entries = json.load(f)
        for e in seed_entries:
            c.execute(
                """INSERT INTO audit
                (timestamp, actor, actor_type, allege_id, action, details,
                 ai_recommended_action, followed_ai_recommendation, seed)
                VALUES (?,?,?,?,?,?,?,?,1)""",
                (
                    e.get("timestamp", _now_iso()),
                    e.get("actor", "system"),
                    e.get("actor_type", "tool"),
                    e.get("allege_id"),
                    e.get("action", ""),
                    e.get("details", ""),
                    e.get("ai_recommended_action"),
                    1 if e.get("followed_ai_recommendation") else 0
                    if e.get("followed_ai_recommendation") is not None
                    else None,
                ),
            )


def log(
    actor: str,
    actor_type: str,
    action: str,
    details: str = "",
    allege_id: Optional[str] = None,
    ai_recommended_action: Optional[str] = None,
    followed_ai_recommendation: Optional[bool] = None,
) -> None:
    with _conn() as c:
        c.execute(
            """INSERT INTO audit
            (timestamp, actor, actor_type, allege_id, action, details,
             ai_recommended_action, followed_ai_recommendation, seed)
            VALUES (?,?,?,?,?,?,?,?,0)""",
            (
                _now_iso(),
                actor,
                actor_type,
                allege_id,
                action,
                details,
                ai_recommended_action,
                None
                if followed_ai_recommendation is None
                else (1 if followed_ai_recommendation else 0),
            ),
        )


def list_entries(limit: int = 500) -> List[Dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM audit ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def reset_live_entries() -> int:
    """Wipe non-seed entries. Returns number deleted."""
    with _conn() as c:
        cur = c.execute("DELETE FROM audit WHERE seed=0")
        return cur.rowcount
