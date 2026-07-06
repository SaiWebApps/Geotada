"""Step 1.4a — POST /audio/generate-trip-stops/{trip_id}: per-stop narration audio.

Integration tests through the real endpoint + real LocalStorageProvider (tmp dir).
A recording provider captures the text actually sent to TTS, proving each stop is
voiced from its stitched `narration` (Step 1.2) and the artifact is persisted on
the ItineraryItem, keyed by the stop id (not the beat).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.audio.provider import MockTTSProvider
from src.connection import get_database
from tests.conftest import needs_neo4j

TRIP_ID = "stop-audio-test-trip"
N1 = "Settle in. Welcome to the Eiffel Tower."
N2 = "Now walk on to the Arc de Triomphe."
# KE3: item1 also carries a "keep exploring here" extra narration; item2 does not.
KE_EXTRA = "The tower has three visitor levels. The top is 276 metres up."


class _Recorder:
    """Records each text sent to TTS; returns a valid (silent) WAV via the mock."""

    def __init__(self) -> None:
        self.texts: list[str] = []

    @property
    def name(self) -> str:
        return "mock"

    def generate(self, text: str, *, voice_id: str | None = None) -> bytes:
        self.texts.append(text)
        return MockTTSProvider().generate(text)


@pytest.fixture(autouse=True)
def _temp_audio_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("AUDIO_STORAGE_PATH", str(tmp_path))
    monkeypatch.setenv("AUDIO_STORAGE", "local")
    return tmp_path


def _seed(driver) -> None:
    with driver.session(database=get_database()) as s:
        s.run(
            "MATCH (t:Trip {id: $tid}) OPTIONAL MATCH (t)-[:HAS_STOP]->(i:ItineraryItem) "
            "DETACH DELETE t, i",
            tid=TRIP_ID,
        )
        # clean_driver is module-scoped (no per-test wipe); remove this trip's
        # POIs too so re-seeding in a second test doesn't hit the POI.id uniqueness
        # constraint.
        s.run(
            "MATCH (p:POI) WHERE p.id STARTS WITH $prefix DETACH DELETE p",
            prefix=f"{TRIP_ID}-poi",
        )
        s.run(
            """
            CREATE (t:Trip {id: $tid, name: 'Stop audio test', status: 'planning',
                            created_at: datetime()})
            CREATE (p1:POI {id: $tid + '-poi1', name: 'Eiffel Tower'})
            CREATE (p2:POI {id: $tid + '-poi2', name: 'Arc de Triomphe'})
            CREATE (i1:ItineraryItem {id: $tid + '-item1', sort_order: 1, narration: $n1,
                                      extra_narration: $ke})
            CREATE (i2:ItineraryItem {id: $tid + '-item2', sort_order: 2, narration: $n2})
            CREATE (i3:ItineraryItem {id: $tid + '-item3', sort_order: 3})
            CREATE (t)-[:HAS_STOP]->(i1)
            CREATE (t)-[:HAS_STOP]->(i2)
            CREATE (t)-[:HAS_STOP]->(i3)
            CREATE (i1)-[:AT_POI]->(p1)
            CREATE (i2)-[:AT_POI]->(p2)
            """,
            tid=TRIP_ID,
            n1=N1,
            n2=N2,
            ke=KE_EXTRA,
        )


def _item_audio(driver) -> dict[str, str | None]:
    with driver.session(database=get_database()) as s:
        records = s.run(
            "MATCH (t:Trip {id: $tid})-[:HAS_STOP]->(i:ItineraryItem) "
            "RETURN i.id AS id, i.audio_url AS audio_url",
            tid=TRIP_ID,
        )
        return {r["id"]: r["audio_url"] for r in records}


@needs_neo4j
class TestGenerateTripStopAudio:
    def test_generates_one_artifact_per_stop_from_narration(
        self, client, clean_driver, _temp_audio_storage
    ):
        _seed(clean_driver)
        recorder = _Recorder()
        with patch("src.audio.pipeline.get_provider", return_value=recorder):
            resp = client.post(
                f"/api/v1/audio/generate-trip-stops/{TRIP_ID}", json={"provider": "mock"}
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # Two stops have narration → generated; the third (no narration) → skipped.
        assert data["generated"] == 2
        assert data["skipped"] == 1
        assert data["failed"] == 0

        # The exact stitched narration is voiced — not a lone beat.
        assert set(recorder.texts) == {N1, N2}

        # Audio persisted on each item, keyed by the stop id (not the beat).
        urls = _item_audio(clean_driver)
        assert urls[f"{TRIP_ID}-item1"] and f"{TRIP_ID}-item1" in urls[f"{TRIP_ID}-item1"]
        assert urls[f"{TRIP_ID}-item2"] and f"{TRIP_ID}-item2" in urls[f"{TRIP_ID}-item2"]
        assert urls[f"{TRIP_ID}-item3"] is None

        # One artifact per generated stop on disk.
        files = list(_temp_audio_storage.rglob("*.mp3"))
        assert len(files) == 2

    def test_second_call_skips_existing(self, client, clean_driver, _temp_audio_storage):
        _seed(clean_driver)
        with patch("src.audio.pipeline.get_provider", return_value=_Recorder()):
            first = client.post(
                f"/api/v1/audio/generate-trip-stops/{TRIP_ID}", json={"provider": "mock"}
            )
            assert first.status_code == 200, first.text
            assert first.json()["generated"] == 2

            second = client.post(
                f"/api/v1/audio/generate-trip-stops/{TRIP_ID}", json={"provider": "mock"}
            )
        assert second.status_code == 200, second.text
        data = second.json()
        assert data["generated"] == 0
        assert data["failed"] == 0
        assert data["skipped"] == 3  # 2 already have audio + 1 has no narration

    def test_unknown_trip_404(self, client):
        resp = client.post(
            "/api/v1/audio/generate-trip-stops/no-such-trip", json={"provider": "mock"}
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


@needs_neo4j
class TestStopAudioStatus:
    def test_status_false_before_and_true_after_generation(
        self, client, clean_driver, _temp_audio_storage
    ):
        _seed(clean_driver)
        item1 = f"{TRIP_ID}-item1"

        before = client.get(f"/api/v1/audio/stop-status/{item1}")
        assert before.status_code == 200, before.text
        assert before.json()["has_audio"] is False
        assert before.json()["audio_url"] is None

        with patch("src.audio.pipeline.get_provider", return_value=_Recorder()):
            gen = client.post(
                f"/api/v1/audio/generate-trip-stops/{TRIP_ID}", json={"provider": "mock"}
            )
        assert gen.status_code == 200, gen.text

        after = client.get(f"/api/v1/audio/stop-status/{item1}")
        assert after.status_code == 200, after.text
        data = after.json()
        assert data["has_audio"] is True
        assert data["audio_url"] and item1 in data["audio_url"]
        assert data["duration_sec"] and data["duration_sec"] > 0

    def test_unknown_stop_404(self, client):
        resp = client.get("/api/v1/audio/stop-status/no-such-stop")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


@needs_neo4j
class TestKeepExploringStopAudio:
    """KE3: POST /audio/stops/{stop_id}/keep-exploring — on-demand extra audio."""

    def test_voices_extra_narration_off_budget(
        self, client, clean_driver, _temp_audio_storage
    ):
        _seed(clean_driver)
        item1 = f"{TRIP_ID}-item1"
        recorder = _Recorder()
        with patch("src.audio.pipeline.get_provider", return_value=recorder):
            resp = client.post(
                f"/api/v1/audio/stops/{item1}/keep-exploring", json={"provider": "mock"}
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "generated"
        assert data["stop_id"] == item1
        # The persisted extra_narration was voiced — verbatim, not the tour narration.
        assert recorder.texts == [KE_EXTRA]
        assert data["audio_url"] and item1 in data["audio_url"]
        assert data["duration_sec"] and data["duration_sec"] > 0
        # Served OFF the tour budget: the item's scheduled tour audio is untouched.
        assert _item_audio(clean_driver)[item1] is None

    def test_stop_without_extras_is_409(self, client, clean_driver, _temp_audio_storage):
        _seed(clean_driver)
        item2 = f"{TRIP_ID}-item2"  # has narration but no extra_narration
        resp = client.post(
            f"/api/v1/audio/stops/{item2}/keep-exploring", json={"provider": "mock"}
        )
        assert resp.status_code == 409, resp.text
        assert "keep-exploring" in resp.json()["detail"].lower()

    def test_unknown_stop_is_404(self, client, clean_driver, _temp_audio_storage):
        _seed(clean_driver)
        resp = client.post(
            "/api/v1/audio/stops/no-such-stop/keep-exploring", json={"provider": "mock"}
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_tts_failure_returns_200_failed(self, client, clean_driver, _temp_audio_storage):
        """Per audio.py's contract, a TTS failure is a soft 200 status='failed',
        never a 500 — the client can retry the on-demand deep dive."""
        _seed(clean_driver)
        item1 = f"{TRIP_ID}-item1"
        from src.audio.provider import TTSError

        class _Boom:
            name = "mock"

            def generate(self, text, *, voice_id=None):
                raise TTSError("provider exploded")

        with patch("src.audio.pipeline.get_provider", return_value=_Boom()):
            resp = client.post(
                f"/api/v1/audio/stops/{item1}/keep-exploring", json={"provider": "mock"}
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "failed"
        assert data["audio_url"] is None
        assert data["error"]
