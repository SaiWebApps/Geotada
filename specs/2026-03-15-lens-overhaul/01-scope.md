# Scope: Lens Overhaul — Universal Lens Hierarchy

**Date:** 2026-03-15
**North Star Ref:** specs/NORTHSTAR.md
**Status:** APPROVED

---

## What we're building

- **Replace the 12 MVP lenses with a hybrid parent/child + leaf lens architecture.** 11 top-level lenses (3 with children, 8 as directly-taggable leaves). Collapse three history-adjacent lenses (`hidden_history`, `dark_history`, `revolutionary`) into a single `history` parent. Add one new lens (`science_innovation`).
- **Establish the tagging rule: beats tag the most specific lens available.** If a lens has children, beats tag a child — never the parent. If a lens is a leaf (no children), beats tag it directly. Parents with children exist only as category groupings.
- **Define Paris child lenses** for 3 parent lenses (`history`, `arch_design`, `music_nightlife`). Child lenses grow over time as we expand to new cities.
- **Update the hardcoded lens definitions** in `src/schema/definitions.py` (`MVP_LENSES` and `DAG_CHILD_LENSES`).
- **Update seed data** in `src/seed/lenses.py` and all downstream seed files that reference lens slugs (`src/seed/narratives.py`, `src/seed/users.py`).
- **Update all tests and fixtures** that reference the old lens slugs or expect 12/13 lens counts.
- **No direct DB changes.** The database is updated by re-running the seed script when ready. This scope only changes code and config files.

### The lens architecture

#### Parent lenses (with children — NOT directly taggable)

| Parent | Child Slug | Display Label |
|--------|-----------|---------------|
| **history** | `hidden_history` | Hidden History |
| | `war_revolution` | War & Revolution |
| | `dark_history` | Dark History |
| | `social_change` | Social Change |
| **arch_design** | `historic_arch` | Historic Architecture |
| | `modern_design` | Modern & Contemporary Design |
| **music_nightlife** | `music_heritage` | Music Heritage |
| | `venues_scenes` | Venues & Scenes |

#### Leaf lenses (directly taggable — no children yet)

| Slug | Display Label |
|------|--------------|
| `local_legends` | Local Legends & Folklore |
| `food_culinary` | Food & Culinary Culture |
| `art_street` | Art & Street Culture |
| `literary_film` | Literary & Film Locations |
| `religious_spiritual` | Religious & Spiritual Sites |
| `nature_green` | Nature & Green Spaces |
| `shopping_markets` | Shopping & Markets |
| `science_innovation` | Science & Innovation |

**Totals:** 11 top-level lenses, 8 child lenses, 8 leaf lenses. Beats can be tagged with any of the **16 taggable lenses** (8 children + 8 leaves).

### Future-proofing strategy

- **Adding a child lens** = add to config, seed it. Zero impact on existing data.
- **Adding a parent lens** = add to config, seed it. Zero impact on existing data.
- **Promoting a leaf to a parent** = the one operation requiring migration. Create a `general` child under the promoted parent, bulk re-tag existing beats to that child. One query, no data loss.

### Tagging constraint

- **1 beat per taggable lens per POI.** Max beats per POI = number of taggable lenses (currently 16).
- **No beat may be tagged with a parent lens.** Parents are category groupings only.

## Why

The current lens set has three history-flavored lenses that are Paris-specific and don't scale to other cities. This conflicts with the Phase 4 gate ("City two live in <6 weeks pipeline work"). The hybrid parent/child + leaf architecture enables rich, categorized beats for the narrative engine while keeping the taxonomy lean. Too many lenses = sparse content per lens. Too few = limited story diversity.

## What we're NOT building

- UI for sub-lens browsing or selection in the workbench (lenses display flat in dropdowns for now)
- Embedding-based lens similarity (explicitly excluded in north star)
- City-specific lens configuration (all lenses are global; child lenses grow as we add cities)
- Automatic leaf-to-parent promotion

## What already exists

- **`src/schema/definitions.py`** (lines 117-139) — `MVP_LENSES` list and `DAG_CHILD_LENSES` list. Primary config to update.
- **`src/seed/lenses.py`** — Lens seeding via Cypher MERGE. Reads from definitions. Already supports `IS_PARENT_OF` relationship creation.
- **`src/seed/narratives.py`** — Beat seed data references lens slugs (`hidden_history`, `dark_history`, etc.). Needs re-mapping to new child/leaf slugs.
- **`src/seed/users.py`** — Profile lens preferences reference slugs. Needs re-mapping.
- **`frontend/review.html`** — `lensDisplayToSlug` mapping, lens dropdowns, `resolveLensSlug()`. Will auto-populate from API, but must only show taggable lenses (children + leaves, not parents) in beat tag dropdowns.
- **`tests/`** — `test_definitions.py`, `test_seed.py`, `test_traversals.py`, `test_upload_api.py` all assert lens counts and slugs.
- **`tests/fixtures/stress_test_upload.json`** — Uses display labels that need updating.

## Dependencies or risks

- **North star update needed:** "12 lenses covered" language needs updating. The lens system commitment ("12 lenses, hardcoded config file") should reflect the new hybrid architecture. The PM Living Doc lens list also needs updating.
- **Re-seed impact:** When the seed script is eventually re-run, it will reset lens data and destroy existing TAGGED_WITH and PREFERS_LENS edges. Acceptable pre-launch with minimal data, but editor should be aware.
- **Frontend lens filtering:** The workbench dropdown must show only taggable lenses (children + leaves), not parent-only lenses. If the API returns all lenses flat, the frontend needs to filter.
- **Beat duration formula:** North star says "Gravity × 60 seconds per beat." With more taggable lenses (16 vs 12), a POI could have more beats. No formula change needed, but the narrative engine should be aware of higher potential beat counts.

## Best practices domains touched

- **Data integrity** — slug migration, tagging constraint enforcement
- **Consistency** — hardcoded definitions, seed data, tests, frontend filtering, and DB must all align
- **UX** — frontend must only expose taggable lenses for beat tagging
