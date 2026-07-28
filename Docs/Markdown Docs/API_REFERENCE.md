# API Reference

Base URL: `http://localhost:8000/api/v1`

Start the server with `make api`. Interactive Swagger docs are available at `http://localhost:8000/docs`.

---

## Node CRUD — `/api/v1/nodes`

### List Nodes

```
GET /nodes/{label}?skip=0&limit=50
```

| Parameter | In    | Type   | Required | Description                |
|-----------|-------|--------|----------|----------------------------|
| label     | path  | string | Yes      | Node type (see enum below) |
| skip      | query | int    | No       | Offset (default 0)         |
| limit     | query | int    | No       | Page size (default 50, max 200) |

**Response 200:**

```json
{
  "items": [
    { "id": "abc-123", "labels": ["POI"], "properties": { "name": "Louvre", "latitude": 48.8606 } }
  ],
  "total": 3,
  "skip": 0,
  "limit": 50
}
```

### Get Single Node

```
GET /nodes/{label}/{node_id}
```

**Response 200:** `{ "id": "...", "labels": ["POI"], "properties": { ... } }`

**Response 404:** Node not found.

### Create Node

```
POST /nodes/{label}
Content-Type: application/json
```

The request body depends on the node type. Required fields are validated by Pydantic models.

#### Create Models by Type

**User:**
```json
{ "email": "alice@example.com" }
```

**Profile:**
```json
{ "display_name": "Alice" }
```

**Lens:**
```json
{ "name": "art", "display_label": "Art & Architecture" }
```

**Trip:**
```json
{
  "name": "Paris Weekend",
  "start_date": "2026-06-01",
  "end_date": "2026-06-03",
  "cover_image_url": "",
  "status": "planning"
}
```

**ItineraryItem:**
```json
{
  "sort_order": 1,
  "scheduled_date": "2026-06-01",
  "start_time": "09:00",
  "duration_min": 120
}
```

**POI:**
```json
{
  "name": "Louvre Museum",
  "short_description": "World's largest art museum",
  "latitude": 48.8606,
  "longitude": 2.3376,
  "importance_tier": 1,
  "trigger_radius": 10,
  "typical_duration_min": 180,
  "kid_friendly": "yes"
}
```

**NarrativeBeat:**
```json
{
  "script_body": "Welcome to the Louvre...",
  "version": 1,
  "active_status": "active",
  "audio_url": "",
  "duration_sec": 90,
  "kid_friendly": "yes"
}
```

**Response 201:** Created node.

**Response 409:** Constraint violation (e.g., duplicate unique property).

**Response 422:** Validation error with field-level detail.

### Update Node

```
PUT /nodes/{label}/{node_id}
Content-Type: application/json
```

Partial update — only the properties you send are changed. Existing properties are preserved.

```json
{
  "properties": {
    "name": "Updated Name"
  }
}
```

**Response 200:** Updated node.

**Response 404:** Node not found.

### Delete Node

```
DELETE /nodes/{label}/{node_id}
```

Cascade delete — removes the node **and all its connected edges**.

**Response 200:** `{ "deleted": true, "id": "abc-123" }`

**Response 404:** Node not found.

---

## Edge CRUD — `/api/v1/edges`

### List Edges

```
GET /edges/{rel_type}?skip=0&limit=50
```

| Parameter | In    | Type   | Required | Description                     |
|-----------|-------|--------|----------|---------------------------------|
| rel_type  | path  | string | Yes      | Relationship type (see enum below) |
| skip      | query | int    | No       | Offset (default 0)              |
| limit     | query | int    | No       | Page size (default 50, max 200) |

**Response 200:**

```json
{
  "items": [
    {
      "id": "5:abc:123",
      "type": "ASSIGNED_TO",
      "source_id": "item-1",
      "target_id": "poi-1",
      "properties": {}
    }
  ],
  "total": 15,
  "skip": 0,
  "limit": 50
}
```

### Get Single Edge

```
GET /edges/{rel_type}/{edge_id}
```

**Response 200:** Single edge object.

**Response 404:** Edge not found.

### Create Edge

```
POST /edges/{rel_type}
Content-Type: application/json
```

```json
{
  "source": { "label": "ItineraryItem", "id": "item-1" },
  "target": { "label": "POI", "id": "poi-1" },
  "properties": {}
}
```

