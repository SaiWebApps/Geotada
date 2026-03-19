# Implementation Plan: Lens Overhaul — Universal Lens Hierarchy

**Date:** 2026-03-17
**Spec Ref:** specs/2026-03-15-lens-overhaul/02-spec.md
**Red Team Ref:** specs/2026-03-15-lens-overhaul/03-red-team.md
**North Star Ref:** specs/NORTHSTAR.md
**Status:** DRAFT — awaiting approval

---

## Part A — Task Breakdown

### Task 1: Update lens definitions in `definitions.py`

**Files to touch:** `src/schema/definitions.py`

**What to do:**
1. Replace `MVP_LENSES` (lines 117-130) with the new 11 top-level lenses. Each dict gets a new `is_parent` key (`True` for `history`, `arch_design`, `music_nightlife`; absent/`False` for the 8 leaves).
2. Replace `DAG_CHILD_LENSES` (lines 133-139) with the 8 child lenses, each referencing its `parent_name`.
3. Add a new `TAGGABLE_LENSES` export — a hardcoded list of the 16 taggable slug strings (8 children + 8 leaves). Not computed from `is_parent`.

**New `MVP_LENSES` (11 items):**
```python
MVP_LENSES = [
    {"name": "history", "display_label": "History", "is_parent": True},
    {"name": "arch_design", "display_label": "Architecture & Design", "is_parent": True},
    {"name": "music_nightlife", "display_label": "Music & Nightlife", "is_parent": True},
    {"name": "local_legends", "display_label": "Local Legends & Folklore"},
    {"name": "food_culinary", "display_label": "Food & Culinary Culture"},
    {"name": "art_street", "display_label": "Art & Street Culture"},
    {"name": "literary_film", "display_label": "Literary & Film Locations"},
    {"name": "religious_spiritual", "display_label": "Religious & Spiritual Sites"},
    {"name": "nature_green", "display_label": "Nature & Green Spaces"},
    {"name": "shopping_markets", "display_label": "Shopping & Markets"},
    {"name": "science_innovation", "display_label": "Science & Innovation"},
]
```

**New `DAG_CHILD_LENSES` (8 items):**
```python
DAG_CHILD_LENSES = [
    {"name": "hidden_history", "display_label": "Hidden History", "parent_name": "history"},
    {"name": "war_revolution", "display_label": "War & Revolution", "parent_name": "history"},
    {"name": "dark_history", "display_label": "Dark History", "parent_name": "history"},
    {"name": "social_change", "display_label": "Social Change", "parent_name": "history"},
    {"name": "historic_arch", "display_label": "Historic Architecture", "parent_name": "arch_design"},
    {"name": "modern_design", "display_label": "Modern & Contemporary Design", "parent_name": "arch_design"},
    {"name": "music_heritage", "display_label": "Music Heritage", "parent_name": "music_nightlife"},
    {"name": "venues_scenes", "display_label": "Venues & Scenes", "parent_name": "music_nightlife"},
]
```

**New `TAGGABLE_LENSES` (16 items):**
```python
TAGGABLE_LENSES: list[str] = [
    # Children of history
    "hidden_history", "war_revolution", "dark_history", "social_change",
    # Children of arch_design
    "historic_arch", "modern_design",
    # Children of music_nightlife
    "music_heritage", "venues_scenes",
    # Leaves (directly taggable)
    "local_legends", "food_culinary", "art_street", "literary_film",
    "religious_spiritual", "nature_green", "shopping_markets", "science_innovation",
]
```

**What NOT to touch:** No schema changes (node labels, relationship types, constraints). No changes to `EDGE_PROPERTIES` or `NODE_PROPERTIES`.

**Success check:** `len(MVP_LENSES) == 11`, `len(DAG_CHILD_LENSES) == 8`, `len(TAGGABLE_LENSES) == 16`. Every child's `parent_name` exists in `MVP_LENSES` and that parent has `is_parent: True`. No parent slug appears in `TAGGABLE_LENSES`.

---

### Task 2: Update lens seeding to set `is_parent` property

**Files to touch:** `src/seed/lenses.py`

