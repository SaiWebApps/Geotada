# Mobile — Decouple client progress from the routing refactor

> **Status:** Design 2 · 2026-08-09 (revised after surveying actual branch progress)
> **Supersedes:** the implicit "Slice 0.4 backend first" ordering in
> [`specs/2026-08-04-mobile-roadmap/roadmap.md`](../2026-08-04-mobile-roadmap/roadmap.md).
> The roadmap's *content* stands; only the *sequencing* is replaced.
> **Related:** [`specs/2026-08-09-public-read-endpoints/`](../2026-08-09-public-read-endpoints/),
> [`specs/2026-08-07-bg-location-spike/`](../2026-08-07-bg-location-spike/),
> [`specs/2026-08-08-tour-playback-bg-audio/`](../2026-08-08-tour-playback-bg-audio/).
> Memory: `project_mobile_prod_api_gap`, `project_team_drives_backend_only`,
> `project_justaudio_silent_background_ios`, `learning_team_shared_checkout_collision`.
> **This doc is NOT code.** It is the re-sequencing plan.

---

## 1. The situation in one paragraph

Client work looked blocked on the backend, because the partner is refactoring **routing**
(which had become wrongly intertwined with tour generation). In fact the golden-path
spine is already live in prod and the app depends on a stable **contract**, not routing
internals — so almost nothing is truly blocked. More importantly, a survey of the actual
branches shows the two hardest risks in the whole project are **already built and proven
on-device**, but that proven work is sitting **unmerged** while `main` is about to move
under the routing refactor. The real priority is therefore to **land the proven work
first**, then keep building on the parts that don't need the refactored backend.

## 2. What is actually built (branch survey, 2026-08-09)

