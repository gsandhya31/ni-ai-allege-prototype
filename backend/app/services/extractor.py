"""Extract trade fields from email body.

Strategy: regex first. Any field regex cannot find gets filled by a single LLM
call (so we don't burn one call per field).
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from app.services.llm import NoLLM, llm_call, llm_enabled

PRODUCT_TYPES = [
    "FX Spot",
    "FX Forward",
    "FX NDF",
    "FX Swap",
    "Interest Rate Swap",
    "Cross Currency Swap",
    "Credit Default Swap",
]

CURRENCY_PAIRS = [
    "USD/JPY",
    "EUR/USD",
    "GBP/USD",
    "EUR/GBP",
    "USD/CHF",
    "EUR/CHF",
    "USD/CAD",
    "USD/HKD",
]

NOMURA_ENTITIES = [
    "Nomura International plc",
    "Nomura Securities Co Ltd",
    "Nomura Financial Products Europe GmbH",
]


# ---- Regex helpers ----
def _find(pattern: str, text: str, flags: int = re.IGNORECASE) -> Optional[str]:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def regex_extract(body: str, subject: str = "") -> Dict:
    """Pull as many fields as possible from plain text. Returns dict with None for missing fields."""
    blob = f"{subject}\n{body}"

    trade_ref = _find(
        r"(?:Trade Ref|Counterparty Ref|Trade Reference|Our Ref|GS Ref|JPM Ref|"
        r"HSBC Ref|Citi Ref|DB Ref|UBS Ref|Barclays Ref|BNP Ref|Morgan Stanley Ref|"
        r"Our Trade Ref|Counterparty Trade Ref|Ref|Reference)"
        r"\s*[:\-]?\s*([A-Z0-9\-/]+)",
        blob,
    )
    # Fallback: look for inline refs like ABC-CDE-20260414-0091 anywhere in subject
    if not trade_ref:
        trade_ref = _find(r"\b([A-Z]{2,5}-[A-Z]{2,5}-\d{8}-\d{3,5})\b", blob)

    trade_date = _find(
        r"(?:Trade Date|Traded On|Executed)\s*[:\-]?\s*(\d{1,2}[\-/\s][A-Za-z]{3,9}[\-/\s]\d{4})",
        blob,
    )
    value_date = _find(
        r"(?:Value Date|Settlement Date|Effective Date|Value)\s*[:\-]?\s*(\d{1,2}[\-/\s][A-Za-z]{3,9}[\-/\s]\d{4})",
        blob,
    )
    # Capture notional AND the currency tag that precedes the amount,
    # e.g. "Notional: USD 20,000,000" → currency=USD, notional=20000000
    notional_match = re.search(
        r"(?:Notional|Amount|Principal)\s*[:\-]?\s*([A-Z]{3})?\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:MM|M)?",
        blob,
        re.IGNORECASE,
    )
    notional: Optional[str] = None
    notional_currency: Optional[str] = None
    if notional_match:
        notional_currency = notional_match.group(1)
        if notional_currency:
            notional_currency = notional_currency.upper()
        notional = notional_match.group(2).replace(",", "")

    currency_pair = None
    for cp in CURRENCY_PAIRS:
        if cp in blob:
            currency_pair = cp
            break
    # Prefer the currency that was tagged on the notional line.
    # Fall back to explicit "Currency:" label, then to the first ISO currency code.
    currency = notional_currency or _find(r"Currency\s*[:\-]?\s*\b(USD|EUR|GBP|JPY|CHF|CAD|HKD|SGD|AUD)\b", blob)
    if not currency:
        # Last-resort fallback — but avoid matching currency-pair tokens
        # by looking for standalone codes not immediately followed by "/"
        m = re.search(r"\b(USD|EUR|GBP|JPY|CHF|CAD|HKD|SGD|AUD)\b(?!/)", blob)
        currency = m.group(1) if m else None
    rate = _find(r"(?:Rate|Price|Fixed Rate)\s*[:\-]?\s*([0-9]+\.[0-9]+)\s*%?", blob)
    if rate:
        rate = rate.replace("%", "").strip()
    direction = _find(
        r"(Nomura\s+(?:Buys|Sells|Pays|Receives)[^\n\r]+?)(?:[\n\r]|$)", blob
    )
    product_type = None
    for pt in PRODUCT_TYPES:
        if pt.lower() in blob.lower():
            product_type = pt
            break
    nomura_entity = None
    for ne in NOMURA_ENTITIES:
        if ne.lower() in blob.lower():
            nomura_entity = ne
            break
    # Counterparty on its own line — tolerate extra spaces after the colon (common in templates).
    # Example: "Counterparty:             Deutsche Bank AG"
    m_cp = re.search(
        r"(?im)(?:^|\n)\s*(?:Counterparty|Counter\s*party)\s*:\s*(.+?)\s*$",
        blob,
    )
    counterparty_stated = m_cp.group(1).strip() if m_cp else None
    if counterparty_stated == "":
        counterparty_stated = None
    # Fallback: "Sent on behalf of …" / "Acting on behalf of …" (often mid-line)
    if not counterparty_stated:
        counterparty_stated = _find(
            r"(?:Sent\s+on\s+behalf\s+of|Acting\s+on\s+behalf\s+of)\s*[:\-]?\s*([A-Z][A-Za-z\s&.,]+?)(?:\n|,|$)",
            blob,
        )

    # Look for a BIC labelled on a line like "BIC: CHASUS33XXX" or
    # "Our BIC: ...". Only accept proper SWIFT BIC shape (8 or 11 chars).
    bic_labelled = _find(
        r"(?:Counterparty\s+BIC|Our\s+BIC|BIC(?:\s+Code)?|SWIFT)\s*[:\-]?\s*"
        r"([A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)",
        blob,
    )
    counterparty_bic: Optional[str] = bic_labelled
    settlement_method = _find(
        r"(?:Settlement(?:\s+Method)?)\s*[:\-]?\s*(CLS|DTCC|MarkitWire|Bilateral|Pending|SWIFT)",
        blob,
    )

    return {
        "counterparty_stated": counterparty_stated,
        "trade_ref": trade_ref,
        "trade_date": trade_date,
        "value_date": value_date,
        "notional": notional,
        "currency": currency,
        "currency_pair": currency_pair,
        "rate": rate,
        "direction": direction,
        "product_type": product_type,
        "nomura_entity": nomura_entity,
        "counterparty_bic": counterparty_bic,
        "settlement_method": settlement_method,
    }


LLM_EXTRACT_SYSTEM = """You are an operations assistant extracting trade details from an allege email.
Return STRICT JSON matching this schema. Use null when truly absent. Do not invent values.

