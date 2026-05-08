"""
Token Encryption
================
AES-256 (Fernet) encryption for OAuth tokens stored in PostgreSQL.
Key is derived from SECRET_KEY env var — never stored in DB.

Usage:
    encrypted = encrypt_token("ya29.access_token_here")
    plaintext = decrypt_token(encrypted)
"""

import base64
import hashlib
import logging
import os

logger = logging.getLogger(__name__)

_fernet = None


def _get_fernet():
    global _fernet
    if _fernet is None:
        try:
            from cryptography.fernet import Fernet
            secret = os.getenv("SECRET_KEY", "fallback-insecure-key-change-me")
            # Derive a 32-byte key from SECRET_KEY using SHA-256
            key_bytes = hashlib.sha256(secret.encode()).digest()
            fernet_key = base64.urlsafe_b64encode(key_bytes)
            _fernet = Fernet(fernet_key)
        except ImportError:
            logger.warning("[Crypto] cryptography package not installed — tokens stored as plaintext")
            _fernet = None
    return _fernet


def encrypt_token(plaintext: str) -> str:
    """Encrypt a token string. Returns base64-encoded ciphertext."""
    if not plaintext:
        return ""
    f = _get_fernet()
    if f is None:
        return plaintext  # fallback: no encryption
    try:
        return f.encrypt(plaintext.encode()).decode()
    except Exception as exc:
        logger.error(f"[Crypto] Encryption failed: {exc}")
        return plaintext


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a token string. Returns plaintext."""
    if not ciphertext:
        return ""
    f = _get_fernet()
    if f is None:
        return ciphertext  # fallback: no encryption
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except Exception:
        # Token may already be plaintext (migration case)
        return ciphertext