Both source and target nodes must exist. Labels are validated against the NodeLabel enum.

**Response 201:** Created edge.

**Response 404:** Source or target node not found.

**Response 422:** Invalid source or target label.

### Update Edge

```
PUT /edges/{rel_type}/{edge_id}
Content-Type: application/json
```

```json
{
  "properties": { "weight": 0.8 }
}
```

**Response 200:** Updated edge.

**Response 404:** Edge not found.

### Delete Edge

```
DELETE /edges/{rel_type}/{edge_id}
```

**Response 200:** `{ "deleted": true, "id": "5:abc:123" }`

**Response 404:** Edge not found.

---

## Schema Introspection — `/api/v1/schema`

These endpoints return static schema information derived from `src/schema/definitions.py`. They do not query the database.

### List All Node Type Schemas

```
GET /schema/nodes
```

**Response 200:**

```json
{
  "items": [
    {
      "label": "POI",
      "properties": [
        { "name": "name", "type": "str", "required": true, "default": null },
        { "name": "latitude", "type": "float", "required": true, "default": null },
        { "name": "importance_tier", "type": "int", "required": false, "default": 1 }
      ],
      "constraints": ["name UNIQUE"],
      "indexes": ["importance_tier"]
    }
  ],
  "total": 7
}
```

### Get Single Node Type Schema

```
GET /schema/nodes/{label}
```

Returns the schema for one node type.

### List All Relationship Type Schemas

```
GET /schema/relationships
```

**Response 200:**

```json
{
  "items": [
    {
      "type": "ASSIGNED_TO",
      "properties": []
    }
  ],
  "total": 11
}
```

### Get Single Relationship Type Schema

```
GET /schema/relationships/{rel_type}
```

Returns the schema for one relationship type.

---

## Trip Generation — `/api/v1/trips`

### Generate Trip

```
POST /trips/generate
Content-Type: application/json
```

Generates a trip by running the tour engine (`src/tour`) end to end: corpus load → route selection (with a density gate that refuses sparse areas) → per-POI beat selection → script assembly. Each stop is one engine route POI in walking order; ALL of its narrated beats persist (`beat_ids`, one `PLAYS_BEAT` edge per beat) with `beat_id` = the primary (first) beat. Lens precedence for selection bias: request `lenses` → the profile's `PREFERS_LENS` edges (sorted) → none (unbiased).

**Request body:**

```json
{
  "profile_id": "prof-123",
  "center_lat": 48.858,
  "center_lng": 2.294,
  "duration_min": 90,
  "round_trip": false,
  "lenses": ["hidden_history"],
  "start_date": "2026-06-01",
  "end_date": "2026-06-03",
  "start_time": "09:00",
  "trip_name": "My Paris Trip"
}
```

| Field             | Type   | Required | Default | Description                                     |
|-------------------|--------|----------|---------|-------------------------------------------------|
| profile_id        | string | Yes      | —       | Profile node whose PREFERS_LENS edges select beats |
| center_lat        | float  | Yes      | —       | Latitude of the tour start (-90 to 90)          |
| center_lng        | float  | Yes      | —       | Longitude of the tour start (-180 to 180)       |
| duration_min      | int    | No       | 60      | Tour budget in minutes (1–600); engine derives walk radius and stop count from it |
| round_trip        | bool   | No       | false   | Return to the start point (loops the route)     |
| lenses            | array  | No       | null    | Lens slugs to bias selection; overrides the profile's PREFERS_LENS |
| radius_m          | int    | No       | 3000    | INERT since M0b (accepted for back-compat only) |
| max_stops         | int    | No       | 10      | INERT since M0b (accepted for back-compat only) |
| kid_friendly_only | bool   | No       | false   | INERT since M0b (accepted for back-compat only) |
| start_date        | string | Yes      | —       | ISO date for the trip start                     |
| end_date          | string | Yes      | —       | ISO date for the trip end                       |
| start_time        | string | No       | "09:00" | Daily start time (HH:MM)                        |
| trip_name         | string | No       | null    | Optional name; auto-generated if omitted        |

**Response 201:**

