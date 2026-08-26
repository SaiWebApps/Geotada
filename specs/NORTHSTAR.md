# ONDOWAY — North Star

> **Last updated:** April 2026 · **Status:** Pre-launch (Phase 1)

---

## Vision

Ondoway makes every city feel like you have a local storyteller in your pocket — surfacing the hidden stories, scandals, and secrets that guidebooks leave out, delivered as GPS-triggered narrative audio that finds you as you walk.

---

## Milestone Plan

| Phase | Window | Gate (must pass to advance) |
|-------|--------|-----------------------------|
| **1 — Build the Machine** | Months 1–3 | 16 taggable lenses covered, 100+ Paris POIs live, Boredom Test passing internally |
| **2 — First Real Walk** | Months 3–4 | 5–10 testers complete a full tour, 8/10 triggers fire, 3/10 recommend unprompted |
| **3 — Public Launch** | Months 4–7 | App Store live, credits active, 200 completed tours, one organic breakthrough |
| **4 — Prove It Scales** | Months 7–12 | City two live in <6 weeks pipeline work, first B2B conversation started |

**Current phase:** Phase 1 — Content pipeline + Editorial Workbench.

**The MVP thesis (everything else is conditional on this):**
Can we generate compelling, personalized narrative tours cost-effectively — and do customers actually care?

---

## Architectural Commitments

These are locked. Do not re-open without a sprint decision entry in the PM Living Doc (Section 04).

- **Database:** Neo4j graph database (Schema v3). Three domains: Traveler's Vault, Global Atlas, Execution Bridge.
- **Graph spine:** User → Profile → Trip → ItineraryItem → POI → NarrativeBeat → Lens. Post-MVP nodes attach as branches, never insertions.
- **Content primitive:** NarrativeBeat — versioned, lensed, gravity-scored (1–5). Max 1 beat per `(lens, sub_location)` tuple per POI. For tier-1/2/3 POIs and any POI where `sub_location` is null, this collapses to the legacy "1 beat per taggable lens per POI" ceiling. For tier-4/5 POIs where the source treats sub-locations as distinct (façade, crypt, nave, salle-des-gens-darmes, pavillon-du-roi, etc.), each non-null `sub_location` gets its own per-lens budget — so Notre-Dame can carry independent `historic_arch` beats for façade + towers + interior without collision. Revised 2026-04-23 from the strict "1 beat per taggable lens per POI" locked commitment, per the extraction-requirements audit against Paris guidebooks — see `Docs/tour-builder/extraction-requirements.md` §B1. PM sprint decision entry pending.
- **Gravity scoring:** Beat-level, not POI-level. Two-signal matrix: POI Reach × Beat Distinctiveness.
- **Lens system:** Hybrid parent/child + leaf architecture. 11 top-level lenses (3 parents, 8 leaves), 8 child lenses = 16 taggable lenses. `is_parent` property on Lens nodes controls taggability. Hardcoded config file. No embedding similarity for MVP. See `specs/2026-03-15-lens-overhaul/`.
- **Audio engine:** ElevenLabs Conversational AI (~$15–20 per 60-min tour). MP3, 256kbps, Stereo, 44.1kHz. Stored on AWS S3.
- **Beat duration formula:** Gravity × 60 seconds per beat.
- **Geocoding:** OpenStreetMap (free) for MVP → Google Maps Geocoding API at launch. 6 decimal places (~10cm). Auto-flag <70% confidence.
- **GPS strategy:** Adaptive polling. 10m fixed geofence trigger radius. Warn user if accuracy >25m.
- **Editorial Workbench:** Browser-based HTML/JS. Leaflet maps. Manual JSON upload (pipeline automation deferred).
- **Content pipeline prompts:** Data Miner V1 (Gemini extraction) and Fact Check & Gravity Score V1 (audit prompt) — both finalized.
- **Extraction philosophy:** Constraints belong at the database layer, not the extraction layer. Keep the miner permissive.
- **Development workflow:** Spec-to-prompt — detailed behavior spec with acceptance criteria → Claude Code implementation prompt → build.
- **Dual-mode product:** Structured Discovery (Planner) and Spontaneous Exploration (Wanderer). Both powered by graph traversals.
- **Golden Ratio:** 20% Anchors (Gravity 5) + 80% Flavour (Gravity 1–4).
- **Monetization:** B2C subscription ($4.99/mo, $39.99/yr) + per-city pass ($3.99–$4.99). Price-to-raise model.
- **Area containment:** `Area` node type with `WITHIN` relationship for spatial hierarchy (city → district → neighborhood/island/corridor). Boundary stored as WKT POLYGON string, containment precomputed into WITHIN edges at ingest. MERGE key: `(name, area_type, city_name)`. See `specs/2026-04-09-area-containment/`.
- **Launch city:** Paris.

