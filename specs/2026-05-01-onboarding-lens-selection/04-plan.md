# 04 — Implementation Plan: Onboarding Lens Selection

**Date:** 2026-05-01
**Status:** Ready for approval
**Decisions:** Keep bottom nav + dark theme. Cut welcome animation, auto-save, multi-call orchestration.

---

## Compliance Checklist (RUN BEFORE EVERY STEP)

```
## Pre-step Checklist
- [ ] Read the Makefile target for what I'm about to do
- [ ] Read the actual files I'm about to modify (full file, not just the part I think matters)
- [ ] State what I'm changing and why (no silent edits)
- [ ] After editing: grep for all callers / usages of anything I changed
- [ ] Run make test after EVERY step (not at the end)
- [ ] Run make flutter-test after EVERY Flutter change
- [ ] Spawn checker agent before reporting step complete
- [ ] 0 failures, 0 skips, or the step is not done
```

---

## Verified API Reference (from actual code, not guesses)

| Action | Method | Actual URL | Body | Source |
|--------|--------|-----------|------|--------|
| List lenses | GET | `/api/v1/nodes/Lens?limit=200` | — | `routes/nodes.py:22` |
| List IS_PARENT_OF edges | GET | `/api/v1/edges/IS_PARENT_OF?limit=200` | — | `routes/edges.py:22` |
| Create profile | POST | `/api/v1/nodes/Profile` | `{"display_name": "Sairam"}` | `routes/nodes.py:54` |
| Create edge | POST | `/api/v1/edges/{rel_type}` | `{"source": {"label": "X", "id": "..."}, "target": {"label": "Y", "id": "..."}}` | `routes/edges.py:47` |
| Delete edge | DELETE | `/api/v1/edges/{rel_type}/{edge_id}` | — | `routes/edges.py:115` |
| Get current user | GET | `/api/v1/auth/me` | — | Returns: `{id, email, created_at, last_logon}` per `schemas.py:30-34` |

**Known gaps to fix:**
- `GET /edges/{rel_type}` has NO source_id filter → need new backend endpoint
- `PREFERS_LENS` and `HAS_PROFILE` use CREATE not MERGE → need to add to merge list
- `AuthService` discards user `id` from `/me` → need to store it
- 21 child lenses (not 18) — `definitions.py:137-167`

---

## Steps (7 total, each ends with a demo)

### Step 1: Backend — `POST /api/v1/onboarding/complete` endpoint

**What:** Single atomic endpoint that creates Profile + HAS_PROFILE + PREFERS_LENS edges in one Cypher transaction. Also add `source_id` filter to `GET /edges/{rel_type}` for edit mode.

**Files to modify:**
- `src/api/auth/routes.py` — add onboarding endpoint (auth-protected, derives user_id from token)
- `src/api/crud/edges.py` — add PREFERS_LENS + HAS_PROFILE to MERGE list (line 108)
- `src/api/routes/edges.py` — add optional `source_id` query param to list_edges
- `src/api/crud/edges.py` — add WHERE clause for source_id filter in list_edges query

**New test file:** `tests/test_onboarding_api.py`

**Demo:** `curl` the endpoint with test data, verify Profile + edges created in Neo4j.

**Compliance gate:** `make test-local` passes (710+ tests, 0 fail, 0 skip).

---

### Step 2: Flutter — AuthService stores user ID

**What:** Extract and store `id` from `/me` response alongside email.

**Files to modify:**
- `mobile/lib/services/auth_service.dart` — add `_userId` field, extract from `/me` JSON, expose via getter

**Demo:** Print `authService.userId` after login in debug console.

**Compliance gate:** `make flutter-test` passes (18 tests, 0 fail).

---

### Step 3: Flutter — Lens model + LensService

**What:** Fetch all lenses + IS_PARENT_OF edges, build grouped hierarchy.

**New files:**
- `mobile/lib/models/lens.dart` — Lens data class (id, name, displayLabel, isParent, parentSlug)
- `mobile/lib/services/lens_service.dart` — fetch lenses, fetch parent edges, build `Map<String, List<Lens>>` grouped by parent display name

**Demo:** Log the grouped lens hierarchy after app start.

**Compliance gate:** `make flutter-test` passes (18+ tests, 0 fail). Add unit test for LensService grouping logic.

---

### Step 4: Flutter — ProfileService + onboarding detection

**What:** Service that calls `POST /onboarding/complete`, fetches existing profile via `GET /edges/HAS_PROFILE?source_id={user_id}`, determines first-time vs return user.

**New files:**
- `mobile/lib/services/profile_service.dart` — `isFirstTime`, `currentProfileId`, `selectedLensIds`, `completeOnboarding(lensIds)`, `fetchProfile()`

