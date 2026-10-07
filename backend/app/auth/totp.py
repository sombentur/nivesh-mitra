"""Second factor: 6-digit codes from an authenticator app (Google Authenticator, Microsoft Authenticator, …)."""

import pyotp
import segno

ISSUER = "NiveshMitra"


def new_totp_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER)


def qr_svg(uri: str) -> str:
    return segno.make(uri, error="m").svg_inline(scale=5, dark="#111827", light="#ffffff")


def verify_code(secret: str, code: str) -> bool:
    code = code.strip().replace(" ", "")
    if not (code.isdigit() and len(code) == 6):
        return False
    # valid_window=1 tolerates a PC clock that is up to 30 s off
    return pyotp.TOTP(secret).verify(code, valid_window=1)
