import base64
import urllib.parse
from base64 import urlsafe_b64encode, urlsafe_b64decode

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# http://localhost:3000/sharekhan/callback?request_token=SexGPGQIjxskhdaUrxNeJ9yUB4G8iRiYfUibOYgpaXYAlFsE2vz5QIiX4hm7NX5mxJdkJHR0AqU=&state=59823656
REQUEST_TOKEN = "SexGPGQIjxskhdaUrxNeJ9yUB4G8iRiYfUibOYgpaXYAlFsE2vz5QIiX4hm7NX5mxJdkJHR0AqU"
SECRET_KEY = "Auvc2BnEPuOaKBWoXCmTkPF9dvJHVzg1"


def add_padding(s: str) -> bytes:
    b = s.encode("utf-8")
    return b + b"=" * ((4 - len(b) % 4) % 4)


def decrypt_request_token(request_token: str, secret_key: str) -> str:
    key = secret_key.encode("utf-8")
    iv = base64.b64decode("AAAAAAAAAAAAAAAAAAAAAA==")

    request_token = urllib.parse.unquote(request_token.strip()).replace(" ", "+")

    encrypted = urlsafe_b64decode(add_padding(request_token))

    ciphertext = encrypted[:-16]
    tag = encrypted[-16:]

    decryptor = Cipher(
        algorithms.AES(key),
        modes.GCM(iv, tag, 16),
        default_backend()
    ).decryptor()

    decrypted = decryptor.update(ciphertext) + decryptor.finalize()

    return decrypted.decode("utf-8")


def encrypt_final_token(plain_text: str, secret_key: str) -> str:
    key = secret_key.encode("utf-8")
    iv = base64.b64decode("AAAAAAAAAAAAAAAAAAAAAA==")

    encryptor = Cipher(
        algorithms.AES(key),
        modes.GCM(iv, None, 16),
        default_backend()
    ).encryptor()

    raw = plain_text.encode("utf-8")

    ciphertext = encryptor.update(raw) + encryptor.finalize()
    final_bytes = ciphertext + encryptor.tag

    return urlsafe_b64encode(final_bytes).rstrip(b"=").decode("utf-8")


decrypted = decrypt_request_token(REQUEST_TOKEN, SECRET_KEY)
print("Decrypted:", decrypted)

request_id, customer_id = decrypted.split("|")

swapped = f"{customer_id}|{request_id}"
print("Swapped:", swapped)

final_token = encrypt_final_token(swapped, SECRET_KEY)
print("Final encrypted token:", final_token)