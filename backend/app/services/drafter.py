"""Render reply email drafts from Jinja2 templates."""
from __future__ import annotations

from typing import Dict, List, Optional

from jinja2 import Template

MATCH_TEMPLATE = Template(
    """Subject: RE: {{ original_subject }}

Dear {{ recipient_name or 'Counterparty Operations' }},

Thank you for your email regarding trade {{ counterparty_ref or '[ref]' }}.

We have located the matching trade in our {{ system_name }} system. Please find the details below for confirmation:

  Nomura Trade Ref:   {{ row.internal_ref }}
  Trade Date:         {{ row.trade_date }}
  Value Date:         {{ row.value_date }}
  Counterparty:       {{ row.counterparty }}
  Nomura Entity:      {{ row.nomura_entity }}
  Product:            {{ row.product_type }}
  Currency Pair:      {{ row.currency_pair or '-' }}
  Notional:           {{ row.currency }} {{ row.notional }}
  Rate:               {{ row.rate or '-' }}
  Direction:          {{ row.direction }}
  Settlement Method:  {{ row.settlement_method }}

{% if mismatches -%}
We note the following field(s) differ between your email and our record: {{ mismatches | join(', ') }}. Please review and confirm.
{% endif -%}

{% if counterparty_note -%}
Note: {{ counterparty_note }}
{% endif -%}

Please confirm these details or let us know if any amendment is required.

Kind regards,
Nomura Settlements
"""
)

NO_MATCH_TEMPLATE = Template(
    """Subject: RE: {{ original_subject }}

Dear {{ recipient_name or 'Counterparty Operations' }},

Thank you for your email regarding trade {{ counterparty_ref or '[ref]' }}.

We have searched our Back Office, Middle Office, and Front Office systems (BO, MO, FO) and are unable to locate a matching trade based on the details provided:

  Trade Date:         {{ extracted.trade_date or '-' }}
  Value Date:         {{ extracted.value_date or '-' }}
  Counterparty:       {{ counterparty_used or '(not provided)' }}
  Product:            {{ extracted.product_type or '-' }}
  Currency Pair:      {{ extracted.currency_pair or '-' }}
  Notional:           {{ extracted.currency or '' }} {{ extracted.notional or '-' }}
  Rate:               {{ extracted.rate or '-' }}
  Direction:          {{ extracted.direction or '-' }}

Please could you share the following so we can continue the investigation:
  - Confirmation of trader / desk that executed the trade on your side
  - Original execution venue (voice, MarkitWire, electronic platform, broker)
  - Any internal reference mapping (UTI / USI)
  - Timestamp of execution if available

{% if counterparty_note -%}
Note: {{ counterparty_note }}
{% endif -%}

Kind regards,
Nomura Settlements
"""
)

MULTI_MATCH_TEMPLATE = Template(
    """Subject: RE: {{ original_subject }}

Dear {{ recipient_name or 'Counterparty Operations' }},

Thank you for your email regarding trade {{ counterparty_ref or '[ref]' }}.

We have located multiple potential matches in our {{ system_name }} system using the details you provided. In order to correctly identify the trade, we need additional information from your side (ideally your internal trade ref or the exact execution timestamp).

Candidate records found:

{% for row in rows -%}
  [{{ loop.index }}] Nomura Ref: {{ row.internal_ref }} | Trade: {{ row.trade_date }} | Value: {{ row.value_date }} | {{ row.product_type }} | {{ row.counterparty }} | {{ row.currency }} {{ row.notional }} @ {{ row.rate or '-' }}
{% endfor %}

Please share the additional identifier at your earliest convenience.

{% if counterparty_note -%}
Note: {{ counterparty_note }}
{% endif -%}

Kind regards,
Nomura Settlements
"""
)

