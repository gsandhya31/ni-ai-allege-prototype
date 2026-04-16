"""Classify an email as allege / not-allege based on its LATEST REPLY only.

LLM path: one Claude call returning strict JSON.
Rules path: keyword scoring with explicit resolved-reply handling.
"""
from __future__ import annotations

import json
import re
from typing import Dict

from app.services.llm import NoLLM, llm_call, llm_enabled

CLASSIFY_SYSTEM = """You are an operations analyst at an investment bank helping classify inbound emails.
Your job: given ONLY the latest reply of an email thread, decide whether it is a live allege from a counterparty (i.e. the counterparty is currently claiming a trade that Nomura has not matched or confirmed).

IMPORTANT RULES:
- Classify based strictly on the latest reply provided. Ignore prior context.
- If the latest reply indicates the issue is resolved ("found the trade", "please ignore", "no further action", "confirmed", "match on our side"), classify as NOT an allege.
- If the latest reply is an invoice, marketing, system notification, or unrelated message, classify as NOT an allege.
- If the latest reply is a counterparty actively asking Nomura to confirm / locate / amend / reconfirm a trade that they believe should exist on Nomura's books, classify as AN ALLEGE.
- Return confidence 0-1. Use 0.9+ for clear cases, 0.6-0.8 for ambiguous, <0.6 when uncertain.

Reply with STRICT JSON only, no prose:
{"is_allege": true|false, "confidence": 0-1, "reasoning": "one sentence"}
"""

RESOLVED_KEYWORDS = [
    "please ignore",
    "no further action",
    "issue resolved",
    "found the trade",
    "found on our side",
    "match on our side",
    "confirmed on our side",
    "apologies for the noise",
    "we've sorted",
    "resolved",
]

ALLEGE_KEYWORDS = [
    "allege",
    "alleged",
    "alleging",
    "unmatched",
    "cannot find",
    "can not find",
    "not confirmed",
    "not booked",
    "please confirm",
    "reconfirm",
    "discrepancy",
    "mismatch",
    "missing ssi",
    "ssi missing",
    "submit ssi",
    "resubmit",
    "break",
    "urgent",
    "value today",
    "same-day value",
    "awaiting your affirmation",
    "awaiting your confirmation",
]

NON_ALLEGE_KEYWORDS = [
    "invoice",
    "billing",
    "payment due",
    "unsubscribe",
    "newsletter",
    "webinar",
]


def _rules_classify(body_latest: str) -> Dict:
    text = body_latest.lower()
    if any(k in text for k in RESOLVED_KEYWORDS):
        return {
            "is_allege": False,
            "confidence": 0.9,
            "reasoning": "Latest reply indicates resolution (keyword match).",
            "source": "rules",
        }
    if any(k in text for k in NON_ALLEGE_KEYWORDS):
        return {
            "is_allege": False,
            "confidence": 0.9,
            "reasoning": "Email looks like a non-trade notification (invoice/billing).",
            "source": "rules",
        }
    score = sum(1 for k in ALLEGE_KEYWORDS if k in text)
    if score >= 2:
        return {
            "is_allege": True,
            "confidence": min(0.95, 0.6 + 0.08 * score),
            "reasoning": f"{score} allege-related keywords matched in latest reply.",
            "source": "rules",
        }
    if score == 1:
        return {
            "is_allege": True,
            "confidence": 0.55,
            "reasoning": "One allege-related keyword matched; ambiguous.",
            "source": "rules",
        }
    return {
        "is_allege": False,
        "confidence": 0.6,
        "reasoning": "No allege signals in latest reply.",
        "source": "rules",
    }


def classify_email(parsed: Dict) -> Dict:
    body_latest = parsed.get("body_latest") or parsed.get("body_full") or ""
    subject = parsed.get("subject") or ""

    if not llm_enabled():
        result = _rules_classify(body_latest)
        return result

    try:
        user_msg = f"SUBJECT: {subject}\n\nLATEST REPLY:\n{body_latest}"
        raw = llm_call(CLASSIFY_SYSTEM, user_msg, max_tokens=300)
        # Extract JSON
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return _rules_classify(body_latest) | {"source": "rules-fallback-no-json"}
        data = json.loads(m.group(0))
        return {
            "is_allege": bool(data.get("is_allege")),
            "confidence": float(data.get("confidence", 0.0)),
            "reasoning": str(data.get("reasoning", "")),
            "source": "llm",
        }
    except NoLLM:
        return _rules_classify(body_latest)
    except Exception as e:
        fallback = _rules_classify(body_latest)
        fallback["reasoning"] += f" (LLM error: {e})"
        fallback["source"] = "rules-fallback-llm-error"
        return fallback
