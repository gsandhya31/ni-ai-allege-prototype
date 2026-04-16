"""Allege CRUD-ish routes."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from app.config import SETTINGS
from app.services import audit, cases

router = APIRouter()


def _shape_for_ui(case: Dict[str, Any]) -> Dict[str, Any]:
    """Merge SQLite metadata with the payload so the UI sees a flat record."""
    payload = case.get("payload") or {}
    out = dict(payload)
    out["allegeId"] = case["allege_id"]
    out["status"] = case.get("status") or payload.get("status") or "Open"
    out["sourceFile"] = case.get("source_file")
    out["createdAt"] = case.get("created_at")
    out["updatedAt"] = case.get("updated_at")
    out["assignedTo"] = case.get("assigned_to")
    out["draftBody"] = case.get("draft_body")
    out["draftTemplate"] = case.get("draft_template")
    out["sentAt"] = case.get("sent_at")
    out["sentPath"] = case.get("sent_path")
    out["resolutionNote"] = case.get("resolution_note") or payload.get("resolutionNote")
    out["isAllege"] = bool(case.get("is_allege"))
    return out


@router.get("")
def list_alleges(
    analyst: Optional[str] = Query(None, description="Filter to alleges assigned to this analyst (or null)."),
    include_non_alleges: bool = Query(True),
):
    # If no explicit analyst filter given, use global admin setting
    if analyst is None:
        analyst = SETTINGS.get("assigned_analyst_filter") or None
    raw = cases.list_cases(analyst_filter=analyst, include_non_alleges=include_non_alleges)
    shaped = [_shape_for_ui(c) for c in raw]
    return {"cases": shaped, "count": len(shaped)}


@router.get("/{allege_id}")
def get_allege(allege_id: str):
    case = cases.get_case(allege_id)
    if not case:
        raise HTTPException(404, f"Allege {allege_id} not found")
    audit.log(
        actor="Gopi",
        actor_type="human",
        action="Allege viewed",
        details=f"Opened detail page for {allege_id}",
        allege_id=allege_id,
    )
    return _shape_for_ui(case)
