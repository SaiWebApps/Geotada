# New-City Onboarding Panel — Atomic Implementation Plan

**Date:** 2026-07-12 · **Tier:** 3 (user-facing feature + registry refactor the prod
API imports + upload/deploy to real DBs + a repo-file-writing HTTP surface + a new
committed city every parametrized suite inherits).

**Goal (the "/goal"):** A workbench panel, presented before the existing city selector,
that onboards a not-yet-supported city (e.g. London): the user types a city, watches
EXHAUSTIVELY which sources are being consulted (live), sees a clean list of POIs + beats,
and uploads locally (button 1) or to cloud/Aura (button 2). After a local upload the city
appears as a first-class option in the existing selector; after a cloud upload it serves
in prod. All tests cover the new city.

## Locked decisions (confirmed with the user 2026-07-12)
- **Sourcing modes** are checkboxes: (a) *License-clean web auto-ingest* — full ingest from
  Wikipedia, Wikivoyage, Wikidata, OpenStreetMap, Project Gutenberg, Internet Archive
  (public-domain). (b) *Shadow-library discovery ONLY* — Anna's Archive / WeLib metadata
  pointers surfaced for the human to acquire legally; NO automated download/ingest of
  copyrighted text (enforced structurally, see §Grey-zone). (c) *Manual rights-cleared book
  drop* — reuse the existing `Books/{city}/` → book-prep → unified-beat-extract flow.
- **Prod is filtered by `cloud_deployed`.** A city onboarded + uploaded LOCALLY must NOT be
  servable by the PUBLIC prod `/trips` API until it is deployed to Aura. `SUPPORTED_CITIES`
  stays "all registered" (keeps the onboarding guard honest + lets the local workbench serve
  it); the cloud-only filter is applied at the `/trips` request boundary keyed on
  `cloud_deployed`, gated by the same signal that disables the workbench in prod
  (`WORKBENCH_API_ENABLED=false`).
- **Execution:** atomic, autonomous, verifier-proven. Each step below = ONE gated commit with
  pasted proof (undo-test + `make lint` + the relevant `make test*` + snapshots where a UI is
  involved). Verifier agents (QA undo-test + 2–4 hostile skeptics on different models + judge
  + acceptance) must PROVE each step; no role blesses its own work.

## The grey-zone hard boundary (structural, 5 independent walls)
1. **Type wall** — shadow results are `DiscoveryPointer` with NO text/content/body field;
   nothing downstream can consume text that does not exist. `assemble`/`beat_draft` accept
   only `SourceDocument` / pinned-file inputs.
2. **Network wall** — the ONLY ingest HTTP door (`src/onboard/fetch.py`) enforces
   `INGEST_DOMAIN_ALLOWLIST`; any `annas-archive.*`/`welib.*`/non-allowlisted host raises.
3. **Persistence wall** — pointers live only in the job's in-memory event log/results,
   rendered as an outbound link labelled "acquire legally, then use Manual book drop"; never
   written into `data/{slug}/` or `Books/`.
   *(NOT YET ENFORCED as of Step 2 — flagged by the 2026-07-14 opus skeptic. The carriers
   `OnboardEvent.data` and `OnboardJob.result` are open `dict`s (`models.py:96,118`), so unlike
   the airtight `DiscoveryPointer` they COULD hold text. BINDING for Step 4/5: (a) a
   `discovery_pointer` event's `data` must be DiscoveryPointer-shaped and text-free — add a
   validator/guard where these events are created (Step 3 shadow_discovery) and rendered
   (Step 5); (b) `assemble`'s persistence layer must NEVER write any event/`result`/pointer
   payload into `data/{slug}/` or `Books/` — add a test asserting a run that surfaced a pointer
   writes nothing shadow-derived to disk.)*
4. **Validator wall (already exists — but weaker than first stated; corrected 2026-07-14 by
   the skeptic panel).** `scripts/validate_beats.py` grounds every beat's `source_passage`
   against a pinned Wikipedia revision or an on-disk `Books/` chunk by VERBATIM substring.
   Caveats it does NOT cover: (a) a *missing* chunk file is a SOFT-SKIP (`validate_beats.py:231`
   `if chunk_text is None: continue`), not a hard block — so absence alone does not stop an
   upload; (b) it checks file *existence + text match*, never *provenance/license*, so a
   shadow book the user (wrongly) drops into `Books/{city}/` would ground SUCCESSFULLY. This
   wall therefore backstops "the quoted text really is in the cited source", NOT "the source
   is license-clean". License-cleanliness is carried by walls 1–3 + the Step-3 connector
   contract, never by this validator.
