"""Tests for POST /audio/generate-trip/{trip_id} — primary-beat-only generation.

Since M0b each ItineraryItem carries one PLAYS_BEAT edge per narrated beat
(`beat_ids`, often 3+ per stop), but mobile polls and plays only the stop's
primary beat, and M7's COMPOSE layer replaces per-beat audio with one composed
MP3 per stop (specs/2026-06-12-tour-algorithm-decision/ALGORITHM-SPEC.md §2.5).
The endpoint must therefore TTS-generate ONLY each item's primary beat — never
the item's whole PLAYS_BEAT set.

Runs against the conftest test instance (port 7688) with the mock TTS provider
and a temp storage dir — no API keys, no live corpus.
"""

from __future__ import annotations

import pytest

from src.connection import get_database
from tests.conftest import needs_neo4j

TRIP_ID = "audio-trip-test-trip"
BEAT_PREFIX = "audio-trip-test-"

# Multi-beat M0b-style item: 3 PLAYS_BEAT edges, b1 is primary.
MULTI_PRIMARY = f"{BEAT_PREFIX}b1"
MULTI_SECONDARY = [f"{BEAT_PREFIX}b2", f"{BEAT_PREFIX}b3"]
# Legacy pre-M0b item: one PLAYS_BEAT edge, no primary_beat_id property.
LEGACY_BEAT = f"{BEAT_PREFIX}b-legacy"
# M0b-style item whose primary beat has no script_body.
NOSCRIPT_BEAT = f"{BEAT_PREFIX}b-noscript"


@pytest.fixture(autouse=True)
def _temp_audio_storage(monkeypatch, tmp_path):
    """Point audio storage at a temp dir so mock WAVs never land in the repo."""
    monkeypatch.setenv("AUDIO_STORAGE_PATH", str(tmp_path))
    monkeypatch.setenv("AUDIO_STORAGE", "local")


def _seed_trip(driver) -> None:
    """Create a deterministic trip: delete any residue, then build fresh.

    Stops: (1) multi-beat item with primary_beat_id, (2) legacy single-edge
    item without primary_beat_id, (3) item whose primary has no script_body,
    (4) item sharing the legacy item's beat as its primary — exercises the
    query's DISTINCT (a shared primary is generated once; without the dedup
    the second occurrence would hit generate_beat_audio's already-has-audio
    PipelineError and surface as failed). No beat starts with audio_url.
    """
    with driver.session(database=get_database()) as s:
        s.run(
            "MATCH (t:Trip {id: $tid}) "
            "OPTIONAL MATCH (t)-[:HAS_STOP]->(i:ItineraryItem) "
            "DETACH DELETE t, i",
            tid=TRIP_ID,
        )
        s.run(
            "MATCH (b:NarrativeBeat) WHERE b.id STARTS WITH $prefix DETACH DELETE b",
            prefix=BEAT_PREFIX,
        )
        s.run(
            """
            CREATE (t:Trip {id: $tid, name: 'Audio trip test', status: 'planning',
                            created_at: datetime()})
            CREATE (b1:NarrativeBeat {id: $b1, script_body: 'Primary beat one.'})
            CREATE (b2:NarrativeBeat {id: $b2, script_body: 'Secondary beat two.'})
            CREATE (b3:NarrativeBeat {id: $b3, script_body: 'Secondary beat three.'})
            CREATE (bl:NarrativeBeat {id: $bl, script_body: 'Legacy beat.'})
            CREATE (bn:NarrativeBeat {id: $bn})
            CREATE (multi:ItineraryItem {id: $tid + '-item-multi', sort_order: 1,
                                         beat_ids: [$b1, $b2, $b3],
                                         primary_beat_id: $b1})
            CREATE (legacy:ItineraryItem {id: $tid + '-item-legacy', sort_order: 2})
            CREATE (noscript:ItineraryItem {id: $tid + '-item-noscript', sort_order: 3,
                                            beat_ids: [$bn], primary_beat_id: $bn})
            CREATE (shared:ItineraryItem {id: $tid + '-item-shared', sort_order: 4,
                                          beat_ids: [$bl], primary_beat_id: $bl})
            CREATE (t)-[:HAS_STOP]->(multi)
            CREATE (t)-[:HAS_STOP]->(legacy)
            CREATE (t)-[:HAS_STOP]->(noscript)
            CREATE (t)-[:HAS_STOP]->(shared)
            CREATE (multi)-[:PLAYS_BEAT]->(b1)
            CREATE (multi)-[:PLAYS_BEAT]->(b2)
            CREATE (multi)-[:PLAYS_BEAT]->(b3)
            CREATE (legacy)-[:PLAYS_BEAT]->(bl)
            CREATE (noscript)-[:PLAYS_BEAT]->(bn)
            CREATE (shared)-[:PLAYS_BEAT]->(bl)
            """,
            tid=TRIP_ID,
            b1=MULTI_PRIMARY,
            b2=MULTI_SECONDARY[0],
            b3=MULTI_SECONDARY[1],
            bl=LEGACY_BEAT,
            bn=NOSCRIPT_BEAT,
        )


