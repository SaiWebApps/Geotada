"""Paris walking-distance smoke routes.

Runs five canonical Paris routes through ``distance.walking_time`` and
prints expected (Google-Maps walking ground truth) vs actual seconds with
the percent deviation. Routes deviating more than 25% get a WARNING flag.
Always exits 0 — this is a diagnostic, not a gate.

The distance module handles the ``127.0.0.1`` base URL and
``trust_env=False`` proxy avoidance, so no special config is needed here.

Usage:
    python scripts/distance_smoke.py
"""

from __future__ import annotations

import sys

from src.tour import distance

# (label, a_latlng, b_latlng, ground_truth_seconds)
ROUTES: list[tuple[str, tuple[float, float], tuple[float, float], int]] = [
    ("Concorde → Notre-Dame", (48.8656, 2.3212), (48.8530, 2.3499), 2200),
    ("Sacré-Cœur → Pigalle", (48.8867, 2.3431), (48.8820, 2.3375), 600),
    ("Place des Vosges → Panthéon", (48.8554, 2.3656), (48.8462, 2.3464), 1500),
    ("Louvre → Palais Royal", (48.8606, 2.3376), (48.8636, 2.3370), 250),
    ("Pont Neuf → Île de la Cité", (48.8567, 2.3412), (48.8556, 2.3449), 300),
]

DEVIATION_THRESHOLD = 25.0


def main() -> int:
    print("Paris distance smoke — expected vs actual walking seconds\n")
    print(f"{'route':<32} {'expected':>9} {'actual':>8} {'dev%':>8}  flag")
    print("-" * 70)
    for label, a, b, expected in ROUTES:
        actual = distance.walking_time(a, b)
        deviation = abs(actual - expected) / expected * 100.0 if expected else 0.0
        flag = ""
        if deviation > DEVIATION_THRESHOLD:
            flag = "WARNING >25%"
        print(f"{label:<32} {expected:>9} {actual:>8} {deviation:>7.1f}%  {flag}")

    print("\ncounters:", distance.get_counters())
    return 0


if __name__ == "__main__":
    sys.exit(main())
