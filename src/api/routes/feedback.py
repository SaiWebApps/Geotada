"""Voice feedback route — transcribe → structure via LLM → create GitHub issue."""

from __future__ import annotations

import json
import os
import re
import time
from collections import deque
from threading import Lock

import anthropic
import httpx
from fastapi import APIRouter, HTTPException, Request

from src.api.models.feedback import FeedbackRequest, FeedbackResponse, TourContext

router = APIRouter(tags=["feedback"])

_GITHUB_REPO = "SaiWebApps/Ondoway"
_GITHUB_API = "https://api.github.com"

# --- Abuse guard (Defect #1) -------------------------------------------------
# The endpoint is intentionally unauthenticated (mobile beta testers, some not
# logged in) but each call spends real money: one Anthropic Haiku completion AND
# a real GitHub issue POST. An anonymous attacker could loop it to burn LLM
# credits and flood the issue tracker. We cap requests per client IP with a
# simple in-process fixed-window counter so a single caller cannot fan out.
_RATE_LIMIT_MAX = int(os.getenv("FEEDBACK_RATE_LIMIT_MAX", "5"))
_RATE_LIMIT_WINDOW_S = int(os.getenv("FEEDBACK_RATE_LIMIT_WINDOW_S", "60"))
# Number of trusted reverse-proxy hops in front of the app. On Render there is
# exactly one edge proxy, so the real client IP is the LAST entry the trusted
# edge appended (i.e. the entry `_TRUSTED_PROXY_HOPS` from the right end).
_TRUSTED_PROXY_HOPS = int(os.getenv("FEEDBACK_TRUSTED_PROXY_HOPS", "1"))
# Optional global fixed-window cap (defense-in-depth). Per-IP limits are
# inherently bypassable at scale by rotating source IPs, so also bound the
# TOTAL accepted requests per window across all clients. Set <=0 to disable.
_GLOBAL_RATE_LIMIT_MAX = int(os.getenv("FEEDBACK_GLOBAL_RATE_LIMIT_MAX", "60"))
_rate_state: dict[str, deque[float]] = {}
_global_hits: deque[float] = deque()
_rate_lock = Lock()


