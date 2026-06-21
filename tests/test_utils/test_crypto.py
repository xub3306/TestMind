"""Tests for the secret encryption module (testmind.utils.crypto)."""

from __future__ import annotations

import os

import pytest

from testmind.utils.crypto import (
    CryptoError,
    ENCRYPTED_PREFIX,
    MASTER_KEY_ENV,
    decrypt,
    decrypt_dict,
    decrypt_value,
    encrypt,
    generate_key,
    get_key,
    is_encrypted,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def with_master_key(monkeypatch):
    """Provide a freshly generated master key in the env for one test."""
    key = generate_key()
    monkeypatch.setenv(MASTER_KEY_ENV, key)
    yield key


@pytest.fixture()
def without_master_key(monkeypatch):
    """Ensure TESTMIND_MASTER_KEY is unset."""
    monkeypatch.delenv(MASTER_KEY_ENV, raising=False)


# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------


class TestKeyManagement:
    def test_generate_key_returns_string(self):
        key = generate_key()
        assert isinstance(key, str)
        assert len(key) > 20

    def test_generate_key_unique(self):
        assert generate_key() != generate_key()

    def test_get_key_missing_raises(self, without_master_key):
        with pytest.raises(CryptoError, match=MASTER_KEY_ENV):
            get_key()

    def test_get_key_present(self, with_master_key):
        assert get_key() == with_master_key


# ---------------------------------------------------------------------------
# Encrypt / decrypt round-trip
# ---------------------------------------------------------------------------


class TestEncryptDecrypt:
    def test_roundtrip(self, with_master_key):
        cipher = encrypt("my-secret-token")
        assert cipher.startswith(ENCRYPTED_PREFIX)
        assert decrypt(cipher) == "my-secret-token"

    def test_encrypt_without_key_raises(self, without_master_key):
        with pytest.raises(CryptoError):
            encrypt("x")

    def test_decrypt_without_key_raises(self, without_master_key):
        with pytest.raises(CryptoError):
            decrypt("enc:something")

    def test_decrypt_non_encrypted_raises(self, with_master_key):
        with pytest.raises(CryptoError, match="not encrypted"):
            decrypt("plain-value")

    def test_decrypt_invalid_token_raises(self, with_master_key):
        with pytest.raises(CryptoError, match="Decryption failed"):
            decrypt("enc:not-a-valid-token")

    def test_wrong_key_fails(self, with_master_key, monkeypatch):
        cipher = encrypt("secret")
        # Switch to a different key.
        monkeypatch.setenv(MASTER_KEY_ENV, generate_key())
        with pytest.raises(CryptoError):
            decrypt(cipher)

    def test_unicode_roundtrip(self, with_master_key):
        cipher = encrypt("token-with-unicode-αβγ-中文")
        assert decrypt(cipher) == "token-with-unicode-αβγ-中文"

    def test_empty_string(self, with_master_key):
        cipher = encrypt("")
        assert decrypt(cipher) == ""


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------


class TestIsEncrypted:
    def test_detects_prefix(self):
        assert is_encrypted("enc:abc123") is True

    def test_rejects_plain(self):
        assert is_encrypted("plain") is False

    def test_rejects_non_string(self):
        assert is_encrypted(None) is False
        assert is_encrypted(42) is False
        assert is_encrypted(["enc:x"]) is False


class TestDecryptValue:
    def test_decrypts_encrypted(self, with_master_key):
        cipher = encrypt("hello")
        assert decrypt_value(cipher) == "hello"

    def test_passes_through_plain(self, with_master_key):
        assert decrypt_value("plain") == "plain"

    def test_passes_through_non_string(self, with_master_key):
        assert decrypt_value(42) == 42
        assert decrypt_value(None) is None


# ---------------------------------------------------------------------------
# dict / nested decryption
# ---------------------------------------------------------------------------


class TestDecryptDict:
    def test_shallow_dict(self, with_master_key):
        cipher = encrypt("secret")
        data = {"token": cipher, "name": "plain", "count": 42}
        out = decrypt_dict(data)
        assert out["token"] == "secret"
        assert out["name"] == "plain"
        assert out["count"] == 42

    def test_nested_dict(self, with_master_key):
        cipher = encrypt("nested-secret")
        data = {"auth": {"token": cipher}, "variables": {"api_key": encrypt("k")}}
        out = decrypt_dict(data)
        assert out["auth"]["token"] == "nested-secret"
        assert out["variables"]["api_key"] == "k"

    def test_list_of_encrypted(self, with_master_key):
        data = {"keys": [encrypt("a"), encrypt("b"), "plain"]}
        out = decrypt_dict(data)
        assert out["keys"] == ["a", "b", "plain"]

    def test_no_encrypted_values_passes_through(self, with_master_key):
        data = {"a": 1, "b": "plain", "c": [1, 2]}
        out = decrypt_dict(data)
        assert out == data

    def test_non_dict_input_returns_unchanged(self, with_master_key):
        assert decrypt_dict("string") == "string"
        assert decrypt_dict(42) == 42
