# `GET /api/v1/profile` — public profile read endpoint

> **Status:** Design 1 · 2026-08-10
> **Adopts:** the parked spec `specs/2026-08-09-public-read-endpoints/` (Product Owner + red-team + AC-6..AC-12). This doc carries that settled contract forward for the standalone build.
> **Fixes:** the profile-read half of `project_mobile_prod_api_gap` — `ProfileService` currently reads `/edges/HAS_PROFILE`+`/nodes/Profile`+`/edges/PREFERS_LENS` (workbench-gated, 404 in prod), so re-editing lenses is broken. `/lenses` shipped 2026-08-10 (PR #18); this is its sibling.

## 1. Scope

**Build + deploy ONE backend endpoint: `GET /api/v1/profile` (read-only, bearer-authed).** Added to the existing `src/api/routes/product.py` router, already mounted OUTSIDE `_workbench_api_enabled()` (so it serves on the public prod deployment).

**Out of scope (deliberate):**
- Any write (PUT/POST/PATCH/DELETE profile) — a later profile-*write* slice.
- The Flutter `ProfileService` repoint — a separate follow-on client slice (same split as `/lenses`).
- Seed / migration / backfill; pagination; caching; city-scoping.

## 2. Contract

**Request:** `GET /api/v1/profile`, `Authorization: Bearer <token>`.

**200 — the caller's profile:**
```json
{
  "profile_id": "9c1f…",
  "display_name": "adam",
  "selected_lens_ids": ["714b…", "2d5e…"],
  "theme_preference": null
}
```
(`profile_id` included per decision 2026-08-10 — the client's future write path needs it; cheap + forward-compatible.)

**Behavior / error semantics:**
- **401** — no header, or malformed/expired token. `get_current_user` (`src/api/auth/dependencies.py`) raises before the body runs, so **no profile data leaks** (AC-10).
- **404** — authenticated user has zero `HAS_PROFILE` profiles. A clear `detail`, **not** an empty `{}`, **not** a 500 (AC-8; honest-data rule — never fabricate an empty profile).
- **Multi-profile tiebreak** — if a user has >1 `HAS_PROFILE`, return the one with the latest `created_at`, and *its* lens set, deterministically; the older must not appear (AC-9).
- `selected_lens_ids` — the returned profile's `PREFERS_LENS → Lens` id set; empty list (not dropped) when the profile has none (AC-6).
- `theme_preference` — verbatim when the property is set, JSON `null` when absent (onboarding never writes it). Read-only pass-through; this endpoint never writes it (AC-7).

## 3. Data flow (grounded in `auth/routes.py:441` — the profile writer)

Onboarding creates: `(:User)-[:HAS_PROFILE]->(:Profile {id: randomUUID(), created_at: datetime(), display_name})`, and `(:Profile)-[:PREFERS_LENS]->(:Lens {is_parent:false})`. `theme_preference` is never set at creation.

One Cypher, executed with the bearer's user id (`get_current_user()["id"]`):
```cypher
MATCH (u:User {id: $uid})-[:HAS_PROFILE]->(p:Profile)
WITH p ORDER BY p.created_at DESC LIMIT 1
OPTIONAL MATCH (p)-[:PREFERS_LENS]->(l:Lens)
RETURN p.id AS profile_id, p.display_name AS display_name,
       p.theme_preference AS theme_preference,
       collect(l.id) AS selected_lens_ids
```
- No rows → user has no profile → handler raises `HTTPException(404, detail=...)`.
- `ORDER BY p.created_at DESC LIMIT 1` → the tiebreak.
- `OPTIONAL MATCH` + `collect` → a lens-less profile yields `[]`, not a dropped row.
- `p.theme_preference` → `null` in the driver when absent → serialized as JSON `null`.

## 4. Components (one file touched, plus tests)

- **`src/api/routes/product.py`** — add `get_profile(current_user = Depends(get_current_user), session = Depends(get_session))`. Re-adds the `get_current_user` import removed when `/lenses` was split out. ~20 lines. No new router, no new mount (the router is already mounted public).
- **`tests/test_product_api.py`** — add `TestProfileEndpoint` covering AC-6/7/8/9/10 (see §5). Reuses the existing `seeded_client`/`clean_driver` fixtures + `seed_lenses`; seeds a User + Profile + PREFERS_LENS via a small helper (or the existing `seed.users`).

## 5. Testing (acceptance criteria → tests)

- **AC-10** — no bearer, and malformed/expired bearer → 401, body contains no `display_name`/`selected_lens_ids`. (This is exactly the test that existed on the removed stub; restore it.)
- **AC-8** — valid bearer, user with zero `HAS_PROFILE` → 404 with a detail, and the body is not a fabricated empty profile.
- **AC-6** — user with one Profile + ≥3 `PREFERS_LENS` child edges → 200 with `display_name` and `selected_lens_ids` == exactly the profile's child-lens id set. Include `profile_id` in the assertions.
- **AC-7** — `theme_preference` verbatim when set; JSON `null` (key present) when absent.
- **AC-9** — user with two Profiles of distinct `created_at` and different lens sets → returns the later-created profile and ITS lens set; the older's id set must not appear.

All hermetic against the local test Neo4j (7688) via `make test-file FILE=tests/test_product_api.py::TestProfileEndpoint`.

## 6. Deploy (Tier-3, same flow as `/lenses`)

Clean worktree off `main` (already created: `build-profile-endpoint`) → TDD build → `make lint` + targeted tests green → judge consult → PR + merge → Render auto-deploys → verify prod (`curl -H "Authorization: Bearer <token>" https://ondoway.com/api/v1/profile` → 200 for a real user; 401 without a token). Reversible via `git revert -m 1 <merge-sha>`.

## 7. What this does NOT do
- No write endpoints, no client repoint, no theme-writing. `ProfileService` stays on the old (broken) endpoints until the follow-on client slice repoints its read path onto this endpoint.