---

## Explicit Boundaries

**Will NOT build for MVP:**
- Multi-language support (English only)
- Social/sharing features
- Turn-by-turn navigation (map pin only)
- Full offline tour packs (download-ahead)
- Actual POI photos (lens icons only — copyright risk)
- Haptic feedback
- Payment gateway (all content free for demo phase)
- Pipeline automation (PDF upload → auto-extraction abandoned; manual JSON upload instead)
- Embedding-based lens similarity
- Post-MVP graph nodes: UserPreferences, Badge, Achievement, Challenge, ChallengeCompletion

**Will NOT do (process):**
- Re-open locked technical decisions without a sprint decision entry
- Enforce extraction constraints (1-beat-per-lens) during mining — only at the database layer
- Build retention features, monetization channels, or agent infrastructure before the MVP thesis is validated
- Let AI agents insulate founders from market feedback during founding stage

---

## Pointers

| Document | Location | What it contains |
|----------|----------|------------------|
| **Schema v3** | `Schema_v3.docx` | Full Neo4j node/relationship specs, traversal patterns, domain architecture |
| **12-Month Milestones** | `ondoway-milestones.docx` | Phase gates, product/marketing/business tasks per phase |
| **PM Living Doc** | `ondoway-pm-living-doc.docx` | Scoreboard, resolved decisions (Section 04), sprint templates, stack snapshot, lens list |
| **Monetization Strategy** | `ondoway-monetization-condensed.docx` | Revenue streams, unit economics, persona WTP, retention plan, runway scenarios |
| **Original North Star PRD** | `Northstar.pdf` | Problem definition, dual-mode discovery, Narrative Matrix, Director, feedback loops |
| **Data Miner Prompt V1** | *(in editorial workbench repo)* | Gemini extraction prompt — orientation blocks, sensory anchors, gravity scoring |
| **Fact Check Prompt V1** | *(in editorial workbench repo)* | Audit prompt — two-signal gravity matrix, structured audit_notes |
| **Editorial Workbench** | *(repo)* | Browser-based staging dashboard, split-screen editor, Leaflet map, Commit to Live flow |
| **Area Containment Spec** | `specs/2026-04-09-area-containment/` | Area node type, WITHIN hierarchy, POI migration, spatial containment |

---

## Active Build Target

**Editorial Workbench — Database Upload & Conflict Resolution slice.**

- Conflict detection: hard match (same POI + same lens) → cosine similarity on script_body (auto-conflict ≥70%, review 30–69%, pass-through <30%)
- POI-level changes trigger side-by-side diff for editor review
- Beat resolution options: replace (with version deprecation), delete incoming, merge into versioned beat, or change lens
- Field mapping: `poi_name` → `name`, coordinate conversion, lens display labels → database slugs

**Spec and Claude Code prompt for this slice have not yet been written.**

---

## Open Strategic Conflicts

1. **Between-trip retention scheduling:** Monetization strategy requires journaling + memory reels by Month 4–5. Milestones place personalization at Month 7+. CTO must make a build/defer call before Phase 3 planning.
2. **Runway floor:** Actual burn rate and downside scenario (1K MAU at Month 6) not yet modeled. Must complete before Phase 3.
3. **Tour-design questions carried forward from the retired rule-forward design doc** (`Docs/tour-builder/design.md`, deprecated 2026-04-22, deleted 2026-08-05 — every beat-schema field it proposed shipped, so only these are still unanswered):
   - **Thin-coverage interests.** When an interest lens has a very small beat pool, does the builder widen the interest multiplier, lean on proxy lenses at the same POIs, or tell the user plainly that the tour is thin?
   - **Multi-city generalisation.** Every tour rule in force was derived from Paris data and has never been tested against a second city.
   - **"Extend my tour" UX.** When we honestly deliver 70 minutes against a 2-hour ask, how does the user get more — a pre-computed longer alternative, or on-demand extension?
