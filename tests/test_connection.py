"""Unit tests for src/connection.py — Neo4j connection management.

All Neo4j interactions are mocked. No running database required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.connection import (
    Neo4jConnectionError,
    _read_env,
    abort_on_connection_error,
    create_driver,
    get_driver,
)

# ── _read_env ──


class TestReadEnv:
    def test_all_present(self, monkeypatch):
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "secret")
        uri, user, pw = _read_env()
        assert uri == "bolt://localhost:7687"
        assert user == "neo4j"
        assert pw == "secret"

    def test_missing_uri(self, monkeypatch):
        monkeypatch.delenv("NEO4J_URI", raising=False)
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "secret")
        with pytest.raises(Neo4jConnectionError, match="NEO4J_URI"):
            _read_env()

    def test_missing_all(self, monkeypatch):
        monkeypatch.delenv("NEO4J_URI", raising=False)
        monkeypatch.delenv("NEO4J_USER", raising=False)
        monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
        with pytest.raises(Neo4jConnectionError) as exc_info:
            _read_env()
        msg = str(exc_info.value)
        assert "NEO4J_URI" in msg
        assert "NEO4J_USER" in msg
        assert "NEO4J_PASSWORD" in msg

    def test_empty_string_treated_as_missing(self, monkeypatch):
        monkeypatch.setenv("NEO4J_URI", "")
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "secret")
        with pytest.raises(Neo4jConnectionError, match="NEO4J_URI"):
            _read_env()


# ── create_driver ──


class TestCreateDriver:
    def test_success(self, monkeypatch):
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "secret")

        mock_driver = MagicMock()
        with patch("src.connection.GraphDatabase.driver", return_value=mock_driver) as mock_factory:
            driver = create_driver()

        mock_factory.assert_called_once_with("bolt://localhost:7687", auth=("neo4j", "secret"))
        mock_driver.verify_connectivity.assert_called_once()
        assert driver is mock_driver

    def test_service_unavailable(self, monkeypatch):
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "secret")

        from neo4j.exceptions import ServiceUnavailable

        mock_driver = MagicMock()
        mock_driver.verify_connectivity.side_effect = ServiceUnavailable("connection refused")
        with (
            patch("src.connection.GraphDatabase.driver", return_value=mock_driver),
            pytest.raises(Neo4jConnectionError, match="Cannot reach Neo4j"),
        ):
            create_driver()

    def test_auth_error(self, monkeypatch):
        """AuthError is caught and re-raised as Neo4jConnectionError."""
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "wrong")

        from neo4j.exceptions import AuthError

        mock_driver = MagicMock()
        mock_driver.verify_connectivity.side_effect = AuthError("bad credentials")
        with (
            patch("src.connection.GraphDatabase.driver", return_value=mock_driver),
            pytest.raises(Neo4jConnectionError, match="Authentication failed"),
        ):
            create_driver()

    def test_verify_false_is_lazy_never_touches_network(self, monkeypatch):
        """verify=False returns the driver WITHOUT calling verify_connectivity, so a
        long-lived web service starts even when the DB is unreachable (the Render
        deploy fix — a paused/gone Aura instance must not crash startup)."""
        monkeypatch.setenv("NEO4J_URI", "neo4j+s://dead.databases.neo4j.io:7687")
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "secret")

        mock_driver = MagicMock()
        # If verify were called it would raise — proving verify=False skips it.
        mock_driver.verify_connectivity.side_effect = AssertionError("must NOT verify")
        with patch("src.connection.GraphDatabase.driver", return_value=mock_driver):
            driver = create_driver(verify=False)

        assert driver is mock_driver
        mock_driver.verify_connectivity.assert_not_called()


# ── get_driver ──


class TestGetDriver:
    def test_yields_and_closes(self, monkeypatch):
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "secret")

        mock_driver = MagicMock()
        with patch("src.connection.GraphDatabase.driver", return_value=mock_driver):
            with get_driver() as d:
                assert d is mock_driver
            mock_driver.close.assert_called_once()

    def test_closes_on_exception(self, monkeypatch):
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "secret")

        mock_driver = MagicMock()
        with patch("src.connection.GraphDatabase.driver", return_value=mock_driver):
            with pytest.raises(ValueError, match="boom"), get_driver():
                raise ValueError("boom")
            mock_driver.close.assert_called_once()


# ── abort_on_connection_error ──


class TestAbortDecorator:
    def test_exits_on_connection_error(self):
        """The decorator catches Neo4jConnectionError and calls sys.exit(1)."""

        @abort_on_connection_error
        def failing_func():
            raise Neo4jConnectionError("test connection error")

        with pytest.raises(SystemExit) as exc_info:
            failing_func()
        assert exc_info.value.code == 1

    def test_passes_through_normal_return(self):
        @abort_on_connection_error
        def ok_func():
            return 42

        assert ok_func() == 42

    def test_prints_to_stderr(self, capsys):
        @abort_on_connection_error
        def failing_func():
            raise Neo4jConnectionError("test message here")

        with pytest.raises(SystemExit):
            failing_func()

        captured = capsys.readouterr()
        assert "test message here" in captured.err
        assert "CONNECTION FAILED" in captured.err
