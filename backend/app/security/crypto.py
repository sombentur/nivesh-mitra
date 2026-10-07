"""Encryption for secrets at rest.

The Fernet master key is created on first use and kept in Windows Credential Manager
(via `keyring`), so the database file alone is useless to anyone who copies it.
"""

import hashlib
import secrets
from functools import lru_cache

import keyring
from cryptography.fernet import Fernet

from app.config import get_config

KEYRING_SERVICE = "NiveshMitra"
KEYRING_USER = "master-key"


@lru_cache
def _fernet() -> Fernet:
    override = get_config().master_key_override
    if override:
        return Fernet(override.encode())
    key = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
    if not key:
        key = Fernet.generate_key().decode()
        keyring.set_password(KEYRING_SERVICE, KEYRING_USER, key)
    return Fernet(key.encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
