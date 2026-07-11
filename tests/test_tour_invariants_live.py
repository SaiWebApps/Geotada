"""Live-graph tour INVARIANT gate (marker: invariants; excluded from the bar).

Generates REAL tours across representative start/duration/lens/end paths on the
dev graph (7687) + Valhalla, and asserts the workbench-reported 2026-07 defect
classes stay dead. Each is a bug a real tester hit; a regression flips this RED.

Run: ``make tour-invariants`` (starts db-up + valhalla-up).

Design notes
------------
- Assertions run on the ENGINE output (``generate`` -> Script + Route), the
  shared core every surface (preview/generate) is built on. Per-stop narration
  is reconstructed by grouping ``script.script`` sentences by ``stop_idx``.
- Every input asserts ALL invariants and collects every violation into one
  message, so a single failing tour reports its full defect list (not just the
  first), the way the mechanical sweep does.
- These are HOLISTIC, real-corpus guards. The fast, deterministic per-fix unit
  guards live in ``test_tour_selection.py`` / ``test_tour_generation.py`` /
  ``test_trip_preview_vignettes.py`` and run in the default bar.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import pytest

pytestmark = pytest.mark.invariants

# Representative paths: the 4 original workbench cases + broad coverage.
# (label, start(lat,lng), duration_min, lenses, end(lat,lng) | None)
_PATHS = [
    ("concorde-250-loop", (48.8656, 2.3281), 200, None, None),
    ("louvre-150-loop", (48.8606, 2.3376), 150, None, None),
    ("marais-150-hidden", (48.8590, 2.3620), 150,
     ["hidden_history", "war_conflict", "social_change"], None),
    ("latin-120-parks", (48.8480, 2.3470), 120,
     ["parks_gardens", "waterways_views", "nature_landscape"], None),
    ("pantheon-120-loop", (48.8462, 2.3464), 120, None, None),
    # Point-to-point (the Test-3/Test-4 shape): a generous budget so the path is
    # feasible — an over-budget fixed end is a separate (cruise-mode) concern.
    ("garnier-leshalles-p2p", (48.8719, 2.3316), 180, None, (48.8626, 2.3449)),
]

# A seated dwell stop must voice at least this much narration — the "empty
# second stop that just says 'Walk to the next stop.'" bug floor.
_MIN_DWELL_NARRATION_CHARS = 80

_SNAPSHOT = None


@pytest.fixture(scope="module", autouse=True)
def _live_snapshot():
    """Load the live Paris corpus once; skip if the dev graph is down."""
    global _SNAPSHOT
    from neo4j import GraphDatabase
    from neo4j.exceptions import AuthError, ServiceUnavailable

    from src.tour.selection import load_paris_corpus
    from tests.test_tour_golden_pdv import _parse_env_file

    env = _parse_env_file(Path(__file__).resolve().parent.parent / ".env")
    uri = env.get("NEO4J_URI", "")
    user = env.get("NEO4J_USER", "")
    pw = env.get("NEO4J_PASSWORD", "")
    if not (uri and user and pw):
        pytest.skip("live dev Neo4j creds not in .env")
    try:
        d = GraphDatabase.driver(uri, auth=(user, pw))
        d.verify_connectivity()
    except (ServiceUnavailable, AuthError, Exception):
        pytest.skip("live dev Neo4j unreachable — start it with `make db-up`")
    _SNAPSHOT = load_paris_corpus(d, city_slug="paris")
    d.close()
    yield


def _build_tour(start, duration_min, lenses, end):
    """Run the real pipeline for one input; return (route, script)."""
    from src.tour.beat_select import select_poi_beats
    from src.tour.contract import BeatSequence, TourInput
    from src.tour.generation import generate
    from src.tour.routing_client import RoutingClient
    from src.tour.selection import select_route

    tour_input = TourInput(
        start=tuple(start), duration_min=duration_min, city_slug="paris",
        round_trip=(end is None), lenses=lenses,
        end=(tuple(end) if end else None),
    )
    with RoutingClient() as rc:
        route = select_route(tour_input, _SNAPSHOT, routing_client=rc)
    plans = [select_poi_beats(p, _SNAPSHOT.beats_for(p.id)) for p in route.pois]
    script = generate(BeatSequence(poi_beats=tuple(plans)), route, tour_input)
    return route, script


def _stop_texts(script):
    """Map stop_idx -> list[Sentence] and stop_idx -> joined narration."""
    by_stop: dict[int, list] = defaultdict(list)
    for s in script.script:
        by_stop[s.stop_idx].append(s)
    return by_stop


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def _check_invariants(route, script) -> list[str]:
    """Return a list of invariant-violation strings (empty == clean)."""
    v: list[str] = []
    by_stop = _stop_texts(script)
    stop_idxs = sorted(by_stop)

    # INV1 — no two ADJACENT stops share a display name (the Tuileries dup).
    names = [p.name for p in route.pois]
    for i in range(1, len(names)):
        if names[i] and names[i] == names[i - 1]:
            v.append(f"INV1 duplicate-adjacent-stop: {names[i]!r} at stops {i - 1},{i}")

    # INV7 — stop_idx values are emitted in non-decreasing order.
    emitted = [s.stop_idx for s in script.script]
    if emitted != sorted(emitted):
        v.append(f"INV7 non-monotonic stop order: {emitted[:12]}...")

    for idx in stop_idxs:
        sents = by_stop[idx]
        beat_sents = [s for s in sents if s.source_type == "beat"]
        narration = " ".join(s.text for s in sents)

        # INV2 — a seated stop is never empty / glue-only. Exception: a pinned
        # fixed-end endpoint (the "__end_b__" sentinel) has no POI content of its
        # own, so the correct output is a graceful arrival ("...your final
        # destination") + the closing — not a beat.
        is_sentinel_end = (
            idx == stop_idxs[-1]
            and idx < len(route.pois)
            and route.pois[idx].id.startswith("__end_b__")
        )
        if not beat_sents:
            if is_sentinel_end and "destination" in narration.lower():
                pass  # graceful pinned-endpoint arrival — correct, not empty
            else:
                v.append(f"INV2 empty/glue-only stop {idx}: {narration[:70]!r}")
        elif len(narration) < _MIN_DWELL_NARRATION_CHARS:
            v.append(f"INV2 too-thin stop {idx} ({len(narration)} chars): {narration[:70]!r}")

        # INV6 — no EXACT-duplicate sentence within a single stop (literal repeat).
        seen: set[str] = set()
        for s in sents:
            key = _norm(s.text)
            if len(key) > 20 and key in seen:
                v.append(f"INV6 exact-duplicate sentence in stop {idx}: {s.text[:60]!r}")
            seen.add(key)

        # INV4/INV5 — opener staging is not doubled or mis-cased.
        for s in sents:
            if "look up at look up at" in s.text.lower() or "notice notice" in s.text.lower():
                v.append(f"INV4 doubled staging verb in stop {idx}: {s.text[:60]!r}")
            if re.search(r"\b(?:look up at|notice)\s+The\s+[a-z]", s.text):
                v.append(f"INV5 mis-cased staging ('at The <noun>') in stop {idx}: {s.text[:60]!r}")

    # INV3 — the LAST stop carries a closing sign-off that thanks the walker.
    if stop_idxs:
        last = " ".join(s.text for s in by_stop[stop_idxs[-1]])
        if "thank you" not in last.lower():
            v.append(f"INV3 no closing sign-off on last stop: ...{last[-80:]!r}")

    return v


@pytest.mark.parametrize("label,start,duration,lenses,end", _PATHS, ids=[p[0] for p in _PATHS])
def test_generated_tour_holds_invariants(label, start, duration, lenses, end):
    from src.tour.density import TourabilityRefusedError

    try:
        route, script = _build_tour(start, duration, lenses, end)
    except TourabilityRefusedError as e:  # a feasible fixture must not refuse
        pytest.fail(f"{label}: engine refused a fixture expected to be feasible — {e}")
    assert route.pois, f"{label}: engine produced no stops"
    violations = _check_invariants(route, script)
    assert not violations, (
        f"\n{label}: {len(violations)} invariant violation(s):\n  " + "\n  ".join(violations)
    )