```json
{
  "trip_id": "a1b2c3d4-...",
  "trip_name": "My Paris Trip",
  "profile_id": "prof-123",
  "total_stops": 5,
  "total_duration_min": 75,
  "anchor_count": 1,
  "flavour_count": 4,
  "lens_coverage": {"hidden_history": 4, "architecture": 2},
  "stops": [
    {
      "sort_order": 1,
      "poi_id": "poi-abc",
      "poi_name": "Louvre Museum",
      "lat": 48.8606,
      "lng": 2.3376,
      "beat_id": "beat-xyz",
      "beat_ids": ["beat-xyz", "beat-uvw"],
      "lens_name": "hidden_history",
      "lens_display": "Hidden History",
      "duration_min": 30,
      "importance_tier": 5,
      "start_time": "09:00",
      "dwell_seconds": 1800,
      "script_body": "…primary beat text…",
      "audio_url": null,
      "audio_duration_sec": null,
      "transit_polyline": null
    }
  ]
}
```

`lens_name`/`lens_display` are the DOMINANT lens of the stop's beats and are `null` when no beat is lensed. `script_body`/`audio_url`/`audio_duration_sec` describe the primary beat. `transit_polyline` is the encoded polyline (6-digit precision) of the walking leg INTO the stop — populated only when the local Valhalla routing engine is running (`make valhalla-up`); otherwise `null` (haversine fallback).

**Response 404:** Profile not found.

**Response 422:** The density gate refused the area (too sparse for a tour of the requested length), or no tourable POIs are reachable from the start.

### What Actually Runs — Implementation Trace (corrected 2026-07-24, after a hostile line-by-line re-audit)

This section names the exact functions and files behind "runs the tour engine
(`src/tour`) end to end" above. The prior 2026-07-23 version of this section
was re-checked claim-by-claim by independent reviewers instructed to find
flaws; several claims held up and several did not, including two that
reversed the original's own conclusions. Corrections are marked explicitly
below rather than silently folded in.

**1. Route is live and unconditionally mounted.** `generate_trip()`
(decorator at `src/api/routes/trips.py:429`, signature/body from `:430`) is
registered via `app.include_router(trips.router, prefix="/api/v1")` in
`src/api/app.py:177` (import at `src/api/app.py:17`), with **no** feature
flag — unlike the workbench CRUD routers, which are gated behind
`_workbench_api_enabled()` starting at `src/api/app.py:188`. This mount runs
the same way in dev, test, and the production Render deployment
(`Dockerfile:22` runs `uvicorn src.api.app:app`, the same `app` object).

**2. Corpus load — real Neo4j reads.** `generate_trip` calls
`load_paris_corpus(driver, city_slug=...)` (`src/tour/selection.py:655-666`),
which runs 5 real Cypher queries (`LOAD_PARIS_POIS_CYPHER`,
`LOAD_PARIS_BEATS_CYPHER`, `LOAD_AREA_TYPES_CYPHER`,
`LOAD_AREA_ADJACENCY_CYPHER`, `LOAD_LENS_HIERARCHY_CYPHER`) against the
injected driver.

**3. Route selection — real algorithm, not a stub.** `select_k_routes()`
(`src/tour/selection.py:2082-2145`) delegates to `select_route()`
(`:1323`, density gate at `:1372-1374`, Valhalla-or-haversine `leg_fn` at
`:1368`) for the first flavour. **Corrected:** it does not simply call
`select_route` "up to two more times." Each additional flavour slot (the
2nd and 3rd, for the default k=3) can itself cost up to 2 calls — one
initial attempt, plus one stricter zero-penalty retry if that candidate
overlaps an existing flavour too much (Jaccard ≥ 0.60, `:2138-2140`). So
reaching 3 flavours can take anywhere from 3 to 5 total `select_route`
calls, not a flat "two more." `select_route` is real
tourability/feasibility/greedy-selection logic, not a placeholder.

**4. Beat plan capping.** Per flavour, `build_poi_beat_plans_capped()`
(`src/tour/selection.py:1199-1262`) applies the "C9 governor v4" domination
cap and the `MAX_DWELL_AUDIO_SECONDS` ceiling — real content-shaping logic,
not a passthrough.

**5. Vignette beat selection.** `select_vignette_beats()`
(`src/tour/beat_select.py:685-736`) picks at most one voiceable `BeatRef`
per walk-past vignette POI using `active_status`/`script_body`/
lens-preference filtering (zero beats for a POI with none voiceable).
**Separately flagged, not a doc-accuracy correction — a code behavior worth
knowing:** this filter does not check the corpus's own
`vignette_eligible`/`requires_dwell` flags, so a beat the corpus explicitly
marks unfit for walk-past voicing can still be selected here.