**What to do:**
1. Update `_MERGE_LENS` Cypher to set `l.is_parent = $is_parent` on Lens nodes. Pass `is_parent` from the lens dict (default `false` if not present).
2. Update `_create_lens()` to pass the `is_parent` parameter.
3. No changes needed to `_MERGE_CHILD_WITH_PARENT` — children inherit `is_parent = false` by default.

**What NOT to touch:** Don't change the `seed_lenses()` function signature or return type.

**Success check:** After seeding, 19 Lens nodes exist. 3 have `is_parent: true`. 8 `IS_PARENT_OF` relationships exist.

---

### Task 3: Update seed data — narratives and users

**Files to touch:** `src/seed/narratives.py`, `src/seed/users.py`

**What to do:**

In `narratives.py`:
1. Remap `lens_names` on Eiffel Tower beat (line 38): `["arch_design", "hidden_history"]` → `["historic_arch", "hidden_history"]`. (`arch_design` becomes a parent; `historic_arch` is the appropriate child. `hidden_history` remains a taggable child of `history`.)
2. `dark_history` (line 59) and `literary_film` (line 49, 70) and `local_legends` (line 70) are already valid taggable slugs — no change needed.
3. Add a validation check: import `TAGGABLE_LENSES` from `definitions.py` and assert all `lens_names` in BEATS are in `TAGGABLE_LENSES` at module load time.

In `users.py`:
1. All current profile lens preferences (`hidden_history`, `food_culinary`, `literary_film`, `art_street`, `nature_green`, `local_legends`) are valid taggable slugs — no remapping needed.
2. Add same validation: import `TAGGABLE_LENSES` and assert all profile `lenses` are taggable at module load time.

**What NOT to touch:** Don't change beat content, importance tiers, or user emails.

**Success check:** Module imports succeed without assertion errors. All `lens_names` and profile `lenses` are in `TAGGABLE_LENSES`.

---

### Task 4: Add API-level validation for TAGGED_WITH edges

**Files to touch:** `src/api/routes/edges.py`

**What to do:**
1. In the `create_edge()` route (line 47), add a check: when `rel_type` is `TAGGED_WITH` and `target.label` is `Lens`, query the target Lens node's `is_parent` property. If `is_parent` is `true`, return HTTP 422 with message: `"Cannot tag a beat with parent-only lens '{name}'. Use a child or leaf lens."`.
2. This validation runs after the existing label validation but before calling `crud.create_edge()`.

**What NOT to touch:** Don't change the generic `create_edge` CRUD function. Validation belongs in the route, not the CRUD layer.

**Success check:** `POST /edges/TAGGED_WITH` with a parent lens target returns 422. With a taggable lens target, returns 201 as before.

---

### Task 5: Update frontend lens dropdown filtering

**Files to touch:** `frontend/review.html`

**What to do:**
1. In `fetchLensesAndPoiList()` (around lines 2087-2123): when populating `lensDisplayToSlug`, `lensSlugSet`, and `lensSlugToId`, skip any lens where `l.properties.is_parent === true`. This ensures parent-only lenses never appear in dropdowns or pass validation.
2. Remove the hardcoded max-12 cap (lines 2218-2224). Delete the entire `if (existingLenses.size >= 12)` block. The constraint is "1 beat per taggable lens per POI" — the taggable lens count naturally bounds it.
3. In `mapBeatForApi()` (line 2142): add a check that the resolved slug is in the set of taggable lenses (i.e., is in `lensSlugSet`, which now only contains taggable lenses after step 1). If not, flag an error.

**What NOT to touch:** Don't change `resolveLensSlug()` logic — it resolves by display label or slug. The filtering happens at population time, so resolution naturally only finds taggable lenses.

**Success check:** Dropdown shows exactly 16 lenses. Parent lenses (`history`, `arch_design`, `music_nightlife`) do not appear. No artificial cap on beats per POI.

---

### Task 6: Update test assertions — definitions and seed counts

**Files to touch:** `tests/test_definitions.py`, `tests/test_seed.py`, `tests/test_api_endpoints.py`

**What to do:**

