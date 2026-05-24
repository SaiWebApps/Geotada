# Tour Planning Algorithm — Engineer Spec

> Draft. Companion: `journey.md` (human-readable behavioural description). Last refined 2026-05-23.

This spec describes the algorithm that produces a personalised walking tour from user inputs. It is implementation-agnostic — the engineer chooses how to code it. The spec defines inputs, outputs, rules, and parameters.

---

## 1. Purpose & scope

Given a user at a starting location with optional destinations and a time budget, produce:
- A walking route (stop sequence, walking segments, interior options, duration estimate)
- Per-Profile narrative content selection (which beats fire at each stop, in what order, for what duration)

The execution layer (geofence triggering, audio playback) is **out of scope** — this spec produces a plan; another system fires it.

### MVP scope: single user, single Profile, single Trip

For MVP, exactly one Profile per Trip. The full multi-Profile family-stay-together architecture is preserved in this spec so the engineer doesn't have to refactor later — but it is **not implemented in MVP**.

What this means concretely:
- `Trip.profiles` is a list, but MVP enforces `len(profiles) == 1`.
- `Layer A` runs once, returns one route.
- `Layer B` runs once, for the single Profile.
- No multi-Profile conflict surfacing, no synced audio across walkers, no per-Profile audio variance UX.
- The `(:User)-[:HAS_PROFILE]->(:Profile)` relationship exists in schema (1:N), but MVP uses 1:1.

Future post-MVP work expands `len(profiles) > 1` and adds family-walking-together UX. The algorithm rules below remain valid in both cases.

---

## 2. Locked architectural commitments

These are decisions made and not to be re-opened without a sprint decision entry:

