# Data Dependencies — Tour Planning Algorithm

Inputs the algorithm requires, what currently exists in the corpus, what's missing, and how the engineer should handle gaps.

---

## 1. Required data — present in corpus ✓

### POI nodes
- `name`, `location` (POINT, 6-decimal precision), `importance_tier` (1-5), `poi_role` (`stop`/`walk_by_only`/`setting`), `city_name`, `kid_friendly`, `trigger_radius`, `typical_duration_min`
- Counts: 367 Paris POIs total — 242 `stop`, 102 `walk_by_only`, 23 `setting`

### NarrativeBeat nodes
- `id`, `script_body`, `duration_sec`, `beat_length_class` (`anchor`/`mid`/`seasoning`/`micro`), `beat_type` (10+ values incl. `transit`, `sensory_observation`, `stop_orientation`), `narrative_function` (`establishing`/`deepen`/`hook`/`climax`/`transition`/`scene_setter`/`callback`), `emotional_register`, `subject_tag`, `entities`, `sub_location`, `active_status`, `kid_friendly`, `physical_cues`, `trigger_address`
- 1,370 active beats in Paris corpus

### Lens nodes
- `name`, `display_label`, `is_parent`
- 11 parents + 8 children + ~10 leaves under parents = 16 taggable lenses

### Area nodes
- `name`, `boundary` (POLYGON WKT), `centroid` (POINT), `area_type` (`city`/`district`/`neighborhood`/`island`), `city_name`
- 34 Paris Areas

