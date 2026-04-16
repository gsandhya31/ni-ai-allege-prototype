"""Read-only audit trail view."""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.services import audit as audit_service

router = APIRouter()


@router.get("")
def list_audit(limit: int = Query(500, ge=1, le=5000)):
    entries = audit_service.list_entries(limit=limit)
    return {"entries": entries, "count": len(entries)}
