"""EDAPT v2 — symmetric encryption for secrets stored in the database.

Used for AIProviderConfig.encrypted_api_key: a third-party AI provider API
key is a genuine secret this app sends on the wire on the admin's behalf,
unlike e.g. an OAuth client_id (a public identifier) — so unlike
OAuthProviderConfig, it must never be stored or returned in plaintext.

Key derivation: Fernet needs a 32-byte urlsafe-base64 key. We derive one
from the app's existing SECRET_KEY (already required, already used for JWT
signing) via SHA-256 rather than requiring a second secret to configure —
one less thing to lose track of in a deployment's env vars. This means
rotating SECRET_KEY also invalidates every previously-encrypted API key
(they'll fail to decrypt and the admin will need to re-enter it) — an
accepted tradeoff for not managing a separate encryption key.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


def _fernet_for(secret_key: str) -> Fernet:
    derived = hashlib.sha256(secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_secret(plaintext: str, secret_key: str) -> str:
    return _fernet_for(secret_key).encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str, secret_key: str) -> str | None:
    """Returns None (rather than raising) on a key rotation / corrupt value
    — callers must treat that as "no usable key configured", not crash."""
    try:
        return _fernet_for(secret_key).decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError):
        return None
