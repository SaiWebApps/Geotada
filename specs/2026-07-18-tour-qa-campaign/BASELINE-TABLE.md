# Phase C Baseline Table — 2026-07-18 Live Authored Tours

Source of every number below: the raw `author_tour.py` transcripts at
`/tmp/ondoway-phase-c/{ile-90,pdv-60,nyc-90,london-75}.txt` (read in full,
2026-07-18). "Attempts" = the highest attempt index shown + 1 (e.g.
`converged in 4` → attempts 0-3 shown → 4 attempts; every
`GROUNDED-STITCH FALLBACK` row shows attempts 0-3, i.e. capped at 4, then
`[author never reached 0/0 — served grounded stitch]`).

This is the exact table the Phase-C re-run gets diffed against. Do not
hand-edit numbers without re-reading the corresponding `.txt` line.

---

## PARIS — Île de la Cité, 90 min (6 stops; source: `ile-90.txt`)

| Stop | POI | Result | Attempts | Facts kept | Craft |
|---|---|---|---|---|---|
| 0 | Notre-Dame Cathedral | converged in 4 | 4 | 33% | 2.27 |
| 1 | Sainte-Chapelle | converged in 1 | 1 | 67% | 2.33 |
| 2 | Conciergerie | **GROUNDED-STITCH FALLBACK** | 4 | 100% | 0.40 |
| 3 | Palais de Justice | converged in 2 | 2 | 67% | 2.27 |
| 4 | Square du Vert-Galant | **GROUNDED-STITCH FALLBACK** | 4 | 100% | 0.71 |
| 5 | Pont Neuf | converged in 2 | 2 | 80% | 2.22 |

Fallbacks: 2 (stops 2, 4 — both mid-tour, neither is a bookend; stop 0 and
stop 5 both converged).

---

## PARIS — Place des Vosges, 60 min, dark_history+social_change (4 stops; source: `pdv-60.txt`)

| Stop | POI | Result | Attempts | Facts kept | Craft |
|---|---|---|---|---|---|
| 0 | Place des Vosges | converged in 2 | 2 | 100% | 0.61 |
| 1 | Musee Carnavalet | converged in 2 | 2 | 50% | 2.24 |
| 2 | Rue de Rivoli | converged in 1 | 1 | 86% | 2.27 |
| 3 | Rue des Rosiers | converged in 3 | 3 | 88% | 2.28 |

Fallbacks: 0. (Note: stop 0 converged but scored a low craft 0.61 — this is
the pre-repair run; the wider-window repair later raised it to 1.96, logged
separately in PHASE-C-RESULTS.md, not part of this baseline.)

---

## NEW YORK — Lower Manhattan, 90 min (5 stops; source: `nyc-90.txt`)

| Stop | POI | Result | Attempts | Facts kept | Craft |
|---|---|---|---|---|---|
| 0 | Castle Clinton | **GROUNDED-STITCH FALLBACK** | 4 | 100% | 0.84 |
| 1 | Battery Park | converged in 4 | 4 | 45% | 2.34 |
| 2 | National Museum of the American Indian | converged in 3 | 3 | 100% | 2.27 |
| 3 | Bowling Green Park | converged in 2 | 2 | 64% | 2.27 |
| 4 | Wall Street | **GROUNDED-STITCH FALLBACK** | 4 | 100% | 1.74 |

Fallbacks: 2 (stops 0 and 4 — **both are tour bookends**: stop 0 is the
first stop, stop 4 is the last stop of a 5-stop [0-4] tour).

---

## LONDON — Westminster, 75 min (5 stops; source: `london-75.txt`)

| Stop | POI | Result | Attempts | Facts kept | Craft |
|---|---|---|---|---|---|
| 0 | Big Ben | **GROUNDED-STITCH FALLBACK** | 4 | 100% | 0.08 |
| 1 | New Scotland Yard | **GROUNDED-STITCH FALLBACK** | 4 | 100% | -0.25 |
| 2 | Westminster Bridge | converged in 2 | 2 | 86% | 1.75 |
| 3 | Palace of Westminster | **GROUNDED-STITCH FALLBACK** | 4 | 100% | -0.12 |
| 4 | Westminster Abbey | converged in 1 | 1 | 67% | 2.17 |

Fallbacks: 3 (stop 0 is the first stop of the tour — **a bookend**; stops 1
and 3 are mid-tour, not bookends; stop 4, the last stop, converged).

---

## Summary

| Metric | Value |
|---|---|
| Total stops (all 4 tours) | 20 |
| Total fallbacks (GROUNDED-STITCH) | **7** |
| Fallbacks that are tour bookends (first or last stop) | **3** — NYC stop 0 (Castle Clinton, first), NYC stop 4 (Wall Street, last), London stop 0 (Big Ben, first) |
| Fallbacks mid-tour (not bookends) | 4 — Île stop 2 (Conciergerie), Île stop 4 (Vert-Galant), London stop 1 (New Scotland Yard), London stop 3 (Palace of Westminster) |
| Converged/authored stops | 13 |
| Mean craft, authored stops (13 stops) | **2.10** — sum 27.29 ÷ 13 (2.27+2.33+2.27+2.22 [Île] + 0.61+2.24+2.27+2.28 [PdV] + 2.34+2.27+2.27 [NYC] + 1.75+2.17 [London]) |
| Mean craft, fallback stops (7 stops) | **0.49** — sum 3.40 ÷ 7 (0.40+0.71 [Île] + 0.84+1.74 [NYC] + 0.08+(-0.25)+(-0.12) [London]) |
| Craft gap (authored − fallback) | 1.61 |

Per-tour fallback count check: Île 2 + PdV 0 + NYC 2 + London 3 = 7. Matches.
Per-tour stop count check: Île 6 + PdV 4 + NYC 5 + London 5 = 20. Matches
13 authored + 7 fallback.
