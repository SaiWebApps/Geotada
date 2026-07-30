# Golden-fixture repair — partial work and one measured finding

The two golden fixtures in the parent directory (`ile_oneway_90min.json`,
`pdv_round_trip_60min.json`) pin their expected beats as random UUIDs. The corpus keys
beats by slug, so **0 of 43 pinned ids exist**, `beat_overlap` is forced to 0.0 no matter
what the code did at the time of writing. **SUPERSEDED 2026-07-30: the repair SHIPPED.** `make _test-golden` and `make _test-grade` are GREEN, the fixtures are re-keyed to durable corpus slugs (`expected_stable_beat_ids`), and the resolutions below were re-derived rather than inherited — exact-slug-suffix first, similarity only as fallback, unresolved tags queued in each fixture's `unresolved_tags`. The files here are the raw HINT material and the historical record of the method; the shipped truth is in `fixtures/tour_golden/*.json`. Two hints in these files were measured WRONG (0.909 onto a wrong beat, 1.000 non-unique) and were re-adjudicated, not carried over.
Everything else about those tours is healthy — measured 2026-07-29, the Île tour scores
`poi_recall=0.625, spine_match=1.0, validation=1.0` and fails only on overlap.

This folder holds the partial re-resolution done toward that repair, plus the finding that
came out of it. It is **input for the repair, not a fixture** — nothing loads it.

## Method (established, and worth preserving)

Each `[TAG:...]` in the empirical tour documents was originally matched to a beat **by
`script_body`**. Re-running that method against today's corpus is the honest repair: it
preserves the human-vetted mapping instead of re-recording current output, which would be
a tautology. Source documents:

- `Docs/tour-builder/empirical-tours/01-place-des-vosges.md`
- `Docs/tour-builder/empirical-tours/02-ile-de-la-cite-notre-dame.md`

## Files

| File | What it is |
|---|---|
| `resolved-both-tours.json` | Fullest run — 50 Île tags + 6 Place des Vosges tags, each with `beat_id`, `poi`, `similarity` |
| `resolved-ile-earlier-run.json` | Earlier run, 21 entries, `beat_id` only |
| `resolved-pdv-earlier-run.json` | Earlier run, 2 entries, `beat_id` only |

The earlier runs are **not subsets**. They hold 8 tags the fullest run lacks (7 Île, 1
PdV) and disagree with it on 2 mappings.

## The finding: text similarity picks high-confidence WRONG beats

**1. `cavaille_coll_organ`**

```
fullest run -> paris_notre_dame_cathedral_historic_arch_frommers_24_great_walks_capacity_rose_windows_organ   (similarity 0.909)
earlier run -> paris_notre_dame_cathedral_music_heritage_rough_guide_paris_cavaille_coll_organ                (exact name match)
```

A 0.909 score landed on a **different** beat while a beat with the exactly matching tag
name existed.

**2. `judgement_day_central_portal`**

```
fullest run -> paris_notre_dame_cathedral_historic_worship_rough_guide_paris_central_portal_day_of_judgement  (similarity 1.000)
earlier run -> paris_notre_dame_cathedral_historic_worship_frommers_24_great_walks_judgement_day_central_portal
```

Similarity **1.000 did not identify a unique beat**: two source books describe the same
fact, so the text matches perfectly against both.

**Consequence for the repair.** Similarity alone is not a safe selector. Prefer an exact
tag-slug match on the beat id wherever one exists, and treat any tag that ties across two
source books as needing a human decision. A confidence score near 1.0 is not evidence the
right beat was found.

## Open decision for the owner

What should the overlap bar be? SETTLED 2026-07-30: the floors are now ABSOLUTE hit counts (Ile 15, PdV 3), each 85% of the first measurement taken against a truthful expectation (Ile 18/31, PdV 4/21) — see the long notes in `tests/test_tour_golden_{ile,pdv}.py`, which record that both numbers went DOWN and why. The old ratio floor was **5/18 (27.8%)** against a stated
**90%** target — it permits 57% drift from the human-vetted tour and still passes, which
means it cannot fail. Needs a deliberate number before the repair lands.

## Trap already paid for — do not repeat it

The two documents use **different tag prefixes**. Place des Vosges uses `[PW:...]`; Île
uses `[RG:...]`, `[F:...]`, `[V:...]`, and a single block can carry two tags joined by `+`
(`**[F:pont_neuf_history + F:statue_napoleon_hidden]**`). A pattern written against the
first document silently returned **zero** matches on the second.

Parse the real structure with plain string operations — quoted lines starting `>`, a bold
tag block delimited by `**[` and `]**`, split on `+`, strip any trailing ` — note`. A
structural parser reached 0 unparsed lines in both documents. **Do not use a regular
expression for this**; it fails silently and returns plausible wrong answers.
