"""ORDER — exact open-path Held-Karp over the selected anchor set (M4).

The greedy's insertion order is a by-product of selection, not an optimum;
§3.2's ORDER step makes it exact. With HARD_ANCHOR_CAP = 12 the bitmask DP
costs at most 2^12 x 12^2 ≈ 590k transitions — sub-millisecond in practice,
no OR-Tools (the design forbids the dependency).

Costs come from the same LegSecondsFn divisor selection uses (routed when
Valhalla is up, pace-corrected haversine otherwise) and may be asymmetric —
the DP is directed throughout.
"""

from __future__ import annotations

from .contract import POI
from .routing import LegSecondsFn, default_leg_seconds


def held_karp_open(
    points: list[POI] | tuple[POI, ...],
    *,
    fixed_start: tuple[float, float],
    fixed_end: POI | None = None,
    round_trip: bool = False,
    routed_cost_fn: LegSecondsFn | None = None,
) -> list[POI]:
    """Optimal visiting order for ``points`` walking out of ``fixed_start``.

    Open path by default — the walk simply stops wherever its cheapest end
    is. ``round_trip`` adds the return-to-start leg to the objective (a
    closed tour); ``fixed_end`` pins one of the points as the mandatory
    final stop (the endpoint-pull contract). The two are mutually exclusive
    because a round trip already ends at the origin.

    Exact for the full cost function, including asymmetric (directed) costs.
    Equal-cost optima tie-break on the ending POI's id, so the result is
    deterministic regardless of input order.
    """
    if fixed_end is not None and round_trip:
        raise ValueError("fixed_end and round_trip are mutually exclusive")
    pts = list(points)
    n = len(pts)
    if n <= 1:
        return pts
    if fixed_end is not None and all(p.id != fixed_end.id for p in pts):
        raise ValueError(f"fixed_end {fixed_end.id!r} is not among the points")

    cost = routed_cost_fn or default_leg_seconds
    start_lat, start_lng = fixed_start

    from_start = [cost(start_lat, start_lng, p.lat, p.lng) for p in pts]
    leg = [
        [0 if i == j else cost(a.lat, a.lng, b.lat, b.lng) for j, b in enumerate(pts)]
        for i, a in enumerate(pts)
    ]
    to_start = [cost(p.lat, p.lng, start_lat, start_lng) for p in pts] if round_trip else None

    # dp[mask][i] = cheapest path from start visiting exactly `mask`, ending
    # at points[i]; parent[mask][i] reconstructs it.
    size = 1 << n
    inf = float("inf")
    dp = [[inf] * n for _ in range(size)]
    parent = [[-1] * n for _ in range(size)]
    for i in range(n):
        dp[1 << i][i] = from_start[i]

    for mask in range(size):
        row = dp[mask]
        for i in range(n):
            base = row[i]
            if base == inf or not (mask >> i) & 1:
                continue
            leg_i = leg[i]
            for j in range(n):
                if (mask >> j) & 1:
                    continue
                nxt = mask | (1 << j)
                cand = base + leg_i[j]
                if cand < dp[nxt][j]:
                    dp[nxt][j] = cand
                    parent[nxt][j] = i

    full = size - 1
    if fixed_end is not None:
        end_indices = [i for i, p in enumerate(pts) if p.id == fixed_end.id]
    else:
        end_indices = range(n)

    def _final_cost(i: int) -> float:
        return dp[full][i] + (to_start[i] if to_start is not None else 0)

    best_end = min(end_indices, key=lambda i: (_final_cost(i), pts[i].id))

    order: list[int] = []
    mask, i = full, best_end
    while i != -1:
        order.append(i)
        nxt_i = parent[mask][i]
        mask ^= 1 << i
        i = nxt_i
    order.reverse()
    return [pts[i] for i in order]
