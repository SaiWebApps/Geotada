# Red Team Review: Lens Overhaul — Universal Lens Hierarchy

**Date:** 2026-03-16
**Spec Ref:** specs/2026-03-15-lens-overhaul/02-spec.md
**North Star Ref:** specs/NORTHSTAR.md
**Status:** APPROVED

---

## 1. Blockers

### B1 — Frontend hardcodes max 12 lenses per POI
`frontend/review.html:2218` checks `if (existingLenses.size >= 12)` and shows error `"max 12"`. This is an artificial cap.

**Resolved:** Remove the hardcoded cap entirely. The constraint is "1 beat per taggable lens per POI" — but there is no limit on total beats per POI. The taggable lens count naturally bounds it, and that count grows over time as lenses are added. No cap should be enforced in the frontend.

### B2 — Frontend does not filter parent lenses from dropdowns
`frontend/review.html:2087-2123` — `fetchLensesAndPoiList()` fetches all Lens nodes and populates `lensDisplayToSlug` without checking `is_parent`. After the overhaul, 3 parent-only lenses (`history`, `arch_design`, `music_nightlife`) will appear in beat-tagging dropdowns, enabling invalid tagging. AC #7 will fail.

**Resolved:** Filter on `is_parent !== true` when populating dropdown options and the `lensDisplayToSlug` / `lensSlugSet` maps used for validation.

### B3 — No validation of taggable-only tagging
The spec's core constraint — "A beat may only be `TAGGED_WITH` a taggable lens. Never a parent." — is not enforced anywhere in the current codebase. The only actual seed data violation is `arch_design` (becomes a parent) in `narratives.py:38`. `hidden_history` and `dark_history` remain taggable as children under `history`, so those references are fine. But nothing prevents future invalid tagging.

**Resolved:** Add validation in three places: (1) `narratives.py` seed script cross-checks `lens_names` against `TAGGABLE_LENSES`, (2) frontend `mapBeatForApi()` validates before submission, (3) API upload route validates `is_parent` before creating `TAGGED_WITH` edges. Fix `arch_design` → child slug in seed data.

---

## 2. Risks

### R1 — Stale test slugs in test_workbench_ui.py (Likelihood: HIGH)
`tests/test_workbench_ui.py:133-147` defines `LENS_SLUGS` with incorrect slugs (`architecture_design` instead of `arch_design`, `local_legends_folklore` instead of `local_legends`). These don't match `definitions.py` even before the overhaul.

**Mitigation:** Fix stale slugs as part of this overhaul. Import from `TAGGABLE_LENSES` rather than maintaining a separate hardcoded list.

### R2 — Fixture `stress_test_upload.json` uses mixed slug/display-label format (Likelihood: MEDIUM)
Most entries use display labels, but line 283 uses a raw slug. Some entries reference lenses that will become parent-only. Line 278 references a non-existent lens (`"Underwater Archaeology"`) — likely an intentional error-case fixture.

**Mitigation:** Audit and remap all fixture lens references. Preserve intentional error-case entries but update expected behavior.

### R3 — Seed data in narratives.py references lenses that become parents (Likelihood: CERTAIN)
`narratives.py` tags beats with `arch_design` (line 38). Under the new hierarchy, `arch_design` becomes a parent, violating the tagging rule. `hidden_history` and `dark_history` become children under `history`, so those are fine. But `arch_design` beats must be remapped to a child.

**Mitigation:** Include explicit remapping table in the implementation plan.

### R4 — `resolveLensSlug()` doesn't know about parent vs. taggable (Likelihood: MEDIUM)
`resolveLensSlug()` resolves any lens by display label or slug. After the overhaul, it will resolve `"History"` → `"history"` (a parent slug), which the spec forbids for beat tagging.

**Mitigation:** Add a separate validation step after resolution, or make `resolveLensSlug()` reject parent slugs.

---

## 3. Open Questions

### Q1 — Should `TAGGABLE_LENSES` be computed or hardcoded?
**Resolved: Hardcoded.** `TAGGABLE_LENSES` is an explicit, manually maintained list in `definitions.py`. Not computed from `is_parent` filtering. Grows as lenses are added over time. This is simpler and avoids the risk of a missing `is_parent` flag silently making a parent taggable.

### Q2 — Should the API validate `is_parent` on beat creation?
**Resolved: Yes.** API upload route must validate that the lens is taggable before creating `TAGGED_WITH` edges. This closes the gap where direct API calls bypass the frontend.

---

## 4. Codebase Conflicts