In `test_definitions.py`:
1. Line 68: `assert len(MVP_LENSES) == 12` → `assert len(MVP_LENSES) == 11`
2. Add test: `assert len(DAG_CHILD_LENSES) == 8`
3. Add test: `assert len(TAGGABLE_LENSES) == 16`
4. Add test: every child's `parent_name` exists in MVP_LENSES and that parent has `is_parent: True`
5. Add test: no parent slug appears in `TAGGABLE_LENSES`

In `test_seed.py`:
1. Lines 25, 36: `== 13` → `== 19` (11 top-level + 8 children)

In `test_api_endpoints.py`:
1. Lines 93, 97: `== 13` → `== 19`

**What NOT to touch:** Don't change unrelated test methods.

**Success check:** All updated tests pass with `pytest tests/test_definitions.py tests/test_seed.py tests/test_api_endpoints.py`.

---

### Task 7: Fix stale test slugs in `test_workbench_ui.py`

**Files to touch:** `tests/test_workbench_ui.py`

**What to do:**
1. Replace the hardcoded `LENS_SLUGS` list (lines 133-147) with an import: `from src.schema.definitions import TAGGABLE_LENSES`. Use `TAGGABLE_LENSES` wherever `LENS_SLUGS` was used.
2. Replace the hardcoded `LENS_DISPLAY_LABELS` dict (lines 149-162) with a computed version derived from `MVP_LENSES` and `DAG_CHILD_LENSES` — or build it from the definitions. Only include taggable lenses.
3. Update any assertions that reference 12 lenses to reference 16.

**What NOT to touch:** Don't change test logic or Playwright interaction patterns.

**Success check:** No hardcoded lens slugs remain in the test file. Tests reference `TAGGABLE_LENSES` from definitions.

---

### Task 8: Update stress test fixture

**Files to touch:** `tests/fixtures/stress_test_upload.json`

**What to do:**
1. Audit all lens references in the fixture. Remap any that reference lenses becoming parents:
   - `"Architecture & Design"` → `"Historic Architecture"` or `"Modern & Contemporary Design"` (choose contextually)
   - `"Music & Nightlife History"` → `"Music Heritage"` or `"Venues & Scenes"`
   - `"Revolutionary Moments"` → `"War & Revolution"` or `"Social Change"` (choose contextually)
2. Keep intentional error-case entries (e.g., `"Underwater Archaeology"` at line 278, empty string at line 288) as-is — they test validation.
3. Lines 445-447: Remove or update the "13th beat exceeds maximum of 12 lenses" test case. Replace with a test for duplicate-lens-per-POI (same lens twice on one POI), since the artificial cap is gone.
4. Line 283: `"dark_history"` (raw slug) — this is fine, it remains a taggable child.

**What NOT to touch:** Don't change POI names, coordinates, or non-lens beat properties.

**Success check:** All fixture lens references are either valid taggable display labels, valid taggable slugs, or intentional error cases. No references to parent-only lenses as valid beat tags.

---

### Task 9: Run full test suite and verify

**Files to touch:** None (verification only)

**What to do:**
1. Run `pytest` — all tests must pass.
2. Manually verify: start the API, seed the database, confirm 19 Lens nodes exist with correct `is_parent` properties and 8 `IS_PARENT_OF` relationships.
3. Open the workbench frontend, confirm the lens dropdown shows exactly 16 taggable lenses.

**What NOT to touch:** Nothing — this is verification only.

**Success check:** All tests green. Manual verification confirms correct lens hierarchy in the database and frontend.

---

## Part B — Test Definitions

### T1: Definitions integrity (unit)
**Verifies AC #1, #2, #3**

| Test | Expected |
|------|----------|
| `len(MVP_LENSES) == 11` | 11 top-level lenses |
| `len(DAG_CHILD_LENSES) == 8` | 8 child lenses |
| `len(TAGGABLE_LENSES) == 16` | 16 taggable slugs |
| Every child's `parent_name` in `[l["name"] for l in MVP_LENSES]` | All parent refs valid |
| Every parent-ref'd lens has `is_parent: True` | Parents flagged correctly |
| No `MVP_LENSES` item with `is_parent: True` has its `name` in `TAGGABLE_LENSES` | Parents excluded from taggable |
| All children + all leaves = `TAGGABLE_LENSES` | Taggable set is complete |

### T2: Seed creates correct graph (integration)
**Verifies AC #4**

