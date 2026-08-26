"""Tests for SimpleAuthService.is_default_password() -- promoted from a
dead private helper (_is_default_password, never called anywhere) to a
public check wired into the dashboard's default-password warning banner.
"""

import hashlib
from unittest.mock import patch

import bcrypt

from src.services.settings_service import SettingsService
from src.services.simple_auth_service import SimpleAuthService


class TestIsDefaultPasswordBcrypt:
    def test_default_bcrypt_password_is_detected(self):
        stored_hash = bcrypt.hashpw(b"mvidarr", bcrypt.gensalt()).decode()
        with patch.object(SettingsService, "get", return_value=stored_hash):
            assert SimpleAuthService.is_default_password() is True

    def test_changed_bcrypt_password_is_not_flagged(self):
        stored_hash = bcrypt.hashpw(b"a-real-password", bcrypt.gensalt()).decode()
        with patch.object(SettingsService, "get", return_value=stored_hash):
            assert SimpleAuthService.is_default_password() is False


class TestIsDefaultPasswordSha256Legacy:
    def test_default_sha256_password_is_detected(self):
        stored_hash = hashlib.sha256(b"mvidarr").hexdigest()
        with patch.object(SettingsService, "get", return_value=stored_hash):
            assert SimpleAuthService.is_default_password() is True

    def test_changed_sha256_password_is_not_flagged(self):
        stored_hash = hashlib.sha256(b"a-real-password").hexdigest()
        with patch.object(SettingsService, "get", return_value=stored_hash):
            assert SimpleAuthService.is_default_password() is False


class TestIsDefaultPasswordFailSafe:
    def test_no_stored_credential_is_treated_as_default(self):
        # Fresh install, credentials not yet initialized -- treat as
        # default rather than silently assuming it's safe.
        with patch.object(SettingsService, "get", return_value=None):
            assert SimpleAuthService.is_default_password() is True

    def test_lookup_error_fails_safe_to_default(self):
        with patch.object(SettingsService, "get", side_effect=RuntimeError("db down")):
            assert SimpleAuthService.is_default_password() is True

    def test_unrecognized_hash_format_fails_safe_to_default(self):
        with patch.object(SettingsService, "get", return_value="not-a-real-hash"):
            assert SimpleAuthService.is_default_password() is True
