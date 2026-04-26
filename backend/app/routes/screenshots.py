"""Screenshot upload endpoint — saves base64 images to the screenshots folder."""
from __future__ import annotations

import base64
import os
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

# Resolve screenshots dir relative to repo root (2 levels up from app/routes/)
_REPO_ROOT = Path(__file__).resolve().parents[3]
SCREENSHOTS_DIR = _REPO_ROOT / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)


class ScreenshotPayload(BaseModel):
    filename: str
    data: str  # base64-encoded JPEG (without the data: URI prefix)


@router.post("/api/screenshot")
def save_screenshot(payload: ScreenshotPayload):
    """Accept a base64 JPEG and write it to the screenshots directory."""
    try:
        img_bytes = base64.b64decode(payload.data)
        out_path = SCREENSHOTS_DIR / payload.filename
        out_path.write_bytes(img_bytes)
        return {"success": True, "path": str(out_path)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@router.get("/api/screenshot/list")
def list_screenshots():
    files = sorted(str(p.name) for p in SCREENSHOTS_DIR.glob("*.jpeg"))
    return {"files": files}
