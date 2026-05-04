"""Voice feedback route — transcribe → structure via LLM → create GitHub issue."""

from __future__ import annotations

import json
import os
import re

import anthropic
import httpx
from fastapi import APIRouter, HTTPException

from src.api.models.feedback import FeedbackRequest, FeedbackResponse

router = APIRouter(tags=["feedback"])

_GITHUB_REPO = "SaiWebApps/Ondoway"
_GITHUB_API = "https://api.github.com"

_SYSTEM_PROMPT = (
    "You are a bug report structurer for a mobile app called Ondoway "
    "(GPS-triggered audio walking tours).\n\n"
    "You receive a raw voice transcript from a beta tester. "
    "Convert it into a structured GitHub issue.\n\n"
    "Return ONLY a JSON object with these fields:\n"
    '- "title": A concise issue title (under 80 chars). '
    "Start with [Bug], [Feature], or [UX].\n"
    '- "body": A markdown body with sections: '
    "**What happened**, **Expected behavior** (if inferable), "
    "**Steps to reproduce** (if inferable). Keep it concise.\n"
    '- "labels": An array of 1-3 labels from: '
    '"bug", "enhancement", "ux", "audio", "map", '
    '"auth", "tour", "performance", "crash".\n\n'
    "If the transcript is vague, do your best — "
    "the tester's words are the source of truth."
)


def _structure_feedback(transcript: str) -> dict:
    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": transcript}],
    )
    text = message.content[0].text.strip()
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)


def _create_github_issue(title: str, body: str, labels: list[str]) -> dict:
    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        raise HTTPException(500, "GITHUB_TOKEN not configured")

    with httpx.Client() as client:
        resp = client.post(
            f"{_GITHUB_API}/repos/{_GITHUB_REPO}/issues",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            json={"title": title, "body": body, "labels": labels},
        )

    if resp.status_code != 201:
        raise HTTPException(502, f"GitHub API error: {resp.status_code} {resp.text}")

    data = resp.json()
    return {"issue_url": data["html_url"], "issue_number": data["number"], "title": title}


@router.post("/feedback", response_model=FeedbackResponse, status_code=201)
def submit_feedback(body: FeedbackRequest):
    """Accept raw voice transcript, structure it via LLM, and create a GitHub issue."""
    metadata_lines = []
    if body.user_email:
        metadata_lines.append(f"**Reporter:** {body.user_email}")
    if body.current_route:
        metadata_lines.append(f"**Screen:** `{body.current_route}`")
    if body.device_platform:
        metadata_lines.append(
            f"**Device:** {body.device_platform} {body.device_os_version}"
        )
    if body.app_version:
        metadata_lines.append(f"**App version:** {body.app_version}")

    metadata_section = "\n".join(metadata_lines)

    structured = _structure_feedback(body.transcript)

    issue_body = structured.get("body", body.transcript)
    if metadata_section:
        issue_body = f"{issue_body}\n\n---\n{metadata_section}"

    labels = structured.get("labels", ["beta-feedback"])
    if "beta-feedback" not in labels:
        labels.append("beta-feedback")

    result = _create_github_issue(
        title=structured.get("title", f"[Feedback] {body.transcript[:60]}"),
        body=issue_body,
        labels=labels,
    )
    return FeedbackResponse(**result)