| Conflict | Location | Detail |
|----------|----------|--------|
| Hardcoded lens count `== 12` | `tests/test_definitions.py:68` | `assert len(MVP_LENSES) == 12` → must become 11 |
| Hardcoded lens count `== 13` | `tests/test_seed.py:25,36` | `assert result["lenses"] == 13` → must become 19 |
| Hardcoded lens count `== 13` | `tests/test_api_endpoints.py:93,97` | API pagination total → must become 19 |
| Hardcoded max `>= 12` | `frontend/review.html:2218` | Frontend cap → remove entirely (no artificial limit) |
| Stale slug names | `tests/test_workbench_ui.py:133-162` | `LENS_SLUGS` and `LENS_DISPLAY_LABELS` don't match `definitions.py` |
| Beat tagging `arch_design` | `src/seed/narratives.py:38` | `arch_design` becomes a parent; beat must remap to a child |
| Fixture max-12 comment | `tests/fixtures/stress_test_upload.json:445-447` | "13th beat exceeds maximum of 12 lenses" → remove cap-based test; replace with duplicate-lens-per-POI test |

---

## 5. North Star Check

**Alignment is good overall.** The spec directly serves the Phase 4 gate ("City two live in <6 weeks pipeline work") by making the lens taxonomy city-agnostic.

**One update needed:** The north star (line 37) already references the new architecture, but line 17 still says "16 taggable lenses covered." The scope acknowledges this (Dependencies section). The north star update should happen as part of this slice's close-out — not deferred.

**No short-sighted decisions detected.** The hybrid parent/child architecture is forward-compatible: adding children or parents requires no migration, and the single risky operation (promoting a leaf to parent) is well-documented with a clear migration path.

---

## 6. Best Practices Audit

### A) Security & Privacy Practices (SECURITY_PRIVACY_PRACTICES.md — 16 sections)

| # | Section | Verdict | Notes |
|---|---------|---------|-------|
| 1 | Data Classification & Minimization | **N/A** | No new data collection. Lens metadata is system config. |
| 2 | Consent & Transparency | **N/A** | No user-facing data collection changes. |
| 3 | Authentication & Authorization | **N/A** | No auth changes. Workbench is local/dev-only. |
| 4 | Secure Session Management | **N/A** | No session changes. |
| 5 | Secrets & Credentials | **Pass** | No secrets involved in lens config. |
| 6 | Encryption | **N/A** | No new data flows. |
| 7 | Logging & Monitoring | **N/A** | No new logging surfaces. |
| 8 | Data Retention & Deletion | **N/A** | Lens nodes are system config. Wipe-and-reseed is appropriate pre-launch. |
| 9 | Third-Party Risk | **N/A** | No new third-party dependencies. |
| 10 | Secure Development Lifecycle | **Pass** | Spec-driven workflow with red team review. |
| 11 | Input Validation & Output Encoding | **Fail → Resolved** | B3 — validation to be added in seed scripts, frontend, and API per resolution. |
| 12 | Infrastructure & Network Security | **N/A** | No infra changes. |
| 13 | Privacy by Design | **N/A** | No user data involved. |
| 14 | Incident Response | **N/A** | No operational changes. |
| 15 | Testing & Verification | **Pass** | Spec requires all tests updated. Stale slugs (R1) must be fixed. |
| 16 | Compliance & Documentation | **Pass** | North star doc update is scoped. |

### B) Best Practices Library — Relevant Domains

#### Data Integrity (primary)

| Item | Verdict | Notes |
|------|---------|-------|
| Tagging constraint enforced at boundary | **Fail** | B3 — no enforcement of parent-only exclusion |
| Slug uniqueness validated | **Pass** | Unique constraint on Lens.name in schema |
| Seed data consistent with definitions | **Fail** | R3 — `narratives.py` tags `arch_design` which becomes a parent |
| Config is single source of truth | **Pass** | `definitions.py` canonical; `TAGGABLE_LENSES` makes it importable |
| Child→parent referential integrity | **Pass** | Tested in `test_definitions.py` |

#### Consistency (secondary)

| Item | Verdict | Notes |
|------|---------|-------|
| All hardcoded counts updated | **Fail** | Multiple files with hardcoded 12/13 |
| Frontend and backend use same slug set | **Fail** | R1 — `test_workbench_ui.py` has wrong slugs |
| Fixtures match current definitions | **Fail** | R2 — fixture references lenses that become parents |
| Display labels ↔ slugs mapping complete | **Pass** | `resolveLensSlug()` handles both formats |

#### UX (minor)

| Item | Verdict | Notes |
|------|---------|-------|
| Only valid options shown in UI | **Fail** | B2 — parent lenses will appear in dropdowns |
| Error messages accurate | **Fail** | B1 — "max 12" message must update to 16 |
| No dead-end states | **Pass** | Lens resolution fallback returns null with clear error |

---

## Summary of Resolutions

| ID | Type | Resolution |
|----|------|-----------|
| B1 | Blocker | **Remove** frontend max-lens cap entirely. No artificial limit on beats per POI. |
| B2 | Blocker | Add `is_parent` filtering to frontend lens dropdown population. |
| B3 | Blocker | Add taggable-lens validation in seed scripts, frontend, and API. Fix `arch_design` → child slug in seed data. |
| Q1 | Open Question | `TAGGABLE_LENSES` is hardcoded, not computed. Manually maintained. |
| Q2 | Open Question | Yes — API-level validation required for Phase 1. |
