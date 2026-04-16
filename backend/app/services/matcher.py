"""Exact-match trade lookup against BO, MO, FO CSV systems.

Lookup order: BO -> MO -> FO. Stop at first system that returns at least one hit.
Key fields differ by product type (see DESIGN.md).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pandas as pd

from app.config import REFERENCE_DIR

SYSTEM_FILES = [
    ("BO", REFERENCE_DIR / "bo_system.csv"),
    ("MO", REFERENCE_DIR / "mo_system.csv"),
    ("FO", REFERENCE_DIR / "fo_system.csv"),
]

# Per-product match-key sets (must all exist in both the email and the row
# for the comparison to be applied). Missing extracted values are skipped for
# that field (i.e. match on the ones we have).
KEY_FIELDS_BY_PRODUCT: Dict[str, List[str]] = {
    "FX Spot": [
        "trade_date",
        "counterparty",
        "currency_pair",
        "notional",
        "rate",
        "direction",
        "value_date",
    ],
    "FX Forward": [
        "trade_date",
        "counterparty",
        "currency_pair",
        "notional",
        "rate",
        "direction",
        "value_date",
    ],
    "FX NDF": [
        "trade_date",
        "counterparty",
        "currency_pair",
        "notional",
        "rate",
        "direction",
        "value_date",
    ],
    "FX Swap": [
        "trade_date",
        "counterparty",
        "currency_pair",
        "notional",
        "rate",
        "direction",
        "value_date",
    ],
    "Interest Rate Swap": [
        "trade_date",
        "counterparty",
        "currency",
        "notional",
        "rate",
        "direction",
        "value_date",
    ],
    "Credit Default Swap": [
        "trade_date",
        "counterparty",
        "currency",
        "notional",
        "direction",
        "value_date",
    ],
    "Cross Currency Swap": [
        "trade_date",
        "counterparty",
        "currency",
        "notional",
        "rate",
        "direction",
        "value_date",
    ],
}


def _normalise(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _row_matches(row: pd.Series, extracted: Dict, counterparty: Optional[str], key_fields: List[str]) -> bool:
    for f in key_fields:
        if f == "counterparty":
            if counterparty is None:
                continue  # skip if we don't have counterparty
            if _normalise(row.get("counterparty")).lower() != _normalise(counterparty).lower():
                return False
        else:
            email_val = extracted.get(f)
            if email_val is None or email_val == "":
                continue  # skip if we don't have this field
            if _normalise(row.get(f)) != _normalise(email_val):
                return False
    return True


def _load(path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _run_search(
    df: pd.DataFrame, extracted: Dict, counterparty: Optional[str], product_type: Optional[str]
) -> List[Dict]:
    if df.empty:
        return []
    key_fields = KEY_FIELDS_BY_PRODUCT.get(product_type or "", KEY_FIELDS_BY_PRODUCT["FX Spot"])
    # Always filter product_type if known
    candidates = df
    if product_type and "product_type" in df.columns:
        candidates = df[df["product_type"].str.lower() == product_type.lower()]
    hits: List[Dict] = []
    for _, row in candidates.iterrows():
        if _row_matches(row, extracted, counterparty, key_fields):
            hits.append({k: row[k] for k in row.index})
    return hits


def match_trade(extracted: Dict, counterparty: Optional[str], product_type: Optional[str]) -> Dict:
    """Returns:
    {
      "outcome": "match" | "multi_match" | "no_match",
      "system_hit": "BO"|"MO"|"FO"|None,
      "systems_checked": ["BO","MO","FO"],
      "candidates": [ {row}, ... ],
      "counterparty_used": str|None,
      "key_fields_used": [...],
    }
    """
    systems_checked: List[str] = []
    key_fields = KEY_FIELDS_BY_PRODUCT.get(product_type or "", KEY_FIELDS_BY_PRODUCT["FX Spot"])
    for system_name, path in SYSTEM_FILES:
        systems_checked.append(system_name)
        df = _load(path)
        hits = _run_search(df, extracted, counterparty, product_type)
        if len(hits) == 1:
            return {
                "outcome": "match",
                "system_hit": system_name,
                "systems_checked": systems_checked,
                "candidates": hits,
                "counterparty_used": counterparty,
                "key_fields_used": key_fields,
            }
        if len(hits) > 1:
            return {
                "outcome": "multi_match",
                "system_hit": system_name,
                "systems_checked": systems_checked,
                "candidates": hits,
                "counterparty_used": counterparty,
                "key_fields_used": key_fields,
            }
    return {
        "outcome": "no_match",
        "system_hit": None,
        "systems_checked": systems_checked,
        "candidates": [],
        "counterparty_used": counterparty,
        "key_fields_used": key_fields,
    }


# Map from snake_case CSV/extracted field names → camelCase UI field names.
# The frontend builds a Set from mismatchFields and checks .has("settlementMethod") etc.
_SNAKE_TO_CAMEL = {
    "trade_date":       "tradeDate",
    "value_date":       "valueDate",
    "notional":         "notional",
    "rate":             "rate",
    "currency_pair":    "currencyPair",
    "currency":         "currency",
    "direction":        "direction",
    "nomura_entity":    "nomuraEntity",
    "settlement_method": "settlementMethod",
}


def diff_fields(extracted: Dict, row: Dict) -> List[str]:
    """Return camelCase field names where counterparty-submitted value differs from internal record."""
    diffs: List[str] = []
    for snake_field, camel_field in _SNAKE_TO_CAMEL.items():
        ev = extracted.get(snake_field)
        rv = row.get(snake_field)
        if ev in (None, "") or rv in (None, ""):
            continue
        if _normalise(ev).lower() != _normalise(rv).lower():
            diffs.append(camel_field)   # UI expects camelCase
    return diffs
