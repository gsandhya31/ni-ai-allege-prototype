"""Orchestrator: take a .eml file through the full pipeline and persist a case."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from app.config import INBOX_DIR
from app.services import audit, cases
from app.services.classifier import classify_email
from app.services.counterparty import resolve_counterparty
from app.services.drafter import draft_reply
from app.services.email_parser import parse_eml
from app.services.extractor import extract_fields
from app.services.matcher import diff_fields, match_trade


def _make_allege_id(path: Path, parsed: Dict) -> str:
    """Deterministic msg-style ID from filename + Message-ID header.

    Format: msg<7-digit-number>. Future enhancement: ID should come from
    Nomura's own mailbox / message-ID scheme; this is a demo placeholder.
    See DESIGN.md Section 7.
    """
    key = f"{path.name}|{parsed.get('message_id', '')}"
    # Hash → 7-digit decimal for a short, readable msg ID
    h = hashlib.sha1(key.encode()).hexdigest()
    num = int(h, 16) % 10_000_000
    return f"msg{num:07d}"


def _aging_bucket(trade_date_str: str) -> str:
    try:
        d = datetime.strptime(trade_date_str, "%d-%b-%Y").replace(tzinfo=timezone.utc)
        delta = (datetime.now(timezone.utc) - d).days
        if delta <= 0:
            return "T+0"
        if delta == 1:
            return "T+1"
        return "T+2+"
    except Exception:
        return "T+0"


def _risk_level(extracted: Dict, outcome: str) -> str:
    try:
        notional = float(extracted.get("notional") or 0)
    except Exception:
        notional = 0
    if outcome == "no_match" or notional >= 50_000_000:
        return "High"
    if notional >= 10_000_000:
        return "Medium"
    return "Low"


def _allege_reason(outcome: str, mismatches: list) -> str:
    if outcome == "no_match":
        return "Not Booked"
    if mismatches:
        return "Detail Mismatch"
    if outcome == "multi_match":
        return "Detail Mismatch"
    return "Booking Pending Approval"


def _derive_source(parsed: Dict) -> str:
    # The existing UI accepts "DTCC" | "MarkitWire" | "SWIFT" | "Email".
    # All our inbox items are Email-sourced for now.
    return "Email"


def _ai_suggested_action(outcome: str, match_info: Dict, cp_resolution: Dict) -> str:
    if outcome == "match":
        return (
            f"Match found in {match_info.get('system_hit')}. "
            f"Send confirmation reply using matched record {match_info['candidates'][0].get('internal_ref')}."
        )
    if outcome == "multi_match":
        return (
            f"Multiple candidates ({len(match_info['candidates'])}) in {match_info.get('system_hit')}. "
            "Request counterparty trade ref or execution timestamp to disambiguate."
        )
    src = cp_resolution.get("source")
    if src == "broker-unknown":
        return (
            "No match found in BO, MO, FO — broker-originated email with no clear counterparty in the body. "
            "Identify the legal counterparty, then mail Front Office to verify the booking."
        )
    if src == "sender-name-fallback":
        return (
            "No match found in BO, MO, FO — counterparty could not be tied to a known entity from email headers alone. "
            "Verify identity (body / BIC / trade ref), then mail Front Office to confirm whether the trade was booked."
        )
    if src == "domain-inferred":
        return (
            "No match found in BO, MO, FO — counterparty was inferred from sender domain. "
            "Confirm with sender if needed, then mail Front Office to verify the booking."
        )
    return "No match found in BO, MO, FO — mail Front Office to verify if trade was booked. Auto-drafted reply to counterparty is ready to review."


def process_eml(path: Path, actor: str = "system") -> Dict[str, Any]:
    parsed = parse_eml(path)
    allege_id = _make_allege_id(path, parsed)

    audit.log(actor="email_parser", actor_type="tool", action="Parsed .eml",
              details=f"File={path.name}, sender={parsed['sender_email']}, subject={parsed['subject']}",
              allege_id=allege_id)

    classification = classify_email(parsed)
    audit.log(
        actor="classifier",
        actor_type="tool",
        action="Classification " + ("ALLEGE" if classification["is_allege"] else "NOT ALLEGE"),
        details=f"source={classification.get('source')}, conf={classification.get('confidence'):.2f}, reasoning={classification.get('reasoning')}",
        allege_id=allege_id,
        ai_recommended_action="Proceed to extraction" if classification["is_allege"] else "Skip - not an allege",
    )

    if not classification["is_allege"]:
        cases.upsert_case(
            allege_id=allege_id,
            source_file=path.name,
            is_allege=False,
            classification_confidence=classification["confidence"],
            payload={
                "parsed": _safe_parsed(parsed),
                "classification": classification,
            },
            assigned_to=None,
            status="Classified Non-Allege",
        )
        return {"allege_id": allege_id, "is_allege": False, "classification": classification}

    extracted = extract_fields(parsed)
    audit.log(actor="extractor", actor_type="tool", action="Fields extracted",
              details=str({k: v for k, v in extracted.items() if v is not None}),
              allege_id=allege_id)

    cp = resolve_counterparty(parsed, extracted)
    audit.log(actor="counterparty_resolver", actor_type="tool", action="Counterparty resolved",
              details=f"counterparty={cp['counterparty']}, source={cp['source']}, broker={cp['broker_detected']}",
              allege_id=allege_id)

    match_info = match_trade(extracted, cp.get("counterparty"), extracted.get("product_type"))
    audit.log(
        actor="matcher",
        actor_type="tool",
        action=f"Match outcome: {match_info['outcome']}",
        details=f"systems_checked={match_info['systems_checked']}, hit_in={match_info['system_hit']}, candidates={len(match_info['candidates'])}",
        allege_id=allege_id,
    )

    mismatches: list = []
    if match_info["outcome"] == "match" and match_info["candidates"]:
        mismatches = diff_fields(extracted, match_info["candidates"][0])

    counterparty_ref = extracted.get("trade_ref")
    draft = draft_reply(
        outcome=match_info["outcome"],
        original_subject=parsed.get("subject", ""),
        recipient_name=parsed.get("sender_name") or None,
        counterparty_ref=counterparty_ref,
        system_name=match_info.get("system_hit"),
        rows=match_info.get("candidates", []),
        extracted=extracted,
        counterparty_used=cp.get("counterparty"),
        cp_resolution=cp,
    )
    audit.log(actor="drafter", actor_type="tool", action=f"Drafted reply ({draft['template']})",
              details=f"Template used: {draft['template']}", allege_id=allege_id)

    ai_action = _ai_suggested_action(match_info["outcome"], match_info, cp)
    risk = _risk_level(extracted, match_info["outcome"])
    aging = _aging_bucket(extracted.get("trade_date") or "")
    reason = _allege_reason(match_info["outcome"], mismatches)

    # Build payload matching frontend AllegeRecord shape loosely
    payload = {
        "allegeId": allege_id,
        "source": _derive_source(parsed),
        "counterparty": cp.get("counterparty"),
        "counterpartyResolution": cp,
        "nomuraEntity": extracted.get("nomura_entity") or (match_info["candidates"][0].get("nomura_entity") if match_info["candidates"] else "Nomura International plc"),
        "productType": extracted.get("product_type") or "FX Spot",
        "tradeDate": extracted.get("trade_date"),
        "valueDate": extracted.get("value_date"),
        "notional": extracted.get("notional"),
        "currency": extracted.get("currency"),
        "currencyPair": extracted.get("currency_pair"),
        "direction": extracted.get("direction"),
        "allegeReason": reason,
        "riskLevel": risk,
        "agingBucket": aging,
        "status": "Open",
        "aiSuggestedAction": ai_action,
        "aiConfidence": classification.get("confidence", 0.0),
        "assignedTo": "Gopi",
        "mismatchFields": mismatches,
        "counterpartyMessage": parsed.get("body_latest"),
        "counterpartyDetails": {
            "ref": extracted.get("trade_ref"),
            "amount": extracted.get("notional"),
            "rate": extracted.get("rate"),
            "settlementMethod": extracted.get("settlement_method"),
            "bic": extracted.get("counterparty_bic"),
            "valueDate": extracted.get("value_date"),
        },
        "nomuraDetails": _row_to_nomura_details(match_info["candidates"][0]) if match_info["candidates"] else None,
        "matchInfo": match_info,
        "draft": draft,
        "parsedEmail": _safe_parsed(parsed),
        "extracted": extracted,
        "classification": classification,
        "resolutionNote": None,
        "resolvedAt": None,
        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    cases.upsert_case(
        allege_id=allege_id,
        source_file=path.name,
        is_allege=True,
        classification_confidence=classification["confidence"],
        payload=payload,
        assigned_to="Gopi",
        status="Open",
        draft_body=draft["body"],
        draft_template=draft["template"],
    )
    return {"allege_id": allege_id, "is_allege": True, "payload": payload}


def _row_to_nomura_details(row: Dict) -> Dict:
    return {
        "ref": row.get("internal_ref"),
        "amount": _to_num(row.get("notional")),
        "rate": _to_num(row.get("rate")) if row.get("rate") else None,
        "settlementMethod": row.get("settlement_method"),
        "bic": row.get("nomura_bic"),
        "valueDate": row.get("value_date"),
    }


def _to_num(v):
    try:
        return float(v)
    except Exception:
        return v


def _safe_parsed(parsed: Dict) -> Dict:
    # Strip very long fields that aren't needed in the UI payload
    out = dict(parsed)
    out.pop("body_full", None)
    return out


def process_inbox(actor: str = "system") -> Dict[str, Any]:
    results = {"processed": [], "skipped": []}
    for eml in sorted(INBOX_DIR.glob("*.eml")):
        try:
            r = process_eml(eml, actor=actor)
            results["processed"].append(r)
        except Exception as e:
            audit.log(actor="pipeline", actor_type="tool", action="Error processing email",
                      details=f"file={eml.name}, error={e}")
            results["skipped"].append({"file": eml.name, "error": str(e)})
    return results
