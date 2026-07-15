"""Unit test for the onboard CLI's ESTIMATE-ONLY ``--dry-run`` path.

Pure — fixture mode, no Neo4j, no network, $0. Run with:
    make test-file FILE=tests/test_onboard_cli_dryrun.py

``--dry-run`` runs the LIVE onboarding fetch/parse + assemble flow (honouring
``ONDOWAY_ONBOARD_HTTP``; here defaulted to ``fixture`` so it stays $0/offline)
and then PRINTS the POI count + the ESTIMATED beat-drafting cost, WITHOUT:

- drafting any beats — it never builds a drafter, so even
  ``ONBOARD_PROVIDER=anthropic`` (which would otherwise spend) is inert; and
- writing anything to disk — no ``data/{slug}/`` corpus, no registry entry.

The undo lever is assertion (b): if ``--dry-run`` were made to call
``write_city`` it would create ``data/london`` under the tmp root and the
"nothing written" assertion would go RED.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.onboard import beat_draft, cli


def test_dry_run_estimates_without_drafting_or_writing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    registry = tmp_path / "cities.json"
    monkeypatch.setenv("ONBOARD_DATA_ROOT", str(data_root))
    monkeypatch.setenv("ONBOARD_REGISTRY_PATH", str(registry))
    monkeypatch.setenv("ONDOWAY_ONBOARD_HTTP", "fixture")
    # A paid provider must be IRRELEVANT in dry-run — no drafter is ever built.
    monkeypatch.setenv("ONBOARD_PROVIDER", "anthropic")

    # Guard (c): dry-run must never call draft_all nor construct a paid drafter.
    calls = {"draft_all": 0, "anthropic_ctor": 0}
    real_draft_all = beat_draft.draft_all

    def _counting_draft_all(*args: object, **kwargs: object) -> list[dict]:
        calls["draft_all"] += 1
        return real_draft_all(*args, **kwargs)

    class _CountingAnthropic(beat_draft.AnthropicBeatDrafter):
        def __init__(self, *args: object, **kwargs: object) -> None:
            calls["anthropic_ctor"] += 1
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(beat_draft, "draft_all", _counting_draft_all)
    monkeypatch.setattr(beat_draft, "AnthropicBeatDrafter", _CountingAnthropic)

    rc = cli.main(["--city", "london", "--modes", "license_clean", "--dry-run"])
    out = capsys.readouterr().out

    # Exit 0 — a dry run has no gate to fail.
    assert rc == 0, out

    # (a) prints the POI count + an est_usd line. 35, not 36: STAGE A now drops the
    # administrative "London" city node (p31 Q515 city / Q5119 capital, and it
    # name-matches the city) — it must never be a tour STOP.
    match = re.search(r"POIs:\s+(\d+)", out)
    assert match is not None, out
    assert int(match.group(1)) == 35, out
    assert "est_usd" in out, out

    # (c) ZERO Anthropic work — no drafter built, no draft_all call.
    assert calls["draft_all"] == 0, out
    assert calls["anthropic_ctor"] == 0, out

    # (b) NOTHING written — no corpus dir, no registry file.
    assert not (data_root / "london").exists(), "dry-run must not write a city corpus"
    assert not registry.exists(), "dry-run must not touch the registry"
