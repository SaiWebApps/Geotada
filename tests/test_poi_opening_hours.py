"""Structural guard on per-POI opening hours in `data/{city}/poi-raw.json`.

Three fields say WHEN a place can be entered (redesign data row 6.1 — "Aiko's
locked door, Rosemary's Tuesday", specs/2026-08-07-tour-algorithm-redesign):

  `opening_hours`         dict | None  Week table: all seven keys `mon`..`sun`,
                                       each a list of ["HH:MM","HH:MM"] open
                                       windows; [] = closed that whole day.
                                       None = NOT GATED (a street, a square, a
                                       bridge) — the same load-bearing null
                                       `visit_seconds_inside` uses.
  `opening_hours_source`  str | None   "osm" | "ai" when hours exist; None when
                                       the place is not gated.
  `opening_hours_basis`   str          One sentence arguing for the table (or
                                       for the null), judgeable by someone who
                                       has never been to the city.

WHAT THIS FILE CHECKS, AND WHAT IT DELIBERATELY DOES NOT. Every assertion is
STRUCTURAL — shape, presence, window sanity. None is knowledge-based: nobody in
this repo can adjudicate whether a particular museum really closes on Tuesday
(`tests/test_poi_visit_duration.py` records the same rule, and its command doc
forbids knowledge tests in writing). The basis sentence plus human review is the
mechanism for wrong-but-well-formed tables; do not add a test asserting a
particular POI's real hours.

Mirrors `tests/test_poi_visit_duration.py` (whose header invites the sibling).
Runs in milliseconds with no database.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "data"

DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

# Cities whose corpus has been through the opening-hours pass and must therefore
# satisfy every data check below. Explicit allow-list, exactly like
# CITIES_WITH_VISIT_CAPACITY in the sibling file: listing a city that has not
# run the pass would make this file permanently red and train readers to ignore
# it. EMPTY until the first pass runs (Phase 1's W1.8 adds "paris").
#
# ADDING a slug here is the deliberate act of declaring "this city's hours are
# in". REMOVING one to reach green is forbidden — it deletes the guard instead
# of fixing the data.
CITIES_WITH_OPENING_HOURS: tuple[str, ...] = ("paris",)


def _pois(city: str) -> list[dict]:
    return json.loads((DATA_ROOT / city / "poi-raw.json").read_text())


def _name(poi: dict) -> str:
    return str(poi.get("name", "<unnamed POI>"))


def _fail(city: str, headline: str, offenders: list[str], remedy: str) -> None:
    shown = offenders[:20]
    more = f"\n  ... and {len(offenders) - len(shown)} more" if len(offenders) > len(shown) else ""
    pytest.fail(
        f"{city}: {headline} ({len(offenders)} of them)\n"
        + "\n".join(f"  {line}" for line in shown)
        + more
        + f"\n{remedy}"
    )


REMEDY = "Run the opening-hours pass: `make poi-opening-hours SLUG=<city>`."


def test_every_poi_records_whether_it_is_gated() -> None:
    """Presence check #1 — the pass ran. Every POI carries the `opening_hours`
    KEY (null is a legitimate value meaning "not gated"; a missing key means
    the pass never reached this POI). On an unpriced corpus this is the check
    that goes red, which is what stops the other bars reading vacuously green.
    """
    for city in CITIES_WITH_OPENING_HOURS:
        offenders = [_name(p) for p in _pois(city) if "opening_hours" not in p]
        if offenders:
            _fail(city, "POI(s) the opening-hours pass never reached", offenders, REMEDY)


def test_every_poi_explains_its_opening_hours() -> None:
    """Presence check #2 — every table AND every null ships with the sentence
    that argues for it. A bare null cannot be told from a shrug without it."""
    for city in CITIES_WITH_OPENING_HOURS:
        offenders = [
            f"{_name(p)}: opening_hours_basis={p.get('opening_hours_basis')!r}"
            for p in _pois(city)
            if not isinstance(p.get("opening_hours_basis"), str)
            or not p.get("opening_hours_basis", "").strip()
        ]
        if offenders:
            _fail(city, "POI(s) whose opening hours carry no reasoning", offenders, REMEDY)


def test_every_gated_poi_carries_a_source_and_a_basis() -> None:
    """A non-null table must say where it came from ("osm" | "ai") and why.

    The basis clause deliberately duplicates the presence check above: a guard
    that goes quiet when its data disappears is not a guard
    (`tests/test_poi_visit_duration.py` records the same duplication rule).
    """
    for city in CITIES_WITH_OPENING_HOURS:
        offenders = []
        for poi in _pois(city):
            if poi.get("opening_hours") is None:
                continue
            source = poi.get("opening_hours_source")
            basis = poi.get("opening_hours_basis")
            if source not in ("osm", "ai"):
                offenders.append(f"{_name(poi)}: opening_hours_source={source!r}")
            if not isinstance(basis, str) or not basis.strip():
                offenders.append(f"{_name(poi)}: opening_hours_basis={basis!r}")
        if offenders:
            _fail(city, "gated POI(s) with no source or no basis", offenders, REMEDY)


def test_opening_tables_parse() -> None:
    """Every non-null table has exactly the seven day keys and well-formed
    ["HH:MM","HH:MM"] windows — the shape the clock filter (S1.6) parses."""
    for city in CITIES_WITH_OPENING_HOURS:
        offenders = []
        for poi in _pois(city):
            hours = poi.get("opening_hours")
            if hours is None or "opening_hours" not in poi:
                continue
            if not isinstance(hours, dict) or set(hours) != set(DAY_KEYS):
                offenders.append(
                    f"{_name(poi)}: keys="
                    f"{sorted(hours) if isinstance(hours, dict) else hours!r}"
                )
                continue
            for day in DAY_KEYS:
                windows = hours[day]
                if not isinstance(windows, list):
                    offenders.append(f"{_name(poi)}: {day} is not a list")
                    continue
                for window in windows:
                    if (
                        not isinstance(window, list)
                        or len(window) != 2
                        or not all(
                            isinstance(t, str) and len(t) == 5 and t[2] == ":" for t in window
                        )
                    ):
                        offenders.append(f"{_name(poi)}: {day} window {window!r}")
        if offenders:
            _fail(city, "POI(s) whose opening table does not parse", offenders, REMEDY)


def test_no_zero_length_open_window() -> None:
    """No open window may be zero-length or backwards: a window that ends when
    it starts admits nobody, and the clock filter would read it as 'open'."""
    for city in CITIES_WITH_OPENING_HOURS:
        offenders = []
        for poi in _pois(city):
            hours = poi.get("opening_hours")
            if not isinstance(hours, dict):
                continue
            for day, windows in hours.items():
                if not isinstance(windows, list):
                    continue
                for window in windows:
                    if (
                        isinstance(window, list)
                        and len(window) == 2
                        and all(isinstance(t, str) for t in window)
                        and window[0] >= window[1]
                    ):
                        offenders.append(f"{_name(poi)}: {day} {window!r}")
        if offenders:
            _fail(city, "POI(s) with a zero-length or backwards open window", offenders, REMEDY)


# ---------------------------------------------------------------------------
# The plumbing: the same three hops the visit-capacity fields travel, tested
# ONE AT A TIME so a failure names the hop that ate the field
# (`tests/test_poi_visit_duration.py` is the pattern). `place_category`
# (data row 6.7) rides the identical plumbing and is asserted alongside.
# ---------------------------------------------------------------------------

CLOCK_FIELDS = (
    "opening_hours",
    "opening_hours_source",
    "opening_hours_basis",
    "place_category",
)


def test_hop_1_the_corpus_query_asks_the_graph_for_the_clock_fields() -> None:
    """HOP 1 — `LOAD_PARIS_POIS_CYPHER` returns ONLY what it names; a property
    absent from its RETURN list reaches nothing downstream, with no error."""
    from src.tour.selection import LOAD_PARIS_POIS_CYPHER

    for field in CLOCK_FIELDS:
        assert f"p.{field}" in LOAD_PARIS_POIS_CYPHER, (
            f"HOP 1: the corpus query never asks the graph for `{field}`, so it can "
            f"never reach the planner however well the rest of the chain works."
        )


def test_hop_2_the_snapshot_builder_carries_the_clock_fields_onto_the_poi() -> None:
    """HOP 2/3 — `_snapshot_from_records` sets fields one by one, onto a `POI`
    that declares them. `POI` is `extra="ignore"` (src/tour/contract.py), so an
    unknown keyword is DISCARDED WITHOUT ERROR — which is why this asserts
    VALUES on the built object, never merely that construction succeeded.

    `opening_hours` arrives from the graph as a JSON-encoded STRING (the
    `physical_cues` upload precedent); the string is what the POI carries.
    """
    from src.tour.selection import _snapshot_from_records

    table = '{"mon": [["09:00", "18:00"]], "tue": [], "wed": [["09:00", "18:00"]], ' \
        '"thu": [["09:00", "18:00"]], "fri": [["09:00", "18:00"]], ' \
        '"sat": [["09:00", "18:00"]], "sun": [["09:00", "18:00"]]}'
    record = {
        "id": "musee-test",
        "name": "Musée Test",
        "tier": 4,
        "poi_role": "stop",
        "lat": 48.86,
        "lng": 2.33,
        "areas": [],
        "opening_hours": table,
        "opening_hours_source": "osm",
        "opening_hours_basis": "Museum; OSM tag 'Mo,We-Su 09:00-18:00; Tu off'.",
        "place_category": "museum",
    }
    poi = _snapshot_from_records([record], [], [], []).pois[0]

    assert poi.opening_hours == table, (
        "HOP 2/3: the record carried opening_hours but the POI does not. Either "
        "_snapshot_from_records does not pass it, or POI does not declare it."
    )
    assert poi.opening_hours_source == "osm", (
        "HOP 2/3: the record carried opening_hours_source but the POI does not."
    )
    assert poi.opening_hours_basis.startswith("Museum;"), (
        "HOP 2/3: the record carried opening_hours_basis but the POI does not."
    )
    assert poi.place_category == "museum", (
        "HOP 2/3: the record carried place_category but the POI does not."
    )


def test_hop_2_an_unpriced_record_lands_on_the_safe_defaults() -> None:
    """A corpus written before the opening-hours pass must still load: every
    field arrives as None from Neo4j and must land on None / None / "" / "" —
    and None hours means NEVER CLOCK-EXCLUDED, which is the safe direction
    (a place is included on a day it is closed, never excluded on a day it is
    open)."""
    from src.tour.selection import _snapshot_from_records

    record = {
        "id": "unpriced",
        "name": "A place with no hours yet",
        "tier": 3,
        "poi_role": "stop",
        "lat": 48.8566,
        "lng": 2.3522,
        "areas": [],
        "opening_hours": None,
        "opening_hours_source": None,
        "opening_hours_basis": None,
        "place_category": None,
    }
    poi = _snapshot_from_records([record], [], [], []).pois[0]
    assert poi.opening_hours is None
    assert poi.opening_hours_source is None
    assert poi.opening_hours_basis == ""
    assert poi.place_category == ""


def test_the_upload_carries_the_clock_fields_in_both_property_lists() -> None:
    """S1.4d's hop — `scripts/upload_paris.py` keeps TWO hardcoded property
    lists (the param dict and the Cypher SET list) whose own comment warns they
    must agree or a field silently never reaches the graph. Both must carry all
    four clock fields (the `test_golden_diff_cli_reads_the_durable_key` genre:
    read the script source, assert on both lists)."""
    source = (REPO_ROOT / "scripts" / "upload_paris.py").read_text()
    for field in CLOCK_FIELDS:
        assert f'"{field}"' in source, (
            f"upload param dict never carries `{field}` — it will never reach the graph"
        )
        assert f"p.{field}" in source, (
            f"upload Cypher SET list never writes `p.{field}` — the param is carried "
            "and then silently dropped at the write"
        )