- **Two-layer architecture.** Layer A produces the shared route. Layer B produces per-person content for that route. One Layer A call per trip; one Layer B call per profile.
- **Gravity is POI-level via `POI.importance_tier`.** Beat-level gravity is not used. (Overrides NORTHSTAR's "Beat-level gravity, POI Reach × Beat Distinctiveness" — sprint decision entry required.)
- **Lens adjacency is computed via graph traversal over the Lens hierarchy.** MVP uses direct hit + parent/child hop only. No vector embeddings. No `RELATED_TO` cross-hierarchy edges in MVP.
- **No user-stated-lens translation in the algorithm.** The algorithm receives canonical Lens names. Any UX-layer theme→lens mapping is transparent to the algorithm.
- **Walking-only.** No transit modes.
- **Walking time = straight-line × 1.3 ÷ 4.5 km/h.** Computed on demand. Upgrade to OSRM later if precision matters.
- **Proximity threshold for flavor = 40 m.** Tunable per city post-launch.
- **Silence floor = 60% of total tour time.** Audio fills no more than 40% of total time.
- **No padding to budget.** If the natural tour is shorter than the budget, return the shorter tour. Slack belongs to the user.
- **Deterministic naming.** Tour name = `{dominant_lens_label}: {top_anchor_poi_name}`. No LLM-validated naming.
- **Family stays together physically.** Layer A is shared; personalisation lives in Layer B. *(Architecture preserved for post-MVP; MVP is single-Profile.)*

---

## 3. Inputs

### Profile (per person, persistent)
| Field | Type | Required | Notes |
|---|---|---|---|
| `selected_lenses` | `[Lens.name]` | yes | One or more canonical lens names from the 16 taggable lenses |
| `kid_friendly` | bool | yes | If true, restrict beats to `kid_friendly='yes'` and use kid-shape rules where applicable |

### Trip (per session)
| Field | Type | Required | Notes |
|---|---|---|---|
| `start_location` | POINT | yes | Lat/lng of starting point |
| `destinations` | `[POI.id]` | optional | Ordered if user-specified; algorithm may geographically reorder with notification |
| `time_budget_min` | int | yes (or `arrive_by`) | Minutes available |
| `arrive_by` | datetime | optional | If set, `time_budget = arrive_by − now − 5 min safety margin`; takes precedence over `time_budget_min` |
| `profiles` | `[Profile.id]` | yes | Profiles walking together; all share Layer A, each gets its own Layer B. **MVP: exactly one Profile per Trip.** |
| `hard_constraints` | object | optional | `mobility`, `kid_friendly` (group-level), etc. |

### Reference data (read from Neo4j)
| Source | Use |
|---|---|
| `POI` nodes | Stop candidates, walk-by candidates, importance tiers |
| `NarrativeBeat` nodes | Layer B content |
| `Lens` graph | Adjacency scoring |
| `Area` nodes + `(POI)-[:WITHIN]->(Area)` | Spatial corridor + area-framing |
| `(POI)-[:HAS_BEAT]->(NarrativeBeat)` | Beat selection at stops |
| `(NarrativeBeat)-[:TAGGED_WITH]->(Lens)` | Lens matching |
| `(Lens)-[:IS_PARENT_OF]->(Lens)` | Adjacency hops |
| `(:User)-[:HEARD]->(:NarrativeBeat)` | Freshness (MVP: assume empty) |

---

## 4. Outputs

### Layer A output (shared route)
```
{
  stops: [
    {
      poi_id: string,
      role: "anchor" | "mood_pacing" | "content" | "segment" | "area_framing_carrier",
      area_id: string?,      // Area this stop sits within
      enters_area: bool,     // true if this is the first stop in a new Area (Area-framing duty)
      interior_option: {     // optional, only on anchors
        available: bool,
        duration_min: int,
        priority: int        // 1=recommended, 2=optional, 3=skip-by-default
      }?
    }
  ],
  segments: [
    {
      from_stop_index: int,
      to_stop_index: int,
      walking_distance_m: int,
      walking_time_min: int,
      flavor_candidates: [POI.id]   // walk_by_only POIs within 40m of path
    }
  ],
  optional_detours: [
    {
      poi_id: string,
      added_walking_min: float,
      surface_to_user: true       // user accepts or rejects pre-tour
    }
  ],
  total_estimate: {
    walking_min: int,
    audio_min_estimated: int,     // computed across the Profile's Layer B (MVP: one Profile)
    dwell_min_with_interiors: int,
    total_min: int
  },
  reordering_notes: [string]      // if destinations were geographically reordered
}
```

### Layer B output (per profile, given a Layer A output)
```
{
  profile_id: string,
  per_stop_audio: [
    {
      stop_index: int,
      beats: [
        {
          beat_id: string,
          play_order: int,
          duration_sec: int,
          role: "opener" | "anchor_point" | "atmospheric" | "callback" | "physical_action_close" | "area_framing"
        }
      ],
      total_audio_sec: int
    }
  ],
  per_segment_audio: [
    {
      segment_index: int,
      flavor_beats: [
        {
          beat_id: string,
          duration_sec: int
        }
      ]
    }
  ],
  tour_name: string,           // {dominant_lens_label}: {top_anchor_poi_name}
  total_audio_min: int,
  silence_pct: float           // must be ≥ 60%
}
```

---

## 5. Layer A — rules

### 5.1 Place categories (used in `role` field)

| Category | Description |
|---|---|
| `anchor` | Unmissable stop. User-named destinations + T5 POIs on natural path. Cannot be cut. |
| `mood_pacing` | Quiet/atmospheric stop inserted to break up content clusters (e.g. Place Dauphine, Square du Vert-Galant). |
| `content` | T3-T4 POI with strong lens density for the group. |
| `segment` | Walk-through segment where the geography itself is the experience (e.g. "along the Seine"). May have minimal or zero audio per stop. |
| `area_framing_carrier` | The first stop within an Area; carries the duty to introduce the Area in its narrative. Not a separate stop type — applied as a tag to whichever stop is first in the Area. |

Two additional categories not stored as stops but tracked:
- **Optional detour** — POI surfaced to user for accept/reject; high content, moderate detour cost.
- **Viewing reference** — POI named within a stop's narrative but not visited (e.g. Institut de France seen across the river from Pont des Arts).

### 5.2 Stop selection

- **Rule B1.** User-named destinations are always anchors.
- **Rule B2.** T5 POIs on the natural route (start→destinations geographic line) are anchors.
- **Rule B3.** Mood/pacing stops are inserted between two content-heavy anchors to break clustering. Selection: candidate POIs with low lens hits but strong atmospheric character (`poi_role='stop'`, `importance_tier ∈ {T2, T3}`, near the route).
- **Rule B4.** Geographic feature stops are valid even with few/no beats — view/place is the experience.
- **Rule B5.** High-content POIs requiring backtracking (detour ≥ 10 min added walking) are excluded.
- **Rule B6.** High-content POIs requiring moderate detour (3-10 min added walking) become optional detours surfaced to the user.
- **Rule B7.** Candidates outside the city geofence are excluded (NORTHSTAR commit: queries scoped to city).

### 5.3 Sequencing

- **Rule C1.** Order stops by geographic projection along the start→destinations line.
- **Rule C3.** Avoid clustering two content-heavy stops without an intervening mood/pacing stop when the route allows.

### 5.4 Areas

- **Rule G1.** The route traverses Areas. Layer A identifies which Areas the route enters/exits via `(POI)-[:WITHIN]->(Area)` relationships and spatial-containment of segments.
- **Rule G2.** The first stop within each Area is tagged `enters_area=true` and carries a narrative duty (Layer B threads Area framing through the stop's audio).
- **Rule G3.** Area-framing is not a separate audio slot — it's woven into the first stop's narrative. No standalone "you are now entering X" beat.

### 5.5 Duration

- **Rule D1.** Natural tour durations cluster at two scales: walk-only (90-150 min) and walk-plus-interior (240-300 min).
- **Rule D2.** Interior options are flagged at specific anchors with `interior_visit_available`, `interior_duration_min`, `interior_priority`. The algorithm surfaces these as user choices; does not auto-include.
- **Rule D3.** No padding to budget. Deliver the shortest natural duration that fits the budget. Slack returned to user.

### 5.6 Detour cost-benefit

- **Rule E1.** Detour cost = added walking time relative to the natural route.
- **Rule E2.** Detour gain = beat count × lens density for the group at the candidate POI.
- **Rule E3.** Thresholds (MVP):
  - `cost ≤ 3 min added` AND `gain > 0` → include as a stop
  - `3 < cost < 10 min` → surface as optional detour
  - `cost ≥ 10 min` → exclude regardless of gain

### 5.7 Feasibility

- **Rule F1.** If destinations are named, check walking distance + minimum dwell time fits the budget. If not, fail before planning (surface conflict to user).
- **Rule F2.** Audio cap = 0.40 × time_budget. Total Layer B audio time must fit. If insufficient lens-matching content exists for a profile, deliver thinner audio rather than padding.

---

## 6. Layer B — rules

### 6.1 Inputs

Receives:
- Layer A output (stops, segments, interior choices)
- Profile (selected_lenses, kid_friendly)
- HEARD relationships (MVP: empty)

### 6.2 Anchor points within a stop

- **Rule H1.** At each stop, group beats by `subject_tag`. Each distinct subject cluster is an "anchor point" of that stop.
- **Rule H2.** Universal anchor points: subject clusters with high beat count and broad lens coverage tend to fire regardless of which lenses are selected (because they hit several lenses each).
- **Rule H4.** Lens-specific anchor points: subject clusters whose beats only hit certain lenses fire only for users with matching lenses.

### 6.3 Beat selection per profile per stop

For each stop (MVP runs this once for the single Profile; post-MVP iterates per Profile):
1. Score candidate beats: `score = lens_adjacency(beat.lens, profile.selected_lenses)`
2. Apply filters: `kid_friendly` if profile.kid_friendly; deprioritise (do NOT exclude) beats in the User's HEARD set so returning users still get content
3. Group selected beats by `subject_tag`; pick at most one beat per `(subject_tag, sub_location)` pair
4. Order selected beats by `narrative_function`: `establishing` → `hook` → `deepen` → `climax` → `transition`
5. Trim if total duration exceeds `max_anchor_audio_sec` (default 150s for anchors, scaled by gravity for lower-tier stops)

### 6.4 Audio duration per stop

- **Rule H7.** Audio duration scales with POI gravity (= `importance_tier`) AND with the number of sub_locations the user covers at that stop:
  - T5 anchors: ~90-150s per sub_location reached. For POIs covered while walking around the site (Notre-Dame exterior loop, Conciergerie + Palais de Justice complex, Louvre courtyards), total audio at the anchor may extend to ~300-400s across multiple sub_locations.
  - T4 anchors: ~60-120s per sub_location
  - T3 supporting: ~45-90s
  - T2 supporting: ~30-60s
  - T1: ~15-45s (often segment-level)

### 6.5 Area framing

- **Rule G2 (Layer B side).** At any stop where `enters_area=true`, the audio is threaded with one Area-framing sentence/clause. Source: a beat from the Area node OR the shadow `setting` POI (e.g. POI `Ile de la Cite` for Area `Île de la Cité`). Selection: highest-gravity, highest-adjacency beat from that source.

### 6.6 Stop opener & closer

- **Rule H6.** Each stop's audio closes with a physical action cue. Source: beat with `physical_cues` populated. If no such beat fires, generate a one-line close from the `physical_cues` field of any selected beat.
- **Rule H6b (opener).** Each stop opens with `beat_type='stop_orientation'` or `narrative_function='establishing'`. When the prior stop's narrative referenced this one ("ahead of us is X"), the opener can be a `narrative_function='callback'` beat.

### 6.7 Sequence awareness

- **Rule H9.** Layer B is sequence-aware. Per-stop selection considers what fired at the prior stop. `narrative_function='callback'` beats are preferred when the prior stop set up the callback.

### 6.8 Connective glue & atmospheric content

- **Rule H10.** Connective/atmospheric audio between facts comes from the corpus, not the runtime. Sources:
  - `beat_type='sensory_observation'` — atmospheric framing
  - `beat_type='transit'` — walking-segment content
  - `beat_type='stop_orientation'` — openers
  - `narrative_function='scene_setter'`, `'transition'` — connective phrasing
- **Rule H11.** At low-gravity stops where factual beats are thin, Layer B leans harder on `sensory_observation` and `scene_setter` beats. The audio becomes atmospheric rather than fact-dense.

### 6.9 Flavor between stops

- **Rule J1.** Walking segments may carry flavor audio. Source: beats at `poi_role='walk_by_only'` POIs within 40 m of the segment path, filtered by `lens_adjacency > 0` for the profile.
- Silence between stops is acceptable. If no qualifying flavor beats exist, the segment is silent.

### 6.10 Tour naming

- **Rule N1.** `tour_name = "{dominant_lens.display_label}: {top_anchor.name}"`
- `dominant_lens` = the lens with the highest summed adjacency-weighted beat count across the locked Layer B audio
- `top_anchor` = the highest-gravity anchor in the route
- Exclude `hidden_history` from being the dominant lens (corpus catch-all; produces low-signal names)

---

## 7. Lens adjacency formula

For each candidate beat:
1. Get the beat's `Lens` (via `TAGGED_WITH`).
2. For each lens in the profile's `selected_lenses`:
   - If beat's lens == profile's lens: adjacency = 1.0 (direct hit)
   - Else if beat's lens is a parent/child of any profile lens (1 hop in `IS_PARENT_OF`): adjacency = 0.6
   - Else: adjacency = 0.0 (miss)
3. Beat's score = max adjacency across the profile's lenses, scaled by `importance_tier`:
   - `beat_score = adjacency × POI.importance_tier`

A beat with adjacency = 0 can still fire if it's a `sensory_observation`, `stop_orientation`, or `scene_setter` (atmospheric/connective beats are lens-agnostic).

---

## 8. Parameters

| Parameter | MVP value | Notes |
|---|---|---|
| Walking speed | 4.5 km/h | |
| Detour factor | 1.3 | Straight-line × detour |
| Proximity threshold (flavor) | 40 m | |
| Detour: include threshold | ≤ 3 min added walking | |
| Detour: reject threshold | ≥ 10 min added walking | |
| Silence floor | 60% of total tour time (audio fills no more than 40%) | |
| Anchor density min | ≥ 1 anchor per 20 min | |
| Lens adjacency: direct hit | 1.0 | |
| Lens adjacency: parent/child hop | 0.6 | |
| Lens adjacency: miss | 0.0 | |
| Min anchor audio per stop | ~60 s | |
| Max anchor audio per stop | ~150 s | |
| Safety margin before `arrive_by` | 5 min | |
| Natural tour durations | 90-150 min (walk-only), 240-300 min (interiors) | |

---

## 9. Worked example

**Inputs (MVP single-Profile):**
- Profile: `{dark_history, hidden_history, historic_arch}` (Royal/Dark/Architecture)
- Start: hotel near Place de la Concorde (`48.8676, 2.3214`)
- Destinations: Louvre Museum, Notre-Dame Cathedral
- Time budget: 180 min

*(The sample-tour.md document shows the same route with three illustrative Profiles to demonstrate how the Layer B architecture extends post-MVP. MVP only runs Layer B once per Trip.)*

**Layer A output (abbreviated):**

| # | POI | Role | Area | Enters area |
|---|---|---|---|---|
| 1 | Place de la Concorde | anchor (T4) | Madeleine-Concorde | true |
| 2 | Jardin des Tuileries | anchor (T5) | 1st Arr | true |
| 3 | Arc de Triomphe du Carrousel | content (T5) | 1st Arr | false |
| 4 | Louvre Museum (destination) | anchor (T5) | 1st Arr | false |
| 5 | (segment: Louvre → Pont Neuf via Seine) | segment | — | — |
| 6 | Pont Neuf | anchor (T5) | Île de la Cité | true |
| 7 | Square du Vert-Galant | mood_pacing (T3) | Île de la Cité | false |
| 8 | Place Dauphine | mood_pacing (T2) | Île de la Cité | false |
| 9 | Conciergerie | anchor (T5) | Île de la Cité | false |
| 10 | Sainte-Chapelle | anchor (T5) | Île de la Cité | false |
| 11 | (mood_pacing stop in Marché aux Fleurs vicinity if corpus content exists) | — | — | — |
| 12 | Notre-Dame Cathedral (destination) | anchor (T5) | Île de la Cité | false |

Total walking ≈ 47 min. Audio cap = 72 min (40% of 180-min budget). Estimated audio for the Profile ≈ 30-45 min. Total estimated = walking 47 + audio 30-45 ≈ 77-92 min (well under the 180-min budget — no padding; slack returned to user per Rule D3).

**Layer B sample at Pont Neuf for Adult A** (illustrative; not actual generated output):
- Area framing woven in: "you're touching the western tip of Île de la Cité, the island where Paris began"
- Anchor points covered: bridge novelty (history), mascarons (architecture), Henri IV statue (royal), open-design (architecture), island gateway (history)
- Total duration: ~120-150s
- Physical action close: "look both ways along the river"

**Layer B sample at Place Dauphine for Adult A:**
- No Area framing (not first in Area)
- Anchor points covered: hidden quality (atmosphere), Henri IV's vision (royal, callback to Pont Neuf), triangular shape (architecture), human scale (atmosphere)
- Total duration: ~60-90s
- Physical action close: "notice how quickly the feeling changes"

(See `sample-tour.md` for full per-persona text.)

---

## 10. Boundaries (NOT in MVP)

- **Multi-Profile per Trip** — architecture supports `len(profiles) > 1` but MVP enforces single Profile. Family-stay-together UX is post-MVP.
- Multi-language support — English only
- LLM-validated theme regeneration — deterministic naming only
- Sightline-based transit beats — proximity only
- Mid-tour drift detection — data model tracks but no surfacing logic
- Embedding-based lens similarity — graph traversal only
- Editorial `RELATED_TO` lens edges — direct + parent/child only
- Tour reordering after start — route is locked at planning time
- Beat-level gravity — POI-level only

---

## 11. Known data quality issues (informational)

- 36% of beats missing `beat_length_class`
- 36% of beats missing `subject_tag` (affects Rule H1)
- 13% of beats have `sub_location` (multi-beat-per-POI stacking is limited)
- 1.7% of beats are `anchor`-class (Golden Ratio target structurally constrained)
- `city_name` empty on all beats — filter via POI relationship
- `film_tv` has 3 beats globally, `street_art` 2 — uneven lens coverage
- `hidden_history` is 22% of corpus — excluded from naming
- 33 of 34 Areas have 0 directly attached beats; content lives on shadow `setting` POIs

---

## 12. Schema additions required for engineer

- `Profile` properties: `selected_lenses: [string]`, `kid_friendly: bool`
- `Trip` properties: `start_location: POINT`, `destinations: [string]`, `time_budget_min: int`, `arrive_by: datetime?`
- `(:User)-[:HAS_PROFILE]->(:Profile)`
- `(:Trip)-[:FOR_PROFILE]->(:Profile)`
- `(:User)-[:HEARD {at: datetime}]->(:NarrativeBeat)` (schema only for MVP; population deferred)
- Optional: `interior_visit_available: bool`, `interior_duration_min: int`, `interior_priority: int` on POI nodes that warrant interior visits

---

## 13. References

- `data-dependencies.md` — full data dependency analysis
- `journey.md` — human-readable behavioural description
- `sample-tour.md` — full 12-stop Layer A route + Pont Neuf and Place Dauphine sample audio for 3 personas
- NORTHSTAR.md (root spec) — locked product commitments