**6. Script assembly — deterministic template, and deliberately so.**
`generate_trip` calls `generate()` (`src/tour/generation.py:310+`) once per
flavour; a separate call to the same function happens inside the different
`compose_trip` handler (`:771`) — not as a second call from `generate_trip`
itself. Neither call site passes a `glue_client` argument, so `generate()`'s
`client = glue_client or MockGlueClient()` (`:328`) always resolves to
`MockGlueClient` (class at `src/tour/glue_client.py:64-81`; the dict at
`:51-61` immediately above it is a separate, unrelated constant).
**Corrected — this is documented as deliberate design, not undocumented
tech debt:** `scripts/tour_build.py`'s own docstring states "Defaults to the
deterministic MockGlueClient so this works without ANTHROPIC_API_KEY. Pass
`--haiku` to switch on the real Haiku glue stitch." **Corrected — the
cold-open text is not simply unmodified `script_body`:** it always prepends
a fixed "Settle in." glue line, and in the common case (most tier-5 anchors,
which lack a `stop_orientation` beat) falls through to a synthesized-
template opener built from the route's area name and beat metadata, not
from any beat's `script_body`. Only the `GLUE_NAV` category actually routes
through `client.stitch()`; the other glue categories never touch the
mock/real distinction at all. **Most significant correction:** the
`/trips/generate` HTTP response does not return this stitched text at
all — `GeneratedStop.narration` stays `None` for this endpoint. The only
beat-derived text actually returned is one primary beat's raw `script_body`,
via `_primary_beat_audio`.

**7. Persistence.** `route_script_to_stops()` (`src/api/crud/trips.py:19-75`,
pure, no DB) builds the stop dicts, and `create_trip_with_stops()`
(`:78-147`) opens one `session.execute_write` transaction that creates the
`:Trip` node, one `:ItineraryItem` node per stop, and the
`HAS_STOP`/`ASSIGNED_TO`/`AT_POI`/`PLAYS_BEAT` edges. **Corrected:** the
standalone seeder `src/seed/trips.py:107-117` orchestrates MERGE-based
Cypher defined in module-level constants (via four helper functions it
calls) — it does not embed Cypher directly in its own body. It is **not**
reachable "only" via `make bootstrap`; roughly 19 Makefile targets
transitively reach it, and pytest test fixtures reach it through a separate
mechanism entirely. All of these paths remain localhost/test-gated; none is
the live production API path, so the original reassurance still holds even
though the "only" wording did not.

**8. Real narration composition happens on two separate endpoints, and both
are permission-gated.** The `/trips/generate` response above is corpus text
plus mock glue only, not composed narration. Actual Opus-or-ChatGPT-authored
prose is produced by `POST /trips/{trip_id}/compose` (`compose_trip`,
`src/api/routes/trips.py:648-659,778-783`) via `Depends(get_compose_client)`
(`src/api/dependencies.py:114-132`; defaults to `AnthropicComposeClient`, or
`OpenAIComposeClient` when `COMPOSE_PROVIDER=openai`). **Corrected — this is
not the only such endpoint:** `POST /trips/preview` also reaches a real
Anthropic call, through a completely separate path —
`Depends(get_premium_compose_executor)` (`src/api/dependencies.py:135-140`)
returns `AnthropicPremiumExecutor` (`src/tour/premium_tour.py:378`), whose
`execute_premium_plan` (`:419`) is called at
`src/api/routes/trips.py:1080`. `generate_trip` itself never reaches either
path. **New finding, not in the prior version:** both real-compose paths are
gated by `_require_paid_call_permission()`
(`src/tour/anthropic_client.py:69`, checked at `:84`), which requires the
env var `ONDOWAY_ENABLE_PAID_LLM_CALLS` (`:66`) — without it, a real call
raises rather than silently falling back to a stub. **Corrected —
`tests/conftest.py` is not the only offline-stub site:**
`tests/conftest.py:91,102,108,115` patches these classes for the general
test bar, but `tests/test_compose_provider.py` independently patches them
again for its own tests.

