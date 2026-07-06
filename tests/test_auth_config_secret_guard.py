"""Regression tests for the fail-closed JWT/magic-link signing-secret guard.

Defect (low, security): JWT_SECRET_KEY / MAGIC_LINK_SECRET_KEY previously
defaulted to "" with no startup guard, so a single missing env var in a deploy
silently downgraded to an HS256 key over the empty string — trivially forgeable
by an attacker. The guard must fail closed (raise) on an empty/short secret in
any real deploy, while still allowing a deterministic non-empty dev placeholder
for local development and the test suite.
"""

from __future__ import annotations

import sys

import pytest

from src.api.auth import config


class TestSigningSecretGuard:
    def test_empty_secret_fails_closed_when_insecure_not_allowed(self, monkeypatch):
        """An empty secret must raise (not silently return "") outside dev/test."""
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
        monkeypatch.delenv("ONDOWAY_ALLOW_INSECURE_AUTH_SECRETS", raising=False)
        # Force _allow_insecure_secrets() to return False by hiding pytest from
        # the module's view of sys.modules (restored automatically after test).
        monkeypatch.delitem(sys.modules, "pytest", raising=False)

        with pytest.raises(RuntimeError, match="trivially-forgeable"):
            config._load_signing_secret("JWT_SECRET_KEY")

    def test_short_secret_fails_closed(self, monkeypatch):
        """A too-short secret is as dangerous as empty and must also raise."""
        monkeypatch.setenv("JWT_SECRET_KEY", "short")
        monkeypatch.delenv("ONDOWAY_ALLOW_INSECURE_AUTH_SECRETS", raising=False)
        monkeypatch.delitem(sys.modules, "pytest", raising=False)

        with pytest.raises(RuntimeError):
            config._load_signing_secret("JWT_SECRET_KEY")

    def test_never_returns_empty_string(self, monkeypatch):
        """Even with the dev escape hatch, the secret is never the empty string."""
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
        monkeypatch.setenv("ONDOWAY_ALLOW_INSECURE_AUTH_SECRETS", "1")

        result = config._load_signing_secret("JWT_SECRET_KEY")
        assert result != ""
        assert len(result) >= config._MIN_SECRET_LEN

    def test_strong_secret_is_used_verbatim(self, monkeypatch):
        """A real, long secret is honored as-is (production path)."""
        strong = "x" * config._MIN_SECRET_LEN
        monkeypatch.setenv("JWT_SECRET_KEY", strong)
        monkeypatch.delenv("ONDOWAY_ALLOW_INSECURE_AUTH_SECRETS", raising=False)

        assert config._load_signing_secret("JWT_SECRET_KEY") == strong

    def test_module_level_secrets_are_non_empty(self):
        """The imported module constants must never be the empty string."""
        assert config.JWT_SECRET_KEY != ""
        assert config.MAGIC_LINK_SECRET_KEY != ""
