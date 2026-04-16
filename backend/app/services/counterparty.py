"""Resolve the counterparty for an allege email.

Priority order:
 1. Stated in body / extracted field "counterparty_stated"
 2. Sender domain mapped to known counterparty (if domain is NOT a broker)
 3. Sender domain is a broker -> flag; try LLM to pick from body signature
 4. Fallback: use sender_name as-is with warning.
"""
from __future__ import annotations

from typing import Dict, Optional

from app.config import BROKER_DOMAINS, DOMAIN_TO_COUNTERPARTY


def resolve_counterparty(parsed: Dict, extracted: Dict) -> Dict:
    stated: Optional[str] = extracted.get("counterparty_stated")
    sender_domain = (parsed.get("sender_domain") or "").lower()
    sender_name = parsed.get("sender_name") or ""

    if stated:
        return {
            "counterparty": stated,
            "source": "stated",
            "confidence": 0.95,
            "broker_detected": sender_domain in BROKER_DOMAINS,
            "sender_domain": sender_domain,
            "note": "Counterparty stated explicitly in email body.",
        }

    if sender_domain in BROKER_DOMAINS:
        # Broker-sent. Counterparty must come from body / LLM extraction.
        # If LLM already found counterparty_stated we'd have returned above.
        return {
            "counterparty": None,
            "source": "broker-unknown",
            "confidence": 0.3,
            "broker_detected": True,
            "sender_domain": sender_domain,
            "note": (
                f"Email sent by inter-dealer broker ({sender_domain}). "
                "Counterparty could not be determined from the body. Analyst must verify."
            ),
        }

    if sender_domain in DOMAIN_TO_COUNTERPARTY:
        return {
            "counterparty": DOMAIN_TO_COUNTERPARTY[sender_domain],
            "source": "domain-inferred",
            "confidence": 0.75,
            "broker_detected": False,
            "sender_domain": sender_domain,
            "note": (
                f"Counterparty inferred from sender domain {sender_domain}. "
                "Verify before sending reply."
            ),
        }

    # Unknown domain — take sender_name as best guess
    return {
        "counterparty": sender_name or None,
        "source": "sender-name-fallback",
        "confidence": 0.4,
        "broker_detected": False,
        "sender_domain": sender_domain,
        "note": "Counterparty could not be inferred with confidence.",
    }
