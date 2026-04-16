"""Trigger pipeline processing of the inbox folder."""
from __future__ import annotations

from fastapi import APIRouter

from app.services import audit
from app.services.pipeline import process_inbox

router = APIRouter()


@router.post("/inbox")
def trigger_process(actor: str = "system"):
    audit.log(actor=actor, actor_type="human" if actor != "system" else "tool",
              action="Inbox processing triggered", details="User or scheduler invoked pipeline")
    result = process_inbox(actor=actor)
    return {
        "processed": len(result["processed"]),
        "skipped": len(result["skipped"]),
        "details": result,
    }
