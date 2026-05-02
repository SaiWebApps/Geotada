"""Tests for the Apple App Site Association endpoint — no Neo4j needed."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api.app import create_app


def _make_client():
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


class TestAASAEndpoint:
    def test_returns_200(self):
        client = _make_client()
        resp = client.get("/.well-known/apple-app-site-association")
        assert resp.status_code == 200

    def test_content_type_is_json(self):
        client = _make_client()
        resp = client.get("/.well-known/apple-app-site-association")
        assert "application/json" in resp.headers["content-type"]

    def test_applinks_structure(self):
        client = _make_client()
        resp = client.get("/.well-known/apple-app-site-association")
        body = resp.json()
        assert "applinks" in body
        assert body["applinks"]["apps"] == []
        assert len(body["applinks"]["details"]) == 1

    def test_paths_include_auth(self):
        client = _make_client()
        resp = client.get("/.well-known/apple-app-site-association")
        detail = resp.json()["applinks"]["details"][0]
        assert "/auth" in detail["paths"]
        assert "/auth/*" in detail["paths"]

    @patch("src.api.auth.config.APPLE_TEAM_ID", "BC7F6Q48GB")
    def test_app_id_matches_config(self):
        client = _make_client()
        resp = client.get("/.well-known/apple-app-site-association")
        detail = resp.json()["applinks"]["details"][0]
        assert detail["appID"] == "BC7F6Q48GB.com.ondoway.app"
