# Tour Planning Algorithm — Human-Readable Spec

> Companion to `engineer-spec.md`. Same content, plain-language structure for collaborating on understanding. The format borrows from the user-journey docs we already use, but the subject here is the algorithm, not the end user.

---

**Algorithm:** Tour Planning (Layer A + Layer B)

**Job:** Given a Trip (start, optional destinations, time budget) and a Profile (lens preferences), produce a walking route and personalised narrative audio.

**MVP scope:** Single user, single Profile, single Trip. The algorithm architecture supports multi-Profile family-stay-together (one shared Layer A route + per-Profile Layer B audio), but **MVP enforces exactly one Profile per Trip**. The multi-Profile capability is preserved in the design so post-MVP family work doesn't require a refactor.

**Caller:** The app's tour-creation flow.

**Pre-conditions:**
- City corpus exists in Neo4j with POIs, NarrativeBeats, Lenses, and Areas populated.
- Trip carries a valid start location, a time budget (or `arrive_by`), and exactly one Profile (MVP).
- The Profile has at least one selected Lens (from the 16 canonical taggable lenses).

---

## Steps

| # | Stage | What the algorithm does | What it produces |
|---|-------|------------------------|------------------|
| 1 | **Validate inputs** | Confirms the Trip has a start location, ≥1 Profile, and either a time budget or an `arrive_by`. Resolves `arrive_by` to a time budget minus a 5-min safety margin. | Validated Trip + Profile set |
| 2 | **Identify the corridor** | Determines the geographic corridor: if destinations are named, the corridor follows their natural ordering (algorithm may reorder for efficiency and surface the change); if no destinations, corridor is the achievable walking radius from start. | Bounding region or path geometry |
| 3 | **Feasibility check** | Confirms named destinations are reachable on foot within the budget. If not, fails before planning and returns the conflict. | Pass/fail + diagnostic |
| 4 | **Layer A — Stop selection** | Picks anchor stops (user-named destinations + T5 POIs on the path), then inserts mood/pacing stops between content-heavy anchors, then identifies segments where geography is the experience. Excludes POIs requiring backtracking (≥10 min detour). Flags moderate detours (3-10 min) as optional. | Ordered stop list with roles (anchor, mood_pacing, content, segment) |
| 5 | **Layer A — Area mapping** | For each stop, looks up the Area it sits in via `(POI)-[:WITHIN]->(Area)`. Tags the first stop in each Area as `enters_area`. | Stops annotated with Area context |
| 6 | **Layer A — Interior options** | For anchors that support interior visits (`interior_visit_available=true`), surfaces them with `interior_priority` for user choice. Algorithm does not auto-include interiors — caller resolves with user. | Optional interior choices |
| 7 | **Layer A — Duration estimate** | Computes walking time (straight-line × 1.3 ÷ 4.5 km/h) plus estimated audio (Layer B's job — first-pass estimate). Picks the smallest natural duration bucket (walk-only or with-interior) that fits the budget. Never pads. | Route output ready for caller confirmation |
| 8 | **Layer B — Lens adjacency** | For the Profile, computes adjacency between every candidate beat's Lens and the Profile's selected Lenses (graph traversal: direct hit 1.0, parent/child hop 0.6, miss 0.0). | Beat scores |
| 9 | **Layer B — Beat selection per stop** | For each stop: groups available beats by `subject_tag` (anchor points). Within each subject, picks the beat with highest adjacency. Applies kid_friendly filter if needed. Deprioritises beats already in the User's HEARD set. | Beat plan per stop |
| 10 | **Layer B — Ordering and budgeting** | Orders selected beats by narrative function (`establishing` → `hook` → `deepen` → `climax` → `transition`). Trims to fit per-stop duration cap (scales by POI.importance_tier: T5 anchors ~150s, T2 supporting ~60s). Closes each stop with a physical-action cue. | Time-budgeted audio sequence per stop |
| 11 | **Layer B — Area framing** | At any stop tagged `enters_area`, threads in one Area-framing beat (from the Area node or the shadow `setting` POI). Not a separate audio slot — woven into the stop's opening. | Area context delivered |
| 12 | **Layer B — Segment flavor** | For each walking segment, checks for `walk_by_only` POIs within 40m of the path with beats matching the Profile's lenses. Selects 0-N flavor beats; silence is acceptable. | Flavor audio per segment |
| 13 | **Layer B — Tour naming** | Computes `dominant_lens` (highest summed adjacency-weighted beat count across the locked audio) and `top_anchor` (highest-gravity anchor). Excludes `hidden_history` from being the dominant lens. Tour name = `"{dominant_lens.display_label}: {top_anchor.name}"`. | Tour name |
| 14 | **Output** | Returns Layer A + Layer B to the caller. | Complete tour plan |

*(Post-MVP multi-Profile mode: steps 8-13 run once per Profile. Layer A is still shared. MVP runs them once.)*

---

## Success state

- Layer A returns a stop list that starts at the user's location, includes every user-named destination, includes T5 POIs on the path, and stays within the time budget without padding.
- The Profile gets a Layer B audio plan: beats per stop ordered by narrative function, scaled by POI gravity, closed with a physical-action cue.
- Total audio time is ≤ 40% of total tour time (silence cap honoured).
- Tour name is deterministic, lens-coherent, and doesn't lead with `hidden_history`.
- *(Post-MVP multi-Profile case: identical Layer A across Profiles + distinct Layer B per Profile.)*

---

## Failure modes

- **Infeasible destinations.** Named destinations can't be reached on foot in the time budget. Algorithm fails at Step 3 with a clear diagnostic. *(No silent destination cutting — Rule F1.)*
- **Corpus-thin lens.** The Profile selects a lens with very few corpus beats (e.g. `film_tv` with 3 beats globally). Layer B delivers atmospheric/connective content instead — does not silence and does not pad. May produce a thin audio plan. *(See open question on graceful-degradation surfacing.)*
- **Lens monoculture at an anchor.** *(Post-MVP)* If two Profiles share a dominant lens, their Layer B at heavy-dark-history anchors like Conciergerie (69% dark_history) overlaps heavily. The "same feet, different tour" promise weakens. Not a concern for MVP single-Profile.
- **Backtracking destinations.** User-stated destination order produces backtracking. Algorithm reorders geographically and surfaces the change to the caller (caller decides whether to accept or override).
- **Empty corpus stop.** A POI the user named or expected has zero beats. Layer B produces a minimum atmospheric beat or stays silent. Algorithm does not invent content.
- **Time budget can't fit a natural duration.** Walking + minimum audio already exceeds budget. Algorithm fails feasibility (Step 3) with diagnostic.

---

## Open questions

- **Graceful-degradation surfacing.** When a Profile's lens has near-zero corpus content, should the algorithm warn the caller (so the UX can tell the user their selection has thin coverage in this corridor), or silently deliver atmospheric content?
- **Optional detour presentation.** Algorithm flags detours as optional in Layer A output. Caller decides whether to surface them pre-tour (toggles) or in-the-moment (prompts as the walker approaches). Out of algorithm scope, but the algorithm needs to know which to optimise for.
- **Beat freshness strength.** HEARD beats are deprioritised in Step 9. How much? Halved? Excluded entirely? Soft-decay over time? Affects returning visitors.
- **Profile defaults.** What happens when a Profile has no lenses set yet? Block the algorithm? Use a default popular set?
- *(Post-MVP)* **Layer B parallelism.** When multi-Profile is enabled, a 4-Profile family means 4× Layer B runs. Run sequentially, in parallel, or as a single multi-Profile query? Performance question for that work.
- *(Post-MVP)* **Conflict between Profiles at the route level.** Profile A wants stop X (high lens match), Profile B doesn't. The route is shared; algorithm includes X for the group. Surface conflict, or silent?