### Relationships
- `(POI)-[:HAS_BEAT]->(NarrativeBeat)`
- `(NarrativeBeat)-[:TAGGED_WITH]->(Lens)`
- `(Lens)-[:IS_PARENT_OF]->(Lens)`
- `(POI)-[:WITHIN]->(Area)`
- `(Area)-[:HAS_BEAT]->(NarrativeBeat)` — exists but sparse (only Le Marais Area has beats currently; other Areas' content lives on shadow `setting` POIs)

---

## 2. Required data — gaps blocking implementation

| Gap | Severity | MVP path |
|---|---|---|
| **User profile schema** | High | `User`/`Profile`/`Trip` labels scaffolded but empty. Engineer defines: `Profile` carries `selected_lenses` (array of Lens names), `kid_friendly` (bool). `Trip` carries `start_location`, `destinations` (ordered array of POI ids), `time_budget_min`, `arrive_by` (optional datetime). |
| **User HEARD relationship** | Medium | For beat-freshness tracking. **MVP fallback: assume empty (first-time visitor) for all users.** Engineer adds `(:User)-[:HEARD {at: datetime}]->(:NarrativeBeat)` from day one even if deprioritisation logic stays simple. |

### Architectural commitments locked in this pass

- **Gravity = `POI.importance_tier`.** Beats inherit their POI's gravity; no beat-level gravity computation in MVP. Overrides NORTHSTAR's "Beat-level gravity, POI Reach × Beat Distinctiveness" commit (requires sprint decision entry in PM Living Doc Section 04 to make official). Rationale: important POIs naturally accumulate more beats; beat-level distinctiveness can be re-introduced post-MVP if needed.
- **Lens adjacency = direct + parent/child only for MVP.** No `RELATED_TO` cross-hierarchy edges required. Adjacency weights: direct hit = 1.0, parent/child hop = 0.6, miss = 0.0. Editorial `RELATED_TO` can be added later without algorithm changes.
- **No user-stated lens translation in the algorithm.** Algorithm receives corpus lens names directly. Any user-facing theme→lens mapping (if needed) happens in the UX layer, transparent to the algorithm.

---

## 3. Optional data — degrades gracefully when absent

| Field | Use case | Behaviour when missing |
|---|---|---|
| `interior_visit_available`, `interior_duration_min`, `interior_priority` on POI | Rule D2 — interior options at anchors | Don't surface interior recommendations. Treat tour as exterior-only. |
| Area-attached beats | Rule G2 — Area framing | Algorithm reads the corresponding `setting` POI for Area-level content (e.g. POI `Ile de la Cite` instead of Area `Île de la Cité`). |
| `walk_by_only` POIs along route | Layer B flavor between stops | 102 already in corpus. If a route has none nearby, walking segments stay silent — silence is design. |
| Beat `sub_location` | Layer B stacking at high-gravity POIs | Only 13% of beats have it. When absent, the legacy 1-beat-per-lens-per-POI ceiling applies. |
| Beat `beat_length_class` | Layer B audio budgeting | 64% of beats have it. When missing, use `duration_sec` directly. |

---

## 4. Schema additions recommended for MVP

These don't exist yet and the engineer would need to add them. Each is small (single field/relationship).

| Addition | Purpose | Effort |
|---|---|---|
| `User.id`, `User.email` (constraints exist, no nodes) | Auth, anchoring | Trivial |
| `Profile.id` + properties `selected_lenses: [string]`, `kid_friendly: bool`, `parent_user_id: string` | Per-person lens prefs (one user may have multiple profiles — adult, kid) | Small |
| `Trip.id` + properties `start_location: POINT`, `destinations: [string POI ids]`, `time_budget_min: int`, `arrive_by: datetime?` | Session inputs | Small |
| `(:User)-[:HAS_PROFILE]->(:Profile)` | Multi-profile per user | Trivial |
| `(:Trip)-[:FOR_PROFILE]->(:Profile)` | One Trip per profile per session | Trivial |
| `(:User)-[:HEARD {at: datetime}]->(:NarrativeBeat)` | Beat freshness | Trivial — schema only, can populate later |

---

## 5. Algorithm parameters — values + defaults

| Parameter | MVP value | Source / notes |
|---|---|---|
| Walking speed | 4.5 km/h | Average tourist pace |
| Detour factor | 1.3 | Straight-line × detour to approximate walking distance |
| Proximity threshold for flavor | 40 m | 10m geofence + Paris street width |
| Detour cost — trivial (auto-include) | ≤ 3 min added walking | MVP guess; tunable |
| Detour cost — reject threshold | ≥ 10 min added walking | MVP guess; tunable |
| Detour cost — middle (surface as optional) | 3-10 min | MVP guess |
| Silence cap | 60% of total tour time | Saved feedback discipline |
| Anchor density min | ≥ 1 anchor per 20 min | From v0.1 Step 9 |
| Lens adjacency — direct hit | 1.0 | |
| Lens adjacency — parent/child hop | 0.6 | |
| Lens adjacency — miss | 0.0 | MVP uses direct + parent/child only |
| Min anchor audio per stop | ~60 s | From Layer B samples |
| Max anchor audio per stop | ~150 s | From Layer B samples |
| Safety margin before `arrive_by` | 5 min | Only when `arrive_by` is set |
| Tour duration buckets | 90-150 min (walk-only), 240-300 min (with interiors) | From gold-standard tour |

---

## 6. Data quality flags — known issues

Not blocking. The engineer should know these.

- **36% of beats missing `beat_length_class`** (494 of 1,370). Affects audio budgeting.
- **36% of beats missing `subject_tag`** (487 of 1,370). Affects Rule H1 (anchor points emerge from subject clustering).
- **Only 1.7% of beats are `anchor`-class** (23 total). Golden Ratio target of 20% anchors is structurally constrained.
- **Only 13% of beats have `sub_location`** (181 of 1,370). Multi-beat-per-POI stacking is limited.
- **All beats have empty `city_name`** (1,370). City filter must traverse via POI relationship, not beat property.
- **`film_tv` lens has 3 beats globally; `street_art` has 2.** Lens coverage is uneven. Algorithm must handle "user selected a lens with near-zero corpus coverage."
- **`hidden_history` is 22% of corpus** (305 beats). Algorithm should not over-rely on it for naming or differentiation.
- **33 of 34 Areas have 0 beats directly attached.** Area-level content lives on shadow `setting` POIs. The algorithm should read either source.

---

## 7. Useful corpus metadata the algorithm should exploit

| Field / value | Use |
|---|---|
| `beat_type='sensory_observation'` (71 beats) | Atmospheric/connective glue at low-gravity stops (Rule H11) |
| `beat_type='stop_orientation'` (28 beats) | Stop openers (Rule H6's opener equivalent) |
| `beat_type='transit'` (89 beats) | Walking-segment content / flavor (Layer B between-stop audio) |
| `narrative_function='scene_setter'` (84 beats) | Establishing audio at start of a stop or Area |
| `narrative_function='transition'` (92 beats) | Between-stop connective audio |
| `narrative_function='callback'` (19 beats) | Cross-stop reference (Rule H9 sequence-awareness) |
| `physical_cues` (75% coverage) | Drives Rule H6 close-with-physical-action |
| `kid_friendly` flag on beat | Filter for kid profile |
| `emotional_register` (7 values) | Optional pacing/mood signal at Layer A |

The corpus is more structurally capable than first reads suggested. Most "missing" infrastructure for the algorithm is actually present — the engineer should be made aware of these fields.

---

## 8. Open data decisions for the engineer

1. **Multi-profile model** — one User has many Profiles (adult, kid). Confirmed shape above.
2. **Trip persistence** — does Trip survive after the walk for memory/journaling, or is it ephemeral planning state? Defer to PM (post-MVP retention question).
3. **NORTHSTAR sprint decision entry** — the gravity = POI.importance_tier commitment overrides NORTHSTAR's beat-level gravity commit. Needs to be recorded in PM Living Doc Section 04 before engineer handoff to avoid contradiction.