def _audio_urls(driver) -> dict[str, str | None]:
    """audio_url per seeded beat id, straight from the graph."""
    with driver.session(database=get_database()) as s:
        records = s.run(
            "MATCH (b:NarrativeBeat) WHERE b.id STARTS WITH $prefix "
            "RETURN b.id AS id, b.audio_url AS audio_url",
            prefix=BEAT_PREFIX,
        )
        return {r["id"]: r["audio_url"] for r in records}


@pytest.fixture()
def trip(clean_driver):
    _seed_trip(clean_driver)
    return TRIP_ID


@needs_neo4j
class TestGenerateTripAudioPrimaryOnly:
    def test_generates_only_primary_beats(self, client, clean_driver, trip):
        resp = client.post(
            f"/api/v1/audio/generate-trip/{trip}", json={"provider": "mock"}
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # One primary per stop: multi's primary + legacy's only beat generate;
        # the no-script primary is skipped. Secondaries never even appear, and
        # the legacy beat — primary of TWO items — is generated exactly once.
        assert data["generated"] == 2
        assert data["skipped"] == 1
        assert data["failed"] == 0
        beat_ids = [r["beat_id"] for r in data["results"]]
        assert beat_ids.count(LEGACY_BEAT) == 1, (
            "a primary shared by two items must be deduped, not generated per item"
        )
        by_beat = {r["beat_id"]: r for r in data["results"]}
        assert set(by_beat) == {MULTI_PRIMARY, LEGACY_BEAT, NOSCRIPT_BEAT}
        assert by_beat[MULTI_PRIMARY]["status"] == "generated"
        assert by_beat[LEGACY_BEAT]["status"] == "generated"
        assert by_beat[NOSCRIPT_BEAT]["status"] == "skipped"
        assert by_beat[NOSCRIPT_BEAT]["reason"] == "no script_body"

        urls = _audio_urls(clean_driver)
        assert urls[MULTI_PRIMARY], "primary beat must get audio"
        assert urls[LEGACY_BEAT], "legacy item's only beat must get audio"
        for beat_id in MULTI_SECONDARY:
            assert urls[beat_id] is None, (
                f"non-primary beat {beat_id} must NOT be generated — mobile "
                "never plays it and M7 COMPOSE supersedes per-beat audio"
            )

    def test_second_call_generates_nothing(self, client, trip):
        first = client.post(
            f"/api/v1/audio/generate-trip/{trip}", json={"provider": "mock"}
        )
        assert first.status_code == 200, first.text
        assert first.json()["generated"] == 2

        second = client.post(
            f"/api/v1/audio/generate-trip/{trip}", json={"provider": "mock"}
        )
        assert second.status_code == 200, second.text
        data = second.json()
        # Generated primaries now carry audio_url; only the no-script primary
        # still matches the needs-audio filter (and is skipped again).
        assert data["generated"] == 0
        assert data["failed"] == 0
        assert [r["beat_id"] for r in data["results"]] == [NOSCRIPT_BEAT]

    def test_unknown_trip_404(self, client, clean_driver):
        resp = client.post(
            "/api/v1/audio/generate-trip/no-such-trip", json={"provider": "mock"}
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()
