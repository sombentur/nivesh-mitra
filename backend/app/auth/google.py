"""Verify a Google Sign-In ID token (the `credential` returned by Google Identity Services)."""

from dataclasses import dataclass

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token


class GoogleAuthError(Exception):
    pass


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    name: str | None


def verify_google_credential(credential: str, client_id: str) -> GoogleIdentity:
    try:
        info = id_token.verify_oauth2_token(credential, google_requests.Request(), client_id)
    except ValueError as exc:  # bad signature, wrong audience, expired, wrong issuer
        raise GoogleAuthError(str(exc)) from exc
    if not info.get("email_verified"):
        raise GoogleAuthError("Google email is not verified")
    return GoogleIdentity(sub=info["sub"], email=info["email"].lower(), name=info.get("name"))
