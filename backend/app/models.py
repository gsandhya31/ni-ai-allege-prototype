"""Pydantic request/response models used by the API.

Kept loose (Dict[str, Any] in many places) because the payload is the rich
allege record that mirrors the frontend AllegeRecord type — tightening the
schema here would force duplication with the TS types.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class HealthResp(BaseModel):
    status: str
    version: str


class CaseListResp(BaseModel):
    cases: List[Dict[str, Any]]
    count: int


class ProcessInboxResp(BaseModel):
    processed: int
    skipped: int
    details: Dict[str, Any]


class ResolveReq(BaseModel):
    note: str
    actor: Optional[str] = "Gopi"


class SendReq(BaseModel):
    edited_body: Optional[str] = None
    actor: Optional[str] = "Gopi"


class SettingsUpdateReq(BaseModel):
    use_llm: Optional[bool] = None
    extended_thinking: Optional[bool] = None
    assigned_analyst_filter: Optional[str] = None


class AuditEntry(BaseModel):
    id: int
    timestamp: str
    actor: str
    actor_type: str
    allege_id: Optional[str]
    action: str
    details: Optional[str]
    ai_recommended_action: Optional[str]
    followed_ai_recommendation: Optional[int]
    seed: int


class AuditListResp(BaseModel):
    entries: List[AuditEntry]
    count: int
