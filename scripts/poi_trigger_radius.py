"""Size each POI's FOOTPRINT — `trigger_radius` — by place kind, with the marquees reviewed
by name. Phase 7 S7.4 (design §5.6 C7; W7.2 R1). Deterministic, $0, re-runnable at will.

WHY. `trigger_radius` is how far from the pin a walker is AT the place: the audio placement
rule (src/tour/placement.py) puts it on the wire and the phone's one predicate reads it. The
Paris corpus carried the field on every record since the first upload and nothing read it
(plan defect 1); 177 of 370 records sat at the uploader's 10 m default — the Louvre, the
Orsay, Notre-Dame, the Pont Neuf, Sainte-Chapelle, Parc de la Villette among them — so the
phone drew one doorway for a 140 m square and a doorway alike. The W7.2 panel ruled 11/11
that "at the stop" is the place's own footprint (Nadia: the Place des Vosges is 140 m
across; Théo: Concorde's three positions; Aiko: "read the field, fix the 177 defaults").

WHAT IT WRITES, per POI in ``data/{slug}/poi-raw.json``:

- A record still at the uploader's default (``UPLOADER_DEFAULT_M``) — the mark of a record
  nobody sized — takes the footprint of its PLACE KIND from the one table
  (``scripts/geocode_pois.py::FOOTPRINT_BY_KIND``, reached through the one function
  ``trigger_radius_for`` — EXTENDED, never copied).
- A record named in ``REVIEWED`` takes the reviewed footprint, whatever it carried: the
  marquees and every stop of the eleven personas' days (W6.12 / W7.1), each with the
  sentence that argues it, written so someone who has never been to Paris can judge it.
- Every other record keeps its curated value (the area-radius fix of 2026-06-16, the
  geocoder's curated streets and squares) — this pass never lowers a reviewed-elsewhere
  number and never touches a record it has no reason for.
- The argument lands in ``_pipeline.trigger_radius_basis`` on the record, the audit trail
  (the ``geocode_audit.trigger_radius_reasoning`` precedent of the New York pass).

The write path (``load_pois`` / ``dump_pois``, the refuse-to-write-on-reformat guard) is
imported from the capacity pass, never copied. Then, AND MANDATORY: ``make sync-poi-exports``
— a field written here does not reach the export chunks, or the graph the API upload
builds, until that sync runs; `tests/test_export_consistency.py` now pins the two equal.

CARRIED (not this pass): a line for a street, a polygon for a cemetery or a garden's walls
(W7.2 R1 d — Théo, Greta, Sofia, Julien, Camille, Marcus); the corpus holds no such
geometry and the rule's ``kind`` field is where it lands.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from scripts.geocode_pois import FOOTPRINT_BY_KIND, trigger_radius_for
from scripts.poi_visit_duration import dump_pois, load_pois

ROOT = Path(__file__).resolve().parent.parent

#: The value `scripts/upload_paris.py` writes when a record carries none — a record still
#: at it was never sized.
UPLOADER_DEFAULT_M: int = 10

#: Cities whose corpus has been through THIS pass — the declaring act, read by the two
#: guards (tests/test_poi_trigger_radius.py, tests/test_export_consistency.py). Adding a
#: slug says "this city's footprints are sized and its export chunks carry them";
#: removing one to reach green is forbidden. New York is not here yet: its poi-raw.json
#: and 15 of its 34 export chunks pre-date the one serialiser (4-space files that
#: `dump_pois` refuses to reformat), so its pass is a normalise-then-sync job of its own.
CITIES_WITH_FOOTPRINTS: tuple[str, ...] = ("paris",)

#: THE REVIEWED FOOTPRINTS, by the corpus name, each with its argument. The marquees, the
#: W7.2 panel's named places, and every stop of the eleven personas' days
#: (evidence/phase7-audio/w71-trigger.tsv). Metres from the corpus pin.
REVIEWED: dict[str, tuple[int, str]] = {
    # W7.13 (the closing panel; Camille's "unreviewed footprint" CLASS): a value that
    # was neither the uploader's default nor on this list was never looked at. The two
    # instances the panel named, reviewed now; the class rule from here on: a stop the
    # visit GOES INSIDE must have a footprint that covers its BUILDING, or leaving the
    # circle happens indoors and the next leg piece can start under the roof (Marcus).
    "Jardin des Tuileries": (
        300,
        "The garden runs about 900 m gate to gate and the pin sits mid-garden: at the "
        "old 100 the Concorde gate stood 325 m outside the circle, so entering there "
        "played nothing for a five-minute walk (W7.13, Camille). 300 reaches the "
        "central alleys and both terraces — the Luxembourg's 390 is the precedent "
        "scale for a royal garden; the gates themselves are the carried polygon row.",
    ),
    "La Samaritaine": (
        60,
        "A four-building block about 100 m deep between rue de Rivoli and the quay: "
        "at the old 20 the circle sat inside the store, so the piece could only start "
        "indoors (W7.1's inverted-threshold list) and leaving the circle happened "
        "under the roof (W7.13, Marcus). 60 from the pin covers the street doors on "
        "all sides.",
    ),
    "Place des Vosges": (
        70,
        "A 140 m square: the arcade runs seventy metres from the central statue, and "
        "stepping under the arcade is being there (Nadia, W7.2 R1).",
    ),
    "Notre-Dame Cathedral": (
        100,
        "The pin sits in the building; the parvis where a walker stands runs about "
        "100 m west of the facade, so the footprint reaches it (Camille's pin check: "
        "the pin itself stays where the corpus put it — a carried data row).",
    ),
    "Louvre Museum": (
        120,
        "The Cour Napoleon around the pyramid is 150 m across and the Cour Carree "
        "another 120 m east of it: a walker at the Louvre is anywhere in those courts "
        "(Greta, Aiko).",
    ),
    "Musee d'Orsay": (
        60,
        "The forecourt between the river quay and the door is about 60 m deep; "
        "Rosemary's bench sits on it.",
    ),
    "Palais-Royal": (
        100,
        "The garden is 275 m by 100 m behind the Cour d'Honneur; Greta's columns, "
        "Aiko's no. 177 and the three galleries are all inside that footprint.",
    ),
    "Place de la Concorde": (
        120,
        "The square is 360 m by 210 m; Theo's three positions on it span the middle.",
    ),
    "Pont Neuf": (
        120,
        "The bridge is 238 m long across both arms of the river: its half-length from "
        "the Vert-Galant point is 120 m (Theo, Fiona & Dev, Sofia).",
    ),
    "Pere Lachaise Cemetery": (
        500,
        "Forty-four hectares inside walls; the 2026-06-16 area fix sized it at the "
        "setting cap and Julien's wall, the columbarium and the memorials are all "
        "inside it — kept (the walls themselves are a carried polygon row).",
    ),
    "Conciergerie": (
        40,
        "The quay facade is 100 m long; the entrance on the boulevard du Palais and "
        "the Seine-side view of the towers both count as being there.",
    ),
    "Sainte-Chapelle": (
        30,
        "Inside the Palais de Justice enclosure: the courtyard in front of the chapel "
        "door, reached through the security line — the line is the place.",
    ),
    "Palais de Justice": (
        40,
        "The boulevard du Palais front is 80 m of gilded gates; standing before them "
        "is being at the Palais (Fiona & Dev's and Sofia's days).",
    ),
    "Bourse de Commerce — Pinault Collection": (
        40,
        "A rotunda 60 m across with its portico and the Medici column on its flank "
        "(Aiko's day).",
    ),
    "Arc de Triomphe du Carrousel": (
        30,
        "A free-standing arch in the open Place du Carrousel: within thirty metres "
        "you are at it (Aiko's and Greta's days).",
    ),
    "Hotel de Ville": (
        60,
        "The parvis in front of the facade is 80 m deep; Paulo stands on it.",
    ),
    "Musee de l'Orangerie": (
        30,
        "A pavilion at the Tuileries' west end: the door on the terrace (Rosemary's day).",
    ),
    "Eiffel Tower": (
        80,
        "The four feet span a 125 m square; under the tower is at the tower.",
    ),
    "Arc de Triomphe": (
        60,
        "The arch stands in the Etoile roundabout; the pavement ring and the underpass "
        "mouths are fifty metres out.",
    ),
    "Sacre-Coeur Basilica": (
        50,
        "The parvis and the top of the stairs in front of the facade.",
    ),
    "Pantheon": (
        40,
        "The Place du Pantheon in front of the portico.",
    ),
    "Parc de la Villette": (
        300,
        "Fifty-five hectares of park; sized at a setting's cap, the way the cemeteries "
        "and the Luxembourg were.",
    ),
    "Centre Pompidou": (
        60,
        "The sloping piazza in front of the building is 60 m deep.",
    ),
    "Grand Palais": (
        60,
        "A 240 m nave; the avenue Winston-Churchill front and its steps.",
    ),
    "Petit Palais": (
        40,
        "The entrance portico on the avenue and the garden court behind it.",
    ),
    "Les Invalides": (
        60,
        "The cour d'honneur and the north front; the esplanade beyond is its own walk.",
    ),
    "Opéra Bastille": (
        40,
        "The curved glass front on the Place de la Bastille and its steps.",
    ),
    "Palais Garnier": (
        40,
        "The steps and the Place de l'Opera front.",
    ),
    "Place de la Bastille": (
        80,
        "A 200 m roundabout-square around the July Column.",
    ),
    "Place Vendome": (
        80,
        "224 m by 213 m with the column at its centre.",
    ),
    "Trocadero": (
        80,
        "The esplanade between the two wings is 150 m wide; the view of the tower is "
        "the whole of it.",
    ),
    "Cimetière de Passy": (
        80,
        "A walled cemetery of two hectares behind the Trocadero; the gate.",
    ),
    "Port de l'Arsenal": (
        100,
        "A 500 m marina basin; the quay along it.",
    ),
    "Rue de la Paix": (
        60,
        "A 230 m street of jewellers between the Opera and Vendome: half a block "
        "(Theo's day).",
    ),
    "Grands Boulevards": (
        75,
        "A two-kilometre arc of boulevards; 75 m is one block of them.",
    ),
    "Rue Montorgueil": (
        60,
        "A 400 m market street; half a block of it.",
    ),
    "Place de la Bourse": (
        40,
        "The open square in front of the Palais Brongniart's colonnade (Aiko's day).",
    ),
    "Passage des Panoramas": (
        60,
        "A passage under glass 133 m long: you are in it from either mouth (Aiko's arcades).",
    ),
    "Place de Louvois": (
        30,
        "A small square around its fountain, opposite the old library.",
    ),
    "Place du Caire": (
        20,
        "A small triangular place in front of the Egyptian facade.",
    ),
}


def size(poi: dict[str, Any]) -> tuple[int, str] | None:
    """The footprint this pass gives one record, with its argument — or None when the
    record keeps what it carries (a curated value nobody reviewed by name)."""
    name = str(poi.get("name", ""))
    if name in REVIEWED:
        return REVIEWED[name]
    if poi.get("trigger_radius", UPLOADER_DEFAULT_M) == UPLOADER_DEFAULT_M:
        return trigger_radius_for(
            name, UPLOADER_DEFAULT_M, place_category=poi.get("place_category") or None
        )
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--slug", default="paris", help="City slug (default: paris)")
    parser.add_argument("--dry-run", action="store_true", help="Print the table and write nothing.")
    args = parser.parse_args(argv)

    path = ROOT / "data" / args.slug / "poi-raw.json"
    if not path.exists():
        raise SystemExit(f"✗ no POI file at {path}")

    pois, original = load_pois(path)
    names = {str(p.get("name", "")) for p in pois}
    unknown = sorted(n for n in REVIEWED if n not in names)
    if unknown:
        raise SystemExit(
            "✗ the reviewed table names records that are not in the corpus "
            f"(renamed? misspelt?): {unknown}"
        )

    rows: list[tuple[str, str, int, int, str]] = []
    by_kind: dict[str, int] = dict.fromkeys(FOOTPRINT_BY_KIND, 0)
    reviewed_hits = 0
    for poi in pois:
        answer = size(poi)
        if answer is None:
            continue
        metres, basis = answer
        before = poi.get("trigger_radius")
        if before == metres and (poi.get("_pipeline") or {}).get("trigger_radius_basis") == basis:
            continue
        name = str(poi.get("name", ""))
        kind = poi.get("place_category") or "other"
        if name in REVIEWED:
            reviewed_hits += 1
        else:
            by_kind[kind] = by_kind.get(kind, 0) + 1
        rows.append((name, kind, before, metres, basis))
        poi["trigger_radius"] = metres
        poi.setdefault("_pipeline", {})["trigger_radius_basis"] = basis

    print(f"{len(pois)} POIs in {path.relative_to(ROOT)}; {len(rows)} footprint(s) to write.")
    print(f"  reviewed by name: {reviewed_hits}; sized by kind from the uploader's default:")
    for kind in FOOTPRINT_BY_KIND:
        if by_kind.get(kind):
            print(f"    {kind:9s} {by_kind[kind]:4d}  -> {FOOTPRINT_BY_KIND[kind]} m")
    for name, kind, before, metres, basis in rows:
        print(f"  {before!s:>4} -> {metres:>4} m  {kind:9s} {name}")
        print(f"                   {basis}")
    if args.dry_run:
        print("\nDry run. Nothing written.")
        return 0
    if not rows:
        print("Nothing to write: every footprint already carries this pass's answer.")
        return 0
    dump_pois(path, pois, original)
    print(f"\n✓ wrote {len(rows)} footprint(s) to {path.relative_to(ROOT)}")
    print(f"  NEXT, AND MANDATORY: make sync-poi-exports SLUG={args.slug}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