**Net effect for API consumers:** calling `/trips/generate` alone returns a
structurally complete, correctly-selected, correctly-persisted trip whose
only beat-derived text is one raw primary-beat `script_body` — not composed
narration. Getting composed narration requires a separate, explicitly
permission-gated call to `/trips/{trip_id}/compose` or `/trips/preview`.
This is deliberate, documented staged design (see item 6), not an
undocumented gap.

**9. The two compose paths do NOT fail the same way, and the difference is
not cosmetic.** `compose_script` (`src/tour/compose.py:1341`, reached from
`/trips/generate`) **splices and reverts** around an offending sentence — the
tour survives. `finalize_certification_composition` (`:890`, reached from
`/trips/preview`) *"never splices or reverts"* (`:904`) — **one** offending
sentence fails the **whole** tour, and the caller gets HTTP 200 with
`candidate_eligible: false`. The workbench Generate button hits the strict
one. Two further consequences are written up in
`Docs/bug-reports/2026-07-27-preview-failure-observability-salvage.md`: five
distinct causes still collapse into a single `generation_failed` code (§2),
and the certification path silently skips the forbidden-phrase scan, so the
`"forbidden"` counter at `src/api/routes/trips.py:793` reads 0 by
construction (§1, pinned by
`tests/test_compose_gate_forbidden_scan.py`).

**Resolved from the prior version's open questions:**
- Test coverage for the generate-then-compose chain **does exist**:
  `tests/test_trip_api.py`'s `TestComposeTripEndpoint` class chains a
  `fresh_trip` fixture (which calls `/trips/generate`) into
  `/trips/{trip_id}/compose` across at least 7 test methods.
- Whether the mobile app can show the pre-compose text directly:
  `mobile/lib/pages/trip_itinerary_page.dart` populates its stop list
  directly from the `/trips/generate` response, and composing is a
  separate, user-initiated action (a flavour picker), not an automatic
  follow-up call. This lead was not independently re-verified to the same
  3-reviewer standard as the rest of this section — treat it as a starting
  point for a dedicated mobile-subsystem review, not a settled fact.

---

## Graph Visualization — `/api/v1/graph`

### Get Full Graph

```
GET /graph
```

Returns all nodes and edges in a format ready for visualization. Used by the graph editor UI.

**Response 200:**

```json
{
  "nodes": [
    {
      "id": "poi-1",
      "label": "Louvre Museum",
      "group": "POI",
      "labels": ["POI"],
      "properties": {
        "name": "Louvre Museum",
        "location": { "lat": 48.8606, "lng": 2.3376 }
      }
    }
  ],
  "edges": [
    {
      "id": "5:abc:123",
      "from": "item-1",
      "to": "poi-1",
      "label": "ASSIGNED_TO",
      "properties": {}
    }
  ]
}
```

**Display label priority:** `display_name` > `name` > `display_label` > `email` > primary label.

**Spatial data:** Neo4j Point types are serialized to `{ "lat": float, "lng": float }`.

---

## Enums

### Node Labels

`User`, `Profile`, `Lens`, `Trip`, `ItineraryItem`, `POI`, `NarrativeBeat`

### Relationship Types

`HAS_PROFILE`, `IS_CAPTAIN_OF`, `IS_CREW_OF`, `PREFERS_LENS`, `HAS_STOP`, `ASSIGNED_TO`, `AT_POI`, `PLAYS_BEAT`, `HAS_BEAT`, `TAGGED_WITH`, `IS_PARENT_OF`

---

## Common Patterns

### Pagination

Node and edge list endpoints accept `skip` and `limit`. The response includes `total` for computing page counts.

```bash
# Page 2 of POIs (10 per page)
curl http://localhost:8000/api/v1/nodes/POI?skip=10&limit=10
```

### Partial Updates

PUT endpoints use partial updates. Only include the properties you want to change — everything else is preserved.

```bash
# Change just the name of a POI
curl -X PUT http://localhost:8000/api/v1/nodes/POI/poi-1 \
  -H "Content-Type: application/json" \
  -d '{"properties": {"name": "Updated Louvre"}}'
```

### Cascade Deletes

Deleting a node automatically deletes all its edges. Deleting an edge does not affect its nodes.

### CORS

All origins, methods, and headers are allowed. The API can be called from any frontend.
