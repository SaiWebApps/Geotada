# Contract Spec: Lens Overhaul — Universal Lens Hierarchy

**Date:** 2026-03-16
**Scope Ref:** specs/2026-03-15-lens-overhaul/01-scope.md
**North Star Ref:** specs/NORTHSTAR.md
**Flavor:** B — Contract Spec
**Status:** APPROVED

---

## 1. Purpose

Replace the flat 12-lens config with a hybrid parent/child + leaf lens architecture (11 top-level, 8 children, 8 leaves = 16 taggable lenses) so the taxonomy scales to new cities without per-city customization, unblocking Phase 4. Clean up the database and re-seed with the new hierarchy.

## 2. Inputs

- **`MVP_LENSES`** — updated list of 11 top-level lens dicts (`name`, `display_label`, `is_parent: bool`)
- **`DAG_CHILD_LENSES`** — updated list of 8 child lens dicts (`name`, `display_label`, `parent_name`). Old `arch_gothic_01` child removed.
- **Seed data** — `narratives.py` beat `lens_names` remapped to new child/leaf slugs; `users.py` profile `lenses` remapped to taggable slugs
- **Frontend** — `fetchLensesAndPoiList()` fetches all Lens nodes; dropdowns filter to taggable lenses using `is_parent` property; `resolveLensSlug()` resolves new slugs

## 3. Outputs

- **Neo4j Lens nodes:** 19 total (11 top-level + 8 children). 3 parents connected to children via `IS_PARENT_OF`.
- **Taggable lens set:** 16 lenses (8 children + 8 leaves). These are the only valid targets for `TAGGED_WITH` on beats and `PREFERS_LENS` on profiles.
- **`TAGGABLE_LENSES` export** — new computed list in `definitions.py` that downstream code can import to know which lenses accept beat tagging.
- **`is_parent` property on Lens nodes** — `true` for parent-only lenses (history, arch_design, music_nightlife), absent/false for taggable lenses. Frontend filters dropdowns using this property.
- **Frontend lens dropdowns** — show only taggable lenses (children + leaves), not parent-only lenses.
- **Clean database** — old lens data wiped, re-seeded with new hierarchy.

## 4. Constraints

- **Tagging rule:** A beat may only be `TAGGED_WITH` a taggable lens (child or leaf). Never a parent. Enforced by config (`TAGGABLE_LENSES`) and validated in seed script and frontend.
- **1 beat per taggable lens per POI.** No hard cap on total beats per POI — the lens count naturally bounds it.
- **`is_parent` is the canonical signal** for whether a lens accepts beat tagging. The property lives on the Lens node in Neo4j and in the `MVP_LENSES` config. If a leaf is later promoted to a parent, the migration must flip this property.
- **Slug stability:** All new slugs are final. Changing a slug after data is seeded requires a migration.
- **No DB schema change.** Same node labels, same relationship types. Only lens data and seed scripts change.
- **Backward compatibility not required.** Pre-launch with minimal data; wipe and re-seed is acceptable.
- **Old `arch_gothic_01` child removed.** Replaced by `historic_arch` and `modern_design` under `arch_design`.

## 5. Acceptance Criteria

1. **Works when** `definitions.py` exports exactly 11 items in `MVP_LENSES`, 8 items in `DAG_CHILD_LENSES`, and 16 items in `TAGGABLE_LENSES`.
2. **Works when** every child lens in `DAG_CHILD_LENSES` references a `parent_name` that exists in `MVP_LENSES` and that parent has `is_parent: True`.
3. **Works when** `TAGGABLE_LENSES` equals all leaves (`is_parent` is False) plus all children — and no parent-only lens appears in it.
4. **Works when** `seed_lenses()` creates 19 Lens nodes and 8 `IS_PARENT_OF` relationships, with `is_parent` property set correctly on each node.
5. **Works when** all `lens_names` in `narratives.py` BEATS are valid taggable slugs from the new hierarchy.
6. **Works when** all `lenses` in `users.py` PROFILES are valid taggable slugs from the new hierarchy.
7. **Works when** the frontend lens dropdown for beat tagging shows exactly the 16 taggable lenses — no parent-only lenses appear.
8. **Works when** all existing tests pass after updating lens slug references and expected counts.

## 6. Downstream Dependencies

- **Frontend workbench** — dropdowns must filter to taggable lenses only using `is_parent` property. `resolveLensSlug()` must resolve both new child slugs and existing leaf slugs.
- **Content pipeline (Data Miner V1)** — extraction prompts reference lens names. When the miner is next updated, it must use the 16 taggable slugs.
- **Narrative engine (future)** — traversals that walk `TAGGED_WITH` edges are unaffected. Traversals that group by parent lens (e.g., "all history beats") need to walk `IS_PARENT_OF` → children → `TAGGED_WITH`.
- **North star doc** — updated to reflect hybrid lens architecture, new taggable count (16), and max beats per POI (16).

## 7. Open Questions

*Resolved — none remaining.*

- ~~Should `is_parent` be a property or inferred from edges?~~ **Resolved: `is_parent` property on the Lens node.** Simpler for frontend filtering. The promotion-to-parent migration (the one operation that changes taggability) must flip this property.
- ~~Should old `arch_gothic_01` be removed or remapped?~~ **Resolved: Remove it.** Clean database re-seed with new hierarchy. No migration needed.
