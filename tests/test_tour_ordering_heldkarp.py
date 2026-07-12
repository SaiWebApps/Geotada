"""M4 — exact open-path Held-Karp ordering. Hermetic: no DB, no engine run.

PROVE (IMPLEMENTATION-PLAN M4): on the seesaw fixture HK beats greedy
nearest-neighbour with zero direction reversals and honors fixed_end; for
every n in 4..8 HK cost equals the itertools.permutations brute-force
optimum (open, round-trip, and asymmetric-cost variants); each case runs
in under a second.
"""

from __future__ import annotations

import itertools
import random
import time

import pytest

from src.tour.contract import POI
from src.tour.ordering import held_karp_open
from src.tour.routing import default_leg_seconds
from src.tour.selection import HARD_ANCHOR_CAP

START = (48.8550, 2.3600)
UNIT = 0.003  # ~220m of longitude at Paris latitude


def _poi(pid: str, lat: float, lng: float) -> POI:
    return POI(id=pid, name=pid, tier=5, poi_role="stop", lat=lat, lng=lng)


def _path_cost(order, *, start=START, round_trip=False, fn=default_leg_seconds) -> float:
    total, (plat, plng) = 0.0, start
    for p in order:
        total += fn(plat, plng, p.lat, p.lng)
        plat, plng = p.lat, p.lng
    if round_trip:
        total += fn(plat, plng, *start)
    return total


def _greedy_nn(points, *, start=START, fn=default_leg_seconds):
    remaining, order, cur = list(points), [], start
    while remaining:
        nxt = min(remaining, key=lambda p: (fn(cur[0], cur[1], p.lat, p.lng), p.id))
        order.append(nxt)
        remaining.remove(nxt)
        cur = (nxt.lat, nxt.lng)
    return order


def _lng_reversals(order) -> int:
    """Direction reversals along the seesaw axis, POI-to-POI legs only."""
    deltas = [b.lng - a.lng for a, b in itertools.pairwise(order)]
    return sum(
        1 for d1, d2 in itertools.pairwise(deltas) if d1 * d2 < 0
    )


# Seesaw: one POI 1.2 units west of the start, four POIs sweeping east.
# Greedy-NN gets lured east (the +1 POI is nearer than the -1.2 one), sweeps
# to +4, then pays a 5.2-unit backtrack for the stranded west POI. The
# optimum clears the west POI first and sweeps east monotonically.
SEESAW = [
    _poi("west", START[0], START[1] - 1.2 * UNIT),
    _poi("e1", START[0], START[1] + 1.0 * UNIT),
    _poi("e2", START[0], START[1] + 2.0 * UNIT),
    _poi("e3", START[0], START[1] + 3.0 * UNIT),
    _poi("e4", START[0], START[1] + 4.0 * UNIT),
]


def test_seesaw_hk_beats_greedy_nn_with_zero_backtrack():
    hk = held_karp_open(SEESAW, fixed_start=START)
    nn = _greedy_nn(SEESAW)
    assert _path_cost(hk) < _path_cost(nn)
    assert [p.id for p in hk] == ["west", "e1", "e2", "e3", "e4"]
    assert _lng_reversals(hk) == 0
    assert _lng_reversals(nn) > 0  # the lure is real: NN does backtrack


def test_seesaw_fixed_end_is_honored():
    end = SEESAW[2]  # "e2" — NOT the natural free end
    hk = held_karp_open(SEESAW, fixed_start=START, fixed_end=end)
    assert hk[-1].id == "e2"
    # exact under the constraint: brute force over permutations ending at e2
    others = [p for p in SEESAW if p.id != "e2"]
    best = min(
        _path_cost([*perm, end]) for perm in itertools.permutations(others)
    )
    assert abs(_path_cost(hk) - best) < 1e-6


def _random_points(n: int, seed: int) -> list[POI]:
    r = random.Random(seed)
    return [
        _poi(f"p{i}", START[0] + r.uniform(-0.008, 0.008), START[1] + r.uniform(-0.008, 0.008))
        for i in range(n)
    ]


def _eastbound_penalty(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    """Asymmetric cost: eastbound legs pay a flat 200s surcharge."""
    base = default_leg_seconds(lat1, lng1, lat2, lng2)
    return base + (200 if lng2 > lng1 else 0)


@pytest.mark.parametrize("n", [4, 5, 6, 7, 8])
def test_exactness_against_brute_force(n: int):
    pts = _random_points(n, seed=40 + n)
    for round_trip, fn in (
        (False, default_leg_seconds),
        (True, default_leg_seconds),
        (False, _eastbound_penalty),  # asymmetric: the DP must stay directed
    ):
        t0 = time.perf_counter()
        hk = held_karp_open(
            pts, fixed_start=START, round_trip=round_trip, routed_cost_fn=fn
        )
        elapsed = time.perf_counter() - t0
        assert elapsed < 1.0, f"n={n} took {elapsed:.3f}s"

        assert sorted(p.id for p in hk) == sorted(p.id for p in pts)
        best = min(
            _path_cost(perm, round_trip=round_trip, fn=fn)
            for perm in itertools.permutations(pts)
        )
        got = _path_cost(hk, round_trip=round_trip, fn=fn)
        assert abs(got - best) < 1e-6, (
            f"n={n} round_trip={round_trip} fn={fn.__name__}: HK {got} != brute {best}"
        )


def test_cap_sized_input_under_a_second():
    # Exercise the REAL anchor cap so the sub-1s guarantee is validated at the
    # ceiling select_route can actually hand the solver (raised 12→15).
    pts = _random_points(HARD_ANCHOR_CAP, seed=99)
    t0 = time.perf_counter()
    hk = held_karp_open(pts, fixed_start=START)
    assert time.perf_counter() - t0 < 1.0
    assert len(hk) == HARD_ANCHOR_CAP


def test_edge_cases_and_contract_errors():
    assert held_karp_open([], fixed_start=START) == []
    single = [SEESAW[0]]
    assert held_karp_open(single, fixed_start=START) == single
    with pytest.raises(ValueError, match="mutually exclusive"):
        held_karp_open(SEESAW, fixed_start=START, fixed_end=SEESAW[0], round_trip=True)
    with pytest.raises(ValueError, match="not among the points"):
        held_karp_open(SEESAW[:3], fixed_start=START, fixed_end=SEESAW[4])
