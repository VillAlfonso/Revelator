"""Encryption helpers for user-supplied AI API keys."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from .config import API_KEY_ENCRYPTION_KEY

_PREFIX = "enc:v1:"
_FERNET = Fernet(base64.urlsafe_b64encode(hashlib.sha256(API_KEY_ENCRYPTION_KEY.encode("utf-8")).digest()))


def encrypt_api_key(value: str | None) -> str | None:
    if value is None or value.startswith(_PREFIX):
        return value
    token = _FERNET.encrypt(value.encode("utf-8")).decode("ascii")
    return f"{_PREFIX}{token}"


def decrypt_api_key(value: str | None) -> str | None:
    if value is None or not value.startswith(_PREFIX):
        return value
    try:
        return _FERNET.decrypt(value[len(_PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise ValueError("Stored API key could not be decrypted. Verify API_KEY_ENCRYPTION_KEY.") from exc
