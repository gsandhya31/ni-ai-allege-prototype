"""Human actions on alleges: approve/send draft, resolve, reclassify."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.config import SENT_DIR
from app.models import ResolveReq, SendReq
from app.services import audit, cases

router = APIRouter()


@router.post("/{allege_id}/send")
def send_draft(allege_id: str, req: SendReq):
    case = cases.get_case(allege_id)
    if not case:
        raise HTTPException(404, f"Allege {allege_id} not found")
    body = req.edited_body or case.get("draft_body") or ""
    if not body.strip():
        raise HTTPException(400, "No draft body to send")

    # Write to sent/ folder
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fname = f"{allege_id}_{ts}.eml"
    target = SENT_DIR / fname
    target.write_text(body, encoding="utf-8")

    cases.mark_sent(allege_id, str(target))
    audit.log(
        actor=req.actor or "Gopi",
        actor_type="human",
        action="Draft approved and sent",
        details=f"Saved reply to {target.name}",
        allege_id=allege_id,
        ai_recommended_action=(case.get("payload") or {}).get("aiSuggestedAction"),
        followed_ai_recommendation=True,
    )
    return {"ok": True, "sent_path": str(target), "sent_filename": fname}


@router.post("/{allege_id}/resolve")
def resolve(allege_id: str, req: ResolveReq):
    case = cases.get_case(allege_id)
    if not case:
        raise HTTPException(404, f"Allege {allege_id} not found")
    cases.update_status(allege_id, "Resolved", note=req.note)
    audit.log(
        actor=req.actor or "Gopi",
        actor_type="human",
        action="Allege marked resolved",
        details=req.note,
        allege_id=allege_id,
    )
    return {"ok": True}


@router.post("/{allege_id}/reject-classification")
def reject_classification(allege_id: str, actor: str = "Gopi"):
    """Analyst overrides the tool's allege classification (marks as non-allege)."""
    case = cases.get_case(allege_id)
    if not case:
        raise HTTPException(404, f"Allege {allege_id} not found")
    cases.update_status(allege_id, "Classified Non-Allege", note="Analyst override: not an allege")
    audit.log(
        actor=actor,
        actor_type="human",
        action="Classification overridden by analyst",
        details="Analyst marked case as not-an-allege.",
        allege_id=allege_id,
        followed_ai_recommendation=False,
    )
    return {"ok": True}


@router.post("/{allege_id}/confirm-classification")
def confirm_classification(allege_id: str, actor: str = "Gopi"):
    """Analyst confirms a low-confidence classification as correct."""
    case = cases.get_case(allege_id)
    if not case:
        raise HTTPException(404, f"Allege {allege_id} not found")
    audit.log(
        actor=actor,
        actor_type="human",
        action="Classification confirmed by analyst",
        details="Analyst confirmed the tool's low-confidence allege classification.",
        allege_id=allege_id,
        followed_ai_recommendation=True,
    )
    return {"ok": True}
