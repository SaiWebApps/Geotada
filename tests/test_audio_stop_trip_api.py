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

# A separate trip whose stops play real NarrativeBeats — used by the unknown-
# provider tests for /audio/generate-trip and /audio/generate-batch (both go
# through generate_beat_audio, not generate_stop_audio).
BEATS_TRIP_ID = "stop-audio-beats-trip"
BEATS_PREFIX = "stop-audio-beats-"


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


def _seed_beats(driver) -> None:
    """A trip whose one stop's primary beat has a script_body — so both
    /audio/generate-trip and /audio/generate-batch have a beat to voice."""
    beat_id = f"{BEATS_PREFIX}b1"
    with driver.session(database=get_database()) as s:
        s.run(
            "MATCH (t:Trip {id: $tid}) OPTIONAL MATCH (t)-[:HAS_STOP]->(i:ItineraryItem) "
            "DETACH DELETE t, i",
            tid=BEATS_TRIP_ID,
        )
        s.run(
            "MATCH (b:NarrativeBeat) WHERE b.id STARTS WITH $prefix DETACH DELETE b",
            prefix=BEATS_PREFIX,
        )
        s.run(
            """
            CREATE (t:Trip {id: $tid, name: 'Beats trip', status: 'planning',
                            created_at: datetime()})
            CREATE (b1:NarrativeBeat {id: $b1, script_body: 'Welcome to this stop.'})
            CREATE (i1:ItineraryItem {id: $tid + '-item1', sort_order: 1,
                                      beat_ids: [$b1], primary_beat_id: $b1})
            CREATE (t)-[:HAS_STOP]->(i1)
            CREATE (i1)-[:PLAYS_BEAT]->(b1)
            """,
            tid=BEATS_TRIP_ID,
            b1=beat_id,
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

    def test_edited_narration_invalidates_its_stop_audio(
        self, client, clean_driver, _temp_audio_storage
    ):
        """Rewriting a stop's narration must re-voice THAT stop and only it.

        The per-stop path was the one generation path with no content hash, so
        "has a url" was the whole staleness test: an edited stop kept playing the
        old recording forever. Phase 2 is that defect. Phase 3 is the pre-existing
        self-heal (a row whose bytes vanished off disk must still re-voice), which
        now shares an `and` chain with the new hash term and must survive it.
        """
        item1 = f"{TRIP_ID}-item1"
        item2 = f"{TRIP_ID}-item2"
        edited = "Settle in. Welcome to the Eiffel Tower, rewritten."

        def _stored_hash(stop_id: str) -> str | None:
            with clean_driver.session(database=get_database()) as s:
                rec = s.run(
                    "MATCH (i:ItineraryItem {id: $sid}) RETURN i.audio_script_hash AS h",
                    sid=stop_id,
                ).single()
            return rec["h"] if rec else None

        # ── Phase 1 — baseline: both narrated stops voiced, and hashed.
        _seed(clean_driver)
        recorder1 = _Recorder()
        with patch("src.audio.pipeline.get_provider", return_value=recorder1):
            first = client.post(
                f"/api/v1/audio/generate-trip-stops/{TRIP_ID}", json={"provider": "mock"}
            )
        assert first.status_code == 200, first.text
        assert first.json()["generated"] == 2, first.text

        stored = _stored_hash(item1)
        assert isinstance(stored, str) and len(stored) == 64, (
            f"no content hash recorded for {item1} (got {stored!r}) — without one, "
            "an edited narration can never be detected as stale"
        )

        # ── Phase 2 — rewrite item1's narration only (AC-25, AC-26).
        with clean_driver.session(database=get_database()) as s:
            s.run(
                "MATCH (i:ItineraryItem {id: $sid}) SET i.narration = $n",
                sid=item1,
                n=edited,
            )
        recorder2 = _Recorder()
        with patch("src.audio.pipeline.get_provider", return_value=recorder2):
            second = client.post(
                f"/api/v1/audio/generate-trip-stops/{TRIP_ID}", json={"provider": "mock"}
            )
        assert second.status_code == 200, second.text
        data = second.json()
        by_stop = {r["stop_id"]: r for r in data["results"]}

        assert data["generated"] == 1, f"only the edited stop may re-voice: {data}"
        assert by_stop[item1]["status"] == "generated", by_stop[item1]
        assert data["skipped"] == 2, f"the untouched stops must both skip: {data}"
        assert by_stop[item2]["status"] == "skipped", by_stop[item2]
        assert by_stop[item2]["reason"] == "already has audio", by_stop[item2]
        assert recorder2.texts == [edited], (
            f"the provider must be handed the rewritten text exactly once: {recorder2.texts}"
        )

        # ── Phase 3 — the self-heal still fires beside the new hash term.
        urls = _item_audio(clean_driver)
        artifact = _temp_audio_storage / urls[item2].removeprefix("/api/v1/audio/files/")
        assert artifact.exists(), f"phase-3 setup found no artifact at {artifact}"
        artifact.unlink()
        assert not artifact.exists()

        recorder3 = _Recorder()
        with patch("src.audio.pipeline.get_provider", return_value=recorder3):
            third = client.post(
                f"/api/v1/audio/generate-trip-stops/{TRIP_ID}", json={"provider": "mock"}
            )
        assert third.status_code == 200, third.text
        third_by_stop = {r["stop_id"]: r for r in third.json()["results"]}
        assert third_by_stop[item2]["status"] == "generated", (
            "a stop whose stored bytes vanished must re-voice even though its "
            f"hash is current — the self-heal must survive: {third_by_stop[item2]}"
        )
        assert recorder3.texts == [N2], recorder3.texts

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

    def test_second_call_returns_cached_url_no_retts(
        self, client, clean_driver, _temp_audio_storage
    ):
        """Defect 11: a repeat keep-exploring for the same stop must return the
        cached url WITHOUT re-invoking paid TTS (cost / DoS guard). The mock
        provider's call count proves the second call never voices again."""
        _seed(clean_driver)
        item1 = f"{TRIP_ID}-item1"
        recorder = _Recorder()
        with patch("src.audio.pipeline.get_provider", return_value=recorder):
            first = client.post(
                f"/api/v1/audio/stops/{item1}/keep-exploring", json={"provider": "mock"}
            )
            assert first.status_code == 200, first.text
            first_data = first.json()
            assert first_data["status"] == "generated"
            assert len(recorder.texts) == 1  # TTS ran exactly once

            second = client.post(
                f"/api/v1/audio/stops/{item1}/keep-exploring", json={"provider": "mock"}
            )
        assert second.status_code == 200, second.text
        second_data = second.json()
        # Same url returned, but TTS was NOT invoked a second time.
        assert second_data["audio_url"] == first_data["audio_url"]
        assert second_data["duration_sec"] == first_data["duration_sec"]
        assert len(recorder.texts) == 1, "cached hit must not re-run TTS"

    def test_different_voice_invalidates_cache(
        self, client, clean_driver, _temp_audio_storage
    ):
        """Defect 1: the keep-exploring TTS cache is keyed on the narration hash
        ONLY. A second call for the SAME narration but a DIFFERENT voice_id must
        NOT hit the cache — otherwise the client silently receives audio voiced
        with the ORIGINAL voice. The mock provider's call count proves the second
        (different-voice) call re-runs TTS instead of serving the cached url."""
        _seed(clean_driver)
        item1 = f"{TRIP_ID}-item1"
        recorder = _Recorder()
        with patch("src.audio.pipeline.get_provider", return_value=recorder):
            first = client.post(
                f"/api/v1/audio/stops/{item1}/keep-exploring",
                json={"provider": "mock", "voice_id": "alice"},
            )
            assert first.status_code == 200, first.text
            assert first.json()["status"] == "generated"
            assert len(recorder.texts) == 1  # TTS ran exactly once

            # Same narration, DIFFERENT voice — must not be served from cache.
            second = client.post(
                f"/api/v1/audio/stops/{item1}/keep-exploring",
                json={"provider": "mock", "voice_id": "bob"},
            )
        assert second.status_code == 200, second.text
        assert second.json()["status"] == "generated"
        assert len(recorder.texts) == 2, "a different voice_id must invalidate the cache"

    def test_force_regenerates_even_when_cached(
        self, client, clean_driver, _temp_audio_storage
    ):
        """Defect 11: force=True bypasses the cache and re-voices."""
        _seed(clean_driver)
        item1 = f"{TRIP_ID}-item1"
        recorder = _Recorder()
        with patch("src.audio.pipeline.get_provider", return_value=recorder):
            first = client.post(
                f"/api/v1/audio/stops/{item1}/keep-exploring", json={"provider": "mock"}
            )
            assert first.status_code == 200, first.text
            assert len(recorder.texts) == 1

            forced = client.post(
                f"/api/v1/audio/stops/{item1}/keep-exploring",
                json={"provider": "mock", "force": True},
            )
        assert forced.status_code == 200, forced.text
        assert forced.json()["status"] == "generated"
        assert len(recorder.texts) == 2, "force=True must re-run TTS"

    def test_changed_extra_narration_invalidates_cache(
        self, client, clean_driver, _temp_audio_storage
    ):
        """Defect 11: if extra_narration changes, the cached url is stale and
        must be regenerated (hash-based invalidation), not served."""
        _seed(clean_driver)
        item1 = f"{TRIP_ID}-item1"
        recorder = _Recorder()
        with patch("src.audio.pipeline.get_provider", return_value=recorder):
            first = client.post(
                f"/api/v1/audio/stops/{item1}/keep-exploring", json={"provider": "mock"}
            )
            assert first.status_code == 200, first.text
            assert len(recorder.texts) == 1

            # Mutate the stop's extra_narration underneath the cache.
            with clean_driver.session(database=get_database()) as s:
                s.run(
                    "MATCH (i:ItineraryItem {id: $sid}) SET i.extra_narration = $new",
                    sid=item1,
                    new="A completely different deep dive about the ironwork.",
                )
            second = client.post(
                f"/api/v1/audio/stops/{item1}/keep-exploring", json={"provider": "mock"}
            )
        assert second.status_code == 200, second.text
        assert second.json()["status"] == "generated"
        assert len(recorder.texts) == 2, "changed narration must invalidate cache"

    def test_over_cap_extra_narration_is_bounded(
        self, client, clean_driver, _temp_audio_storage
    ):
        """Defect 17: an over-cap extra_narration must not fan out into unbounded
        TTS. The input handed to TTS is capped at the same 20000-char limit the
        other audio endpoints enforce (AudioPreviewRequest)."""
        _seed(clean_driver)
        item1 = f"{TRIP_ID}-item1"
        # 30k chars of full sentences — well past the 20000 cap.
        huge = ("The tower rises above Paris. " * 1100).strip()
        assert len(huge) > 20000
        with clean_driver.session(database=get_database()) as s:
            s.run(
                "MATCH (i:ItineraryItem {id: $sid}) SET i.extra_narration = $new",
                sid=item1,
                new=huge,
            )
        recorder = _Recorder()
        with patch("src.audio.pipeline.get_provider", return_value=recorder):
            resp = client.post(
                f"/api/v1/audio/stops/{item1}/keep-exploring", json={"provider": "mock"}
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "generated"
        # The text handed to TTS is capped: never longer than the input we sent,
        # and no longer than the enforced 20000-char limit.
        assert recorder.texts, "TTS should still run on capped input"
        voiced = recorder.texts[0]
        assert len(voiced) <= 20000, f"extra_narration must be capped, got {len(voiced)}"


@needs_neo4j
class TestUnknownProviderNever500:
    """Defects 7/8/10/14: an unknown provider name must be a soft per-stop/beat
    failure, never an uncaught ValueError → 500. Each of the four routes that
    catch only PipelineError is exercised with {"provider": "evil"} against the
    REAL get_provider (no patch) so the unknown-provider ValueError actually
    fires at its true source (pipeline.get_provider)."""

    def test_keep_exploring_unknown_provider_soft_fails(
        self, client, clean_driver, _temp_audio_storage
    ):
        _seed(clean_driver)
        item1 = f"{TRIP_ID}-item1"
        resp = client.post(
            f"/api/v1/audio/stops/{item1}/keep-exploring", json={"provider": "evil"}
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "failed"
        assert data["audio_url"] is None
        assert data["error"] and "evil" in data["error"].lower()

    def test_generate_trip_stops_unknown_provider_soft_fails(
        self, client, clean_driver, _temp_audio_storage
    ):
        _seed(clean_driver)
        resp = client.post(
            f"/api/v1/audio/generate-trip-stops/{TRIP_ID}", json={"provider": "evil"}
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # Two stops carry narration; both fail (unknown provider), none succeed.
        assert data["generated"] == 0
        assert data["failed"] == 2
        for item in data["results"]:
            if item["status"] == "failed":
                assert "evil" in (item["error"] or "").lower()

    def test_generate_trip_unknown_provider_soft_fails(
        self, client, clean_driver, _temp_audio_storage
    ):
        _seed_beats(clean_driver)
        resp = client.post(
            f"/api/v1/audio/generate-trip/{BEATS_TRIP_ID}", json={"provider": "evil"}
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["generated"] == 0
        assert data["failed"] >= 1
        for item in data["results"]:
            if item["status"] == "failed":
                assert "evil" in (item["error"] or "").lower()

    def test_generate_batch_unknown_provider_soft_fails(
        self, client, clean_driver, _temp_audio_storage
    ):
        _seed_beats(clean_driver)
        resp = client.post(
            "/api/v1/audio/generate-batch", json={"provider": "evil"}
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["succeeded"] == 0
        assert data["failed"] >= 1
        for item in data["results"]:
            if not item["success"]:
                assert "evil" in (item["error"] or "").lower()
