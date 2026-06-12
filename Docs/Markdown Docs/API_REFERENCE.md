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
