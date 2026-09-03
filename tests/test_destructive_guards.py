"""Guards against wiping/overwriting the production (Aura) Neo4j from the CLI.

Root cause these tests lock down (forensically confirmed): destructive code
trusted the active ``NEO4J_URI`` with no localhost check, so with ``.env`` in
cloud mode, ``make db-reset`` / ``make setup`` / ``make deploy`` / pytest
all hit production. The guards below refuse a non-local target and — critically
— fire BEFORE any driver/session is opened, so they protect even when Aura is
unreachable or paused (no network call is needed to reject the op).

These tests are pure: they monkeypatch ``NEO4J_URI`` and assert ``SystemExit``
without ever constructing a Neo4j driver. If a guard ever regressed to connect
first, this suite would hang/error against a real DB instead of exiting fast.
"""

from __future__ import annotations

import pytest

from scripts.upload_paris import _assert_upload_target_allowed
from src.main import _assert_local_target

# A representative Aura host of the neo4j+s://<id>.databases.neo4j.io shape.
_AURA_URI = "neo4j+s://8a37bbaf.databases.neo4j.io"

_LOCAL_URIS = [
    "bolt://localhost:7688",
    "bolt://127.0.0.1:7687",
    "bolt://localhost:7687",
    "neo4j://localhost:7687",
]

_NON_LOCAL_URIS = [
    _AURA_URI,
    "neo4j+s://deadbeef.databases.neo4j.io",
    "bolt://10.0.0.5:7687",
    "bolt://db.internal.example.com:7687",
    "",  # empty URI has no host → must be refused, never silently allowed
]


# ── src.main._assert_local_target ──


@pytest.mark.parametrize("uri", _NON_LOCAL_URIS)
def test_assert_local_target_refuses_non_local(monkeypatch, uri):
    monkeypatch.setenv("NEO4J_URI", uri)
    with pytest.raises(SystemExit) as exc:
        _assert_local_target()
    # The message must name the offending URI so the operator can see it.
    assert "REFUSING" in str(exc.value)


@pytest.mark.parametrize("uri", _LOCAL_URIS)
def test_assert_local_target_allows_localhost(monkeypatch, uri):
    monkeypatch.setenv("NEO4J_URI", uri)
    # Must NOT raise for any localhost/loopback target.
    _assert_local_target()


def test_assert_local_target_refuses_missing_env(monkeypatch):
    monkeypatch.delenv("NEO4J_URI", raising=False)
    with pytest.raises(SystemExit):
        _assert_local_target()


# ── src.main.clean() / setup() fire the guard BEFORE any connection ──
#
# We monkeypatch get_driver so that if the guard DID NOT fire first, the test
# would fail loudly (RuntimeError) instead of touching a DB. Because the guard
# raises SystemExit first, get_driver is never reached.


def _explode(*_args, **_kwargs):  # pragma: no cover - must never be called
    raise RuntimeError("get_driver() was called before the local-target guard fired")


def test_clean_refuses_cloud_before_connecting(monkeypatch):
    import src.main as main_mod

    monkeypatch.setenv("NEO4J_URI", _AURA_URI)
    monkeypatch.setattr(main_mod, "get_driver", _explode)
    with pytest.raises(SystemExit):
        main_mod.clean()


def test_setup_refuses_cloud_before_connecting(monkeypatch):
    import src.main as main_mod

    monkeypatch.setenv("NEO4J_URI", _AURA_URI)
    monkeypatch.setattr(main_mod, "get_driver", _explode)
    with pytest.raises(SystemExit):
        main_mod.setup()


def test_clean_allows_local(monkeypatch):
    """With a localhost URI the guard passes and control reaches get_driver.

    We stub get_driver to raise a sentinel so no real DB is needed; reaching it
    (a NON-SystemExit sentinel) proves the guard did NOT block a local target.
    """
    import src.main as main_mod

    sentinel = RuntimeError("reached-get-driver")

    def _sentinel(*_a, **_k):
        raise sentinel

    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7688")
    monkeypatch.setattr(main_mod, "get_driver", _sentinel)
    with pytest.raises(RuntimeError) as exc:
        main_mod.clean()
    assert exc.value is sentinel  # got past the guard, not a SystemExit


# ── scripts.upload_paris._assert_upload_target_allowed ──


@pytest.mark.parametrize("uri", _NON_LOCAL_URIS)
def test_upload_refuses_non_local_without_flag(monkeypatch, uri):
    monkeypatch.setenv("NEO4J_URI", uri)
    with pytest.raises(SystemExit) as exc:
        _assert_upload_target_allowed(allow_cloud=False)
    assert "REFUSING" in str(exc.value)


@pytest.mark.parametrize("uri", _LOCAL_URIS)
def test_upload_allows_local_without_flag(monkeypatch, uri):
    monkeypatch.setenv("NEO4J_URI", uri)
    _assert_upload_target_allowed(allow_cloud=False)


def test_upload_allows_cloud_with_explicit_flag(monkeypatch):
    """A deliberate, typed --allow-cloud upload is still possible."""
    monkeypatch.setenv("NEO4J_URI", _AURA_URI)
    _assert_upload_target_allowed(allow_cloud=True)
