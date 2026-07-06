# R1 (golden-gap emission) — implementation findings

**Date:** 2026-07-05. **Status:** shipped (bounded form). Supersedes the naive
"emit the whole no-key pool" reading of R1 in `GOLDEN-GAP-DIAGNOSTIC.md`.

## What R1 was supposed to do

The diagnostic identified that `_order_by_sub_location` / `_order_by_trigger_address`
emit **exactly one** beat from the entire no-spatial-key pool (beats with
`sub_location=None` / `trigger_address=None`) — 16 of the 22 Île misses. R1 =
emit more of that pool, "within existing caps + audio headroom", predicted to
lift Île 53→85% (script-level).

## What actually happens — measured, Valhalla-routed golden-probe

Every variant was measured on the live dev graph with real routing. Baseline:
**Île 16/47, PdV 10/18.**

| variant | Île | PdV | verdict |
|---|---|---|---|
| baseline (single closer) | 16 | 10 | — |
| emit WHOLE no-key pool, uncapped | 29 | 13 | **encyclopedia-dump** — Notre-Dame emitted **40 beats** (golden ceiling is 8/POI). The C9 governor EXEMPTS the marquee stop from its share cap, so removing the single-closer left the marquee's no-key pool unbounded. Gaming overlap by breadth. |
| no-key pool arc-ordered, cap 8 | 22 | 9 | PdV **regressed** — narrative-arc reordering moved `_pick_best` off the front, so the governor's audio-prefix dropped a golden beat. |
| no-key best-first, keyed unbounded, cap 8 | 24 | 11 | keyed buckets still unbounded → Notre-Dame 22 beats (over the ceiling). |
| **total cap 8, keyed-first (spatial prefix)** | 17 | **6** | prefix truncation seats the first-8 *addresses* (spatial order), not the best beats — drops the human's editorial picks. |
| total cap 8, best-by-score, cap AFTER tone | 19 | 11 | two skeptic-refuted bugs (below); the 19/11 was partly INFLATED by the orientation-drop bug (a content golden-beat took the dropped cold-open's slot). |
| **total cap 8, best-by-score, cap after DEDUP but before TONE (SHIPPED)** | **18** | **10** | both bugs fixed; the honest number. +2 Île / +0 PdV overlap — modest. The real win is the DISTRIBUTION: every stop ≤8 (golden's human-ideal ceiling), so the marquee no longer over-emits (Notre-Dame ~15→8). |

**Honest scope of the win:** the golden-overlap gain is marginal (+2 Île, 0 PdV) —
`_beat_score` picks the right *count* but not always the human's exact *beats*. The
shippable value is the **bounded, human-ideal-shaped distribution** (no stop over
`DEFAULT_FLAT_MAX`) plus **best-by-score selection** (a dense stop voices its best
beats, not the first ones in walk order). Overlap-chasing past this needs selection
PRECISION (a better score), a separate effort.

## KE-invariant fix (opus skeptic panel, refuted the first cut)

The first shipped cut ran the cap BEFORE `_apply_b8_lite_dedup`. A hostile opus
skeptic refuted it: `select_poi_beats` (capped) and `select_poi_beats_full` (KE0,
uncapped) then ran **two independent dedup passes over different populations**, so
a paraphrase cluster straddling the cap kept different survivors — a VOICED beat
could be absent from the `full` plan `extra_beat_ids` diffs against, and
keep-exploring could surface a paraphrase of an already-voiced beat (`voiced ⊆
full` violated). Fix: the cap runs AFTER dedup, over the same deduped plan the KE0
path returns, so `voiced ⊆ full` holds *by construction* (a single shared dedup
pass). Guarded by `test_spatial_capped_is_subset_of_full_even_with_dedup_cluster`
(mutation-confirmed: reverting to cap-before-dedup fails it).

**Second skeptic (sonnet), refuted the cap-after-TONE cut:** `_enforce_tone_variety`
runs after `_hoist_orientation` and can swap the orientation beat OFF index 0 (it
is the lone non-somber swap donor). A positional index-0 cap then protected the
wrong beat, and the displaced low-score orientation lost the score competition and
was DROPPED — `generation._find_orientation_beat` then found nothing and silently
fell through to a synthesized opener, losing curated cold-open content. Final fix:
run the cap after dedup but BEFORE tone-variety, so it protects the still-at-head
orientation and tone-variety only reorders the survivors (never drops). `voiced ⊆
full` still holds (tone-variety is set-preserving). This is also why the honest
overlap is 18/10, not the bug-inflated 19/11. Guarded by
`test_spatial_cap_never_drops_the_cold_open_orientation`.

## Two findings that shaped the shipped form

1. **The golden caps every POI at 8 beats** — including the 23-address Place des
   Vosges (curated to 8, not 23) and the 42-beat-corpus Notre-Dame (curated to 8).
   The human-ideal never voices more than `DEFAULT_FLAT_MAX` at a single stop. So
   the per-tier ceiling that the flat strategy always had now applies to the
   spatial strategies too (`select_poi_beats` → `_apply_flat_cap` /
   `_cap_spatial_by_score`).

2. **Select-then-sequence, not sequence-then-truncate.** A spatial plan is ordered
   address-by-address; truncating it to the ceiling keeps the first-8 *addresses*,
   which are low-value early beats, and drops the editorial picks later in the
   walk (PdV 6/18). Selecting the best-8 *by score* and then leaving the survivors
   in walk order keeps both the right beats and the sequence (PdV 10/18). This is
   a genuine user-facing quality fix independent of the golden: every dense stop
   now voices its **best** beats, not its **first** ones.

## The remaining gap (why not 90%)

- **Per-POI score-selection ceiling** (top-8 by `_beat_score` from ALL active
  beats, ignoring one-per-bucket) is Île **28/47**, PdV **17/18**. The shipped
  one-per-bucket form reaches 18 / 10 because (a) one-per-bucket drops within-
  bucket runners-up the golden includes, and (b) the C9 audio governor + B8 dedup
  trim the per-POI selection further downstream. Recovering the ceiling needs a
  multi-beat-per-bucket spec change (measured +1 for the extra complexity — not
  worth it now) AND governor co-design so the audio-prefix keeps the selected
  beats. Both are their own reviewed steps.
- The last points to 90% are **selection PRECISION**, not emission: `_beat_score`
  (lens-match, length-class, word-count) is a crude proxy for the human's
  editorial judgment. Closing it is a scoring/content effort, explicitly beyond
  "emission relaxation" — the diagnostic's R3/R4/R5 rungs and metadata backfill.

The goldens remain aspirational RED targets; R1 ratchets the engine toward them
(16→18 Île, 10→10 PdV) without touching the fixtures — a modest overlap move whose
real value is the bounded, human-ideal-shaped distribution (see the honest-scope
note above), not the two extra golden beats.
