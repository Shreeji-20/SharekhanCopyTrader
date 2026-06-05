import base64
import urllib.parse
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


ZERO_IV = base64.b64decode("AAAAAAAAAAAAAAAAAAAAAA==")
GCM_TAG_LENGTH = 16


class SharekhanTokenError(ValueError):
    pass


@dataclass(frozen=True)
class ConvertedRequestToken:
    final_encrypted_token: str
    request_key: str
    customer_id: str


def _add_base64_padding(value: str) -> bytes:
    raw = value.encode("utf-8")
    return raw + b"=" * ((4 - len(raw) % 4) % 4)


def _clean_request_token(request_token: str) -> str:
    return urllib.parse.unquote(request_token.strip()).replace(" ", "+")


def _validate_secret_key(secret_key: str) -> bytes:
    if not secret_key:
        raise SharekhanTokenError("Sharekhan Secure Key is missing")
    key = secret_key.encode("utf-8")
    if len(key) not in {16, 24, 32}:
        raise SharekhanTokenError("Sharekhan Secure Key must be a 16, 24, or 32 byte AES key")
    return key


def decrypt_request_token(request_token: str, secret_key: str) -> str:
    if not request_token:
        raise SharekhanTokenError("Sharekhan request token is missing")

    key = _validate_secret_key(secret_key)
    try:
        encrypted = urlsafe_b64decode(_add_base64_padding(_clean_request_token(request_token)))
        ciphertext = encrypted[:-GCM_TAG_LENGTH]
        tag = encrypted[-GCM_TAG_LENGTH:]
        if not ciphertext or len(tag) != GCM_TAG_LENGTH:
            raise SharekhanTokenError("Sharekhan request token has an invalid encrypted payload")

        decryptor = Cipher(
            algorithms.AES(key),
            modes.GCM(ZERO_IV, tag, GCM_TAG_LENGTH),
            default_backend(),
        ).decryptor()
        return (decryptor.update(ciphertext) + decryptor.finalize()).decode("utf-8")
    except SharekhanTokenError:
        raise
    except Exception as exc:
        raise SharekhanTokenError("Sharekhan request token could not be decrypted with the stored Secure Key") from exc


def encrypt_final_token(plain_text: str, secret_key: str) -> str:
    key = _validate_secret_key(secret_key)
    try:
        encryptor = Cipher(
            algorithms.AES(key),
            modes.GCM(ZERO_IV, None, GCM_TAG_LENGTH),
            default_backend(),
        ).encryptor()
        ciphertext = encryptor.update(plain_text.encode("utf-8")) + encryptor.finalize()
        return urlsafe_b64encode(ciphertext + encryptor.tag).rstrip(b"=").decode("utf-8")
    except Exception as exc:
        raise SharekhanTokenError("Sharekhan final encrypted token could not be generated") from exc


def convert_request_token_for_access_token(request_token: str, secret_key: str) -> ConvertedRequestToken:
    decrypted = decrypt_request_token(request_token, secret_key)
    parts = decrypted.split("|")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise SharekhanTokenError("Sharekhan decrypted request token did not contain key and customer ID")

    request_key, customer_id = parts
    final_encrypted_token = encrypt_final_token(f"{customer_id}|{request_key}", secret_key)
    return ConvertedRequestToken(
        final_encrypted_token=final_encrypted_token,
        request_key=request_key,
        customer_id=customer_id,
    )
