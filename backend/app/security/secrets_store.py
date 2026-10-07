"""Encrypted store for API keys. Values go in, but only a masked status ever comes back out over the API."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import Secret
from app.security.crypto import decrypt, encrypt


@dataclass(frozen=True)
class SecretSpec:
    name: str
    label: str
    help: str


# The only secrets the app accepts. You type these into Settings yourself.
KNOWN_SECRETS: dict[str, SecretSpec] = {
    s.name: s
    for s in [
        SecretSpec(
            "groww_totp_token",
            "Groww API key (TOTP token)",
            "groww.in/trade-api/api-keys → Generate TOTP token → copy the token.",
        ),
        SecretSpec(
            "groww_totp_secret",
            "Groww TOTP secret",
            "Shown next to the TOTP token (the text under the QR code). Lets the app renew its daily login by itself.",
        ),
        SecretSpec(
            "trendlyne_mcp_url",
            "Trendlyne MCP server URL",
            "The personal server URL Trendlyne gave you with your MCP subscription.",
        ),
        SecretSpec("eodhd_api_key", "EODHD API key", "Optional alternative fundamentals vendor."),
        SecretSpec(
            "anthropic_api_key",
            "Claude API key",
            "console.anthropic.com → API keys. Used only to reword explanations in simple language.",
        ),
        SecretSpec(
            "anthropic_workspace_id",
            "Claude workspace ID (only if your key needs it)",
            "Needed only when your Claude key wasn't created inside a workspace. console.anthropic.com → Settings → "
            "Workspaces → open the workspace: its ID starts with wrkspc_. Or simply create the key inside a workspace.",
        ),
    ]
}


@dataclass(frozen=True)
class SecretStatus:
    name: str
    label: str
    help: str
    is_set: bool
    last4: str | None
    updated_at: datetime | None


def set_secret(db: Session, name: str, value: str) -> None:
    if name not in KNOWN_SECRETS:
        raise KeyError(name)
    value = value.strip()
    if not value:
        raise ValueError("empty secret")
    row = db.get(Secret, name) or Secret(name=name)
    row.ciphertext = encrypt(value)
    row.last4 = value[-4:]
    row.updated_at = utcnow()
    db.add(row)


def get_secret(db: Session, name: str) -> str | None:
    """Backend-internal use only (connectors). Never return this from an API route."""
    row = db.get(Secret, name)
    return decrypt(row.ciphertext) if row else None


def delete_secret(db: Session, name: str) -> None:
    row = db.get(Secret, name)
    if row:
        db.delete(row)


def list_status(db: Session) -> list[SecretStatus]:
    out = []
    for spec in KNOWN_SECRETS.values():
        row = db.get(Secret, spec.name)
        out.append(
            SecretStatus(
                name=spec.name,
                label=spec.label,
                help=spec.help,
                is_set=row is not None,
                last4=row.last4 if row else None,
                updated_at=row.updated_at if row else None,
            )
        )
    return out