**Files to modify:**
- `mobile/lib/main.dart` — register ProfileService + LensService providers
- `mobile/lib/services/auth_service.dart` — call `profileService.fetchProfile()` after auth

**Demo:** Login → console shows `isFirstTime: true`. Complete onboarding via API → re-login → console shows `isFirstTime: false` with correct lens IDs.

**Compliance gate:** `make flutter-test` passes. Add tests for ProfileService.

---

### Step 5: Flutter — Lens selection page

**What:** 2-column colored tile grid, 21 lenses grouped by 8 parent categories. "Welcome, {Name}" header. "Pick at least 3" subtitle. Sticky footer with count + Continue button.

**New files:**
- `mobile/lib/pages/lens_selection_page.dart` — grid with onboarding mode (has Continue button + min 3 gate) and edit mode (has Save button)
- `mobile/lib/widgets/lens_tile.dart` — individual colored tile with selected/unselected state, checkmark badge, scale animation

**Color mapping:** Hardcode by lens `name` slug (stable across re-seeds, defined in `definitions.py`). NOT by display name.

**Demo:** Navigate to lens selection page, see all 21 tiles in 8 groups, tap tiles, see checkmarks, see count update, Continue enables at 3+.

**Compliance gate:** `make flutter-test` passes. Add widget test for lens selection page (renders all tiles, enforces minimum, Continue works).

---

### Step 6: Flutter — Dark theme + bottom nav + routing

**What:** Global dark theme (#121212 background, #3D5AFE primary). Bottom nav with 3 tabs (Explore, Lenses, Profile). Updated GoRouter with StatefulShellRoute.

**New files:**
- `mobile/lib/widgets/app_shell.dart` — StatefulShellRoute scaffold with NavigationBar
- `mobile/lib/pages/explore_page.dart` — placeholder ("Your first tour starts here")
- `mobile/lib/pages/profile_page.dart` — email display + logout + "Edit Lenses" (or Lenses is its own tab)

**Files to modify:**
- `mobile/lib/main.dart` — set `themeMode: ThemeMode.dark`, custom dark `ThemeData` with #121212 background + #3D5AFE primary
- `mobile/lib/router.dart` — REWRITE: add `/welcome` (lens selection in onboarding mode), `StatefulShellRoute` for `/explore`, `/lenses`, `/profile`. Update redirect logic to handle `isFirstTime` from ProfileService. Update all `context.go('/home')` references.
- `mobile/lib/pages/callback_page.dart` — change `context.go('/home')` to profile-aware routing
- `mobile/lib/pages/login_page.dart` — change `context.go('/home')` to profile-aware routing

**Delete:** `mobile/lib/pages/home_page.dart` (replaced by explore_page.dart)

**Critical routing logic:**
```
After auth succeeds:
  ProfileService.fetchProfile() completes →
    isFirstTime? → /welcome (lens selection in onboarding mode)
    not firstTime? → /explore (inside shell with bottom nav)
```

**Redirect guard must allow:** `/login`, `/auth`, `/auth/callback`, `/welcome` — without redirecting to shell prematurely.

**Demo:** Full flow — login → lens selection → Continue → lands on Explore tab with bottom nav. Switch tabs. Logout. Login again → skip onboarding, land on Explore directly.

**Compliance gate:** `make flutter-test` passes. All existing tests updated for route changes. New tests for shell navigation.

---

### Step 7: Polish + full verification

**What:** Verify the complete flow end-to-end. Fix any visual issues. Ensure dark theme looks correct on all screens.

**Demo:** Screen-by-screen walkthrough: Login → Lens selection → Explore → Lenses tab (edit mode, pre-checked) → Save → Profile tab → Logout → Re-login (skips onboarding).

**Compliance gate:**
- `make test` passes (all Python local + cloud)
- `make flutter-test` passes (all Flutter tests)
- Manual flow on iOS simulator verified
- No dead routes, no orphaned files, no broken imports

---

## Risk Mitigations

| Risk | Mitigation |
|------|-----------|
| GoRouter redirect race with async profile check | Block navigation with loading screen until ProfileService.fetchProfile() completes |
| Half-onboarded state (profile exists, 0 lenses) | Detection: "has profile with ≥1 PREFERS_LENS edge". Backend onboarding endpoint is atomic. |
| `context.go('/home')` references in callback/login | Step 6 grep for ALL `/home` references before deleting home_page.dart |
| StatefulShellRoute tab state loss | Use `StatefulShellRoute.indexedStack` (GoRouter 14.x), not plain ShellRoute |
| Color mapping breaks if lens renamed | Map by `name` slug (e.g., "hidden_history"), not `display_label` |
| Duplicate PREFERS_LENS edges on retry | Backend uses MERGE after Step 1 fix |
| Token expiry during lens selection | Document as known tech debt — not blocking for this scope |