COUNTERPARTY_INFERRED_TEMPLATE = Template(
    """Subject: RE: {{ original_subject }}

Dear {{ recipient_name or 'Counterparty Operations' }},

Thank you for your email.

Your message did not explicitly identify the counterparty. Based on {{ cp_source_explained }}, we have assumed the counterparty is {{ counterparty_assumed }}. Please confirm whether this is correct.

Under that assumption:
{% if outcome == 'match' -%}
  We have located the matching trade in our {{ system_name }} system:
      Nomura Trade Ref:  {{ row.internal_ref }}
      Trade Date:        {{ row.trade_date }}
      Value Date:        {{ row.value_date }}
      Product:           {{ row.product_type }}
      Notional:          {{ row.currency }} {{ row.notional }}
      Rate:              {{ row.rate or '-' }}
      Direction:         {{ row.direction }}
{% elif outcome == 'multi_match' -%}
  We have located multiple candidate trades in our {{ system_name }} system. Please provide your internal trade ref so we can disambiguate.
{% else -%}
  We were unable to find a matching trade in any of our systems (BO, MO, FO). Please confirm the counterparty and resend the trade details.
{% endif %}

{% if broker_detected -%}
We note this email was received from an inter-dealer broker address ({{ sender_domain }}). Please confirm whether the broker is acting on behalf of {{ counterparty_assumed }} or another party.
{% endif %}

Kind regards,
Nomura Settlements
"""
)


def draft_reply(
    outcome: str,
    original_subject: str,
    recipient_name: Optional[str],
    counterparty_ref: Optional[str],
    system_name: Optional[str],
    rows: List[Dict],
    extracted: Dict,
    counterparty_used: Optional[str],
    cp_resolution: Dict,
) -> Dict:
    counterparty_note = cp_resolution.get("note") if cp_resolution.get("source") != "stated" else None
    broker_detected = cp_resolution.get("broker_detected")

    # Counterparty-inferred cases get their own template regardless of match outcome
    if cp_resolution.get("source") in ("domain-inferred", "broker-unknown", "sender-name-fallback"):
        text = COUNTERPARTY_INFERRED_TEMPLATE.render(
            original_subject=original_subject,
            recipient_name=recipient_name,
            counterparty_ref=counterparty_ref,
            system_name=system_name,
            row=rows[0] if rows else {},
            outcome=outcome,
            counterparty_assumed=counterparty_used or "(unknown)",
            cp_source_explained=_explain_source(cp_resolution),
            broker_detected=broker_detected,
            sender_domain=cp_resolution.get("sender_domain"),
        )
        template_used = "counterparty_inferred"
    elif outcome == "match":
        row = rows[0]
        mismatches: List[str] = []
        for f in ["trade_date", "value_date", "notional", "rate", "currency_pair", "currency", "direction", "settlement_method", "nomura_entity"]:
            if extracted.get(f) not in (None, "") and str(row.get(f, "")).lower() != str(extracted.get(f, "")).lower():
                mismatches.append(f)
        text = MATCH_TEMPLATE.render(
            original_subject=original_subject,
            recipient_name=recipient_name,
            counterparty_ref=counterparty_ref,
            system_name=system_name,
            row=row,
            mismatches=mismatches,
            counterparty_note=counterparty_note,
        )
        template_used = "match"
    elif outcome == "multi_match":
        text = MULTI_MATCH_TEMPLATE.render(
            original_subject=original_subject,
            recipient_name=recipient_name,
            counterparty_ref=counterparty_ref,
            system_name=system_name,
            rows=rows,
            counterparty_note=counterparty_note,
        )
        template_used = "multi_match"
    else:
        text = NO_MATCH_TEMPLATE.render(
            original_subject=original_subject,
            recipient_name=recipient_name,
            counterparty_ref=counterparty_ref,
            extracted=extracted,
            counterparty_used=counterparty_used,
            counterparty_note=counterparty_note,
        )
        template_used = "no_match"

    return {"template": template_used, "body": text}


def _explain_source(cp_resolution: Dict) -> str:
    src = cp_resolution.get("source")
    if src == "domain-inferred":
        return f"the sender domain ({cp_resolution.get('sender_domain')})"
    if src == "broker-unknown":
        return "a broker-originated email where the counterparty was not explicitly stated"
    if src == "sender-name-fallback":
        return "the sender's name/signature"
    return "the information provided"
