# 03 — Red Team: Onboarding Lens Selection

**Date:** 2026-05-01
**Reviewers:** 3 independent agents (UI/UX, Backend, Scope)

---

## P0 — Ship-blockers (must fix before building)

### 1. API endpoints in the spec are WRONG

The spec says `POST /api/v1/edges` with rel_type in the body. The actual API is `POST /api/v1/edges/{rel_type}` with rel_type in the URL path. Same for nodes: spec says `GET /nodes?label=Lens`, actual is `GET /nodes/Lens`. If the implementer follows the spec literally, every call 404s.

**Fix:** Correct all endpoint references in the spec.

### 2. No user ID available in AuthService

The spec needs `user_id` to create `HAS_PROFILE` edges. But `AuthService._fetchMe()` only extracts `email` — the `id` field from the `/me` response is discarded.

**Fix:** Add `_userId` field to AuthService, extracted from `/me` response.

### 3. No way to query a user's profile or lens preferences

`GET /edges/{rel_type}` has no `source_id` filter. The frontend cannot answer "does this user have a profile?" or "what are this profile's lens preferences?" without fetching ALL edges of that type across ALL users.

**Fix:** Either add `source_id`/`target_id` query params to the edge list endpoint, or (better) create a dedicated `POST /api/v1/onboarding/complete` endpoint.

### 4. No parent info on Lens nodes for grouping

The spec needs lenses grouped by parent category. But Lens nodes don't carry `parent_id` — the parent-child relationship is stored as `IS_PARENT_OF` edges. Grouping requires a second API call.

**Fix:** Either add a `parent_slug` property to child lens nodes, or create a `GET /api/v1/lenses` endpoint that returns the hierarchy.

### 5. PREFERS_LENS and HAS_PROFILE use CREATE, not MERGE

If the user retries after a partial failure, duplicate edges are created. The backend doesn't prevent `Profile→Lens` duplicates.

**Fix:** Add both to the MERGE list in `crud/edges.py`.

---

## P1 — Will break if not addressed in design

### 6. Half-onboarded zombie state

If profile is created but PREFERS_LENS edges fail (app crash, network drop), the user has a profile with zero lenses. The first-time check ("has profile?") says return user. The return-user check ("has lenses?") says... nothing. User is stuck — skips onboarding, lands on Explore with no preferences.

**Fix:** Detection should be "has profile with ≥1 PREFERS_LENS edge", not just "has profile". Better: use the single onboarding endpoint so it's atomic.

### 7. GoRouter redirect vs async profile check race

The current redirect fires synchronously on auth state change. `ProfileService.fetchProfile()` is async. The redirect will send users to the wrong destination before the profile check completes.

**Fix:** Add `isOnboardingComplete` to the redirect guard, sourced from ProfileService. Block navigation until profile check completes (show loading).

### 8. CallbackPage and LoginPage navigate to dead `/home`

Both files hard-code `context.go('/home')`. After this feature, `/home` is removed. Post-login navigation will crash or 404.

**Fix:** Update both to use profile-aware routing logic.

### 9. No token refresh mechanism

`AuthService` stores a refresh token but never uses it. If the user sits on the lens selection screen for >60 minutes, the access token expires and all API calls 401 silently.

**Fix:** Not blocking for this scope, but document as known tech debt.

---

## P2 — Design challenges that need spec clarity

### 10. Auto-save add-then-remove race condition

User taps a lens (POST fires), then immediately un-taps it (needs DELETE with edge ID from the POST that hasn't returned yet). No edge ID → can't delete. The spec gives no guidance on debouncing or queuing.

### 11. Tab state not preserved without StatefulShellRoute

GoRouter's `ShellRoute` rebuilds child widgets on tab switch. Scroll position resets. Need `StatefulShellRoute.indexedStack` from GoRouter 14.x.

### 12. Lens count mismatch: spec says 18, palette table has 21, backend has 21

`definitions.py` defines 21 universal child lenses. The spec header says "18 taggable." The color palette table lists 21 entries. Inconsistency will confuse the implementer.

---

## Scope Challenges — Features to reconsider

### A. Welcome animation: CUT

A choreographed 4-stage timed animation with crossfade is vanity for Phase 1. It creates a dedicated route, an AnimationController, staggered delays, and edge cases (what if lens fetch fails during the animation?). **Replace with:** "Welcome, Sairam" as a header on the lens selection page itself. One screen instead of two.

### B. Auto-save in edit mode: CUT

Auto-save requires per-tap API calls, optimistic UI, rollback, debouncing, edge ID tracking, and "last lens" enforcement that races with in-flight deletions. An explicit "Save" button batches changes into one call, identical UX to onboarding mode. Nobody edits lenses under time pressure.

### C. Bottom nav with 2 empty tabs: CUT

Explore is a placeholder. Profile is a logout button. Building a 3-tab `StatefulShellRoute` to house one real feature and two empty rooms makes the app feel unfinished. **Replace with:** Land on a home page with "Edit Lenses" accessible from app bar. Add bottom nav when Explore has real content (Phase 2).

### D. Dark theme globally: SCOPE DOWN

Force-switching to dark theme touches login, callback, and every existing page. Risk of visual regressions. The only page that benefits from dark background is the lens grid (tile contrast). **Replace with:** Dark scaffold on the lens selection page only. Leave login/callback unchanged.

### E. Client-side multi-call orchestration: REPLACE

2+N REST calls with no transaction support = partial failure states. The backend already has the pattern (`crud/trips.py` creates Trip + edges in one Cypher transaction). **Replace with:** Single `POST /api/v1/onboarding/complete` endpoint. One call, one transaction, one success/failure. ~30 lines of backend code eliminates an entire failure category.

---

## Recommended Revised Scope

| Keep | Cut / Defer |
|------|-------------|
| Lens selection grid (colored tiles, 2-column) | Welcome animation → header text on lens page |
| Onboarding mode with "Continue" (min 3) | Auto-save → explicit "Save" in edit mode too |
| Profile + PREFERS_LENS creation (atomic backend) | Bottom nav → defer to Phase 2 |
| First-time vs return detection | Global dark theme → dark on lens page only |
| Edit lenses from home page link | Dedicated Lenses/Profile tabs |
| Single `POST /onboarding/complete` endpoint | Client-side multi-call orchestration |

**Result:** ~4 new Flutter files + 2 modified + 1 new backend endpoint. Down from 7+3+0. Same user-facing value: user picks lenses, app remembers them, tour generation uses them.
