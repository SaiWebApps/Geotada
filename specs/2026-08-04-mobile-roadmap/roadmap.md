# Ondoway Mobile — Implementation Roadmap

> **Status:** Draft 1 · 2026-08-04
> **Source of truth for behavior:** the 54-screen user journey (`ondoway-journey-wireframes.html`
> / https://ondoway-user-journey.netlify.app), see [[reference_ondoway_user_journey_wireframes]].
> **Grounded against:** live survey of `mobile/lib` (Flutter) + `src/api` (FastAPI/Neo4j), 2026-08-04.
> **This doc is NOT code.** It is the master plan. Each slice below is expanded into an
> executable plan via superpowers `writing-plans` when you reach it.

---

## 0. How to use this document

- **Framework:** Flutter, **extend the existing app** (not a rewrite). iOS-first; Android is the
  final slice. See [[project_mobile_client_framework_decision]].
- **Build order:** *vertical slice first* — one thin thread on your device end-to-end, then
  deepen block by block. Narrative order (login→…→monetization) is **not** build order.
- **Every slice ends on your physical iPhone.** The acceptance gate for each slice is a
  "touch it and confirm" test, spelled out per screen — not a passing unit test alone.
- **Execution loop per slice:**
  ```
  this roadmap slice
     → taste hero targets for the slice's screens        (imagegen-frontend-mobile / apple-design)
     → superpowers writing-plans   (turn the slice into a TDD-shaped plan)
     → using-git-worktrees          (isolate)
     → executing-plans + test-driven-development
     → BUILD TO DEVICE → touch-to-confirm  (human acceptance gate)
     → requesting-code-review → finishing-a-development-branch
  ```
- **Two harnesses, by track.** *Client* slices run through **superpowers** (mobile-agnostic).
  *Backend* tasks (marked 🛠 BACKEND) run through the repo's own Judge/skeptic + `make test`
  discipline, since they live in the Python/Neo4j test rig.
- **`/team` drives the 🛠 backend register ONLY — never a client slice.** `/team`'s atomic step
  is one file-scoped change proven by exactly one node-id pytest going RED→GREEN through
  `team-engine.js` on the local Neo4j/pytest rig; it cannot build a Flutter IPA and cannot express
  a human sensory gate like "audio auto-fires while I walk." The §6 backend endpoints *are*
  file-scoped Python/Neo4j changes with node-id tests, so they are the correct — and only — target
  for `/team`. Every Flutter/on-device slice runs the superpowers → build-to-device loop above.
  Do not point `/team` at Slice 1 (or any client slice); it will refuse or misfire.

### Spec-card template (every screen gets one when its slice is planned)

| Field | Meaning |
|---|---|
| **Journey ref** | screen id + block from the 54-screen journey |
| **Status** | REAL / PARTIAL / MOCK / MISSING (from the grounding survey) |
| **Behavior** | trigger · what's on screen · primary actions · system logic (from the journey) |
| **Visual ref** | the taste hero target to produce for this screen (Point 2 taste hook) |
| **Data/state contract** | exact endpoints (method+path), request/response models, app state read/written |
| **Acceptance test** | the on-device "do X, see Y" that proves the slice |

Status legend comes straight from the survey: **REAL** = wired & working · **PARTIAL** = some
real, some stub · **MOCK** = hardcoded/placeholder · **MISSING** = not built.

---

## 1. Locked architecture decisions

1. **Flutter, extend existing app.** iOS-first, Android final slice.
2. **Map behind a `MapView` seam from day one; swap the plugin only when Android forces it.**
   Slice 0 introduces a `MapView` wrapper around the **existing** `apple_maps_flutter` — the wrapper
   *is* the swappability. The actual swap to a cross-platform plugin is deferred to Slice 10
   (Android), where it is genuinely forced; doing it on day 0 buys no iOS-first payoff and would make
   Slice 1.6 build brand-new polyline rendering against a freshly-swapped plugin. See §7.
3. **Location/audio behind a service seam.** `providers.dart` already defines
   `LocationProvider` / `AudioProvider`; formalize so the Android background-location impl is a
   drop-in later. **iOS background location is spiked in Slice 0.3, not Slice 2** — the golden-path
   walk (Slice 1.6) depends on it, so it must be proven before Slice 1 can close.
4. **Offline = client-side prefetch** (folded in per recommendation B). Reuse `AudioService`'s
   existing mp3 cache + cache the trip JSON/polylines as a client-side "tour package."
   **No new backend packaging endpoint.**
5. **Product API surface, not workbench CRUD** (folded in per recommendation A). The app must
   stop calling `/nodes/*` and `/edges/*` (404 in prod) and call purpose-built public endpoints.
   See [[project_mobile_prod_api_gap]].
6. **Design system in Slice 0** — promote the wireframe's embedded language to Flutter
   `ThemeData` tokens + a widget kit (Point 1 taste hook).
7. **State management stays `provider` + `ChangeNotifier`** (existing).
8. **Entitlement seam from day one.** Block 08 monetization gates the tour itself, so its check
   will sit inside generate/compose/audio-prepare — the very endpoints Slice 1 wires. Slice 0
   decides *where* that gate sits (even as a no-op pass-through until Slice 9) so Slice 9 does not
   reopen Slice 1's spine.

---

## 2. The slice plan (dependency-ordered)

| # | Slice | Covers (journey blocks) | New backend? | Device-testable outcome |
|---|---|---|---|---|
| **0** | **Foundation** | — | 🛠 product API surface | Any screen renders on your iPhone against a *deployed* API; design system + `MapView` seam + entitlement seam in place; **iOS background-location geofence proven on hardware** |
| **1** | **Golden Path** (vertical slice) | 01→02→03→04→05→06→07 (happy only) | — | Sign in → pick lenses → generate a Paris tour → prepare audio → **walk it (GPS-triggered)** → completion, end-to-end on device |
| **2** | **Execution depth** | 06 (fail/edge) | 🛠 surface `trigger_radius` | Running-late, off-route, offline ribbon, transcript, manual trigger — the differentiator hardened |
| **3** | **Home/Explore depth** | 03 (catalog, city landing, coming-soon, library) | 🛠 cities + trip delete + library persist | Browse cities, open a city page, library survives restart |
| **4** | **Builder depth** | 04 (Now/Plan modes, suggestions, stops, anchor, fail states) | maybe (mode flag) | Both build modes + all builder guardrail screens |
| **5** | **Review depth** | 05 (per-stop tune, download-fail, edit-breaks-timing) | — | Full tune layer + review fail states |
| **6** | **Completion depth** | 07 (feedback tags, ended-early, sync-fail) | 🛠 negative-reason tags | Structured feedback + partial/offline completion |
| **7** | **Onboarding/Lens depth** | 02 (default set, lens example) · 01 (link-not-received) | 🛠 default lens set | Starter-set flow + resend flow |
| **8** | **Multi-profile** | 03/04/06 (whose lenses, profiles, per-listener) | 🛠 multi-profile + active profile | Netflix-style profiles; "a tour each" |
| **9** | **Monetization** | 08 (teaser, paywall, unlock, partner) | 🛠 entitlements + IAP | Free teaser + purchase + partner unlock |
| **10** | **Android target** | — (platform) | — | Same app on an Android device |

**Rationale:** get the golden path walking (1) — but note the hardest iOS risk (background-location
geofence) is proven in **Slice 0.3**, because Slice 1's walk gate depends on it; Slice 2 then
hardens the *execution UX* (late/off-route/offline/transcript) on top of that proven foundation.
Then breadth. Multi-profile (8) and monetization (9) are greenfield on both sides; their *impl* is
off the "does the core product work?" path so it comes late — but the **entitlement seam** is placed
in Slice 0 (locked decision 8 / Slice 0.3b) because the gate lives inside Slice 1's endpoints. Android (10) is last, per the
framework decision — the two seams (map, background location) were kept swappable from Slice 0 to
keep it cheap.

---

## 3. Slice 0 — Foundation *(full detail)*

No user-facing feature; this is the walking skeleton + guardrails everything depends on.

### 0.1 — Design system (Point 1 taste hook)
- **Source of truth = the v10 design system**, committed at `mobile/design/design-system-v10.html`
  (+ `mobile/design/README.md` with the extracted tokens). The old
  `specs/.../design-system.html` is STALE v2 — do not use it. Cobalt blue `#2C6CC0` is the single house accent;
  neutrals are warm bone (`#F6F4F0` / `#ECE7DD`) + cool navy (`#20242C` / `#171A20`); type is
  **Fraunces (display) / Space Grotesk (sans) / Space Mono (labels)**; buttons are pills, cards
  16–24px. Lens categories keep a *secondary* color code beneath the blue. This supersedes the
  wireframe's sage/earthy palette — see [[reference_ondoway_brand_tokens]].
- **Do:** encode those tokens into `mobile/lib/theme/` (`ThemeData` + a `Tokens` class), then build
  **only the components Slice 1 screens consume** (primary/outline **pill** buttons, `LensTile`
  [exists — de-hardcode its 21 colors, blue selected ring], cards, dark location pill,
  Preparing→Downloading→Ready strip). Replace the literal hex in `lens_selection_page.dart` and
  elsewhere with tokens. Fonts load via the same Google Fonts families the site uses (`google_fonts`
  package or bundled). **Grow the kit per slice — do not build bottom nav or other unreached-screen
  components here** (bottom nav serves Slice 3); front-loading them is the horizontal build this
  roadmap avoids.
- **Open decision (§7):** keep the secondary lens-category colors, or collapse categories into
  blue tints only.
- **Acceptance (device):** a debug "Style Gallery" route renders every token + component; open it
  on your iPhone and confirm it matches the v2 hero screens in light and dark.

### 0.2 — Map seam (guardrail)
- **Do:** introduce a `MapView` wrapper widget around the **existing** `apple_maps_flutter` usage in
  `trip_duration_page.dart` (import :11, controller :48, `_onMapTap` :119, `AppleMap` widget :499).
  Nothing else uses the map today, so blast radius is one file. **Do not swap the plugin here** — the
  wrapper is the swappability; the cross-platform swap is Slice 10 (Android). Draw-polyline support
  goes through this same wrapper (Slice 1.6 needs it; `transit_polyline` is parsed today but never
  rendered).
- **Acceptance (device):** the builder Start-Point tab still drops/moves a pin and recenters on
  your iPhone, now via the `MapView` wrapper.

### 0.3 — Location/audio service seam **+ iOS background-location spike**
- **Do:** confirm/formalize `LocationProvider`/`AudioProvider` interfaces (`providers.dart`) so
  `LocationService` (foreground today) can be swapped for a background-capable impl without touching
  screens. **Then spike iOS background location here, not in Slice 2:** the golden-path walk
  (1.6) is "phone pocketed, screen off," and iOS foreground-only location stops updating when the
  screen locks — so the geofence will not fire pocketed without a background-capable location impl
  (Info.plist background modes, `NSLocationAlwaysAndWhenInUseUsageDescription`, a background-capable
  location package). This is the single hardest iOS risk; it must be proven before Slice 1 can close.
- **Acceptance (device):** with the app backgrounded and the **screen locked, phone pocketed**, a
  simulated/real location crossing a test geofence still fires a callback on your iPhone. Existing
  audio playback + location read still work. The seam is one file.

### 0.3b — Entitlement seam (no-op pass-through)
- **Do:** decide and stub *where* the monetization gate sits (inside `generate`/`compose`/audio-
  prepare) so it is a no-op pass-through until Slice 9 rather than a Slice-1-spine rewrite later.
- **Acceptance:** the golden path runs unchanged; the seam exists and is documented.

### 0.4 — 🛠 BACKEND: product API surface *(repo Judge/make-test track)*
- **Do:** add PUBLIC (non-workbench) endpoints and repoint the client:
  - `GET /api/v1/lenses` → lens taxonomy + IS_PARENT_OF hierarchy (replaces `LensService`'s
    `GET /nodes/Lens` + `GET /edges/IS_PARENT_OF`).
  - `GET /api/v1/profile` (me, from bearer) + `PUT /api/v1/profile` + lens-prefs read/write
    (replaces `ProfileService`'s `/edges/HAS_PROFILE`, `/nodes/Profile/{id}`, `/edges/PREFERS_LENS`,
    `PUT /nodes/Profile/{id}`).
  - Do **not** enable the workbench routers in prod.
- **Acceptance:** `curl` the deployed (workbench-off) API returns 200 **with a non-empty lens
  hierarchy** for `/lenses` and a real profile for `/profile` (200 on an empty `[]` is NOT a pass —
  see [[feedback_no_empty_data]]); the app renders the loaded lenses + profile on device pointed at
  that deployed API. Closes [[project_mobile_prod_api_gap]].

### 0.5 — Build-to-device pipeline
- **Do:** a `make` target that builds + installs on your physical iPhone with
  `--dart-define=API_BASE_URL=<reachable API>` (LAN IP or a staging/prod host — **not** localhost,
  which a real device can't reach). Confirm deep-link (magic-link) return works on-device.
- **Per-dev signing (see §7.3):** move `DEVELOPMENT_TEAM` + `PRODUCT_BUNDLE_IDENTIFIER` out of the
  committed `project.pbxproj` into a gitignored `mobile/ios/Flutter/DevSigning.xcconfig`; Adam's
  holds `com.ondoway.app.adam` + his team, Sai's holds `com.ondoway.app` + his. Prereqs the human
  must do once: `xcode-select` onto the full Xcode app, `brew install --cask flutter`, and sign into
  Xcode with the correct Apple ID to pick the team.
- **Acceptance:** you install from one command and any screen opens on your iPhone against a real
  API.

**Slice 0 done when:** the app builds to your device, renders the design system, the map works via
the `MapView` seam (still on `apple_maps_flutter`), lens/profile load from public prod endpoints,
**a pocketed/screen-locked geofence callback fires on hardware**, and the entitlement pass-through
seam is in place.

---

## 4. Slice 1 — Golden Path (the vertical slice) *(full spec cards)*

**Scope discipline:** happy path only. Paris only. One profile. No fail/edge screens, no
monetization, no catalog. The point is the *first end-to-end walk on your device*. Most of this
path is already REAL — the only net-new builds are **execution UI** (wire the existing engine) and
**completion**.

> Produce taste hero targets for this slice's screens **before** building (just-in-time Point 2 hook).

### 1.1 `login-main` → `login-sent` → callback — **VERIFY (REAL)**
- **Journey ref:** 01 · screens 1–2.
- **Status:** REAL (`login_page.dart`, `callback_page.dart`, `auth_service.dart`).
- **Behavior:** email → magic link → deep-link return → route by account state.
- **Visual ref:** apply the Slice 0 design system to the existing login.
- **Data contract:** `POST /auth/magic-link/request {email}` → `{message}`;
  `POST /auth/magic-link/verify {token}` → `{access_token, refresh_token}`; `GET /auth/me`.
  State written: `AuthService` tokens (secure storage).
- **Acceptance (device):** on your iPhone, enter your email, tap the emailed link, land
  authenticated. (This exercises 0.5's deep-link config against a deployed API.)

### 1.2 `lens-initial` / `lens-selected` — **VERIFY + REPOINT**
- **Journey ref:** 02 · screens 5–6.
- **Status:** REAL, but must move off workbench endpoints (Slice 0.4).
- **Behavior:** grid of lens tiles; select ≥1 (onboarding requires ≥3); Save persists to profile.
- **Visual ref:** Apple-Music tile hero; selected = sage ring + white check (journey-mandated).
- **Data contract:** `GET /api/v1/lenses` (new); save via
  `POST /auth/onboarding/complete {lens_ids:[…]}` → `{profile_id, display_name, lens_count}`.
- **Acceptance (device):** first-run after sign-in shows lenses loaded **from the deployed API**,
  pick 3, Save, land on home.

### 1.3 `explore-incity` (minimal) — **TRIM MOCK**
- **Journey ref:** 03 · screen 9.
- **Status:** MOCK (Paris hardcoded in `explore_page.dart`).
- **Behavior (slice-1 subset):** show Paris; the primary action is **"Take a tour now"** →
  builder. (Full catalog/city-landing deferred to Slice 3.)
- **Visual ref:** home hero with the on-demand CTA primary.
- **Data contract:** none new; Paris constant is acceptable for the vertical slice.
- **Acceptance (device):** open app (already signed in) → tap "Take a tour now" → builder opens.

### 1.4 `build-now` (→ generate) — **VERIFY (REAL)**
- **Journey ref:** 04 · screens 19, 25–26.
- **Status:** REAL (`trip_duration_page.dart`).
- **Behavior:** confirm start point (GPS/pin), pick a time budget, Generate.
- **Visual ref:** builder screen(s) restyled to the design system; map via the new plugin.
- **Data contract:** `POST /trips/generate` with `TripGenerateRequest{ profile_id, center_lat,
  center_lng, end_lat?, end_lng?, duration_min, start_date, end_date, start_time="09:00",
  lenses?, round_trip=false, city_slug="paris" }` → `TripGenerateResponse{ trip_id, total_stops,
  stops:[GeneratedStop], options:[RouteOption] }`. `GeneratedStop` = `{ sort_order, poi_name, lat,
  lng, beat_id, duration_min, start_time, script_body?, narration?, audio_url?, dwell_seconds,
  transit_polyline? }`.
- **Acceptance (device):** set a Paris start + a 60-min budget on your iPhone, tap Generate, get a
  real multi-stop tour back.

### 1.5 `review-preview` → `review-preparing` → `review-ready` — **VERIFY (REAL)**
- **Journey ref:** 05 · screens 31, 33–35.
- **Status:** REAL (`trip_itinerary_page.dart` + `audio_service.dart`).
- **Behavior:** map-led preview; "Confirm & Prepare" generates per-stop narration audio with a
  poll/progress strip; on ready, primary CTA = **Start Now**.
- **Visual ref:** preview card + the Preparing→Downloading→Ready strip from the design system.
- **Data contract:** `POST /trips/{id}/compose {route_id}`;
  `POST /audio/generate-trip-stops/{trip_id}`; poll `GET /audio/stop-status/{stop_id}` →
  `{has_audio, audio_url, duration_sec}`; `AudioService` caches mp3 to temp dir (this **is** the
  Slice-1 offline story — prefetch all stop audio before Start).
- **⚠️ Change on the golden path:** the "Start Tour" button currently dead-ends to `/saved-trips`
  (`trip_itinerary_page.dart:513`, FAB `onPressed` at :511). **Repoint it to the new execution
  route (1.6).**
- **Acceptance (device):** prepare a tour, watch the strip reach Ready; verify **N stops → N mp3
  files on disk** in the audio cache (not just a "Ready" label — prefetch can silently miss a stop).

### 1.6 `exec-live` + `exec-story` — **BUILD (engine exists, UI missing)** ⭐ core new work
- **Journey ref:** 06 · screens 38–39.
- **Status:** MISSING screen; **`TourPlaybackService` engine is fully built and unwired.**
- **Behavior:** full-screen guide mode — `MapView` shows position + route ahead; a next-direction
  banner; a single audio card (play/pause/replay/skip); story fires automatically on proximity to a
  stop; manual trigger available.
- **Visual ref:** the "look up at the city, not down at the phone" hero (apple-design motion for
  the arriving-at-stop transition).
- **Data/state contract:** consume the loaded `Trip`; drive
  **`TourPlaybackService.startTour(trip.stops)`** — the engine is fully built and registered in
  `main.dart` but consumed by no screen today; its signature takes `List<ItineraryStop>`, so pass
  `trip.stops`, not the `Trip`. It already does the 10m geofence trigger, auto-advance on
  audio-complete, and approaching-stop nudge; wire it via `LocationProvider` + `AudioProvider`.
  Draw `transit_polyline` on the map through the `MapView` seam (currently never rendered). Trigger
  radius: use the engine's 10m default now; surfacing `POI.trigger_radius` from the API is Slice 2.
  **Depends on Slice 0.3's background-location impl** — this is where it pays off.
- **Acceptance (device):** **the real test of the product** — start a prepared tour and physically
  walk it in Paris **with the screen locked and the phone in your pocket** (NOT simulator-only, and
  NOT screen-on-in-hand — that hides the foreground-location trap); audio auto-fires at each stop,
  map tracks you, next-stop banner updates. Then repeat one leg in **airplane mode** to prove the
  Slice-1 offline prefetch story actually plays from cache. Screenshot/transcript per stop.

### 1.7 `complete-summary` (minimal) — **BUILD (missing)**
- **Journey ref:** 07 · screen 46.
- **Status:** MISSING UI (engine has a `completed` state).
- **Behavior (slice-1 subset):** on reaching the final stop, a calm recap (route, time, stops
  completed) + "Return home." (Feedback tags deferred to Slice 6.)
- **Visual ref:** calm close (not confetti).
- **Data/state contract:** read completed/skipped from `TourPlaybackService`; mark trip completed
  locally. (A minimal `POST /feedback` up/down is optional here; structured tags = Slice 6.)
- **Acceptance (device):** finish the walk → see the summary → return home.

**Slice 1 done when:** you complete that entire chain on your iPhone in one sitting. That is the
first genuine "the product works" moment.

---

## 5. Deepening slices 2–10 *(block-level plans — expand to full spec cards just-in-time)*

Each is intentionally lighter here; expand into per-screen spec cards (and taste targets) when you
reach it.

### Slice 2 — Execution depth (Block 06 fail/edge) — *do this right after Slice 1*
- Screens: `exec-transcript` (40), `exec-late` (41), `exec-offroute` (42), `exec-offline` (43),
  `exec-end` (44).
- New work: transcript sheet with pinned mini-player; pace tracking → "running late, skip an
  optional stop"; off-route → manual trigger + recenter, **no reroute** (MVP rule); offline ribbon
  (trivial — package already local); end-early confirm → completion.
- 🛠 BACKEND: surface per-stop **`trigger_radius`** (stored on `POI`, not in the trip/stop response
  today) so triggering isn't a hardcoded 10m.
- Note: **background location is already proven in Slice 0.3** (moved earlier — Slice 1's walk
  depends on it). This slice hardens the execution *UX* on top of it, not the location plumbing.

### Slice 3 — Home/Explore depth (Block 03)
- Screens: `explore-catalog` (12), `city-landing` (13), `city-comingsoon` (14), `library` (15),
  `library-menu` (16), `profile-home` (18 — partial, full multi-profile is Slice 8).
- 🛠 BACKEND: public cities list (**adapt the existing workbench-gated `GET /cities` at
  `graph.py:60` into a public endpoint — not greenfield**) + city-landing content + coming-soon
  capture (these two are genuinely new); `DELETE /trips/{id}` (missing); wire `library` to
  `GET /trips?profile_id=` so it survives restart (today session-only).

### Slice 4 — Builder depth (Block 04)
- Screens: `build-later`/Plan mode (20), `build-time-advanced` (22), `build-anchor` (23),
  `build-suggest` (24), `build-stops` (25 full), and fail states `build-notime` (27), `build-far`
  (28), `build-impossible` (29), `build-coverage` (30).
- Note: the backend already returns **422 with alternatives** for density/feasibility refusals —
  wire those to the fail screens rather than inventing new logic. Now/Plan is a client mode toggle
  over the same `POST /trips/generate` (no separate builder).

### Slice 5 — Review depth (Block 05)
- Screens: `review-tune` (32 full — make-faster / replace-stop / change-destination),
  `review-dlfail` (36), `review-edittiming` (37). Compose re-run on edit is one-shot (409) — handle
  the regenerate path.

### Slice 6 — Completion depth (Block 07)
- Screens: `complete-feedback` (47), `complete-negative` (48), `complete-early` (49),
  `complete-syncfail` (50).
- 🛠 BACKEND: **structured negative-reason tags** — today `POST /feedback` carries only up/down +
  free-text; the journey wants a fixed multi-select tag set.

### Slice 7 — Onboarding/Lens depth (Blocks 02, 01)
- Screens: `lens-none` default starter set (7), `lens-example` (8), `login-noemail`/resend (3),
  `login-error` as a dedicated screen (4).
- 🛠 BACKEND: **default/starter lens computation** (explicitly a "future feature" today — no-lens
  profile currently runs unbiased).

### Slice 8 — Multi-profile (cross-cutting)
- Screens: `profile-home` full (18), `build-whose` (21), `exec-multilistener` (45, fast-follow /
  directional).
- 🛠 BACKEND: real multi-profile (today one `Profile` per user, MERGE'd on email local-part; no
  list/create/switch, no active-profile). Greenfield both sides.

### Slice 9 — Monetization (Block 08) — greenfield, last
- Screens: `free-teaser` (51), `paywall-unlock` (52), `unlocked` (53), `partner-unlock` (54).
- 🛠 BACKEND: **entire entitlements/purchase/partner surface — none exists.** Plus StoreKit IAP on
  the client. Biggest single greenfield build; sequenced last deliberately.

### Slice 10 — Android target (platform)
- `flutter create --platforms=android .`; verify the two seams (map plugin, background location);
  Android manifest permissions + foreground service; Google sign-in on Android; store setup;
  device test. Cheap *because* the seams were kept swappable from Slice 0.

---

## 6. Backend work register 🛠 *(repo Judge/skeptic + `make test` track, not superpowers)*

| Backend gap | Needed by | Note |
|---|---|---|
| Public `/lenses`, `/profile` product endpoints | Slice 0 | Fixes the prod 404s ([[project_mobile_prod_api_gap]]) |
| Surface per-stop `trigger_radius` | Slice 2 | Stored on `POI`, not in trip/stop response |
| Cities list + city-landing + coming-soon | Slice 3 | No *public* endpoint — but `GET /cities` already exists behind the workbench gate (`graph.py:60`); **lift/adapt it, don't write greenfield**. City-landing + coming-soon are genuinely new. |
| `DELETE /trips/{id}` + library server-load | Slice 3 | Delete only via gated workbench today |
| Now/Plan mode (likely client-only) | Slice 4 | Same generate endpoint; feasibility 422s already exist |
| Structured negative-reason tags | Slice 6 | Feedback carries only up/down + free text |
| Default/starter lens computation | Slice 7 | Explicitly a future feature today |
| Multi-profile + active-profile | Slice 8 | One profile per user today |
| Entitlements / purchase / partner unlock | Slice 9 | Zero monetization code today |

Everything the app touches is a **synchronous** call (generation is not job-based) and
**ownership-scoped** (returns 404, never 403, for foreign ids). Identity = HS256 bearer + rotating
refresh; data store = Neo4j (Aura in prod, with a wake-on-503 resume coordinator).

---

## 7. Open decisions

1. **Cross-platform map plugin — deferred to Slice 10, NOT a Slice 0 blocker.** Slice 0 wraps the
   existing `apple_maps_flutter` in a `MapView` seam; the actual swap happens only when Android
   forces it. When it does, recommendation is **`maplibre_gl`** (no API key, custom branded styling —
   fits an audio-tour product); alternative **`google_maps_flutter`** (simplest drop-in, needs a
   Google Maps API key). *Decide before Slice 10, not now.*
2. **Device-test API host (Slice 0.5).** A physical iPhone can't reach `localhost`. Options: your
   LAN IP to the local API, or a staging/prod deploy with the new public endpoints. Recommendation:
   point at prod once 0.4 lands (workbench stays off).
3. **iOS signing / bundle ID — RESOLVED + BUILT (Option 1, 2026-08-07).** `com.ondoway.app` is an
   explicit App ID owned by Sai's individual team `BC7F6Q48GB`; explicit App IDs are globally unique
   to one team, and with no shared org account (individual accounts can't add members) Adam cannot
   sign it under his own Apple ID. So Adam builds under a distinct bundle ID with his own team
   `RRN584S8HY`. Only functional cost: the Google Sign-In button (its OAuth client is bound to
   `com.ondoway.app`) — use email magic-link, which rides the `ondoway://` scheme and is unaffected.
   **As built:** committed `mobile/ios/Flutter/Signing.xcconfig` holds Sai's defaults
   (`ONDOWAY_DEV_TEAM`/`ONDOWAY_BUNDLE_ID`) and `#include?`s a **gitignored `DevSigning.xcconfig`**
   each dev overrides; `Debug`/`Release.xcconfig` include it and the committed `project.pbxproj`
   references `$(ONDOWAY_DEV_TEAM)`/`$(ONDOWAY_BUNDLE_ID)`, so it never churns between developers.
   Proven both ways via `xcodebuild -showBuildSettings`. Adam's local bundle ID is
   `com.ondoway.app.adam` (in his gitignored `DevSigning.xcconfig`; the next `make flutter-device`
   re-provisions it as a fresh install on device). Do NOT set team/bundle in Xcode's Signing tab (rewrites
   the pbxproj to a literal). See [[project_ios_per_dev_signing]]. A proper `Flutter/Profile.xcconfig`
   is still owed before `flutter build ipa`/TestFlight (Profile currently borrows `Release.xcconfig`,
   which works with a benign CocoaPods warning).
4. **Confirmed folded in:** offline = client prefetch (B); product API surface over workbench CRUD
   (A). Flag now if either should change.

---

## 8. What this roadmap deliberately does NOT do yet
- No full spec cards for Slices 2–10 — those are written just-in-time (matches the just-in-time
  taste pass and `writing-plans`).
- No visual concepts generated yet — the taste hero pass runs per slice, starting with Slice 0's
  design system + Slice 1's golden-path screens.
- No code. This is the plan the execution loop consumes.
