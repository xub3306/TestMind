"""Lightweight secret encryption for TestMind project configurations.

Provides a symmetric encryption layer so that sensitive values (tokens,
passwords, API keys) can be stored encrypted inside project files rather
than only being injectable via environment variables.  This is handy
for CI/CD setups where pre-setting env vars is awkward, and for sharing
project configs without leaking plaintext secrets.

Design:

* **Master key** — a Fernet symmetric key, sourced from the
  ``TESTMIND_MASTER_KEY`` environment variable.  When the env var is
  unset, callers can generate a new key via :func:`generate_key` and
  persist it themselves.  The key is never written to disk by this
  module.
* **Encrypted value format** — ``enc:<base64-token>``.  The ``enc:``
  prefix lets config loaders transparently detect and decrypt values
  without extra metadata fields.
* **No new required deps** — uses ``cryptography.fernet.Fernet``, which
  is already installed in this environment.  When ``cryptography`` is
  absent, :func:`encrypt` / :func:`decrypt` raise a clear
  ``ImportError`` so the rest of TestMind keeps working.

Usage::

    from testmind.utils.crypto import encrypt, decrypt, is_encrypted

    cipher = encrypt("my-secret-token")  # needs TESTMIND_MASTER_KEY
    assert is_encrypted(cipher)          # True, starts with "enc:"
    plain = decrypt(cipher)              # "my-secret-token"
"""

from __future__ import annotations

import base64
import os
from typing import Final

__all__ = [
    "ENCRYPTED_PREFIX",
    "MASTER_KEY_ENV",
    "generate_key",
    "get_key",
    "encrypt",
    "decrypt",
    "is_encrypted",
    "decrypt_value",
    "decrypt_dict",
    "CryptoError",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ENCRYPTED_PREFIX: Final[str] = "enc:"
MASTER_KEY_ENV: Final[str] = "TESTMIND_MASTER_KEY"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CryptoError(Exception):
    """Raised on encryption/decryption failures (missing key, bad token)."""


# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------


def generate_key() -> str:
    """Generate a new Fernet master key and return it as a UTF-8 string.

    The caller is responsible for persisting the key (typically by
    exporting it as the ``TESTMIND_MASTER_KEY`` environment variable).
    This function does **not** write anything to disk.
    """
    try:
        from cryptography.fernet import Fernet
    except ImportError as e:
        raise CryptoError(
            "The 'cryptography' package is required for secret encryption. "
            "Install it with: pip install cryptography"
        ) from e
    return Fernet.generate_key().decode("utf-8")


def get_key() -> str:
    """Return the master key from the ``TESTMIND_MASTER_KEY`` env var.

    Raises:
        CryptoError: If the env var is not set.
    """
    key = os.environ.get(MASTER_KEY_ENV)
    if not key:
        raise CryptoError(
            f"No master key found. Set the {MASTER_KEY_ENV} environment "
            f"variable to a Fernet key (generate one with "
            f"'testmind crypto gen-key')."
        )
    return key


def _fernet():
    """Build a Fernet cipher from the current master key."""
    try:
        from cryptography.fernet import Fernet
    except ImportError as e:
        raise CryptoError(
            "The 'cryptography' package is required for secret encryption. "
            "Install it with: pip install cryptography"
        ) from e
    return Fernet(get_key().encode("utf-8"))


# ---------------------------------------------------------------------------
# Encrypt / decrypt
# ---------------------------------------------------------------------------


def encrypt(plaintext: str) -> str:
    """Encrypt *plaintext* and return a ``enc:<token>`` string.

    The master key is read from :data:`MASTER_KEY_ENV`.

    Args:
        plaintext: The secret value to encrypt.

    Returns:
        A string prefixed with ``enc:`` followed by the base64 Fernet
        token.

    Raises:
        CryptoError: If the master key is missing or ``cryptography``
            is not installed.
    """
    if not isinstance(plaintext, str):
        raise TypeError("plaintext must be a str")
    token = _fernet().encrypt(plaintext.encode("utf-8"))
    return ENCRYPTED_PREFIX + token.decode("utf-8")


def decrypt(cipher_value: str) -> str:
    """Decrypt an ``enc:<token>`` string back to the original plaintext.

    Args:
        cipher_value: A string produced by :func:`encrypt` (must start
            with ``enc:``).

    Returns:
        The decrypted plaintext.

    Raises:
        CryptoError: If the value is not encrypted, the master key is
            missing, or the token is invalid.
    """
    if not is_encrypted(cipher_value):
        raise CryptoError(f"Value is not encrypted (missing '{ENCRYPTED_PREFIX}' prefix)")
    token = cipher_value[len(ENCRYPTED_PREFIX) :].encode("utf-8")
    try:
        plaintext = _fernet().decrypt(token)
    except Exception as e:
        raise CryptoError(f"Decryption failed: {e}") from e
    return plaintext.decode("utf-8")


def is_encrypted(value: str) -> bool:
    """Return True if *value* starts with the ``enc:`` prefix."""
    return isinstance(value, str) and value.startswith(ENCRYPTED_PREFIX)


# ---------------------------------------------------------------------------
# Transparent decryption helpers
# ---------------------------------------------------------------------------


def decrypt_value(value):
    """Decrypt *value* if it is an encrypted string, otherwise return as-is.

    This is the main entry point for config loaders: pass any config
    value through this function and encrypted values are transparently
    decrypted while plain values pass through unchanged.
    """
    if is_encrypted(value):
        return decrypt(value)
    return value


def decrypt_dict(data: dict) -> dict:
    """Return a shallow copy of *data* with encrypted string values decrypted.

    Nested dicts and lists are recursed into so that secrets buried
    inside ``variables`` / ``headers`` / ``params`` are all resolved.
    """
    if not isinstance(data, dict):
        return data
    result: dict = {}
    for k, v in data.items():
        result[k] = _decrypt_recursive(v)
    return result


def _decrypt_recursive(value):
    if is_encrypted(value):
        return decrypt(value)
    if isinstance(value, dict):
        return {k: _decrypt_recursive(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decrypt_recursive(item) for item in value]
    return value


# ---------------------------------------------------------------------------
# Base64 helpers (used by CLI for key display)
# ---------------------------------------------------------------------------


def encode_key_for_display(key: str) -> str:
    """Return *key* as-is (already base64 URL-safe from Fernet)."""
    return key


def decode_key_from_input(raw: str) -> str:
    """Trim whitespace from a user-supplied key string."""
    return raw.strip()
