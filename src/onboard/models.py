"""Typed contracts for the new-city onboarding flow.

These models are the CONTRACT that Steps 3-5 depend on, so field names and the
structural walls below are load-bearing:

- ``SourceDocument`` is the ONLY thing carrying ingestable full text, and it
  cannot be constructed without a ``license`` (the license wall).
- ``DiscoveryPointer`` is metadata-only BY DESIGN: it has no text field and
  forbids extras, so a shadow-library (Anna's Archive / WeLib) result can never
  smuggle copyrighted body text into the pipeline (grey-zone wall 1).
- ``OnboardEvent`` / ``OnboardJob`` are what the live progress stream (Step 5)
  serialises so the user watches sources being consulted in real time.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

# A source's licensing basis. ``SourceDocument`` REQUIRES one of these — an
# un-licensed document is a construction error, not a runtime check downstream.
SourceLicense = Literal["public_domain", "cc_by_sa", "user_provided"]


class SourceDocument(BaseModel):
    """A FETCHED, INGESTABLE full-text source (e.g. a Wikipedia revision, a
    Wikivoyage page, a Project Gutenberg book).

    ``license`` is the license wall: it is required, so nothing that carries
    ``text`` can exist without an explicit licensing basis. ``extra="forbid"``
    keeps the shape closed so callers cannot slip untyped fields past review.
    """

    model_config = ConfigDict(extra="forbid")

    source: str  # provider slug, e.g. "wikipedia"
    license: SourceLicense  # REQUIRED — the license wall
    title: str
    url: str
    text: str
    retrieved_at: str | None = None
    meta: dict = {}  # provider metadata, e.g. {"revid": 12345}


class DiscoveryPointer(BaseModel):
    """A shadow-library METADATA pointer (grey-zone wall 1) — e.g. an Anna's
    Archive / WeLib search hit surfaced so the human can acquire the work
    LEGALLY and then feed it through the Manual book-drop flow.

    This model is metadata-ONLY by design and MUST stay that way. It carries NO
    ``text`` / ``content`` / ``body`` / ``full_text`` field: the absence of any
    text-bearing field is the structural wall that makes automated download or
    ingest of copyrighted text impossible — there is simply no field for such
    text to live in. ``extra="forbid"`` closes the last door: a caller cannot
    sneak a text field in via kwargs (that raises ``ValidationError``).
    """

    model_config = ConfigDict(extra="forbid")

    source: str  # provider slug, e.g. "annas_archive" / "welib"
    title: str
    author: str | None = None
    year: int | None = None
    format: str | None = None
    source_url: str  # outbound link the human follows to acquire legally


# The kind of a live progress record. ``discovery_pointer`` events carry a
# ``DiscoveryPointer``-shaped payload in ``data`` (never text); the rest narrate
# what the onboarding run is doing so the user can watch it work.
OnboardEventKind = Literal[
    "source_consult",
    "candidate_batch",
    "discovery_pointer",
    "phase",
    "rate_limited",
    "error",
    "info",
]


class OnboardEvent(BaseModel):
    """One live progress record. The snapshot/SSE endpoint (Step 5) streams
    these in ``seq`` order so the user watches every source being consulted.

    ``seq`` is assigned by the job store (monotonic, strictly increasing,
    starting at 1) — do not set it by hand.
    """

    seq: int
    kind: OnboardEventKind
    message: str
    source: str | None = None
    url: str | None = None
    data: dict = {}
    at: str | None = None  # ISO-8601 timestamp


# Lifecycle of an onboarding run. Steps advance it: created → running →
# assembled (POIs merged) → drafting (beats) → uploaded, or → error.
OnboardStatus = Literal[
    "created",
    "running",
    "assembled",
    "drafting",
    "uploaded",
    "error",
]


class OnboardJob(BaseModel):
    """One onboarding run.

    Mutable by design (NOT frozen): the job store appends events and advances
    status in place. ``result`` is filled incrementally by later steps — Step 3
    appends a ``pointers`` list (``DiscoveryPointer`` payloads), Step 4 fills
    POIs/beats — so it is left as an open ``dict``.
    """

    id: str
    slug: str
    modes: list[str]
    status: OnboardStatus = "created"
    events: list[OnboardEvent] = []
    result: dict = {}
    error: str | None = None
    created_at: str | None = None  # ISO-8601 timestamp