def _client_ip(request: Request) -> str:
    """Resolve the real client IP for rate-limiting.

    ``X-Forwarded-For`` is client-controllable: a caller can prepend arbitrary
    fake entries on the LEFT, so the leftmost hop can NOT be trusted as the
    identity — trusting it lets an attacker land every request in a fresh bucket
    (a new spoofed IP each time), fully defeating the limiter.

    Instead we trust only our own edge. With ``_TRUSTED_PROXY_HOPS`` proxies in
    front of the app (1 on Render), the real client is the entry that the
    innermost trusted proxy observed and appended — i.e. counting
    ``_TRUSTED_PROXY_HOPS`` from the RIGHT of the header. Anything to the left of
    that is attacker-supplied and ignored. Fall back to the socket peer when the
    header is absent (direct connection / local dev)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            # The rightmost entry was appended by our edge and records the peer
            # it saw. With N trusted hops, the true client sits N positions from
            # the right; clamp to the leftmost real entry for short headers.
            idx = max(0, len(parts) - _TRUSTED_PROXY_HOPS)
            return parts[idx]
    if request.client:
        return request.client.host
    return "unknown"


def _rate_limit(request: Request) -> None:
    """Per-IP fixed-window guard. Raises HTTPException(429) when the caller has
    exceeded _RATE_LIMIT_MAX requests within the trailing _RATE_LIMIT_WINDOW_S
    seconds. In-process only (single worker) — enough to stop a naive loop from
    one host from draining LLM credits / spamming issues."""
    client_ip = _client_ip(request)
    now = time.monotonic()
    cutoff = now - _RATE_LIMIT_WINDOW_S
    with _rate_lock:
        # Defense-in-depth global cap: bound TOTAL accepted requests per window
        # so IP rotation can't spend unbounded LLM credits / GitHub issues.
        if _GLOBAL_RATE_LIMIT_MAX > 0:
            while _global_hits and _global_hits[0] <= cutoff:
                _global_hits.popleft()
            if len(_global_hits) >= _GLOBAL_RATE_LIMIT_MAX:
                retry_after = max(1, int(_global_hits[0] + _RATE_LIMIT_WINDOW_S - now))
                raise HTTPException(
                    status_code=429,
                    detail="Feedback is temporarily rate limited, please retry later",
                    headers={"Retry-After": str(retry_after)},
                )

        if _RATE_LIMIT_MAX > 0:
            hits = _rate_state.setdefault(client_ip, deque())
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= _RATE_LIMIT_MAX:
                retry_after = max(1, int(hits[0] + _RATE_LIMIT_WINDOW_S - now))
                raise HTTPException(
                    status_code=429,
                    detail="Too many feedback submissions, please retry later",
                    headers={"Retry-After": str(retry_after)},
                )
            hits.append(now)

        if _GLOBAL_RATE_LIMIT_MAX > 0:
            _global_hits.append(now)


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


def _extract_json_object(text: str) -> str | None:
    """Best-effort pull of a single JSON object out of an LLM response.

    Handles (a) a fenced ```json ... ``` block (even without a closing fence)
    and (b) a bare object embedded in prose, via a brace-matching scan that is
    string/escape aware so braces inside JSON strings don't confuse it.
    Returns the object substring, or None if no plausible object is found.
    """
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _structure_feedback(transcript: str) -> dict:
    client = anthropic.Anthropic()
    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": transcript}],
        )
    except anthropic.RateLimitError as exc:
        # Defect #3: upstream throttling -> 503 with a retry hint, not a 500.
        raise HTTPException(
            status_code=503,
            detail=f"LLM provider rate limited: {exc}",
            headers={"Retry-After": "30"},
        ) from exc
    except anthropic.APIError as exc:
        # Defect #3: any other provider failure (connection/status) -> clean 502.
        raise HTTPException(status_code=502, detail=f"LLM provider error: {exc}") from exc

    # Defect #1: an empty content list or a non-text first block would raise
    # IndexError/AttributeError here — uncaught, that surfaces as a 500. Guard the
    # access so a missing/non-text response degrades to the deterministic fallback
    # below (empty text -> _extract_json_object returns None).
    block = message.content[0] if message.content else None
    text = getattr(block, "text", "").strip()
    candidate = _extract_json_object(text)
    if candidate is not None:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed

    # Defect #2: the LLM returned prose / malformed JSON. Never lose the report —
    # degrade to a deterministic issue built straight from the transcript.
    return {
        "title": f"[Feedback] {transcript[:60]}",
        "body": transcript,
        "labels": ["beta-feedback"],
    }


def _tour_context_section(ctx: TourContext) -> str:
    """Render the workbench tour-eval context as a '## Tour Context' markdown section.

    Human-mediated loop (Track B Step B.7): the context is rendered for a human
    reader on the GitHub issue — nothing here feeds back into the engine.
    """
    verdict_label = "👍 up" if ctx.verdict == "up" else "👎 down"
    end_label = f"{ctx.end[0]:.5f}, {ctx.end[1]:.5f}" if ctx.end else "open walk"
    lines = [
        "## Tour Context",
        f"**Verdict:** {verdict_label}",
        f"**Start:** {ctx.start[0]:.5f}, {ctx.start[1]:.5f}",
        f"**End:** {end_label}",
        f"**Duration:** {ctx.duration_min} min",
        f"**Lenses:** {', '.join(ctx.lenses) if ctx.lenses else '—'}",
    ]
    if ctx.stops:
        lines.append("**Stops:**")
        lines.extend(f"{i}. {s.name} ({s.band})" for i, s in enumerate(ctx.stops, 1))
    if ctx.note:
        lines.append(f"**Note:** {ctx.note}")
    return "\n".join(lines)


def _create_github_issue(title: str, body: str, labels: list[str]) -> dict:
    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        raise HTTPException(500, "GITHUB_TOKEN not configured")

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{_GITHUB_API}/repos/{_GITHUB_REPO}/issues",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                json={"title": title, "body": body, "labels": labels},
            )
    except httpx.TimeoutException as exc:
        # Defect #2: a transport timeout must degrade to a clean 503 with a
        # retry hint, not a raw 500 stack trace that loses the tester's report.
        raise HTTPException(
            status_code=503,
            detail="GitHub API timeout",
            headers={"Retry-After": "30"},
        ) from exc
    except httpx.RequestError as exc:
        # Defect #2: connection/network errors (ConnectError, etc.) -> clean 502.
        raise HTTPException(status_code=502, detail=f"GitHub API unreachable: {exc}") from exc

    if resp.status_code != 201:
        raise HTTPException(502, f"GitHub API error: {resp.status_code} {resp.text}")

    data = resp.json()
    return {"issue_url": data["html_url"], "issue_number": data["number"], "title": title}


@router.post("/feedback", response_model=FeedbackResponse, status_code=201)
def submit_feedback(request: Request, body: FeedbackRequest):
    """Accept raw voice transcript, structure it via LLM, and create a GitHub issue."""
    _rate_limit(request)
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
    # Defect #4: the LLM output is untrusted. Coerce the shape defensively so a
    # non-dict top level or a non-list/non-str 'labels' can never crash the route
    # (or forward junk labels to the GitHub API and trigger a 422 -> 502).
    if not isinstance(structured, dict):
        structured = {}

    issue_body = structured.get("body", body.transcript)
    if not isinstance(issue_body, str):
        issue_body = body.transcript
    if metadata_section:
        issue_body = f"{issue_body}\n\n---\n{metadata_section}"

    # Track B Step B.7: append the tour eval context when present (absent -> unchanged).
    if body.tour_context is not None:
        issue_body = f"{issue_body}\n\n{_tour_context_section(body.tour_context)}"

    raw_labels = structured.get("labels", [])
    if not isinstance(raw_labels, list):
        raw_labels = []
    labels = [x for x in raw_labels if isinstance(x, str)]
    if "beta-feedback" not in labels:
        labels.append("beta-feedback")

    title = structured.get("title")
    if not isinstance(title, str) or not title:
        title = f"[Feedback] {body.transcript[:60]}"

    result = _create_github_issue(
        title=title,
        body=issue_body,
        labels=labels,
    )
    return FeedbackResponse(**result)
