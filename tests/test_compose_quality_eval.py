"""Sustainable compose quality eval — runs in the normal `make test` bar at $0.

This is the standing regression guard for the tour NARRATION logic. It exercises
the real stitcher (generate) and the real compose gate (build_full_verifier) on
a small stratified fixture, and asserts:

  * a GOOD composed tour passes both the gate AND the deterministic scoreboard;
  * the metrics catch a regression the GATE is blind to — a fused sentence that
    silently drops a date passes VERIFY (0.34 coverage floor + omission-blind
    entailment) yet trips quality_violations. This is the whole reason the
    scoreboard exists, proven end to end;
  * the real per-chapter orchestration serves a cached tour at $0 via
    ReplayComposeClient (which HARD-FAILS on a cache miss — no silent live call);
  * the fixtures are pinned to the exact compose + entailment prompt text, so a
    prompt edit turns this RED ("stale") instead of silently testing old behavior.

No LLM, no network: faithfulness is the injected Mock, composition is replay.
The live-capture counterpart (real Opus goldens) is tools/compose_snapshot.py,
which spends only behind an explicit approval gate.
"""

from __future__ import annotations

import pytest

from src.tour.claim_dedup import claims_realized_by
from src.tour.compose import ComposeRequest, compose_script_per_chapter
from src.tour.compose_gate import build_full_verifier
from src.tour.compose_metrics import (
    compute_compose_metrics,
    metric_regressions,
    quality_violations,
)
from src.tour.contract import (
    POI,
    BeatRef,
    BeatSequence,
    POIBeats,
    Route,
    Script,
    Sentence,
    TourInput,
    TransitSegment,
)
from src.tour.generation import generate
from src.tour.verify import MockFaithfulnessChecker
from tools.compose_snapshot import compose_prompt_fingerprint

# The compose + entailment prompt text these fixtures were authored against. A
# prompt edit changes this and turns the eval RED, forcing a fixture review /
# recapture — the guard against a permanently-green suite that quietly stopped
# testing reality. Update it (and recapture live goldens, if any) on purpose.
PINNED_PROMPT_FINGERPRINT = "5fab7880e9916b30"  # set by test_fixtures_pinned_to_prompt


# --- a 3-stop Marais-flavoured fixture: stop 0 has a cross-book DUPLICATE ------

def _poi(pid: str, name: str) -> POI:
    return POI(id=pid, name=name, tier=5, poi_role="stop", lat=48.855, lng=2.365)


def _beat(bid: str, poi: str, claim: str, secs: int) -> BeatRef:
    return BeatRef(id=bid, poi_id=poi, script_body=claim, word_count=len(claim.split()),
                   key_claims=(claim,), est_spoken_seconds=secs)


# b0a and b0b are the SAME fact from two different guidebooks (a duplicate pair
# the stitch voices twice and a good compose fuses into one).
B0A = _beat("b0a", "p0", "Henri IV completed the Place des Vosges in 1612", 18)
B0B = _beat("b0b", "p0", "The square was finished under Henri IV in 1612", 16)
B1 = _beat("b1", "p1", "Victor Hugo lived at number 6 from 1832 to 1848", 15)
B2 = _beat("b2", "p2", "The Hotel de Sully was built in 1624 for Mesme Gallet", 14)

SEQ = BeatSequence(poi_beats=(
    POIBeats(poi_id="p0", poi_name="Place des Vosges", ordering_strategy="sub_location",
             beats=(B0A, B0B)),
    POIBeats(poi_id="p1", poi_name="Maison de Victor Hugo", ordering_strategy="sub_location",
             beats=(B1,)),
    POIBeats(poi_id="p2", poi_name="Hotel de Sully", ordering_strategy="sub_location",
             beats=(B2,)),
))
BEATS = {b.id: b for plan in SEQ.poi_beats for b in plan.beats}
POIS = (_poi("p0", "Place des Vosges"), _poi("p1", "Maison de Victor Hugo"),
        _poi("p2", "Hotel de Sully"))


def _route() -> Route:
    # Short legs -> no reflection slots, so the fixture stays about fusion.
    transits = tuple(
        TransitSegment(from_poi_id=None if i == 0 else POIS[i - 1].id, to_poi_id=p.id,
                       distance_m=120.0, walk_seconds=30)
        for i, p in enumerate(POIS)
    )
    return Route(pois=POIS, transits=transits, total_walk_distance_m=360.0, total_walk_seconds=60)


def _stitched() -> Script:
    return generate(SEQ, _route(), TourInput(start=(48.855, 2.365), duration_min=60,
                                             city_slug="paris"))


def _fuse_stop0(stitched: Script, *, drop_date: bool) -> Script:
    """Fuse stop 0's two duplicate beat sentences into one telling that cites
    both beats. ``drop_date`` models the single most common fusion error — the
    year silently vanishes — to prove the scoreboard catches what the gate does
    not."""
    fused_text = (
        "Henri IV completed the Place des Vosges, finished under his reign"
        if drop_date
        else "Henri IV completed the Place des Vosges in 1612, finished under his reign"
    )
    out: list[Sentence] = []
    done = False
    for s in stitched.script:
        if s.source_type == "beat" and s.source_id in ("b0a", "b0b"):
            if not done:
                out.append(Sentence(text=fused_text, source_id="b0a", source_type="beat",
                                    stop_idx=s.stop_idx, also_cites=("b0b",)))
                done = True
            continue  # drop both originals; the fused line replaces them
        # A good compose has no em dashes (they mangle TTS); the stitcher's glue
        # does, so normalize them out — modelling what the composer produces.
        out.append(s.model_copy(update={"text": s.text.replace("—", ", ")}))
    return stitched.model_copy(update={"script": tuple(out)})


