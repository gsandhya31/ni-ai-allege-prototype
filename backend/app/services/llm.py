"""Anthropic Claude client, with a rule-based mock fallback.

- If ANTHROPIC_API_KEY is missing/empty OR admin toggle use_llm is False,
  calls into llm_call() raise NoLLM and the caller must use its rules path.
- Else it calls Claude Sonnet and returns the raw text.
- Extended thinking is toggleable from admin.
"""
from __future__ import annotations

from typing import Optional

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, SETTINGS


class NoLLM(Exception):
    """Raised when LLM is disabled or API key missing."""


def llm_enabled() -> bool:
    return bool(ANTHROPIC_API_KEY) and bool(SETTINGS.get("use_llm", True))


_client = None


def _get_client():
    global _client
    if _client is None:
        from anthropic import Anthropic

        _client = Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def llm_call(
    system: str,
    user: str,
    max_tokens: int = 1024,
    extended_thinking: Optional[bool] = None,
) -> str:
    """Single-shot call. Returns the text of the first text block."""
    if not llm_enabled():
        raise NoLLM("LLM disabled (admin toggle off or API key missing).")

    client = _get_client()
    use_thinking = (
        SETTINGS.get("extended_thinking", False)
        if extended_thinking is None
        else extended_thinking
    )

    kwargs = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    if use_thinking:
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": 2000}
        # Anthropic requires max_tokens > budget_tokens when thinking is on
        kwargs["max_tokens"] = max(max_tokens, 4096)

    resp = client.messages.create(**kwargs)

    # Extract first text block (skip thinking blocks)
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            return block.text
    return ""