| Test | Expected |
|------|----------|
| `MATCH (l:Lens) RETURN count(l)` | 19 |
| `MATCH (:Lens)-[:IS_PARENT_OF]->(:Lens) RETURN count(*)` | 8 |
| `MATCH (l:Lens) WHERE l.is_parent = true RETURN count(l)` | 3 |
| `MATCH (l:Lens) WHERE l.is_parent IS NULL OR l.is_parent = false RETURN l.name` | 16 names matching `TAGGABLE_LENSES` |

### T3: Seed data uses only taggable lenses (unit)
**Verifies AC #5, #6**

| Test | Expected |
|------|----------|
| All `lens_names` in `narratives.BEATS` are in `TAGGABLE_LENSES` | No parent slugs in beat tags |
| All `lenses` in `users.PROFILES` are in `TAGGABLE_LENSES` | No parent slugs in preferences |

### T4: Frontend shows only taggable lenses (manual/E2E)
**Verifies AC #7**

| Test | Expected |
|------|----------|
| Lens dropdown option count | 16 |
| Dropdown does NOT contain "History", "Architecture & Design", "Music & Nightlife" | Parent labels absent |
| Dropdown DOES contain all 16 taggable display labels | All children + leaves present |

### T5: API rejects parent lens tagging (integration)
**Verifies AC #7 (API layer), red team B3/Q2**

| Test | Expected |
|------|----------|
| `POST /edges/TAGGED_WITH` with target = `history` lens node | 422 error |
| `POST /edges/TAGGED_WITH` with target = `hidden_history` lens node | 201 success |

### T6: All existing tests pass after update (regression)
**Verifies AC #8**

| Test | Expected |
|------|----------|
| `pytest` full suite | All green |

---

## Part C — Claude Code Prompt

