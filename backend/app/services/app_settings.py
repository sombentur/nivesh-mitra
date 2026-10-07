"""User-editable settings stored in the app_settings table, with typed defaults."""

from typing import Any

from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import AppSetting

# key -> (default, allowed values or None for free-form)
SETTING_DEFAULTS: dict[str, tuple[Any, tuple | None]] = {
    # First-run setup (doc 01 §4). The Google client ID is public, not a secret.
    "google_client_id": (None, None),
    "allowed_email": (None, None),
    # Explanations: Claude API or plain-language templates (doc 01 §6)
    "explanation_mode": ("template", ("template", "claude")),
    "claude_monthly_cap_inr": (500, None),
    # Fundamentals (doc 06): primary provider for historical statements
    "fundamentals_provider": ("manual", ("manual", "eodhd")),
    "trendlyne_enabled": (False, (True, False)),
    "trendlyne_plan": ("pro", ("pro", "max")),
    "language": ("en", ("en", "kn")),
    # Short-term practice trading: pretend capital used for position sizing
    "trading_paper_capital": (10000, None),
    # Onboarding / engine state, set by the app
    "sebi_ack_at": (None, None),
    "paper_mode_start": (None, None),
    "trading_ideas_status": (None, None),
    "claude_spend": (None, None),  # {"month": "2026-09", "inr": 12.5, "calls": 3}
    # Intraday practice: the plan made for each coming session and the scoreboard of each finished one (last few kept)
    "intraday_plans": (None, None),
    "intraday_recaps": (None, None),
}

SETUP_KEYS = ("google_client_id", "allowed_email")
SYSTEM_KEYS = ("sebi_ack_at", "paper_mode_start", "trading_ideas_status", "claude_spend", "intraday_plans", "intraday_recaps")
USER_EDITABLE_KEYS = tuple(k for k in SETTING_DEFAULTS if k not in SETUP_KEYS + SYSTEM_KEYS)


SETTING_VALIDATORS = {
    "trading_paper_capital": (lambda v: isinstance(v, (int, float)) and 1000 <= v <= 1000000, "Practice capital must be between ₹1,000 and ₹10,00,000"),
    "claude_monthly_cap_inr": (lambda v: isinstance(v, (int, float)) and 0 <= v <= 100000, "The Claude spending cap must be between ₹0 and ₹1,00,000"),
}


def get_setting(db: Session, key: str) -> Any:
    row = db.get(AppSetting, key)
    if row is not None:
        return row.value_json
    return SETTING_DEFAULTS[key][0]


def set_setting(db: Session, key: str, value: Any) -> None:
    if key not in SETTING_DEFAULTS:
        raise KeyError(key)
    allowed = SETTING_DEFAULTS[key][1]
    if allowed is not None and value not in allowed:
        raise ValueError(f"{key} must be one of {allowed}")
    if key in SETTING_VALIDATORS and not SETTING_VALIDATORS[key][0](value):
        raise ValueError(SETTING_VALIDATORS[key][1])
    row = db.get(AppSetting, key) or AppSetting(key=key)
    now = utcnow()
    row.value_json = value
    row.updated_at = now
    row.effective_at = now
    db.add(row)


def all_settings(db: Session, keys: tuple[str, ...] = USER_EDITABLE_KEYS) -> dict[str, Any]:
    return {k: get_setting(db, k) for k in keys}


def is_configured(db: Session) -> bool:
    return all(get_setting(db, k) for k in SETUP_KEYS)
