"""Tests for the fail-closed Make execution environment builder."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import dev_env


def test_committed_profiles_pin_three_distinct_local_database_ports() -> None:
    assert dev_env.read_profile("local")["NEO4J_URI"] == "bolt://localhost:7687"
    assert dev_env.read_profile("test")["NEO4J_URI"] == "bolt://localhost:7688"
    assert dev_env.read_profile("workbench")["NEO4J_URI"] == "bolt://localhost:7689"


def test_profile_parser_rejects_malformed_lines(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "bad").write_text("NOT_AN_ASSIGNMENT\n", encoding="utf-8")
    monkeypatch.setattr(dev_env, "PROFILE_DIR", tmp_path)
    with pytest.raises(dev_env.EnvironmentError, match="expected KEY=VALUE"):
        dev_env.read_profile("bad")


def test_render_environment_merges_linked_groups_then_service_overrides(monkeypatch) -> None:
    def fake_pages(path: str, _api_key: str) -> list[dict]:
        if path == "/env-groups":
            return [
                {
                    "envGroup": {
                        "id": "evg-1",
                        "serviceLinks": [{"id": dev_env.RENDER_SERVICE_ID}],
                        "envVars": [
                            {"key": "SHARED", "value": "group"},
                            {"key": "GROUP_ONLY", "value": "present"},
                        ],
                    }
                }
            ]
        return [
            {"envVar": {"key": "SHARED", "value": "service"}},
            {"envVar": {"key": "DIRECT_ONLY", "value": "present"}},
        ]

    monkeypatch.setattr(dev_env, "_paginated", fake_pages)
    assert dev_env.fetch_render_environment("secret") == {
        "SHARED": "service",
        "GROUP_ONLY": "present",
        "DIRECT_ONLY": "present",
    }


def test_conflicting_linked_groups_fail_instead_of_guessing(monkeypatch) -> None:
    monkeypatch.setattr(
        dev_env,
        "_paginated",
        lambda path, _key: (
            [
                {
                    "id": "evg-1",
                    "serviceLinks": [{"id": dev_env.RENDER_SERVICE_ID}],
                    "envVars": [{"key": "CLASH", "value": "one"}],
                },
                {
                    "id": "evg-2",
                    "serviceLinks": [{"id": dev_env.RENDER_SERVICE_ID}],
                    "envVars": [{"key": "CLASH", "value": "two"}],
                },
            ]
            if path == "/env-groups"
            else []
        ),
    )
    with pytest.raises(dev_env.EnvironmentError, match="conflict"):
        dev_env.fetch_render_environment("secret")


def test_render_neo4j_is_atomically_replaced_by_test_profile(monkeypatch) -> None:
    monkeypatch.setattr(dev_env, "keychain_api_key", lambda: "secret")
    monkeypatch.setattr(
        dev_env,
        "fetch_render_environment",
        lambda _key: {
            "NEO4J_URI": "neo4j+s://production.databases.neo4j.io",
            "NEO4J_USER": "production",
            "NEO4J_PASSWORD": "production-secret",
            "RESEND_API_KEY": "resend-secret",
        },
    )
    child = dev_env.build_environment(profile="test", render=True)
    assert child["NEO4J_URI"] == "bolt://localhost:7688"
    assert child["NEO4J_USER"] == "neo4j"
    assert child["NEO4J_PASSWORD"] == "ondoway_test_2026"
    assert child["RESEND_API_KEY"] == "resend-secret"


def test_local_safety_assertion_rejects_cloud_uri() -> None:
    with pytest.raises(dev_env.EnvironmentError, match="refusing"):
        dev_env._assert_local_profile(
            "test",
            {
                "NEO4J_URI": "neo4j+s://production.databases.neo4j.io",
                "NEO4J_DATABASE": "neo4j",
            },
        )


def test_deploy_status_uses_keychain_api_without_printing_secrets(monkeypatch, capsys) -> None:
    monkeypatch.setattr(dev_env, "keychain_api_key", lambda: "never-print-this")
    monkeypatch.setattr(
        dev_env,
        "_request_json",
        lambda path, key: [
            {
                "deploy": {
                    "id": "dep-1",
                    "status": "live",
                    "commit": {"message": "safe commit"},
                }
            }
        ],
    )
    dev_env.print_deploy_status()
    output = capsys.readouterr().out
    assert "ondoway-api: live | dep-1 | safe commit" in output
    assert "never-print-this" not in output
