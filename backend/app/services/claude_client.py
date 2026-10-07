"""Claude API for words, never numbers (doc 01 §6): it labels and summarises what the engines already produced.

- Used only when Settings → Explanations is "Claude" and an API key is saved; otherwise callers fall back to templates.
- Every call's real token usage is priced and added to this month's spend; calls stop at the monthly cap in Settings.
- Refusals: the server-side `fallbacks: "default"` option re-runs a declined request on Anthropic's recommended model.
"""

import json
from datetime import datetime

import anthropic
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.security.secrets_store import get_secret
from app.services import app_settings

MODEL = "claude-opus-5-5"
PRICE_USD_PER_MTOK = {"input": 4.00, "output": 20.00, "cache_read": 0.20, "cache_write": 5.00}
USD_TO_INR = 88.0  # conservative: overstating the rupee cost keeps spending under the cap
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeUnavailable(Exception):
    """Claude is switched off, has no key, hit the monthly cap, declined, or couldn't be reached. Use the template instead."""


def enabled(db: Session) -> bool:
    return app_settings.get_setting(db, "explanation_mode") == "claude" and bool(get_secret(db, "anthropic_api_key"))


def _month() -> str:
    return datetime.now().strftime("%Y-%m")


def spend(db: Session) -> dict:
    s = app_settings.get_setting(db, "claude_spend") or {}
    if s.get("month") != _month():
        s = {"month": _month(), "inr": 0.0, "calls": 0}
    return s | {"cap_inr": float(app_settings.get_setting(db, "claude_monthly_cap_inr") or 0)}


def _cost_inr(usage) -> float:
    u = {
        "input": getattr(usage, "input_tokens", 0) or 0,
        "output": getattr(usage, "output_tokens", 0) or 0,
        "cache_read": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "cache_write": getattr(usage, "cache_creation_input_tokens", 0) or 0,
    }
    return sum(u[k] * PRICE_USD_PER_MTOK[k] for k in u) / 1e6 * USD_TO_INR


def _api_message(exc: anthropic.APIStatusError) -> str:
    body = getattr(exc, "body", None)
    if isinstance(body, dict) and isinstance(body.get("error"), dict) and body["error"].get("message"):
        return str(body["error"]["message"])[:240]
    return str(getattr(exc, "message", "") or exc)[:240]


def json_call(db: Session, *, system: str, user: str, schema: dict, max_tokens: int = 16000, effort: str = "low") -> dict:
    """One request whose reply must match `schema`. Returns the parsed JSON; raises ClaudeUnavailable otherwise."""
    if app_settings.get_setting(db, "explanation_mode") != "claude":
        raise ClaudeUnavailable("Explanations are set to templates in Settings")
    key = get_secret(db, "anthropic_api_key")
    if not key:
        raise ClaudeUnavailable("No Claude API key saved in Settings")
    s = spend(db)
    if s["inr"] >= s["cap_inr"]:
        raise ClaudeUnavailable(f"This month's Claude budget (₹{s['cap_inr']:,.0f}) is used up")
    workspace = (get_secret(db, "anthropic_workspace_id") or "").strip()
    client = anthropic.Anthropic(
        api_key=key, max_retries=2, timeout=120.0, default_headers={"anthropic-workspace-id": workspace} if workspace else None
    )
    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.AuthenticationError as exc:
        raise ClaudeUnavailable("The saved Claude API key was rejected — check it in Settings") from exc
    except anthropic.RateLimitError as exc:
        raise ClaudeUnavailable("Claude is busy (rate limited) — try again in a minute") from exc
    except anthropic.APIStatusError as exc:
        text = _api_message(exc)
        if "workspace" in text.lower():
            raise ClaudeUnavailable(
                "Your Claude API key isn't linked to a workspace: add the workspace ID in Settings, or create a key inside a workspace"
            ) from exc
        raise ClaudeUnavailable(f"Claude API error {exc.status_code}: {text}") from exc
    except anthropic.APIConnectionError as exc:
        raise ClaudeUnavailable("Couldn't reach Claude (network)") from exc
    cost = _cost_inr(response.usage)
    app_settings.set_setting(db, "claude_spend", {"month": s["month"], "inr": round(s["inr"] + cost, 4), "calls": s["calls"] + 1, "last_at": utcnow().isoformat()})
    db.commit()
    if response.stop_reason == "refusal":
        raise ClaudeUnavailable("Claude declined this request")
    if response.stop_reason == "max_tokens":
        raise ClaudeUnavailable("Claude's reply was cut off")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ClaudeUnavailable("Claude's reply wasn't valid JSON") from exc
