# Tour Algorithm QA Campaign — 2026-07-18

**Goal:** aggressive multi-agent QA of the core tour algorithm across Paris, London, New York:
generate diverse complex tours, judge them against the grounded rubric + the product owner's
known-good Place des Vosges sample, and independently verify every walking path. All at $0
(mock glue; no compose, no TTS, no user-API spend).

**Method:** 16-build matrix (6 Paris / 4 NYC / 4 London / 2 designed-refusal edge cases) via
`make tour-build` → 11 served tours → Workflow: 11×2 review agents (quality rubric arm +
walking-path arm, sonnet) → 133 findings → 91 critical/major → top-12 adversarially verified
(opus refuters, default-refute) → second verify round on 6 more key patterns (opus skeptics).
Baseline `make tour-invariants`: **10/10 green**. Campaign: ~40 agents, ~1.3M session tokens,
skeptic-gated pre-launch per `.claude/FAILURES.md` F1.

Artifacts: `/tmp/ondoway-qa-tours/` (tours, geometry extracts, manifest, review_results.json,
final_result.json).

---

## VERDICT — split, and precisely bounded

### The geometric/mathematical core is ROCK-SOLID (verified, not assumed)
Hostile verifiers tried to break the engine's math and FAILED on every axis:

- **Distances are honest:** in 10/11 tours the route arm's independent haversine recomputation
  matched `total_walk_distance_m` to within 0.1–0.8 m; round-trips close to single-digit meters
  (P1: 7.3 m from start); zero backtracking/zigzag pathology in any city.
- **Ordering is provably optimal:** a verifier re-ran Held–Karp AND brute-forced all 24
  permutations of L2 with the real leg-cost function — the served order is the unique optimum
  (1250.0 s, exactly matching the artifact; next best +14%).
- **The accounting the panel attacked is correct-by-design:** 9 of 12 first-round
  critical findings (duration shortfall, `total_planned_seconds` "mismatches",
  corpus-underutilization) were REFUTED — `ERR_SHORT=0.83` is the deliberate planning target
  (`src/tour/routing.py:42`), `total_planned_seconds` is the err-short budget not an itemized
  sum, and beat caps behaved per spec. One verifier reproduced P6 EXACTLY via `select_route`
  against the live graph.
- **Refusals are honest:** all 5 refusals (2 designed + Times Sq lens / Trafalgar RT / Covent
  Garden RT) are the density gate correctly reporting thin *audio capacity* (London lead-only
  extracts ≈ tiny voiced seconds per POI), with actionable alternatives. Not geometric bugs.
- Baseline `make tour-invariants` 10/10; all 11 tours validation PASS (untraceable=0, forbidden=0).

### The content-assembly layer is NOT rock-solid — 9 verified defects
Every one below survived a hostile opus refuter (default-verdict REFUTED) or was
confirmed twice. Ranked by tourist impact:

