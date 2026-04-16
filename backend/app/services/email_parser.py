"""Parse .eml files into a structured dict, isolating the latest reply."""
from __future__ import annotations

import email
import re
from email import policy
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, Optional

QUOTED_HEADER_PATTERNS = [
    r"^-{2,}\s*Original Message\s*-{2,}",
    r"^On .+ wrote:\s*$",
    r"^From:\s+.+",  # catches forwarded headers when they appear in plain text body
    r"^Sent:\s+.+",
    r"^Date:\s+.+",
    r"^To:\s+.+",
    r"^Subject:\s+.+",
]


def _extract_body(msg: EmailMessage) -> str:
    # Prefer text/plain
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                try:
                    return part.get_content()
                except Exception:
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode(errors="ignore")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                try:
                    html = part.get_content()
                    return re.sub(r"<[^>]+>", " ", html)
                except Exception:
                    pass
        return ""
    try:
        return msg.get_content()
    except Exception:
        payload = msg.get_payload(decode=True)
        return payload.decode(errors="ignore") if payload else ""


def _latest_reply(body: str) -> str:
    """Return only the latest reply portion, stripping quoted history."""
    if not body:
        return ""
    lines = body.splitlines()
    cut_idx = len(lines)
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Quoted-line markers
        if stripped.startswith(">"):
            cut_idx = i
            break
        # Header-like lines that look like the start of a quoted original
        for pat in QUOTED_HEADER_PATTERNS:
            if re.match(pat, stripped, re.IGNORECASE):
                cut_idx = i
                break
        if cut_idx == i:
            break
    latest = "\n".join(lines[:cut_idx]).strip()
    return latest or body.strip()


def parse_eml(path: Path) -> Dict[str, Optional[str]]:
    with open(path, "rb") as f:
        msg: EmailMessage = email.message_from_binary_file(f, policy=policy.default)  # type: ignore
    body = _extract_body(msg)
    latest = _latest_reply(body)
    from_hdr = msg.get("From", "") or ""
    # Extract raw email
    m = re.search(r"<([^>]+)>", from_hdr)
    sender_email = m.group(1).strip() if m else from_hdr.strip()
    sender_domain = sender_email.split("@")[-1].lower() if "@" in sender_email else ""
    sender_name = from_hdr.split("<")[0].strip().strip('"') if "<" in from_hdr else ""
    return {
        "file": str(path.name),
        "message_id": msg.get("Message-ID", ""),
        "in_reply_to": msg.get("In-Reply-To", ""),
        "date": msg.get("Date", ""),
        "from": from_hdr,
        "sender_email": sender_email,
        "sender_domain": sender_domain,
        "sender_name": sender_name,
        "to": msg.get("To", ""),
        "subject": msg.get("Subject", ""),
        "body_full": body,
        "body_latest": latest,
        "is_reply_thread": bool(msg.get("In-Reply-To")) or body != latest,
    }