5. **Regression wall** — `tests/test_onboard_boundary.py`: allowlist rejection, model-shape,
   a repo-wide scan that no `data/*/beats.json` attribution references shadow domains, and an
   AST/grep check that `shadow_discovery.py` never imports the document fetcher.

## Grounded facts (verified in-repo 2026-07-12)
- Selector is DB-driven: `GET /api/v1/cities` (`src/api/routes/graph.py:61` `list_cities`)
  → distinct `POI.city_name`. A city shows up once its POIs upload. No selector code needed.
- Registration today = 3 Python literals + beats: `CITY_BBOX` (`scripts/upload_paris.py:68`),
  `SUPPORTED_CITIES` (`src/tour/contract.py:17`), `data/{slug}/beats.json`. Guard:
  `tests/test_data_integrity.py::test_every_data_city_is_fully_registered`.
- `/trips` city validation: `src/api/models/trips.py:12 _validate_city_slug` → `SUPPORTED_CITIES`.
- Workbench routers mount ONLY inside `_workbench_api_enabled()` (`src/api/app.py:177`);
  prod Render sets `WORKBENCH_API_ENABLED=false`. Prod Dockerfile ships `src/`+`frontend/`
  only, NOT `data/` → the registry file must live under `src/`.
- Cost pattern: `conftest.py:37` forces `COMPOSE_PROVIDER=mock`; add `ONBOARD_PROVIDER=mock`
  the same way. `conftest.py` flips any skip → FAILURE. Data suites auto-parametrize over
  `data/*/`; the gravity tier-shape test needs ≥30 POIs, each with a `_pipeline.gravity_audit`.
- Upload targets: `make deploy CITY=x` (local) / `make deploy-cloud CITY=x` (Aura).
  `scripts/db_parity.py` iterates ALL `data/` cities → a local-only city would read as cloud
  drift unless skipped when `cloud_deployed:false`.
- Naming hazard: `test_onboarding_api.py` + `/auth/onboarding/*` already exist (USER
  onboarding). All new artifacts use **onboard** (city), never onboarding.
- Streaming: no SSE/WS today → use FastAPI `StreamingResponse` SSE + seq-numbered snapshot
  polling (zero deps, deterministic for tests; EventSource works from review.html's `file://`
  given CORS `allow_origins="*"`).
- Valhalla tiles are NOT required (degenerate-iso fallback → honest-but-thin tours;
  precedent: NYC). Real dependency for tour QUALITY only, deferred.

## Atomic steps (each = one gated commit)

### Step 1 — City registry foundation  [$0, no live HTTP/LLM]
The enabler; tightly coupled → ONE coherent unit.
- Add `src/cities.json` (paris, new_york — bbox values byte-equal to today's literals; each
  gets `display_name`, `bbox`, `centre`, `cloud_deployed:true`).
- Add `src/city_registry.py`: `load_registry()`, `bbox_map()`, `supported_cities()`,
  `servable_cities()` (all registered locally; only `cloud_deployed` when
  `WORKBENCH_API_ENABLED=false`), `register_city(entry)` (atomic sorted write),
  `mark_cloud_deployed(slug)`.
- `src/tour/contract.py`: `SUPPORTED_CITIES = frozenset(city_registry.supported_cities())`
  (same symbol, same import sites).
- `scripts/upload_paris.py`: `CITY_BBOX = city_registry.bbox_map()`; keep `PARIS_BBOX`.
- `src/api/models/trips.py`: `_validate_city_slug` → `city_registry.servable_cities()`.
- `scripts/db_parity.py`: on a cloud target, cities with `cloud_deployed:false` report
  `SKIP (local-only)`, not drift.
- `tests/test_data_integrity.py`: guard → registry-based, same fail-fast intent + message.
- NEW `tests/test_city_registry.py`.
- **Proof:** paris/new_york bbox byte-equal to the old literals; guard green; a monkeypatched
  fake unregistered `data/zzz/` fails naming zzz; prod-mode (`WORKBENCH_API_ENABLED=false`)
  excludes a non-`cloud_deployed` city from `servable_cities()`; `make lint` + `make test-local`.
  Undo-test: revert `city_registry.py` → derivation/guard tests RED.