| # | Defect | Layer | Severity | Evidence |
|---|--------|-------|----------|----------|
| D1 | **No cross-beat contradiction guard exists anywhere** — contradictory beats are voiced adjacent in one stop. N3: arch beat `66a46fa3` ships a FALSE claim (an 1889 arch "celebrating the centennial of Washington's return" — that centennial was 1883; the 1889 centennial was the inauguration, which the adjacent beat correctly states). N2 Battery Park: 1623-landing/naming/battery story vs 1625-founding story voiced 2 sentences apart. Verified: every existing mechanism (`_apply_b8_lite_dedup`, `claim_dedup.py`) suppresses *agreement*; nothing detects *disagreement*. | corpus_data + engine gap | **critical** | verifier a405e3 |
| D2 | **Guidebook navigation/transit prose served as narration, hoisted to stop HEAD.** Paris P6: stop 2 opens "Leave the cemetery…" (no cemetery in tour; beat `49d230f3` = a book's routing sentence). NYC N2: "Take the 4 or 5 train to Bowling Green" voiced immediately after glue said "just ahead" on foot — beat classified `stop_orientation/establishing`, so it EVADES the nf-keyed transit filter (`generation.py:710`) and `_hoist_orientation` promotes it to first position. Scoping: ≥13 nav-imperative beats corpus-wide evade the filter (10 Paris, 3 NY; lexical undercount — e.g. Battery Park's "From the subway, walk into…" also leaks). | pipeline classification + filter gap | **high** | verifiers (2×, both confirmed) |
| D3 | **Big Ben is mis-tiered tier-1 → silently dropped from a Westminster tour whose start is 4 METERS from it.** The dedicated Big Ben POI has 5 active beats (incl. the Benjamin Hall nickname hook); tier-1 fails the dwell floor and the landmark-never-silent guard (`selection.py:153` requires tier ≥ 4). Fix the tier and the SAME Held–Karp opens the tour on Big Ben automatically. Audit other cities for mis-tiered marquee POIs. | POI data (tiering) + SELECT | **high** | verifier a62e2e (refuted "ordering", re-filed here) |
| D4 | **Stop-overload without movement:** N1 Wall Street seats 9 beats about buildings several blocks apart in ONE stop (dwell at the 420s ceiling) — walker stands at a corner being told about things they can't see. | beat_select / POI granularity | **major** | confirmed round 1 |
| D5 | **Prerequisite-context gap:** P2 Notre-Dame narrates the 2023 flèche re-installation and the 2022 pre-scaffolding dig as settled fact but the 2019 fire is NEVER mentioned. | beat_select (context) | **major** | confirmed round 1 |
| D6 | **Cross-water legs unrouted in London + displayed ETA/distance dishonest:** L4's National Gallery→London Eye leg crosses the Thames mid-river (no bridge on the 136° line); displayed total 959 m vs real ~1250–1300 m (~35% under), glue says "11-minute walk" vs real ~15–19 min. The Seine audit (`audit.py`) is Paris-only AND dead code (not called in any served path). BONUS city-agnostic bug: glue ETA uses raw haversine at 80 m/min while the engine budgets 3 km/h × 1.35 — internally inconsistent by ~2.1× on EVERY leg in EVERY city. Time budget itself self-heals (refuted sub-claim). | routing/glue | **major** | verifier ac9985 |
| D7 | **Within-stop paraphrase repetition at 3–4× magnitude** — exact count: 3 of 6 P2 stops carry ≥3× same-fact clusters; Sainte-Chapelle stacks FOUR clusters in one stop ("built to house the relics" ×3, "relics now at Notre-Dame" ×3-4, dates ×3, restoration ×3). The "occasional retelling" premise behind the deferral does not hold at this magnitude. | beat_select / compose-deferred | **major** | verifier a363a2 |
| D8 | **London corpus is city-wide impoverished + no quality gate catches it:** 0/561 London beats have `physical_cues`, 0 have entities (Paris: 74%/87%) — so the L2 Scotland Yard opener and the L4 London Eye finale are flat fact-lists with nothing better available (beat_select voiced 100% of existing beats; refuted at that layer). The engine has NO vivid-beat scoring (`_beat_score` ranks lens/length/wc/id only) and validation blesses kill-switch stops ("Validation passed: True" checks only traceability). | corpus_data + missing quality gate | **major** (city-scoped) | verifier ae0dca |
| D9 | **Tourability banner self-contradiction at the fill boundary:** P5 prints "100% audio fill. This tour ran below the empirical 70-80% audio-fill bar" — above-bar fill rendered with below-bar messaging. | tourability display | minor | artifact, direct |

### Refuted (trust these engine behaviors — do not re-litigate)
- `ERR_SHORT=0.83` target budget; `total_planned_seconds` semantics (three findings).
- "Corpus-underutilization" per-stop caps (by design; deep-thin remains the known open item).
- P5 "misrouted opener" (fabricated premise — Louvre POI is 135.8 m from start, not 0).
- L2 "anti-climactic ordering" at the ordering layer (geometric optimum; arc is COMPOSE's job
  by spec `ALGORITHM-SPEC.md:168-170`; symptom re-filed as D3).
- London kill-switch stops as beat_select failures (100% of corpus voiced; re-filed as D8).

### Is it "interesting"?
In mock mode, not yet — and the campaign located precisely why, with one bright proof of the
ceiling: the quality arm found P1's Place des Vosges stop material is a near word-for-word
match to the product owner's gold-standard sample ("Find a bench in the garden, near the
children's play area…", the Hebrew/Yiddish/Arabic line) — the corpus + selection CAN surface
exactly the right material. The gold sample itself is the author engine over this same
corrected corpus. What stands between today's output and that experience at scale is:
D1/D2/D5 (trust), D4/D7 (shape), D3/D8 (data), then the author/compose layer for voice.

### Recommended next steps (each atomic, test-first, in leverage order)
1. D3: fix Big Ben tier (data) + a marquee-POI tier audit across cities — smallest diff,
   instantly better London tours.
2. D2: semantic transit/practical-directions detection at extraction (model-based per
   no-lexical-shortcuts rule) + runtime guard; migrate the 13 known evaders.
3. D1: contradiction check on co-seated beats (extend the Île-de-la-Cité sweep pipeline to
   NY/London corpora; runtime guard is the Tier-3 follow-up).
4. D6: unify glue ETA with the engine leg budget (one-line class of bug, city-agnostic) +
   either wire a water-crossing guard for tile-less cities or exclude cross-river POIs under
   haversine fallback.
5. D5/D4/D7: beat_select context/granularity work (Tier 2-3, forecast first).
6. D8: London re-onboard with full extracts (`ONBOARD_TARGET_POIS` + non-lead sections) —
   corpus work, not engine.