{
  "trade_ref": string|null,
  "trade_date": "DD-MMM-YYYY"|null,
  "value_date": "DD-MMM-YYYY"|null,
  "notional": number|null,
  "currency": "USD"|"EUR"|"GBP"|"JPY"|"CHF"|"CAD"|"HKD"|null,
  "currency_pair": "USD/JPY"|"EUR/USD"|"GBP/USD"|"EUR/GBP"|"USD/CHF"|"EUR/CHF"|"USD/CAD"|"USD/HKD"|null,
  "rate": number|null,
  "direction": string|null,
  "product_type": "FX Spot"|"FX Forward"|"FX NDF"|"FX Swap"|"Interest Rate Swap"|"Cross Currency Swap"|"Credit Default Swap"|null,
  "nomura_entity": "Nomura International plc"|"Nomura Securities Co Ltd"|"Nomura Financial Products Europe GmbH"|null,
  "counterparty_bic": string|null,
  "settlement_method": "CLS"|"DTCC"|"MarkitWire"|"Bilateral"|"Pending"|"SWIFT"|null,
  "counterparty_stated": string|null
}
"""


def llm_extract_missing(body: str, subject: str, existing: Dict) -> Dict:
    """Fill missing fields by asking the LLM in a single call."""
    missing: List[str] = [k for k, v in existing.items() if v in (None, "")]
    if not missing:
        return existing
    if not llm_enabled():
        existing["counterparty_stated"] = existing.get("counterparty_stated")
        return existing

    user_msg = f"SUBJECT: {subject}\n\nEMAIL BODY:\n{body}\n\nMISSING FIELDS: {missing}\nReturn JSON for ALL fields (use regex results if already present)."
    try:
        raw = llm_call(LLM_EXTRACT_SYSTEM, user_msg, max_tokens=600)
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return existing
        data = json.loads(m.group(0))
        merged = dict(existing)
        # Guard against the LLM hallucinating filler strings for missing fields
        JUNK_VALUES = {"unmatched", "unknown", "n/a", "na", "none", "missing", "-", "--"}
        for k, v in data.items():
            # Only overwrite if existing value is missing
            if merged.get(k) in (None, "") and v not in (None, ""):
                # Reject junk placeholder strings
                if isinstance(v, str) and v.strip().lower() in JUNK_VALUES:
                    continue
                merged[k] = v
        # Never overwrite a regex-extracted counterparty with an LLM guess/null.
        if merged.get("counterparty_stated") in (None, "") and data.get("counterparty_stated") not in (None, ""):
            merged["counterparty_stated"] = data["counterparty_stated"]
        return merged
    except NoLLM:
        return existing
    except Exception:
        return existing


def extract_fields(parsed: Dict) -> Dict:
    body = parsed.get("body_latest") or parsed.get("body_full") or ""
    subject = parsed.get("subject") or ""
    regex_result = regex_extract(body, subject)
    final = llm_extract_missing(body, subject, regex_result)
    # Normalise notional to float if possible
    try:
        if final.get("notional") is not None:
            final["notional"] = float(str(final["notional"]).replace(",", ""))
    except Exception:
        pass
    try:
        if final.get("rate") is not None:
            final["rate"] = float(final["rate"])
    except Exception:
        pass
    return final