### Step 2 — Onboard core (models + jobs + fetch + boundary)  [$0]
- NEW `src/onboard/__init__.py`, `models.py` (`SourceDocument{license,text,...}`,
  `DiscoveryPointer{title,author,year,format,source_url}` — no text field, `OnboardEvent`,
  `OnboardJob`), `jobs.py` (in-memory `JobStore`, append-only `seq`-numbered events),
  `fetch.py` (`INGEST_DOMAIN_ALLOWLIST` + `ONDOWAY_ONBOARD_HTTP=live|fixture`).
- NEW `tests/test_onboard_jobs.py`, `tests/test_onboard_boundary.py` (walls 1,2,5).
- **Proof:** allowlist raises on `annas-archive.*`/`welib.*`; `DiscoveryPointer` has no text
  field (model test); event seq monotonic + snapshot `after_seq`; repo-wide beats scan clean.
  Undo-test: add a shadow domain to the allowlist → RED.

### Step 3 — Source connectors (parallel, one file each)  [$0, fixture HTTP]
- NEW `src/onboard/sources/{wikipedia,wikivoyage,wikidata,osm,gutenberg,internet_archive,
  shadow_discovery}.py`; fixtures under `tests/fixtures/onboard/london/`; NEW
  `tests/test_onboard_sources.py` (fixture-mode parse per connector; NO live HTTP in the bar).
  osm/wikidata must return coordinates; shadow_discovery returns `DiscoveryPointer` only and
  never imports the document fetcher.
- **BINDING requirements from the 2026-07-14 skeptic panel (do not drop):**
  - **F6 — the `internet_archive` connector MUST verify per-ITEM public-domain status before
    emitting a `SourceDocument`.** The `archive.org` allowlist entry is HOST-based, not
    license-based (archive.org hosts in-copyright CDL scans + community uploads), so the host
    wall alone does NOT satisfy the plan's "Internet Archive (public-domain)" decision. The
    connector reads each item's `metadata` (`possible-copyright-status` == "NOT_IN_COPYRIGHT"
    and/or a public-domain `licenseurl`/`rights`) and REFUSES any item that is not provably
    public-domain. Add a test proving an in-copyright IA fixture is rejected. (Live IA full-text
    ingest is deferred to Step 8, so this is not on the near-term path — but the wall lands here.)
  - **F8 — Wall 5's connector-isolation check ships in THIS step.** Add to
    `tests/test_onboard_boundary.py` an AST/import scan asserting `shadow_discovery.py` never
    imports `src.onboard.fetch` (nor any httpx/requests network module) — this is the committed
    proof of fetch.py's "only door" property, currently unenforced. Undo: make shadow_discovery
    import the fetcher → RED.
- **Proof:** each connector parses its fixture → typed candidates with the expected fields
  (coords where required); undo a connector → its case RED. Fan out to parallel devs.
- **2026-07-14 skeptic-panel outcome (what actually shipped in Step 3):** 7 connectors built in
  parallel against a frozen `base.py` interface (connectors are PURE `consult_url`+`parse`; only
  `base.run_connector` imports `fetch` — verified sole caller). A 2-model panel then found + we fixed:
  (R1) wikidata `KeyError` on WDQS-omitted `placeLabel` → defensive `.get` + skip labelless;
  (R2) wikivoyage `{{listing}}` regex not brace-balanced → nested templates silently dropped coords →
  replaced with a brace-balanced scanner; (R3) internet_archive `KeyError` on missing `title`/`response`
  → `.get` guards + skip. **F6 (the IA public-domain wall) broke THREE times under re-attack** — a
  substring collapse, a host-spoofed `licenseurl`, then an OR-override where a genuine-host PD
  `licenseurl` beat an explicit `IN_COPYRIGHT` status — so it was SIMPLIFIED to one authoritative,
  fail-closed signal: **IA auto-ingest accepts iff `possible-copyright-status` normalizes to exactly
  `NOT_IN_COPYRIGHT` (string or list; fail-closed on missing/empty/mixed/non-string). No `licenseurl`
  and no free-text `rights` acceptance path remains.** DELIBERATE COVERAGE BOUNDARY: a genuinely-PD IA
  item lacking that computed status is NOT auto-ingested — use the Manual book-drop. (F8) the shadow
  connector-isolation AST guard was hardened (dynamic `__import__`/`import_module` detection +
  `urllib3`/`aiohttp`/`socket`/`http.client`); transitive-import evasion is a documented single-file-AST
  limitation, not covered. Every fix is red-first + undo-verified; each wall re-attacked until an
  adversary failed.

