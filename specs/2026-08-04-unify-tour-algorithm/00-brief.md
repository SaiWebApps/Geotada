# Unify the tour algorithm — owner brief (Phase 1 of 2)

Verified at commit `a7df218c`. This brief IS the research. Do not re-derive it and do
not re-litigate the decisions below; they are owner-decided.

**Phase 1 scope: algorithm only.** Do NOT change workbench auth or persistence.

---

## TARGET SHAPE (owner-decided)

The workbench adopts the phone's two-step split. Both surfaces then call two shared
blocks in `src/tour`:

- **BLOCK 1 — PLAN.** start (required), end (optional), lenses, timing → K=3 route
  options. Selects POIs, orders, routes, computes ETA/dwell/vignettes/tourability.
  NO LLM, NO spend. Its output IS the tour preview.
- **BLOCK 2 — AUTHOR.** one chosen option → per-stop scripts → audio. PAID. Never
  re-plans; authors the exact route handed to it.

The user-facing flow, identical on both surfaces:

1. Enter start point (required).
2. Enter end point (optional).
3. Select lens. App uses the profile default with selective overrides from a dropdown;
   the workbench uses the dropdown alone.
4. Specify timing.
5. Generate tour options — selects POIs + routes them to match the inputs above. These
   ARE the tour previews. No spend.
6. User selects one option.
7. NOW generate the tour scripts and audio.

### Consequences

- `/trips/preview`'s plan-and-author-in-one-call is DELETED. The workbench makes two
  calls like the phone does.
- Block 2 is `premium_tour.py`'s seam (`execute_premium_plan` + `finalize_premium_tour`).
  `authoring.py:805-1038` is DELETED. Reason: `finalize_premium_tour`
  (`premium_tour.py:627-654`) hard-codes `enforce_claim_coverage=True` +
  `scan_glue_for_invention=True` and gives `faithfulness_checker` no default, so a caller
  cannot omit it. `author_prebuilt_route` (`authoring.py:934-942`) defaults all three OFF
  and relies on `trips.py:631-637` switching them on. The incident that shape caused is
  recorded at `premium_tour.py:480-486`.
- "Flavour" = a different route through different POIs for the SAME lens, duration, start
  and end (`selection.py:246-247`: `DIVERSITY_PENALTY` 0.3, `JACCARD_OVERLAP_MAX` 0.60).
  Not a lens. Workbench shows 3, same as the phone's sheet
  (`trip_itinerary_page.dart:163-245`).

### OUT OF SCOPE for Phase 1 (Phase 2, separate ledger)

Moving the workbench onto `/trips/generate` + `/trips/{id}/compose` as
`testuser@ondoway.app`, on the 7689 workbench graph. That needs `ensure_dev_data.py`'s
`_assert_local_dev` to accept 7689. `src/seed/users.py` already seeds that user with two
profiles (Mom, Kid) carrying real `PREFERS_LENS` edges.

---

## AS-BUILT — verified at a7df218c

### SURFACES

- Workbench tour UI = `frontend/review.html` Tour Preview view (button 1031, form
  2149-2185, POST `/trips/preview` 3262, POST `/audio/preview` 3175). Opened `file://` by
  `scripts/workbench.sh:13`.
- `frontend/tour-preview.html` = thin POC, same two calls (72, 123).
- iOS: `trip_service.dart:61` `/trips/generate` · `:208` `/trips/{id}/compose` · `:176`
  `/audio/generate-trip-stops`. Compose call `trip_itinerary_page.dart:187`.

### DIVERGENCE 1 — ROUTE PLANNING

- **preview** `trips.py:946` → `plan_premium_tour` (`premium_tour.py:239`) →
  `certification_planning_policy` (`premium_tour.py:230-236`: 0.90/1.10, nominal 1.00,
  `max_stops=8`) → `select_k_routes(...,3,policy)` → `choose_discrete_route`
  (`selection.py:588`) → receipt bar (`premium_tour.py:260-275`)
- **generate** `trips.py:325` `select_k_routes(...,3,routing_client=...)` with NO policy →
  `LEGACY_ROUTE_PLANNING_POLICY` (`routing.py:124-128`, 0.83 flat, `max_stops=None`) →
  `flavours[0]` (`trips.py:326`), `choose_discrete_route` skipped, no receipt bar
- **compose** `trips.py:570-578` `summarise_route(...)` no policy → legacy 0.83.
  Hand-restores vignettes (583-585) + anchors (589-590). `tourability` always None. No
  Held-Karp reordering.
- Certification-only timebox repair: `selection.py:1970-1982` →
  `_apply_certification_timebox_repair` (`selection.py:2870-3014`).
