import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings


def _key_bytes() -> bytes:
    raw = get_settings().app_secret_key
    try:
        decoded = base64.b64decode(raw, validate=True)
        if len(decoded) == 32:
            return decoded
    except Exception:
        pass
    return hashlib.sha256(raw.encode("utf-8")).digest()


def encrypt_secret(value: str | None) -> str | None:
    if value is None:
        return None
    nonce = os.urandom(12)
    ciphertext = AESGCM(_key_bytes()).encrypt(nonce, value.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_secret(value: str | None) -> str | None:
    if value is None:
        return None
    raw = base64.urlsafe_b64decode(value.encode("ascii"))
    nonce, ciphertext = raw[:12], raw[12:]
    return AESGCM(_key_bytes()).decrypt(nonce, ciphertext, None).decode("utf-8")