### Step 4 — Assemble + beat draft + CLI  [$0 in bar via mock]
- NEW `src/onboard/assemble.py` (merge on `canonical_name_key` + rapidfuzz; coords
  Wikidata→OSM→Wikivoyage; forced-distribution tiers shaped to pass
  `test_gravity_distribution`; stamp `_pipeline.gravity_audit{signal_source:"onboard_auto_v1"}`;
  atomically write `poi-raw.json`, `areas.json=[]`, `within_edges.json`, `book-log.json`,
  pinned `wikipedia/` texts; `city_registry.register_city`).
- NEW `src/onboard/beat_draft.py` (`MockBeatDrafter`/`AnthropicBeatDrafter` on
  `ONBOARD_PROVIDER`, mock default; drafts ONLY from pinned Wikipedia revisions; output passes
  `validate_beats.py` unchanged; `estimate_cost(n)` for the confirm modal).
- NEW `src/onboard/cli.py` + Makefile `onboard-city` target.
- **BINDING requirements from the 2026-07-14 researcher stock-take (the silent gates that will
  turn RED the instant `data/london/` exists — design against them up front):**
  - **Forced-distribution histogram + bbox clamp.** `test_gravity_distribution` (auto-parametrized
    over every `data/*/`) enforces T5 ∈ [7,20]%, T3 ≤ 35%, **T1+T2 ≥ T4+T5** (bottom-heavy), and a
    truthy `_pipeline.gravity_audit` on EVERY POI. `assemble` must emit an explicit target histogram,
    and CLAMP/verify every POI's coords inside the registry bbox (`upload_paris.py:149` silently drops
    out-of-bbox POIs, which can also break the centroid check `test_data_integrity.py:82`).
  - **Verbatim-substring Wikipedia grounding.** `validate_beats.py:158-159` requires each beat's
    `source_passage` to be a literal (normalized) substring of `data/london/wikipedia/{chunk}.txt`.
    So (a) `assemble` MUST actually write those pinned `wikipedia/{slug}-rev-{revid}.txt` files (reuse
    `scripts/wiki_fetch.py`'s save path), and (b) even `MockBeatDrafter` must QUOTE a real span from the
    pinned fixture text — paraphrase/lorem fails. Mock path must be self-consistent: fixture wiki text →
    mock quotes a substring of that same text.
  - **Accent-normalized dedup.** `canonical_name_key` (`nodes.py:25`) only lowercases + collapses
    whitespace; it does NOT strip accents, but `test_data_integrity.py:92` dedups on accent-strip+casefold
    (`_norm`) and `:151` forbids `name_variation` collisions. Merge key MUST mirror `_norm` (accent-strip)
    and use `rapidfuzz` for near-dups, staying conservative per poi-dedup's ZERO-FALSE-MERGE rule.
  - **Cost hygiene:** force `ONBOARD_PROVIDER=mock` in `tests/conftest.py` (mirror `COMPOSE_PROVIDER`
    at `conftest.py:37`) so the bar never makes a live Anthropic call. Do NOT emit a `centre` field —
    `src/cities.json` / `register_city` validate only `display_name`/`bbox`/`cloud_deployed`.
- **Reuse (zero new deps — researcher-confirmed):** wikipedia/wikivoyage → `scripts/wiki_fetch.py`;
  osm → `src/utils/spatial.py` (Overpass); merge → `rapidfuzz` (already a dep) + `canonical_name_key`;
  wikidata coords → P625; do NOT add `osmnx`/`gutenbergpy`/`internetarchive` (heavy, uv.lock/Apple-index risk).
- **Proof:** `make onboard-city CITY=london MODES=license_clean` (fixture+mock, tmp DATA_ROOT)
  → ≥30 POIs each with coords + `gravity_audit`, registry entry written, `beats.json` passes
  `validate_beats.py`; live provider without `confirm_cost` makes ZERO Anthropic calls
  (counting fake). Undo-test per new behavior.
- **2026-07-14 skeptic-panel outcome (Step 4):** built `assemble.py` (pure merge/tier/dedup) +
  `write_city` (sole disk/registry touch; wall-3 STRUCTURAL — it only ever receives POI dicts +
  `WikiExtract`, never a `DiscoveryPointer`) + `beat_draft.py` (mock/Anthropic; BOTH set
  `source_passage` to a mechanical verbatim slice of the pinned extract, so live grounding cannot
  regress vs. mock) + `cli.py` + `make onboard-city`. Proof: `make onboard-city CITY=london` (fixture+mock,
  tmp DATA_ROOT) → 36 POIs, tiers T5=3/T4=6/T3=9/T2=9/T1=9 (passes the shape guard), 35 grounded beats,
  `validate_beats` PASS, registry entry (no `centre`), and NOTHING written to committed `data/` — hermetic.
  A 2-model panel (opus grounding/wall-3/flow SURVIVED; sonnet tiers SURVIVED verified N=30..2e6, registry
  try/finally SURVIVED under forced exception) found + we FIXED: (i) `write_text` missing `encoding="utf-8"`
  (would break the first accented city on a non-utf-8 runner); (ii) distance-blind exact-`_norm` merge that
  silently collapsed two distinct same-named places → now geo-aware (co-located merge; distant same-names
  kept as separate, disambiguated, logged POIs); (iii) added the registry-exception-restore test. All
  red-first + undo, with a hard regression gate that London's 36-POI output is unchanged.
- **DEFERRED to Step 8 (BINDING, real-data — documented, all fail-CLOSED/visible, none silent-corrupt):**
  (a) abbreviation-equivalence dedup ("St." vs "Saint" at same coords currently survive as a visible
  same-coords duplicate) — deferred because "St"→"Saint" vs "Street" is genuinely ambiguous and needs real
  data + human review; (b) live identical-body `hash_body` collision (aborts the run via `validate_beats`,
  not corrupts) — add a live de-dup/retry in Step 8; (c) `slugify`-collision surviving `_norm` dedup
  ("Notre-Dame" vs "Notre Dame" → identical `beat_id`, one shared extract) — aborts loudly via identity gate.
  The full geo-split + disambiguation quality tuning is best validated against the real London corpus at the
  Step-8 milestone (acceptance-agent tour judgement + human sign-off), not a synthetic fixture.

### Step 5 — Onboard API router  [$0 in bar via mock+fixture]
- NEW `src/api/routes/onboard.py` (`POST /onboard/jobs`, `GET /onboard/jobs/{id}` snapshot,
  `GET /onboard/jobs/{id}/stream` SSE, `POST .../draft-beats` with 409+estimate cost gate,
  `POST .../upload {target:"local"}` running `scripts.deploy` as a subprocess with NEO4J env
  copied from the API's OWN environment).
- `src/api/app.py`: include the router INSIDE `_workbench_api_enabled()`.
- NEW `tests/test_onboard_api.py` (TestClient, mock+fixture; SSE content-type; 409 gate with
  zero-LLM counter; router absent when workbench disabled; upload subprocess env-pinning).
- **Proof:** full mock-mode flow returns ≥1 `source_consult` per selected source each with a
  concrete URL; stream is `text/event-stream`; workbench-disabled → router absent. Undo-tests.
- **2026-07-14 outcome (Step 5):** shared flow extracted to `src/onboard/flow.py` (imported by BOTH
  cli.py and the router — no API→CLI private coupling); `src/api/routes/onboard.py` mounts INSIDE
  `_workbench_api_enabled()` (prod `WORKBENCH_API_ENABLED=false` → never mounted; guarded by
  `test_render_manifest`). SSE via BackgroundTasks (deterministic under TestClient: job terminal before
  the POST returns), worker try/except always terminates the stream, 409 cost gate makes zero LLM calls,
  upload pins NEO4J_* from the API's own env via a patched `_run_deploy` seam. Bar: make lint clean,
  test_onboard_api 16 passed (incl. security + negative-path coverage), test_onboard_assemble 15 passed,
  onboard-city regression 36/PASS, FULL make test-local 1761 passed/0 failed/0 skipped. QA: all undo-tests genuine. **Security skeptic (opus) found a REAL hole: slug
  path-traversal** — `slug` was unvalidated on the write path, so `write_city` wrote OUTSIDE data_root
  before `register_city` (the only allowlist) ran last; and a valid `slug="paris"` would clobber
  committed data/paris. FIXED: `^[a-z][a-z0-9_]*$` validation at the API boundary + at the top of
  `write_city` + a `CityContext` validator, PLUS create_job rejects an already-registered slug
  (onboarding is for NEW cities). Also hardened: upload wraps `_run_deploy` (deploy failure → status
  error, not stuck "assembled").
- **RESOLVED 2026-07-14 (own commit, user-activated): `_workbench_api_enabled()` flipped to FAIL-CLOSED** —
  now mounts the workbench CRUD + onboard routers ONLY on an explicit truthy `WORKBENCH_API_ENABLED`
  ({true,1,yes,on}); unset/empty/typo'd → OFF. CI + local dev opt in explicitly (conftest `setdefault`,
  Makefile `api`/`api-test`, `scripts/workbench.sh`); prod `render.yaml` "false" stays OFF; `city_registry`'s
  cloud-filter mirror left as-is (intentional unset-value asymmetry, commented). Proof: full `make test-local`
  1777 passed + real-browser `make test-workbench` 58 passed + an 18-value fail-closed parser probe + judge
  mutation-check. **Auth (a shared-secret/localhost dep) was DELIBERATELY NOT added** — the surface is now
  fail-closed + prod-unmounted + 127.0.0.1-bound, so auth stays a further optional step, not shipped here.
- **(historical) DEFERRED hardening (documented, not changed in Step 5): `_workbench_api_enabled()` was FAIL-OPEN** —
  only `{false,0,no,off}` disable it; an unset/typo'd value (`WORKBENCH_API_ENABLED=disabled`) would
  expose the unauthenticated repo-write+deploy surface. Prod is safe today (`render.yaml` sets `"false"`,
  guarded by the render-manifest test) and this behavior is PRE-EXISTING + shared by all workbench CRUD
  routers (graph/nodes/edges/schema) with CI depending on default-on — so flipping to fail-closed is a
  separate, broader decision, not a Step-5 change. Follow-up: make it opt-in (fail-closed) + add auth to
  the workbench surface.

### Step 6 — Frontend panel  [proof in Step 7]
- NEW `frontend/onboard.html` (mode checkboxes; live consult feed; POI/beat panes; cost-confirm
  modal; "Upload locally" + "Upload to cloud" (cloud disabled until Step 8's cloud slice)).
- `frontend/review.html`: one "Onboard a new city →" anchor in `#cityOverlay`, preserving
  `apiPort`.

### Step 7 — Real-browser proof  [Playwright, not in the bar]
- `tests/test_workbench_ui.py`: new class — fixture-mode onboard run on :8001, feed shows EVERY
  source line-by-line, POI/beat panes render, "Upload locally" → `/cities` contains london →
  reopen review.html → selector shows "London — N POIs". Screenshots to `tests/reports/screenshots/`.
- **Proof:** `make test-workbench` green + pasted screenshots.

### Step 8 — Real onboarding + milestone gate  [LIVE spend — cost-estimated + user-confirmed]
- Run the panel live for London (real HTTP; LLM beat drafting with a printed $ estimate and
  explicit confirm), review output, `make deploy CITY=london`, commit `data/london/` + registry
  entry. Then the milestone bar: full `make test` green with London present, `make db-parity`,
  acceptance agent judges a REAL London tour (good-for-tourist, not just correct), skeptic panel
  on the boundary + registry equivalence, judge PROCEED. Human sign-off.
- Deferred to follow-on slices: cloud/Aura upload button wiring + `mark_cloud_deployed`;
  shadow-library discovery EXECUTION (walls built in Step 2); manual `Books/{city}` orchestration;
  Gutenberg/IA full-text→beats; London Valhalla tiles; London live-invariant scenarios.

## Per-step test bar (tiered — amendment 2026-07-12, ratified by the Step-1 judge)
- **Modifies an existing widely-imported module** (e.g. Step 1's `contract.py`): bar = `make lint`
  + FULL `make test-local` (0 failed/0 skipped) — a broad import-time change can break an unrun suite.
- **Purely additive isolated new files** (nothing existing imports them — Steps 2–4's `src/onboard/*`):
  bar = `make lint` + every new test file (`make test-file`/`test-file-local`) + `uv run pytest
  --collect-only -q` (via a make target) to prove nothing else's collection broke. Full `make test-local`
  is NOT required per step (avoids re-running the live-OpenAI audio gate on unrelated code).
- **Wires new files into an existing module** (Step 5's `app.py` router include): bar = additive rule
  + FULL `make test-local` (the include touches app startup, a wide surface).
- **Milestone** (Step 8): full `make test` (Python + Flutter) + `make test-workbench` + browser
  screenshots + `make db-parity` + acceptance-agent tour judgement + human sign-off.

## Verifier discipline (applies to every step)
- Developer (Sonnet 5 / Opus 4.8 agent) implements minimal change + red-first test.
- QA agent: undo-test (revert fix → new test RED) + `make lint` + relevant `make test*`.
- Skeptic panel (2–4, different models) — only rewarded for breaking the claim; majority refute kills it.
- Judge: PROCEED / PROVE-FIRST / STOP before each commit. Paste the ruling.
- Manager (me): gate on green + reviewed diff, commit on `main` (per project policy), do not auto-push.