- Stop cap: certification clamps to 8 (`selection.py:1699-1707`); legacy
  `min(HARD_ANCHOR_CAP=15, duration//10)` (`selection.py:265,273,1698`).

### DIVERGENCE 2 — SCRIPT GENERATION (11 duplicated blocks)

`premium_tour.py` ↔ `authoring.py`

| | premium_tour.py | authoring.py | what |
|---|---|---|---|
| A | 171-180 | 805-816 | compose-unit dataclass, same 8 fields |
| B | 358-362 | 835-841 | executor Protocol (`PrebuiltRouteExecutor` has ZERO references; `trips.py:492` passes the premium one) |
| C | 146 | 844-854 | route hash, identical canonicalisation |
| D | 302-310 | 885-893 | candidate identity, same 7 kwargs |
| E | 311-321 | 894-904 | character-for-character identical |
| F | 322-340 | 905-923 | unit build loop |
| G | 431-432 | 955-956 | worker-count guard |
| H | 436-456 | 958-976 | failure-recording wrapper (same AC-4 comment) |
| I | 460-461 | 980-981 | thread-pool fan-out |
| J | 492-528 | 985-1021 | response-binding loop, line-for-line |
| K | 529-542 | 1024-1037 | response-set validation + finalizer call |

ALREADY SHARED, keep: `_certification_compose_requests` (`authoring.py:489`),
`candidate_compose_request_envelope` (413), `compose_input_sha256` (400),
`_sentences_from_json` (455), `finalize_certification_composition` (553).

Only downstream of `finalize_premium_tour` (`premium_tour.py:627-706`), no counterpart on
the phone: `resolve_build_identity`, `derive_playback_assignments`,
`remap_provider_playback_assignments`, `BuildFingerprint`, `build_final_blueprint`,
`validate_llm_composed_blueprint`. `authoring.py` stops at a bare `Script` (1038).

### DIVERGENCE 3 — PREVIEW PAYLOAD (a fourth copy)

`_preview_stops` (`trips.py:734`, called 975 + 1113) duplicates the interleave in
`build_route_option` (`src/tour/options.py:51`, called only `trips.py:451-460`).
`trips.py:740` states it mirrors `build_route_option`. One survives, in `src/tour`.

### DIVERGENCE 4 — AUDIO

Conversion core is ALREADY shared: `provider.generate()` → `normalize_for_tts`
(`tts_normalize.py:239-241`) → `_split_for_tts(4000)` (`provider.py:104,107,213`). Same
voice/model both paths: nova / tts-1-hd (`provider.py:198-199`). Divergent around it:

- `/audio/preview` (`audio.py:288`) caps at `_PREVIEW_MAX_CHARS=6000` (`audio.py:118`) →
  the workbench can be judging truncated narration. In-process LRU of 16
  (`audio.py:309-311`). Returns bytes. 400/502.
- `/audio/generate-trip-stops` (`audio.py:789`) → `generate_stop_audio`
  (`pipeline.py:315-334`) → storage `stops/{poi_slug}/{stop_id}.mp3`
  (`pipeline.py:283-288`). Skips whenever `audio_url` exists (`audio.py:845`) with NO
  content hash — edit a stop's narration and stale audio survives. Every other generation
  path hashes: per-beat `audio_script_hash` (`pipeline.py:122`), keep-exploring
  `keep_exploring_audio_hash` (`audio.py:972-974`). Soft-fails 200 + `status=failed`.

---

## DEAD CODE — verified no caller, delete in scope

- `mobile/lib/widgets/beat_audio_player.dart` — `BeatAudioPlayer` never instantiated
- `TripService.confirmTripAudio` (`trip_service.dart:142`) — no caller
- `PrebuiltRouteExecutor` (`authoring.py:835`) — zero references
- `prebuilt_route_sha256` (`authoring.py:844`) — no caller outside `authoring.py`

NOT dead, leave alone — verified these have tests: `/audio/compare`, `/audio/eval`,
`/audio/generate-batch` (`test_audio_api.py`, `test_audio_route_hardening.py`,
`test_audio_functional.py`). `checkAudioStatus` is live at
`trip_itinerary_page.dart:324`.

---

## TEST LANDSCAPE

**ALLIES, must stay green:**
- `test_premium_workbench_wiring.py::test_preview_uses_shared_premium_plan_and_finalizer`
- `test_tour_authoring_gates.py::test_the_preview_surface_runs_the_same_three_gates_as_the_phone`
  (:886, assertion :954)
- `test_tour_authoring_gates.py::test_cross_stop_echo_is_suppressed` (:758, assertion :839)

