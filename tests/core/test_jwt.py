"""Tests for JWT security module."""
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest

from src.core.security.jwt import (
    TokenData,
    create_access_token,
    create_refresh_token,
    create_token_pair,
    decode_token,
    hash_password,
    verify_password,
)


class TestHashPassword:
    """Tests for hash_password function."""

    def test_hash_password_returns_string(self):
        """Should return a hashed string."""
        password = "my_secure_password"
        hashed = hash_password(password)

        assert isinstance(hashed, str)
        assert hashed != password

    def test_hash_password_different_for_same_input(self):
        """Should return different hashes for same password (due to salt)."""
        password = "my_secure_password"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        # Bcrypt uses random salt, so hashes should be different
        assert hash1 != hash2

    def test_hash_password_starts_with_bcrypt_prefix(self):
        """Hashed password should start with bcrypt identifier."""
        password = "test_password"
        hashed = hash_password(password)

        # Bcrypt hashes start with $2b$ or $2a$
        assert hashed.startswith("$2")


class TestVerifyPassword:
    """Tests for verify_password function."""

    def test_verify_correct_password(self):
        """Should return True for correct password."""
        password = "correct_password"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_incorrect_password(self):
        """Should return False for incorrect password."""
        password = "correct_password"
        hashed = hash_password(password)

        assert verify_password("wrong_password", hashed) is False

    def test_verify_empty_password(self):
        """Should handle empty password correctly."""
        password = ""
        hashed = hash_password(password)

        assert verify_password("", hashed) is True
        assert verify_password("non_empty", hashed) is False

    def test_verify_password_case_sensitive(self):
        """Password verification should be case sensitive."""
        password = "CaseSensitive"
        hashed = hash_password(password)

        assert verify_password("CaseSensitive", hashed) is True
        assert verify_password("casesensitive", hashed) is False
        assert verify_password("CASESENSITIVE", hashed) is False


class TestCreateAccessToken:
    """Tests for create_access_token function."""

    def test_create_access_token_returns_string(self):
        """Should return a JWT token string."""
        user_id = str(uuid.uuid4())
        token = create_access_token(user_id)

        assert isinstance(token, str)
        # JWT tokens have 3 parts separated by dots
        assert len(token.split(".")) == 3

    def test_create_access_token_decodable(self):
        """Created token should be decodable."""
        user_id = str(uuid.uuid4())
        token = create_access_token(user_id)

        decoded = decode_token(token, is_refresh=False)

        assert decoded is not None
        assert decoded.user_id == user_id
        assert decoded.token_type == "access"

    def test_create_access_token_with_custom_expiry(self):
        """Should accept custom expiry time."""
        user_id = str(uuid.uuid4())
        token = create_access_token(user_id, expires_delta=timedelta(hours=1))

        decoded = decode_token(token, is_refresh=False)

        assert decoded is not None
        assert decoded.user_id == user_id

    def test_access_token_has_correct_type(self):
        """Access token should have type 'access'."""
        user_id = str(uuid.uuid4())
        token = create_access_token(user_id)

        decoded = decode_token(token, is_refresh=False)

        assert decoded.token_type == "access"


class TestCreateRefreshToken:
    """Tests for create_refresh_token function."""

    def test_create_refresh_token_returns_string(self):
        """Should return a JWT token string."""
        user_id = str(uuid.uuid4())
        token = create_refresh_token(user_id)

        assert isinstance(token, str)
        assert len(token.split(".")) == 3

    def test_create_refresh_token_decodable(self):
        """Created refresh token should be decodable with is_refresh=True."""
        user_id = str(uuid.uuid4())
        token = create_refresh_token(user_id)

        decoded = decode_token(token, is_refresh=True)

        assert decoded is not None
        assert decoded.user_id == user_id
        assert decoded.token_type == "refresh"

    def test_refresh_token_not_valid_as_access(self):
        """Refresh token should not be valid when decoded as access token."""
        user_id = str(uuid.uuid4())
        token = create_refresh_token(user_id)

        # Should fail when decoded as access token (wrong secret + wrong type)
        decoded = decode_token(token, is_refresh=False)

        assert decoded is None


class TestDecodeToken:
    """Tests for decode_token function."""

    def test_decode_valid_access_token(self):
        """Should decode a valid access token."""
        user_id = str(uuid.uuid4())
        token = create_access_token(user_id)

        decoded = decode_token(token, is_refresh=False)

        assert decoded is not None
        assert decoded.user_id == user_id
        assert decoded.token_type == "access"

    def test_decode_valid_refresh_token(self):
        """Should decode a valid refresh token."""
        user_id = str(uuid.uuid4())
        token = create_refresh_token(user_id)

        decoded = decode_token(token, is_refresh=True)

        assert decoded is not None
        assert decoded.user_id == user_id
        assert decoded.token_type == "refresh"

    def test_decode_invalid_token(self):
        """Should return None for invalid token."""
        decoded = decode_token("invalid.token.here", is_refresh=False)

        assert decoded is None

    def test_decode_tampered_token(self):
        """Should return None for tampered token."""
        user_id = str(uuid.uuid4())
        token = create_access_token(user_id)

        # Tamper with the token
        parts = token.split(".")
        parts[1] = parts[1] + "tampered"
        tampered_token = ".".join(parts)

        decoded = decode_token(tampered_token, is_refresh=False)

        assert decoded is None

    def test_decode_access_token_as_refresh_fails(self):
        """Access token should fail when decoded as refresh token."""
        user_id = str(uuid.uuid4())
        token = create_access_token(user_id)

        decoded = decode_token(token, is_refresh=True)

        assert decoded is None

    def test_decode_expired_token(self):
        """Should return None for expired token."""
        user_id = str(uuid.uuid4())
        # Create token that expires immediately (negative delta)
        token = create_access_token(user_id, expires_delta=timedelta(seconds=-1))

        decoded = decode_token(token, is_refresh=False)

        assert decoded is None


class TestCreateTokenPair:
    """Tests for create_token_pair function."""

    def test_create_token_pair_returns_tuple(self):
        """Should return a tuple of (access_token, refresh_token)."""
        user_id = str(uuid.uuid4())
        result = create_token_pair(user_id)

        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_create_token_pair_both_valid(self):
        """Both tokens in pair should be valid."""
        user_id = str(uuid.uuid4())
        access_token, refresh_token = create_token_pair(user_id)

        access_decoded = decode_token(access_token, is_refresh=False)
        refresh_decoded = decode_token(refresh_token, is_refresh=True)

        assert access_decoded is not None
        assert access_decoded.user_id == user_id
        assert access_decoded.token_type == "access"

        assert refresh_decoded is not None
        assert refresh_decoded.user_id == user_id
        assert refresh_decoded.token_type == "refresh"

    def test_create_token_pair_tokens_are_different(self):
        """Access and refresh tokens should be different."""
        user_id = str(uuid.uuid4())
        access_token, refresh_token = create_token_pair(user_id)

        assert access_token != refresh_token
