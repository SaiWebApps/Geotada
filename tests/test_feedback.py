"""Tests for the voice feedback → GitHub Issues endpoint."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    with patch("src.api.app.init_driver"), patch("src.api.app.close_driver"):
        from src.api.app import create_app

        app = create_app()
        with TestClient(app) as c:
            yield c


class TestFeedbackEndpoint:
    def test_missing_transcript_returns_422(self, client):
        resp = client.post("/api/v1/feedback", json={})
        assert resp.status_code == 422

    def test_empty_transcript_returns_422(self, client):
        resp = client.post("/api/v1/feedback", json={"transcript": ""})
        assert resp.status_code == 422

    @patch("src.api.routes.feedback._create_github_issue")
    @patch("src.api.routes.feedback._structure_feedback")
    def test_success_flow(self, mock_structure, mock_github, client):
        mock_structure.return_value = {
            "title": "[Bug] Map doesn't load",
            "body": "**What happened**\nThe map screen is blank.",
            "labels": ["bug", "map"],
        }
        mock_github.return_value = {
            "issue_url": "https://github.com/SaiWebApps/Ondoway/issues/99",
            "issue_number": 99,
            "title": "[Bug] Map doesn't load",
        }

        resp = client.post(
            "/api/v1/feedback",
            json={
                "transcript": "the map doesn't load when I open the explore tab",
                "current_route": "/explore",
                "device_platform": "iOS",
                "device_os_version": "18.4",
                "app_version": "0.1.0",
                "user_email": "tester@example.com",
            },
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["issue_url"] == "https://github.com/SaiWebApps/Ondoway/issues/99"
        assert data["issue_number"] == 99
        assert data["title"] == "[Bug] Map doesn't load"

        mock_structure.assert_called_once()
        call_kwargs = mock_github.call_args.kwargs
        assert "beta-feedback" in call_kwargs["labels"]

    @patch("src.api.routes.feedback._create_github_issue")
    @patch("src.api.routes.feedback._structure_feedback")
    def test_metadata_appended_to_body(self, mock_structure, mock_github, client):
        mock_structure.return_value = {
            "title": "[UX] Colors are weird",
            "body": "**What happened**\nColors look off in dark mode.",
            "labels": ["ux"],
        }
        mock_github.return_value = {
            "issue_url": "https://github.com/SaiWebApps/Ondoway/issues/100",
            "issue_number": 100,
            "title": "[UX] Colors are weird",
        }

        client.post(
            "/api/v1/feedback",
            json={
                "transcript": "the colors are weird in dark mode",
                "current_route": "/profile",
                "device_platform": "Android",
                "user_email": "beta@test.com",
            },
        )

        call_kwargs = mock_github.call_args.kwargs
        issue_body = call_kwargs["body"]
        assert "beta@test.com" in issue_body
        assert "/profile" in issue_body
        assert "Android" in issue_body

    @patch("src.api.routes.feedback._create_github_issue")
    @patch("src.api.routes.feedback._structure_feedback")
    def test_beta_feedback_label_always_added(
        self, mock_structure, mock_github, client
    ):
        mock_structure.return_value = {
            "title": "[Feature] Offline mode",
            "body": "User wants offline tours.",
            "labels": ["enhancement"],
        }
        mock_github.return_value = {
            "issue_url": "https://github.com/SaiWebApps/Ondoway/issues/101",
            "issue_number": 101,
            "title": "[Feature] Offline mode",
        }

        client.post(
            "/api/v1/feedback",
            json={"transcript": "I wish I could download tours for offline use"},
        )

        call_kwargs = mock_github.call_args.kwargs
        labels = call_kwargs["labels"]
        assert "beta-feedback" in labels
        assert "enhancement" in labels

    @patch("src.api.routes.feedback._structure_feedback")
    def test_github_token_missing_returns_500(self, mock_structure, client, monkeypatch):
        mock_structure.return_value = {
            "title": "[Bug] Test",
            "body": "Test body",
            "labels": ["bug"],
        }
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        resp = client.post(
            "/api/v1/feedback",
            json={"transcript": "something is broken"},
        )
        assert resp.status_code == 500

    @patch("src.api.routes.feedback._create_github_issue")
    @patch("src.api.routes.feedback._structure_feedback")
    def test_no_auth_required(self, mock_structure, mock_github, client):
        """The feedback endpoint must work without an Authorization header."""
        mock_structure.return_value = {
            "title": "[Bug] Login broken",
            "body": "Can't log in.",
            "labels": ["bug", "auth"],
        }
        mock_github.return_value = {
            "issue_url": "https://github.com/SaiWebApps/Ondoway/issues/102",
            "issue_number": 102,
            "title": "[Bug] Login broken",
        }

        resp = client.post(
            "/api/v1/feedback",
            json={"transcript": "I can't log in the app just spins"},
        )
        assert resp.status_code == 201
