"""Step 1.5d-2 — the standalone tour-preview page is served and wires the right
endpoints. Thin smoke test; the underlying /trips/preview + /audio/preview are
tested in test_trip_api.py / test_audio_*.py.
"""

from __future__ import annotations

from tests.conftest import needs_neo4j


@needs_neo4j
def test_tour_preview_page_is_served(client):
    resp = client.get("/tour-preview")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    assert "Tour Preview" in body
    # The page must wire the preview-narration + per-stop-audio endpoints.
    assert "/trips/preview" in body
    assert "/audio/preview" in body