```
## Lens Overhaul — Implementation Prompt

**Goal:** Replace the flat 12-lens config with a hybrid parent/child + leaf lens architecture (11 top-level, 8 children = 19 total; 16 taggable) so the taxonomy scales to new cities.

**Reference documents — read these first:**
- `specs/NORTHSTAR.md` — project north star
- `specs/2026-03-15-lens-overhaul/02-spec.md` — approved contract spec
- `specs/2026-03-15-lens-overhaul/03-red-team.md` — red team review with resolutions
- `specs/2026-03-15-lens-overhaul/04-plan.md` — this implementation plan (Part A tasks + Part B tests)

**Execute these tasks in order:**

### Task 1: Update `src/schema/definitions.py`
- Replace `MVP_LENSES` with 11 top-level lenses. Add `"is_parent": True` to `history`, `arch_design`, `music_nightlife`. Other lenses omit `is_parent` or set it `False`.
- Replace `DAG_CHILD_LENSES` with 8 child lenses (see 04-plan.md Task 1 for exact data).
- Add `TAGGABLE_LENSES: list[str]` — hardcoded list of 16 taggable slugs (8 children + 8 leaves). Not computed.
- Verify: `len(MVP_LENSES) == 11`, `len(DAG_CHILD_LENSES) == 8`, `len(TAGGABLE_LENSES) == 16`.

### Task 2: Update `src/seed/lenses.py`
- Update `_MERGE_LENS` Cypher to set `l.is_parent = $is_parent`.
- Pass `lens.get("is_parent", False)` as the `is_parent` parameter in `_create_lens()`.

### Task 3: Update seed data
- `src/seed/narratives.py` line 38: change `"arch_design"` → `"historic_arch"` in Eiffel Tower beat.
- Add module-level validation in both `narratives.py` and `users.py`: import `TAGGABLE_LENSES` and assert all lens references are taggable.
- Do NOT change beat content, importance tiers, or user emails.

### Task 4: Add API validation in `src/api/routes/edges.py`
- In `create_edge()`: when `rel_type == "TAGGED_WITH"` and target is a Lens, query the Lens node's `is_parent` property. If `true`, return HTTP 422.
- Add the check after label validation, before calling `crud.create_edge()`.

### Task 5: Update `frontend/review.html`
- In `fetchLensesAndPoiList()`: skip lenses where `is_parent === true` when populating `lensDisplayToSlug`, `lensSlugSet`, `lensSlugToId`.
- Remove the entire `if (existingLenses.size >= 12)` block (~lines 2218-2224). No artificial cap.
- In `mapBeatForApi()`: add validation that the resolved slug is in `lensSlugSet` (which now only has taggable lenses).

### Task 6: Update test assertions
- `tests/test_definitions.py`: `MVP_LENSES` count → 11. Add assertions for `DAG_CHILD_LENSES == 8`, `TAGGABLE_LENSES == 16`, parent/child referential integrity, parent exclusion from taggable.
- `tests/test_seed.py`: lens count → 19.
- `tests/test_api_endpoints.py`: lens total → 19.

### Task 7: Fix `tests/test_workbench_ui.py`
- Replace hardcoded `LENS_SLUGS` and `LENS_DISPLAY_LABELS` with imports from `src.schema.definitions` (`TAGGABLE_LENSES`, `MVP_LENSES`, `DAG_CHILD_LENSES`).
- Build display label mapping from definitions, not hardcoded.

### Task 8: Update `tests/fixtures/stress_test_upload.json`
- Remap lens display labels that reference parent-only lenses to appropriate children.
- Replace "max 12" test case with a duplicate-lens-per-POI test.
- Keep intentional error cases (`"Underwater Archaeology"`, empty string) as-is.

### Task 9: Run full test suite
- Run `pytest`. All tests must pass.
- Verify 19 Lens nodes, 3 with `is_parent: true`, 8 `IS_PARENT_OF` edges.

**What NOT to touch:**
- No schema changes (node labels, relationship types, constraints)
- No changes to `EDGE_PROPERTIES` or `NODE_PROPERTIES`
- No beat content changes (script_body, importance_tier)
- No user data changes (emails, display names)
- No changes to `resolveLensSlug()` logic

**Best practices checklist (must implement):**
- [ ] Input validation: API rejects `TAGGED_WITH` edges targeting parent lenses (Task 4)
- [ ] Input validation: Seed scripts validate lens references against `TAGGABLE_LENSES` (Task 3)
- [ ] Input validation: Frontend only populates taggable lenses in dropdowns (Task 5)
- [ ] Data integrity: `TAGGABLE_LENSES` is single source of truth for taggable slugs (Task 1)
- [ ] Consistency: All hardcoded counts updated across test files (Task 6, 7)
- [ ] Consistency: Fixture lens references match new hierarchy (Task 8)

Before starting, confirm you understand the full scope and flag any conflicts with the existing codebase or assumptions you are making.
```

---

## Part D — Best Practices Implementation Checklist

| # | Practice | Task(s) | How to Verify |
|---|----------|---------|---------------|
| 1 | **API rejects TAGGED_WITH to parent lenses** | Task 4 | `POST /edges/TAGGED_WITH` with `history` lens → 422. With `hidden_history` → 201. |
| 2 | **Seed scripts validate lens refs at import time** | Task 3 | Import `narratives` and `users` modules — no assertion errors. Temporarily add a parent slug → assertion fires. |
| 3 | **Frontend filters parent lenses from dropdowns** | Task 5 | Open workbench → lens dropdown shows 16 items, no parents. |
| 4 | **No artificial beat-per-POI cap** | Task 5 | Frontend allows >12 beats per POI (bounded only by taggable lens count). |
| 5 | **`TAGGABLE_LENSES` is canonical source** | Task 1, 7 | Tests import from `definitions.py`, no hardcoded slug lists elsewhere. |
| 6 | **All hardcoded counts updated** | Task 6, 7, 8 | `pytest` passes — no stale 12/13 assertions. |
| 7 | **`is_parent` property set on Lens nodes** | Task 2 | Cypher query: `MATCH (l:Lens) WHERE l.is_parent = true RETURN l.name` → 3 results. |

---

## North Star Final Check

The plan aligns with the north star:
- **Phase 4 gate** ("City two live in <6 weeks pipeline work") — the universal taxonomy eliminates per-city lens customization.
- **Architectural commitment** (line 37) already references the hybrid architecture. This plan implements it.
- **Explicit boundary** — no embedding similarity, no city-specific config, no automatic promotion. All respected.
- **No schema changes** — same node labels, same relationship types. Only data and config change.
