"""Tests for scripts/wiki_fetch.py — focused on the --city path-safety guard.

The network fetch path is exercised via the live `make wiki-fetch` integration;
here we only assert the security-relevant input handling, which short-circuits
before any network call or filesystem write.
"""

from __future__ import annotations

import json

from scripts.wiki_fetch import main


def test_wiki_fetch_rejects_traversal_city(capsys):
    """A city containing path-traversal characters is rejected before any
    fetch or write (no escaping the data tree)."""
    rc = main(["--city", "../../etc", "--name", "X", "--title", "Mercury"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "invalid_city"


def test_wiki_fetch_rejects_slash_city(capsys):
    main(["--city", "paris/../secrets", "--name", "X", "--title", "Mercury"])
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "invalid_city"


def test_wiki_fetch_accepts_valid_city_and_reaches_fetch(monkeypatch, capsys):
    """A valid (case-insensitive) city slug passes the guard and proceeds to
    the fetch. Stub the network so the test stays offline."""
    monkeypatch.setattr(
        "scripts.wiki_fetch.fetch_article",
        lambda title: {"query": {"pages": {"1": {"missing": True}}}},
    )
    rc = main(["--city", "Paris", "--name", "X"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "not_found"  # passed the city guard, reached fetch
