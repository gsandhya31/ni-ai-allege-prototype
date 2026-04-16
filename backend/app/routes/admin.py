"""Admin: toggle settings, reset demo, view LLM usage status."""
from __future__ import annotations

import shutil

from fastapi import APIRouter

from app.config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    INBOX_DIR,
    SAMPLES_DIR,
    SETTINGS,
    update_setting,
)
from app.models import SettingsUpdateReq
from app.services import audit, cases

router = APIRouter()


@router.get("/settings")
def get_settings():
    return {
        "use_llm": SETTINGS.get("use_llm", True),
        "extended_thinking": SETTINGS.get("extended_thinking", False),
        "assigned_analyst_filter": SETTINGS.get("assigned_analyst_filter", "Gopi"),
        "anthropic_api_key_set": bool(ANTHROPIC_API_KEY),
        "anthropic_model": ANTHROPIC_MODEL,
    }


@router.post("/settings")
def post_settings(req: SettingsUpdateReq):
    changed = []
    if req.use_llm is not None:
        update_setting("use_llm", req.use_llm)
        changed.append(f"use_llm={req.use_llm}")
    if req.extended_thinking is not None:
        update_setting("extended_thinking", req.extended_thinking)
        changed.append(f"extended_thinking={req.extended_thinking}")
    if req.assigned_analyst_filter is not None:
        update_setting("assigned_analyst_filter", req.assigned_analyst_filter)
        changed.append(f"analyst_filter={req.assigned_analyst_filter}")
    audit.log(
        actor="Admin",
        actor_type="human",
        action="Settings updated",
        details="; ".join(changed) if changed else "(no changes)",
    )
    return get_settings()


@router.post("/reset")
def reset_demo(actor: str = "Admin"):
    """Wipe live state, re-seed inbox from samples, preserve seed audit entries."""
    seed_dir = SAMPLES_DIR / "inbox_seed"
    # 1. Clear live inbox
    for f in INBOX_DIR.glob("*.eml"):
        f.unlink()
    # 2. Re-seed inbox
    restored = 0
    if seed_dir.exists():
        for f in seed_dir.glob("*.eml"):
            shutil.copy(f, INBOX_DIR / f.name)
            restored += 1
    # 3. Clear sent folder
    from app.config import SENT_DIR

    sent_cleared = 0
    for f in SENT_DIR.glob("*.eml"):
        f.unlink()
        sent_cleared += 1
    # 4. Wipe live audit entries (seed preserved)
    live_audit_wiped = audit.reset_live_entries()
    # 5. Wipe all cases
    cases_wiped = cases.reset_all_cases()

    audit.log(
        actor=actor,
        actor_type="human",
        action="Demo reset",
        details=(
            f"inbox_seeded={restored}, sent_cleared={sent_cleared}, "
            f"live_audit_wiped={live_audit_wiped}, cases_wiped={cases_wiped}"
        ),
    )
    # After reset, auto-run the pipeline so the dashboard is never empty for the demo.
    from app.services.pipeline import process_inbox as _process

    processed = _process(actor=actor)
    audit.log(
        actor=actor,
        actor_type="tool",
        action="Auto-processed inbox after reset",
        details=f"processed={len(processed['processed'])}, skipped={len(processed['skipped'])}",
    )
    return {
        "inbox_restored": restored,
        "sent_cleared": sent_cleared,
        "live_audit_wiped": live_audit_wiped,
        "cases_wiped": cases_wiped,
        "auto_processed": len(processed["processed"]),
    }
