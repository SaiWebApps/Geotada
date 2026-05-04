"""Pydantic models for the voice feedback → GitHub Issues endpoint."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FeedbackRequest(BaseModel):
    transcript: str = Field(..., min_length=1, max_length=5000)
    current_route: str = Field(default="", max_length=200)
    device_platform: str = Field(default="", max_length=50)
    device_os_version: str = Field(default="", max_length=50)
    app_version: str = Field(default="", max_length=50)
    user_email: str | None = Field(default=None, max_length=200)


class FeedbackResponse(BaseModel):
    issue_url: str
    issue_number: int
    title: str
