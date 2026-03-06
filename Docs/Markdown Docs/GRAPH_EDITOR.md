# Graph Editor — User Guide

Interactive canvas-based editor for viewing and modifying the Travlr knowledge graph.

## Getting Started

```bash
# 1. Bootstrap (first time only)
make all                # Creates venv, installs deps, starts Neo4j, seeds data

# 2. Start the API server
make api                # FastAPI at http://localhost:8000

# 3. Open the editor
open http://localhost:8000/editor
```

The editor loads the full graph from `/api/v1/graph` on startup. The connection badge in the header turns **green** ("connected") when the API is reachable. If it turns **red**, check that the API is running and Neo4j is up (`make db-status`).

## Interface Overview

```
┌──────────────────────────────────────────────────────┐
│  Travlr Graph Editor         [connected] 12 nodes 15 edges │
├──────────────────────────────────────────────────────┤
│  [+ Node] [+ Edge] [Refresh]                         │
│                                                      │
│                                                      │
│           ◉ User ─── ◉ Profile                ┌─────┤
│            │                                  │ Side │
│           ◉ Trip ── ◉ ItineraryItem           │Panel │
│            │          │                       │      │
│           ◉ Lens     ◉ POI ── ◉ Beat          │Forms │
│                                               │      │
│                                               └─────┤
│  [User] [Profile] [Trip] [POI] [Beat] [Lens] [Item]  │
└──────────────────────────────────────────────────────┘
   Header          Canvas                      Panel    Legend
```

### Header
- **Connection badge**: green = connected, red = failed
- **Stats**: live count of nodes and edges (updates after every operation)

### Floating Toolbar (top-left)
- **+ Node**: open the create-node form
- **+ Edge**: open the create-edge form
- **Refresh**: reload the full graph from the API

### Canvas
- Force-directed graph visualization on an HTML5 canvas
- Nodes are color-coded circles; edges are arrows with labels
- Physics simulation runs for ~5 seconds, then settles

### Legend (bottom)
- Color key for all 7 node types

### Side Panel (right)
- Slides in when creating or editing a node/edge
- Contains dynamic forms generated from the API schema
- Close with the **X** button or press **Escape**

## Node Types & Colors

| Type           | Color      | Size  |
|----------------|------------|-------|
| User           | Blue       | 18 px |
| Profile        | Light blue | 16 px |
| Trip           | Sky blue   | 16 px |
| POI            | Green      | 20 px |
| NarrativeBeat  | Light green| 14 px |
| Lens           | Lime green | 14 px |
| ItineraryItem  | Amber      | 12 px |

## Relationship Types

11 edge types connect nodes in the graph:

| Type            | From → To                     |
|-----------------|-------------------------------|
| HAS_PROFILE     | User → Profile                |
| IS_CAPTAIN_OF   | User → Trip                   |
| IS_CREW_OF      | User → Trip                   |
| PREFERS_LENS    | Profile → Lens                |
| HAS_STOP        | Trip → ItineraryItem          |
| ASSIGNED_TO     | ItineraryItem → POI           |
| AT_POI          | NarrativeBeat → POI           |
| PLAYS_BEAT      | POI → NarrativeBeat           |
| HAS_BEAT        | Lens → NarrativeBeat          |
| TAGGED_WITH     | NarrativeBeat → Lens          |
| IS_PARENT_OF    | Lens → Lens                   |

## Mouse & Keyboard Controls

### Mouse
| Action                | Effect                              |
|-----------------------|-------------------------------------|
| Hover over node       | Tooltip shows type, ID, properties  |
| Click node            | Select — opens edit panel           |
| Drag node             | Reposition on canvas                |
| Click edge            | Select — opens edit panel           |
| Click empty space     | Deselect / close panel              |

### Keyboard
| Key              | Effect                                   |
|------------------|------------------------------------------|
| Escape           | Close the side panel                     |
| Delete/Backspace | Delete selected node or edge (when not typing in a form field) |

## Creating a Node

1. Click **+ Node** in the toolbar
2. Select a node type from the dropdown (e.g., "POI")
3. The form populates with fields from the schema — required fields are marked with a red **\***
4. Fill in the properties and click **Save**
5. The new node appears on the canvas

### Example: Creating a POI

| Field                | Required | Default |
|----------------------|----------|---------|
| name                 | Yes      | —       |
| short_description    | No       | ""      |
| latitude             | Yes      | —       |
| longitude            | Yes      | —       |
| importance_tier      | No       | 1       |
| trigger_radius       | No       | 10      |
| typical_duration_min | No       | 30      |
| kid_friendly         | No       | "yes"   |

## Creating an Edge

1. Click **+ Edge** in the toolbar
2. Select a relationship type from the dropdown (e.g., "ASSIGNED_TO")
3. Click the **Source** button — it turns orange; cursor changes to crosshair
4. Click a node on the canvas to pick it as the source — button turns green
5. The **Target** button activates automatically — click a node for the target
6. Fill in any edge properties (if the relationship type has them)
7. Click **Save**

## Editing

1. Click any node or edge on the canvas
2. The side panel opens with the entity's current properties
3. Read-only fields (ID, label/type, created date) appear at the top
4. Modify editable properties in the form
5. Click **Save** to apply changes

## Deleting

1. Click a node or edge to select it
2. Either:
   - Click the **Delete** button in the side panel, or
   - Press **Delete** / **Backspace** (while not typing in a form field)
3. Confirm in the dialog

Deleting a node also deletes all its connected edges.

## Working with Test Data

After running `make setup`, the graph is populated with seed data:

- **1 User** (test traveler) with **1 Profile**
- **12 Lenses** (Art, History, Food, etc.) with DAG hierarchy
- **3 POIs** (Paris locations: Louvre, Notre-Dame, Shakespeare & Co.)
- **4 Narrative beats** (audio tour scripts)
- **1 Trip** with **3 itinerary items**
- **11 relationship types** connecting them all

This gives you a representative graph to explore. You can add, edit, and delete freely — run `make setup` again to reset to the seed state (it's idempotent).

## Troubleshooting

| Symptom                        | Fix                                   |
|--------------------------------|---------------------------------------|
| Badge shows "connection failed"| Run `make api` to start the server    |
| No nodes on canvas             | Run `make setup` to seed data         |
| Nodes fly off screen           | Click Refresh — physics will re-settle|
| Form fields missing            | Schema endpoint may be down — check `curl http://localhost:8000/api/v1/schema/nodes` |