| Item | Status | Where |
|---|---|---|
| **iOS background-location + geofence, locked/pocketed** | ✅ **built + on-device proven** | `slice0-bg-location-spike` (PR #15) |
| **Locked-screen audio (native path) + GPS-trigger** | ✅ **mechanism on-device proven via a debug proof harness**; production routing (iOS→native player) unit-tested. The production *screen* is NOT built (Step 2). | `tour-playback-bg-audio` (stacked on #15) |
| Per-dev signing + build-to-device + CocoaPods→SPM | ✅ built | folded into the stack |
| Tour-playback **engine** wiring (`TourPlaybackService`) | ✅ engine proven via debug proof harness (2 hardcoded stops); not yet wired to a production screen | `tour-playback-bg-audio` |
| `/lenses` public endpoint | ✅ built + adversarially proven, **not deployed** | `backend-public-read-endpoints` (commit `9f9b4c9`) |
| 0.1 Design system (`mobile/lib/theme/`) | ❌ not built | — |
| 0.2 `MapView` seam (wrapper widget) | ❌ not built (map+pins proven in a proof page, not yet a reusable seam) | — |
| 0.3b Entitlement seam | ❌ not built | — |
| Real styled screens 1.5 / 1.6 / 1.7 | ❌ not built (engine proven; UI is the remaining work) | — |
| Frozen-contract fixture | ❌ not built (proof page uses 2 hardcoded stops) | — |

**Integration state:** `slice0-bg-location-spike` = 17 commits ahead of main; the audio
branch (stacked) = 30 ahead; the `/lenses` branch = 1 ahead. All are **0 commits behind
main**. They do **not** touch `src/`, but they DO touch the build system — `Makefile` +
`scripts/preflight.py` (a new `cocoapods` requirement) — which is the same subsystem the
partner is editing uncommitted (`tests/test_preflight.py`). Verified 2026-08-09 in an
isolated worktree off the audio tip: the branch's `cocoapods` requirement passes its own
`test_preflight.py` guard; `flutter analyze` clean; `flutter test` green (243, incl. the 5
new files re-run explicitly = 44 pass); the only 2 `test_preflight` reds are pre-existing +
environment-driven (a live `:8000` dev server) and reproduce on plain `main`.

**✅ LANDED 2026-08-10** — merged to `main` via **PR #16** (merge commit `4ec37d9`; PR #15
auto-closed as MERGED, its 17 commits being ancestors). Two judge PROCEED rulings.
Remote-only merge; the partner's uncommitted work never touched. Known-environmental red
documented in the PR body. Rollback if ever needed: `git revert -m 1 4ec37d9`.

## 3. The plan (priority order)

### Step 0 — Land the proven mobile stack to `main` ✅ DONE (2026-08-10)
Merged via **PR #16** (merge commit `4ec37d9`), one PR / merge-commit, subsuming PR #15.
Verified in an isolated worktree (see §2); two judge PROCEED rulings; remote-only.
**Next actual work starts at Step 1.**

### Step 1 — Remaining foundation (zero backend)
On consolidated `main`: **0.1** design system (`theme/` tokens + the Slice-1 widget kit),
**0.2** `MapView` wrapper (promote the proven map+pins work into the reusable seam),
**0.3b** entitlement no-op seam. Client → superpowers → build-to-device loop.

### Step 2 — Real tour screens against the frozen contract
Build the styled **1.5** review-prepare, **1.6** exec-live/exec-story, **1.7** completion
screens. The engine underneath is already proven; this is UI. Use the frozen fixture (§4)
so the in-flight routing backend can't block it.

### Step 3 — Ship `/lenses` + repoint (independent, any time)
Deploy the already-proven `/lenses` and point the app's `LensService` at it, so onboarding
loads real data instead of the fixture. Details in §5.

## 4. The frozen-contract fixture (keeps Step 2 non-garbage)

Mobile consumes the Pydantic contract in [`src/api/models/trips.py`](../../src/api/models/trips.py)
(`GeneratedStop`, `TripGenerateResponse`, `TripComposeResponse`) — **not** routing
internals. Of every field, exactly one is both routing-derived *and* needed early —
`transit_polyline` (already `String? | null`, so absence degrades gracefully); `options`
isn't consumed until Slices 4–5.

- **Capture** one real `/trips/generate` + `/compose` response from **prod** (prod runs
  pre-refactor `main`; it is the exact bytes the app parses; no local rig; immune to the
  partner's local WIP). Commit as
  `mobile/test/fixtures/paris_golden_trip.generate.json` / `.compose.json`.
  If prod returns null `transit_polyline` (no Valhalla), that's fine for Steps 1–2; capture
  a non-null polyline from a local `main` worktree only when map-line rendering is built.
- **Inject** through the existing seam — `TripService({http.Client? httpClient})` →
  `GeneratedTrip.fromJson` ([`mobile/lib/services/trip_service.dart`](../../mobile/lib/services/trip_service.dart)).
- **Drift guard (mechanical):** a hermetic backend test snapshots `model_json_schema()`
  for the three response models and fails on any structural change — firing at the source
  the instant the refactor alters the contract. When it fires, re-capture and `diff`:
  internals-only → UI untouched; `transit_polyline`/`options` shape change → the diff is
  the exact reconcile list.
- **Honest limit:** the fixture proves the UI *renders the contract*; it does not validate
  tour *quality*. The real pocketed Paris-walk quality gate waits for the routing refactor.

## 5. `/lenses` deploy (Step 3 detail)

`/lenses` touches only `product.py` + one mount line in `app.py` — zero overlap with the
routing files — so it is isolatable from the red-suite collision that parked the /team
slice.
1. Clean worktree off `main`; bring over the proven `/lenses` from `9f9b4c9`.
2. **Split** it so only `/lenses` ships — not the bundled `/profile` `{}` stub (this repo
   forbids shipping empty data to prod: roadmap 0.4 "200 on empty `[]` is NOT a pass";
   `feedback_no_empty_data`). Split is cheap given the isolation.
3. Targeted product-router tests only (not checkout-wide `make audit`, which the partner's
   reds poison) → judge consult → merge → Render auto-deploys.
4. Then repoint `LensService` off `/nodes/*`+`/edges/*` onto `GET /api/v1/lenses` (client
   loop). Closes the lens half of `project_mobile_prod_api_gap`.

## 6. Open product decisions (surfaced by the on-device walk)

- **10m geofence is too tight.** A clean walk missed a stop by 0.2m (closest approach
  10.2m vs 10.0m). `TourPlaybackService.triggerRadiusMeters` is now configurable (default
  10m preserved; proof used 20m). Decide: widen the default and/or go accuracy-aware. Ties
  into Slice 2's backend `trigger_radius`.

## 7. What this plan does NOT do

- Does not validate tour quality (waits for the routing refactor + the real walk).
- Does not build the route-`options` picker or polyline rendering now (later slices).
- Does not touch `/team`; deploy runs the repo Judge/`make test` track, client work runs
  superpowers → build-to-device.
- Does not merge or deploy anything during planning — Steps 0/3 are gated by judge + a
  human go at execution.