**MUST CHANGE:**
`test_workbench_matches_the_app.py::test_the_preview_stop_cap_and_the_persisted_stop_cap_are_pinned`
(:2002) hard-codes (8, 15) at :2046. Its own docstring calls this "a LIVE divergence,
pinned rather than blessed". Both ceilings are being removed — re-point it at the time
budget.

**BECOMES THE SPEC, re-point rather than delete:**
`test_tour_authoring_from_route.py` (7 tests). It forbids the authoring seam from reaching
a planner (`_PLANNING_CALLS` :74-85, assertion :121). Under the two-block design that
prohibition is exactly right — it now describes Block 2. Note :381 currently pins that
receiptless haversine legs must author; see parameter 4 below.

**ALSO TOUCHED:** `test_trip_preview_contract.py`, `test_trip_preview_vignettes.py`,
`test_tour_flavours.py`, `test_trip_api.py`, `test_tour_generation.py:1525`.

---

## PLANNER PARAMETERS — DECIDED, implement as stated

1. **STOP CAP: NONE.** Duration is the only bound. Delete `max_stops=8` from
   `certification_planning_policy` (`premium_tour.py:230-236`) and the legacy
   `min(HARD_ANCHOR_CAP, duration//10)` clamp (`selection.py:1698-1707`). ALSO delete the
   1..15 guard in `_certification_compose_requests` (`authoring.py:501-502`) — it enforces
   the same ceiling in the authoring seam. Re-point
   `test_tour_authoring_from_route.py:415` and `test_workbench_matches_the_app.py:2002` at
   the time budget instead of a stop count. Note the spend shape: nothing but duration
   then bounds the number of paid authoring calls.

2. **WALK/AUDIO BUDGET: certification, 0.90-1.10, nominal 1.00.** The legacy 0.83 flat
   policy (`routing.py:124-128`) is deleted, not made optional. The phone has been
   planning ~20% less walking and audio than the workbench; the workbench figure is
   correct.

3. **AUDIO CHAR CAP: deleted.** Remove `_PREVIEW_MAX_CHARS` / `_cap_narration` from the
   preview path (`audio.py:118, 288`). It is an abuse bound on an anonymous paid endpoint,
   not a quality setting; Phase 2 resolves that exposure by moving the workbench onto
   authenticated `/audio/generate-trip-stops`. Any future bound keys on the authenticated
   user, per `trips.py:136-143`.

4. **VALHALLA RECEIPT BAR:** a route with estimated (haversine) leg times is never shipped
   silently. Leg time drives the whole time budget and the audio is paced to it, so a
   fabricated leg breaks GPS-triggered playback invisibly — `HAVERSINE_CORRECTION` 1.35 at
   `PACE_KMH` 3.0 (`routing.py:41-53`) is a straight line, and two POIs 200m apart across
   the Seine with no nearby bridge is a 900m walk. Either refuse with a structured reason
   naming routing as the cause — model it on `TourabilityRefusedError`'s shape
   (`trips.py:196-221`), not a flat 422 — or surface it explicitly through the existing
   degradations channel (`degradations.py`, `trips.py:916-919`, owner ruling at
   `trips.py:906-911`). The silent substitution that happens today goes away either way.

   **RESOLVED BY THE PLANNER-MANAGER, 2026-08-04 — labelled degradation, NOT hard
   refusal.** Evidence: `render.yaml:98-124` deploys Valhalla as a production Render
   private service (`ondoway-valhalla`, `type: pserv`, `plan: starter`, 10GB
   `valhalla-data` disk, tiles built from Geofabrik Île-de-France), wired to the API via
   `VALHALLA_URL` `fromService … property: hostport`. It is a real network dependency that
   can cold-start, restart, or rebuild tiles. Per the brief's own rule — "If it is a
   production service that can fail, prefer the labelled-degradation path — a hard refusal
   would take down tour generation for every user during an outage" — the receipt bar is
   implemented as an explicit, structured entry on the existing degradations channel, on
   BOTH surfaces. The silent substitution goes away; generation stays up.

5. **AUDIO STALENESS:** add a content hash to the per-stop path so editing a stop's
   narration invalidates its audio, matching the per-beat (`audio_script_hash`,
   `pipeline.py:122`) and keep-exploring (`keep_exploring_audio_hash`,
   `audio.py:972-974`) paths. It is the only generation path without one.

---

## CONSTRAINTS

- Repurpose or extend what exists. No new module or Makefile target where an existing one
  can carry it. This applies to Makefile targets too.
- Zero dead code left behind.
- Every test failure is ours. Bar is `make test`: 0 failed, 0 skipped.
- Judge consult before every commit, every "done", every infra action.
- Workbench behaviour claims need a real-browser run with screenshots.
