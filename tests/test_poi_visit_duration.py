"""Structural guard on the per-POI visit capacities in `data/{city}/poi-raw.json`.

Three fields describe how long a visitor usefully spends at a place:

  `typical_duration_min`  int          MINUTES spent at the place WITHOUT going in.
  `visit_seconds_inside`  int | None   SECONDS spent INSIDE. None = no interior
                                       (a street, a bridge, a square).
  `visit_basis`           str          One sentence arguing for the numbers, written
                                       so someone who has never been to the city can
                                       judge them ("interior, ~30 rooms, 45-60 min").

Two numbers exist because one cannot serve two visitors. Camille gives
Sainte-Chapelle 66 minutes including the queue; Theo gives the same building 15
minutes from the outside and never goes in (`docs/personas/01-architecture-pilgrim.md`
steps 16-17, `docs/personas/02-dark-history-walker.md:77`).

WHAT THIS FILE CHECKS, AND WHAT IT DELIBERATELY DOES NOT. Every assertion here is
STRUCTURAL — shape, sign, ordering, presence. None is knowledge-based, because the
repo owner cannot check Paris facts and a test nobody can adjudicate is worse than no
test. A plausible-but-wrong "20 minutes" for a specific church passes here by design;
`visit_basis` exists so a human reviewer can catch that class, and nothing automated
can. Do not add a test asserting a particular POI's number.

MIND THE UNITS. The outside number is MINUTES and the inside number is SECONDS.
Comparing them without converting is the mistake this file's second test is written
to make impossible to ship.

WHY THREE OF THESE CAN PASS ON A FILE THAT HAS NEVER BEEN PRICED. The three checks
about `visit_seconds_inside` — ordering, sign, ceiling — are conditional on the
place having an interior at all, because `null` is a legitimate value for a street
or a bridge. On a corpus where nothing has been priced yet they are vacuously true
and report green. That is correct, but it means a partial green here is NOT evidence
the data is partly fine: the two presence checks are what say whether the pass ran.
Read them first.

The tests run in a few milliseconds with no database.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "data"

SECONDS_PER_MINUTE = 60

# Cities whose corpus has been through the visit-capacity pass and must therefore
# satisfy every check below. This is an explicit allow-list rather than "every city
# with a poi-raw.json" because london and new_york have not run the pass: including
# them would make this file permanently red and train the next reader to ignore it.
#
# ADDING a slug here is the deliberate act of declaring "this city has been priced".
# REMOVING one to reach green is forbidden — it deletes the guard instead of fixing
# the data, and the data is the thing the tour engine reads.
CITIES_WITH_VISIT_CAPACITY: tuple[str, ...] = ("paris",)

# Ceiling on a single interior visit. There is no principled value to derive: the
# tour contract accepts any request from 1 to 600 minutes (`src/tour/contract.py:49`,
# `duration_min: int = Field(..., gt=0, le=600)`), so there is no "shortest supported
# tour" to size a cap against. 90 minutes is therefore CHOSEN, and chosen from
# evidence: the longest real single-place visit in the persona set is Camille's
# Sainte-Chapelle at 66 minutes (28 queueing + 38 inside), so any cap at or below 66
# would reject a visit that actually happens. 90 leaves headroom over the largest
# observed case while still refusing the AI-invented half-day that no walking tour
# can absorb.
MAX_VISIT_SECONDS_INSIDE = 5400

# Floor on the outside number. A place nobody pauses at for even two minutes is a
# walk-past, not a stop, and should not be occupying a slot on a tour. The floor is
# also what stops a too-timid capacity pass from looking finished: `0` is the default
# the tour contract will fall back to, so a pass that leaves every street and square
# at 0 writes a file that reads as complete and prices half the corpus at nothing.
MIN_TYPICAL_DURATION_MIN = 2


def _pois(city: str) -> list[dict]:
    return json.loads((DATA_ROOT / city / "poi-raw.json").read_text())


def _name(poi: dict) -> str:
    return str(poi.get("name", "<unnamed POI>"))


def _fail(city: str, headline: str, offenders: list[str], remedy: str) -> None:
    """Fail naming the offending POIs, so the message is actionable on its own."""
    shown = offenders[:20]
    more = f"\n  ... and {len(offenders) - len(shown)} more" if len(offenders) > len(shown) else ""
    pytest.fail(
        f"{city}: {headline} ({len(offenders)} of them)\n"
        + "\n".join(f"  {line}" for line in shown)
        + more
        + f"\n{remedy}"
    )


REMEDY = (
    "Run the capacity pass: `make poi-visit-duration SLUG=<city>` "
    "(see .claude/commands/poi-visit-duration.md)."
)


@pytest.mark.parametrize("city", CITIES_WITH_VISIT_CAPACITY)
def test_every_poi_has_an_outside_visit_duration(city: str) -> None:
    """Every POI must say how long a visitor spends at it without going in.

    This is the only number every POI gets — a street has no interior, so the
    outside number is its whole visit. A POI missing it is priced at nothing.
    """
    offenders = [
        f"{_name(p)}: typical_duration_min={p.get('typical_duration_min')!r}"
        for p in _pois(city)
        if not isinstance(p.get("typical_duration_min"), int)
        or isinstance(p.get("typical_duration_min"), bool)
    ]
    if offenders:
        _fail(city, "POI(s) with no outside visit duration", offenders, REMEDY)


@pytest.mark.parametrize("city", CITIES_WITH_VISIT_CAPACITY)
def test_inside_capacity_is_never_shorter_than_outside(city: str) -> None:
    """Going inside must never be quicker than staying outside.

    UNITS: `typical_duration_min` is MINUTES and `visit_seconds_inside` is SECONDS,
    so the comparison converts. An inside value below the outside one means the two
    numbers were priced against different questions.
    """
    offenders = []
    for poi in _pois(city):
        inside = poi.get("visit_seconds_inside")
        outside_min = poi.get("typical_duration_min")
        if inside is None or not isinstance(inside, int) or not isinstance(outside_min, int):
            continue
        outside_s = outside_min * SECONDS_PER_MINUTE
        if inside < outside_s:
            offenders.append(
                f"{_name(poi)}: inside {inside}s ({inside / 60:.0f} min) "
                f"< outside {outside_s}s ({outside_min} min)"
            )
    if offenders:
        _fail(city, "POI(s) where the interior is quicker than the exterior", offenders, REMEDY)


@pytest.mark.parametrize("city", CITIES_WITH_VISIT_CAPACITY)
def test_no_visit_capacity_is_negative(city: str) -> None:
    """No visit capacity may be negative.

    Separate from the two-minute floor and the 90-minute ceiling because it catches
    the one case neither does: a negative `visit_seconds_inside` is below every
    ceiling, so only a sign check refuses it.
    """
    offenders = []
    for poi in _pois(city):
        outside = poi.get("typical_duration_min")
        inside = poi.get("visit_seconds_inside")
        if isinstance(outside, int) and outside < 0:
            offenders.append(f"{_name(poi)}: typical_duration_min={outside}")
        if isinstance(inside, int) and inside < 0:
            offenders.append(f"{_name(poi)}: visit_seconds_inside={inside}")
    if offenders:
        _fail(city, "POI(s) with a negative visit capacity", offenders, REMEDY)


@pytest.mark.parametrize("city", CITIES_WITH_VISIT_CAPACITY)
def test_every_poi_explains_its_visit_capacity(city: str) -> None:
    """Every number must ship with the sentence that argues for it.

    Nobody involved in this repo has visited most of these places, so a bare number
    is unauditable. `visit_basis` is the only thing that makes a wrong number
    findable by a human reader.
    """
    offenders = [
        f"{_name(p)}: visit_basis={p.get('visit_basis')!r}"
        for p in _pois(city)
        if not isinstance(p.get("visit_basis"), str) or not p.get("visit_basis", "").strip()
    ]
    if offenders:
        _fail(city, "POI(s) whose visit capacity carries no reasoning", offenders, REMEDY)


@pytest.mark.parametrize("city", CITIES_WITH_VISIT_CAPACITY)
def test_inside_capacity_never_exceeds_ninety_minutes(city: str) -> None:
    """No single interior visit may exceed 90 minutes (5400 s).

    WHY 90 AND NOT SOMETHING DERIVED: nothing in the codebase offers a bound to
    derive one from. `src/tour/contract.py:49` accepts any requested duration in
    `0 < duration_min <= 600`, so there is no shortest supported tour to measure a
    single stop against. 90 is a chosen concrete cap, anchored on the largest real
    visit in the persona set — Camille's 66 minutes at Sainte-Chapelle, queue
    included — so that a cap set any lower would reject something that genuinely
    happens. Above that, a single stop eating an hour and a half of a walking tour
    is an AI-invented number, not a visit.
    """
    offenders = [
        f"{_name(p)}: visit_seconds_inside={p['visit_seconds_inside']}s "
        f"({p['visit_seconds_inside'] / 60:.0f} min)"
        for p in _pois(city)
        if isinstance(p.get("visit_seconds_inside"), int)
        and p["visit_seconds_inside"] > MAX_VISIT_SECONDS_INSIDE
    ]
    if offenders:
        _fail(
            city,
            f"POI(s) whose interior visit exceeds the {MAX_VISIT_SECONDS_INSIDE}s "
            f"({MAX_VISIT_SECONDS_INSIDE // 60} min) ceiling",
            offenders,
            REMEDY,
        )


@pytest.mark.parametrize("city", CITIES_WITH_VISIT_CAPACITY)
def test_outside_capacity_is_at_least_two_minutes(city: str) -> None:
    """Every POI must be worth at least two minutes outside.

    WHY TWO: a place nobody pauses at for even two minutes is a walk-past, not a
    stop, and a tour should route past it rather than book time at it. The floor
    also refuses the failure this whole file exists to catch — a capacity pass timid
    enough to leave streets and squares at `0`. Zero is what the tour contract falls
    back to when a POI carries nothing, so a file full of zeroes looks priced and is
    not, and the shortfall only surfaces much later as a tour that cannot be filled.

    A MISSING value is an offender here too, not a skip. The first test in this file
    also reports it, and the small duplicate noise is deliberate: "every POI" has to
    mean every POI even if that other test is one day deleted or narrowed. A guard
    that quietly goes vacuous when its data disappears is not a guard.
    """
    offenders = [
        f"{_name(p)}: typical_duration_min={p.get('typical_duration_min')!r}"
        for p in _pois(city)
        if not isinstance(p.get("typical_duration_min"), int)
        or isinstance(p.get("typical_duration_min"), bool)
        or p["typical_duration_min"] < MIN_TYPICAL_DURATION_MIN
    ]
    if offenders:
        _fail(
            city,
            f"POI(s) priced below the {MIN_TYPICAL_DURATION_MIN}-minute floor",
            offenders,
            REMEDY,
        )


# ---------------------------------------------------------------------------
# The plumbing: three hops between Neo4j and the planner, each of which can eat
# a field in silence. This block tests them ONE AT A TIME, so a failure names
# the hop that ate it rather than just saying the number is missing.
# ---------------------------------------------------------------------------

VISIT_FIELDS = ("typical_duration_min", "visit_seconds_inside", "visit_basis")


def test_hop_1_the_corpus_query_asks_the_graph_for_the_visit_fields() -> None:
    """HOP 1 — the Cypher returns ONLY what it names.

    `LOAD_PARIS_POIS_CYPHER` has an explicit RETURN list. A property absent from
    it is not returned, no error is raised, and every later hop then sees nothing
    to carry. This is the cheapest of the three failures to cause and the hardest
    to spot, because the symptom appears two layers away as "the number is zero".
    """
    from src.tour.selection import LOAD_PARIS_POIS_CYPHER

    for field in VISIT_FIELDS:
        assert f"p.{field}" in LOAD_PARIS_POIS_CYPHER, (
            f"HOP 1: the corpus query never asks the graph for `{field}`, so it can "
            f"never reach the planner however well the rest of the chain works."
        )


def test_hop_2_the_snapshot_builder_carries_the_visit_fields_onto_the_poi() -> None:
    """HOP 2 — the snapshot builder sets fields one by one and never splats.

    A column returned by hop 1 but not named here is simply unused. And because
    `POI` is `extra="ignore"`, even passing it as an unknown keyword would be
    discarded WITHOUT an error — that is hop 3, and it is why this assertion
    checks the values on the built object rather than trusting the call.
    """
    from src.tour.selection import _snapshot_from_records

    record = {
        "id": "sainte-chapelle",
        "name": "Sainte-Chapelle",
        "tier": 5,
        "poi_role": "stop",
        "lat": 48.8554,
        "lng": 2.3450,
        "areas": ["Ile de la Cite"],
        "typical_duration_min": 15,
        "visit_seconds_inside": 3960,
        "visit_basis": "28-minute queue plus 38 minutes under the glass.",
    }
    snapshot = _snapshot_from_records([record], [], [], [])
    poi = snapshot.pois[0]

    assert poi.typical_duration_min == 15, (
        "HOP 2/3: the record carried typical_duration_min but the POI does not. "
        "Either _snapshot_from_records does not pass it, or POI does not declare it."
    )
    assert poi.visit_seconds_inside == 3960, (
        "HOP 2/3: the record carried visit_seconds_inside but the POI does not."
    )
    assert poi.visit_basis.startswith("28-minute queue"), (
        "HOP 2/3: the record carried visit_basis but the POI does not."
    )


def test_hop_2_an_unpriced_record_lands_on_the_safe_defaults() -> None:
    """A corpus written before the capacity pass must still load.

    Neo4j returns None for a property a node does not carry, so every field
    arrives as None rather than absent. That must become 0 / None / "" — today's
    behaviour — and never raise.
    """
    from src.tour.selection import _snapshot_from_records

    record = {
        "id": "unpriced",
        "name": "A place nobody has priced",
        "tier": 3,
        "poi_role": "stop",
        "lat": 48.8566,
        "lng": 2.3522,
        "areas": [],
        "typical_duration_min": None,
        "visit_seconds_inside": None,
        "visit_basis": None,
    }
    poi = _snapshot_from_records([record], [], [], []).pois[0]
    assert poi.typical_duration_min == 0
    assert poi.visit_seconds_inside is None
    assert poi.visit_basis == ""