def _verifier():
    return build_full_verifier(
        SEQ, BEATS,
        faithfulness_checker=MockFaithfulnessChecker(),
        expected_claim_ids=claims_realized_by(_stitched(), BEATS),
    )


class ReplayComposeClient:
    """A ComposeClient that replays cached per-stop sentences — so the REAL
    compose_script_per_chapter orchestration runs end to end at $0. HARD-FAILS on
    a cache miss (raises): it must never silently fall back to a live call."""

    def __init__(self, composed_by_stop: dict[int, tuple[Sentence, ...]]):
        self._by_stop = composed_by_stop
        self.calls: list[int] = []

    def compose(self, request: ComposeRequest, attempt: int, prev_report) -> tuple[Sentence, ...]:
        stops = {s.stop_idx for s in request.stitched.script}
        if len(stops) != 1:
            raise ValueError(f"expected a single-stop request, got stops {stops}")
        idx = next(iter(stops))
        self.calls.append(idx)
        if idx not in self._by_stop:
            raise KeyError(f"replay cache miss for stop {idx} — fixtures stale; recapture")
        return self._by_stop[idx]


def _by_stop(script: Script) -> dict[int, tuple[Sentence, ...]]:
    out: dict[int, list[Sentence]] = {}
    for s in script.script:
        out.setdefault(s.stop_idx, []).append(s)
    return {k: tuple(v) for k, v in out.items()}


def test_the_fixture_actually_has_a_duplicate_to_fuse():
    # Guards against a vacuous eval: if the stitch had no duplicate, "fusion"
    # would be meaningless. The two cross-book beats MUST collide.
    m = compute_compose_metrics(_stitched(), _stitched(), SEQ, BEATS)
    assert m.stitched_dupe_pairs >= 1


def test_good_compose_passes_gate_and_scoreboard():
    stitched = _stitched()
    good = _fuse_stop0(stitched, drop_date=False)
    report = _verifier()(good)
    assert report.passed  # the real gate serves it
    m = compute_compose_metrics(stitched, good, SEQ, BEATS, report=report)
    assert quality_violations(m) == []
    assert m.composed_dupe_pairs < m.stitched_dupe_pairs  # it genuinely fused
    assert metric_regressions(m, m) == []


def test_dropped_date_passes_the_gate_but_the_scoreboard_catches_it():
    # THE point of the scoreboard: the gate is blind to a silently dropped date
    # (>0.34 of the claim tokens survive, and entailment only polices invention),
    # but the deterministic numeral diff is not.
    stitched = _stitched()
    regressed = _fuse_stop0(stitched, drop_date=True)
    report = _verifier()(regressed)
    assert report.passed  # <-- the existing gate does NOT catch it
    m = compute_compose_metrics(stitched, regressed, SEQ, BEATS, report=report)
    viols = quality_violations(m)
    assert any("dropped numerals" in v for v in viols)  # <-- the scoreboard does


def test_replay_runs_real_orchestration_at_zero_cost():
    stitched = _stitched()
    good = _fuse_stop0(stitched, drop_date=False)
    client = ReplayComposeClient(_by_stop(good))
    served = compose_script_per_chapter(
        stitched, SEQ, _route(), client=client, faithfulness_checker=MockFaithfulnessChecker(),
    )
    assert served.validation.passed
    assert quality_violations(compute_compose_metrics(stitched, served, SEQ, BEATS)) == []
    assert client.calls  # the real per-chapter path actually drove the client


def test_replay_hard_fails_on_a_cache_miss():
    stitched = _stitched()
    good = _fuse_stop0(stitched, drop_date=False)
    missing = {k: v for k, v in _by_stop(good).items() if k != 2}  # drop stop 2
    client = ReplayComposeClient(missing)
    with pytest.raises(KeyError):
        compose_script_per_chapter(
            stitched, SEQ, _route(), client=client,
            faithfulness_checker=MockFaithfulnessChecker(),
        )


def test_eval_never_touches_a_live_model(monkeypatch):
    # Strip the API key and force mock: the ENTIRE offline flow (stitch -> replay
    # compose -> real gate) must still complete. If any live Opus/Haiku call
    # sneaked into this path it would raise without a key, failing here — a real
    # guard, not a tautology.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("COMPOSE_PROVIDER", "mock")
    stitched = _stitched()
    good = _fuse_stop0(stitched, drop_date=False)
    served = compose_script_per_chapter(
        stitched, SEQ, _route(), client=ReplayComposeClient(_by_stop(good)),
        faithfulness_checker=MockFaithfulnessChecker(),
    )
    assert served.validation.passed


def test_fixtures_pinned_to_prompt():
    # If this fails, the compose or entailment prompt changed: review the
    # fixtures (and recapture any live goldens), then update PINNED_...
    assert compose_prompt_fingerprint() == PINNED_PROMPT_FINGERPRINT, (
        "compose/entailment prompt changed since these fixtures were authored — "
        "review tests/test_compose_quality_eval.py fixtures and rerun "
        "tools.compose_snapshot, then update PINNED_PROMPT_FINGERPRINT"
    )
