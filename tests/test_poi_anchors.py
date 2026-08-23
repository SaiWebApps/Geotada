"""Phase 7 S7.7 (B) — THE REVIEWED ANCHORS of the marquee (design §5.6 "segments"; W7.2
R4, all eleven: segments ONLY where a person placed the coordinates, marquee anchors only,
Notre-Dame first — D8). The data guard: Notre-Dame's anchors in ``data/paris/poi-raw.json``
are inside the place's own footprint, each names the sub-locations it stands for and carries
its argument, the labels on its beats are all claimed, the interior is marked as such, and
the export chunks (what the workbench upload reads) carry the same anchors — the
``trigger_radius`` precedent (S7.4). Free tier: files only.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.sync_poi_exports import SYNCED_FIELDS
from src.tour.contract import Anchor
from src.tour.routing import haversine_m
from src.tour.selection import _decode_anchors

ROOT = Path(__file__).resolve().parent.parent
POI_RAW = ROOT / "data" / "paris" / "poi-raw.json"
BEATS = ROOT / "data" / "paris" / "beats.json"
EXPORT = ROOT / "data" / "paris" / "export"
MARQUEE = "Notre-Dame Cathedral"


def _record(name: str) -> dict:
    return next(p for p in json.loads(POI_RAW.read_text()) if p["name"] == name)


def test_notre_dame_s_anchors_are_placed_reviewed_and_inside_its_footprint():
    poi = _record(MARQUEE)
    raw = poi.get("anchors")
    assert isinstance(raw, list) and len(raw) >= 3, "the marquee carries no reviewed anchors"
    anchors = [Anchor.model_validate(a) for a in raw]
    labels = [a.label for a in anchors]
    assert len(set(labels)) == len(labels), "two anchors share a label"
    claimed: list[str] = []
    for a in anchors:
        assert a.basis.strip(), f"{a.label}: no argument"
        assert 10 <= a.radius_m <= float(poi["trigger_radius"]), a.label
        d = haversine_m(poi["latitude"], poi["longitude"], a.lat, a.lng)
        assert d <= float(poi["trigger_radius"]), f"{a.label} sits {d:.0f} m off the pin"
        assert a.sub_locations, f"{a.label} stands for nothing"
        claimed.extend(a.sub_locations)
    assert len(set(claimed)) == len(claimed), "a sub-location is claimed twice"
    # Every labelled Notre-Dame beat belongs to exactly one reviewed anchor.
    labelled = {
        b["sub_location"]
        for b in json.loads(BEATS.read_text())
        if b.get("poi_name") == MARQUEE and b.get("sub_location")
    }
    assert labelled <= set(claimed), f"unclaimed sub-locations: {sorted(labelled - set(claimed))}"
    # Under the roof is marked, and only under the roof.
    indoor = {a.label for a in anchors if a.indoor}
    assert indoor, "no interior anchor"
    for a in anchors:
        assert a.indoor == any(s.startswith(("interior", "choir")) for s in a.sub_locations), (
            a.label
        )


def test_the_anchors_reach_the_export_chunks_and_the_loader_reads_them():
    assert "anchors" in SYNCED_FIELDS
    poi = _record(MARQUEE)
    for chunk in sorted(EXPORT.glob("*.json")):
        for rec in json.loads(chunk.read_text()):
            if rec.get("name") == MARQUEE:
                assert rec.get("anchors") == poi["anchors"], chunk.name
                break
        else:
            continue
        break
    else:
        raise AssertionError("the marquee is in no export chunk")
    # The graph stores the list JSON-encoded (the opening_hours precedent); the
    # loader reads either form and tolerates the unloaded shapes.
    decoded = _decode_anchors(json.dumps(poi["anchors"]))
    assert [a.label for a in decoded] == [a["label"] for a in poi["anchors"]]
    assert _decode_anchors(poi["anchors"]) == decoded
    assert _decode_anchors(None) == () and _decode_anchors("") == () and _decode_anchors([]) == ()


def test_an_outdoor_anchor_is_sized_to_where_people_stand_to_look_at_it():
    """W7.11 defect 16 — the blind listening panel, 11/11 `circle_45m: too_tight`.

    The anchors were first placed at arm's length from the thing they name. Every one of
    the eleven said that is the wrong distance, because you do not look at a cathedral
    front from under it — you walk backwards until it fits. Greta: "To look at that front
    you walk backwards… I was most of the way back across the paving, near the little
    bronze star. Forty-five metres wide puts me almost under the doors, craning at
    stonework two feet from my nose." Paulo: "You cannot take the towers in from twenty
    metres… Then nothing plays, and the thing that would ruin it is that I would not know.
    Silence and 'there is nothing here' sound identical." Sofia: "Size the circle to where
    people stand to look, not to the doorstep." Aiko: "my diagonal keeps me fifty metres
    out. I clip nothing, so I hear nothing."

    THE RULE, as a number a reviewer can check: an OUTDOOR anchor's circle covers at least
    half the place's own footprint — the standing-back distance, not the doorstep. An
    INDOOR anchor is exempt: it is offered on the screen and tapped, because GPS is useless
    under a roof (W7.2 R4), so its radius decides nothing.
    """
    poi = _record(MARQUEE)
    footprint = float(poi["trigger_radius"])
    anchors = [Anchor.model_validate(a) for a in poi["anchors"]]
    outdoor = [a for a in anchors if not a.indoor]
    assert outdoor, "the marquee has no outdoor anchor to stand at"
    for a in outdoor:
        assert a.radius_m >= footprint / 2, (
            f"{a.label}: {a.radius_m:.0f} m round a {footprint:.0f} m place is the "
            "doorstep, not where a person stands to look at it (W7.11, 11/11)"
        )
        assert "stand" in a.basis.lower() or "look" in a.basis.lower(), (
            f"{a.label}: the basis must say where a person STANDS to look at it"
        )
