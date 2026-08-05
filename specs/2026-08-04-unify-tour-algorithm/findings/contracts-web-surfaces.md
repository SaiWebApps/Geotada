> # ⛔ OWNER RULINGS OVERRIDE THIS DOCUMENT — READ FIRST
>
> This contract was written BEFORE the owner answered the plan's open questions on
> 2026-08-04. Where this document and the rulings below disagree, **THE RULINGS WIN.**
> The authoritative copy of each is in `../state.json` under `decisions`, keyed
> `OWNER_RULING_1..5`. Do not follow a superseded instruction because it is more
> detailed — detail is not authority.
>
> 1. **Planning shows PLACES ONLY.** During route planning, on BOTH surfaces, an option
>    shows POI names, order, walking time and ETA — and NO descriptive text whatsoever.
>    No LLM glue, no vignette prose, no teaser text, no narration. All words arrive only
>    at script generation, after a route is picked. Planning therefore makes NO paid call.
> 2. **The workbench never asks a human to log in.** Phase 2 gives it a background
>    identity it uses silently. The Phase-1 no-login route is a stopgap for that, and the
>    operator's trigger is a **"Select / Build this tour"** button on each of the three
>    option cards.
> 3. **`frontend/tour-preview.html` is DELETED**, not re-pointed. Step 13 is a deletion
>    proof.
> 4. **The build-version stamp (`resolve_build_identity`) STAYS UNCHANGED.** It is what
>    makes a tour traceable to the code that built it. The fix belongs in the test setup,
>    which must declare itself a local build via the EXISTING
>    `ONDOWAY_ALLOW_DIRTY_LOCAL_BUILD=1` opt-in, exactly as `scripts/workbench.sh` does.
>    Do not bypass, weaken or delete the check.
> 5. **No stop limits. Period.** All SEVEN ceilings go, including
>    `quality_rubric.MAX_COMPOSED_STOPS`. Consequence accepted by the owner: the C3 check
>    stops flagging long tours, and duration alone bounds tour length everywhere.
>
> Also pinned: the new route is **`POST /trips/preview/author`** (never
> `/trips/preview/compose` — that name is already taken by the authenticated saved-trip
> route). Its option selector is `route_id`, a 12-hex plan fingerprint; a stale
> fingerprint is refused `409 plan_changed` rather than authoring an unseen tour.
>
> **DEAD IN THIS FILE:** (a) any option-card design that shows descriptive text — cards are told apart by places, order and walking time alone; (b) every mention of `/trips/preview/compose` — the route is `/trips/preview/author`; (c) the step-13 re-point fork — deletion is the ruling, use the deletion contract only; (d) marking `buildDegradationPanel` UNCHANGED — step 12 MUST adopt the six-line fix from `contracts-block1-and-options.md` so the operator-facing cause is visible on screen, or AC-21 fails.

---

# Implementation contract — STEP 12 and STEP 13 (the two browser surfaces)

Author: contract agent, 2026-08-04. Verified read-only against the working tree at
`a7df218c`. Nothing in this document was executed; no source file was edited.

This is a CONTRACT. Every function name, every URL, every request field, every DOM id and
every user-visible string below is binding. The implementer chooses nothing.

---

## 0. Node-id existence check (asked for explicitly)

Both proving-test node ids were grepped across the whole repository (excluding this spec
folder's own `state.json` and `run-context.md`, which merely name them):

| Ledger step | Node id | Exists today? |
| --- | --- | --- |
| 12 | `tests/test_workbench_preview_wiring.py::test_generate_tour_options_is_a_separate_call_from_authoring` | **NO** — zero hits anywhere in the tree |
| 13 | `tests/test_workbench_preview_wiring.py::test_the_standalone_preview_page_makes_the_same_two_calls` | **NO** — zero hits anywhere in the tree |

Neither is a pre-existing pass, so neither step is a regression pin. Both must be written
as part of their step. `tests/test_workbench_preview_wiring.py` exists (396 lines) and both
tests are appended to it.

---

## 1. The network contract (both surfaces)

### 1.1 CALL ONE — the PLAN call, issued when the operator presses generate

```
POST {API_BASE}/trips/preview
Content-Type: application/json
```

Request body, exactly these fields and no others (this is the body `generateTourPreview`
sends today at `frontend/review.html:3264-3275`, unchanged):

```json
{
  "center_lat": 48.8566,
  "center_lng": 2.3522,
  "duration_min": 60,
  "lenses": ["historic_arch"],
  "round_trip": false,
  "end_lat": null,
  "end_lng": null,
  "city_slug": "paris"
}
```

`lenses` is `null` when the lens field is empty. `end_lat`/`end_lng` are `null` when the
destination field is empty.

Response fields consumed by the page (200):

| Field | Type | Used for |
| --- | --- | --- |
| `options` | array of 3 `RouteOption` | the three cards |
| `options[].route_id` | string | the identifier echoed on CALL TWO |
| `options[].stops[]` | array | card contents + the map sketch |
| `options[].stops[].name` | string | the place names on the card |
| `options[].stops[].lat` / `.lng` | number | the map sketch |
| `options[].stops[].minutes` | int | dwell minutes (walking = eta − dwell) |
| `options[].stops[].band` | `"dwell"` \| `"vignette"` | stop vs. walk-past counting, pin style |
| `options[].eta_seconds` | int | total minutes on the card |
| `spine_area` | string \| null | the header line above the cards |
| `degradations` | array | the degradation panel (see §5) |
| `tourability` | object \| null | not read on the option screen (read by `renderTourStops` after authoring) |

`RouteOption`'s field names are fixed by `src/tour/contract.py:564-591`; the stop field
names by `src/tour/contract.py:545-561` (note `name`, NOT `poi_name`, and `minutes`, NOT
`duration_min`).

Non-200: unchanged from today — `{"detail": {...}}` with an `alternatives` array renders
through `renderTourRefusal` (`frontend/review.html:3298`); anything else goes to
`showError` (`frontend/review.html:1214`).

### 1.2 CALL TWO — the AUTHOR call, issued only when the operator clicks a card

```
POST {API_BASE}/trips/preview/compose
Content-Type: application/json
```

Request body — byte-for-byte the PLAN body plus one field:

```json
{
  "center_lat": 48.8566,
  "center_lng": 2.3522,
  "duration_min": 60,
  "lenses": ["historic_arch"],
  "round_trip": false,
  "end_lat": null,
  "end_lng": null,
  "city_slug": "paris",
  "route_id": "preview-opt1"
}
```

Response: the existing `TripPreviewResponse` shape (`src/api/models/trips.py:320-370`) —
`stops`, `spine_area`, `total_audio_min`, `candidate_eligible`, `basic_tour`,
`narration_kind`, `compose_status`, `provider`, `quality`, `narration_quality`,
`tourability`, `lens_coverage_note`, `degradations`. It is handed straight to
`renderTourStops`, which is why that renderer needs no change.

### 1.3 THE INVARIANT (AC-5)

Pressing generate issues **exactly one** network POST. No request to
`/trips/preview/compose`, `/audio/preview` or any authoring route may be issued until the
operator clicks an option card. Drawing an option on the map issues no request at all.

### 1.4 Cross-step lock (see also §9, BLOCKING AMBIGUITY 1)

The URL `/trips/preview/compose` and the "plan body + `route_id`" request shape are what
STEP 11 ("A sibling anonymous route authors exactly the option the operator chose",
`src/api/routes/trips.py`, `src/api/models/trips.py`) must implement. Nothing is persisted
in Phase 1, so the endpoint receives the original inputs and the chosen `route_id` and
rebuilds that option before authoring it. If STEP 11 lands a different URL or field name,
this contract's URL string and the `route_id` key change with it and nothing else does.

---

## 2. STEP 12 — `frontend/review.html`

### 2.1 Page state (module-level `let` declarations)

Immediately after `let tourStops = [];` (`frontend/review.html:1142`), add:

```js
  // The 3 PLAN options currently on screen (RouteOption wire objects). Empty
  // whenever the page is showing stops, a refusal, or nothing.
  let tourOptions = [];
  // The exact body of the last PLAN request, replayed verbatim on the AUTHOR
  // call so the endpoint rebuilds the option the operator is looking at.
  let lastTourPlanBody = null;
  // The minutes the operator asked for, needed by renderTourStops's thin-tour note.
  let lastTourRequestedMinutes = 60;
```

`lastTourPreviewRequest` (`frontend/review.html:3046`) stays exactly as it is — it feeds
the degradation panel's "Copy report for Claude".

### 2.2 The delegated click dispatcher

`detailBody.addEventListener('click', ...)` at `frontend/review.html:1147-1154`. Insert two
branches **after** the existing `#tourGenerateBtn` branch (line 1148) and before the
`#tourClearBtn` branch (line 1149):

```js
    const pick = e.target.closest('.tour-option-pick');
    if (pick) { authorTourOption(parseInt(pick.dataset.tourOption, 10)); return; }
    const showOn = e.target.closest('.tour-option-map');
    if (showOn) { drawTourRoute(tourOptionMapStops(tourOptions[parseInt(showOn.dataset.tourOption, 10)])); return; }
```

The `#tourGenerateBtn` branch is not touched, and nothing is inserted before it —
`tests/test_workbench_matches_the_app.py:1812-1828` fails if any statement appears between
the branch's `{` and `generateTourPreview()`.

### 2.3 `generateTourPreview()` — REPLACED IN PLACE

Currently `async function generateTourPreview()` at `frontend/review.html:3219-3294`. Same
name (three tests locate it by that exact declaration), same signature `()`, returns a
Promise resolving to `undefined`. Everything from the start of the function through the
input validation and `genBtn.disabled = true` line is unchanged; the body from
`stopsEl.innerHTML = ''` (`:3252`) onward is replaced with:

```js
    genBtn.disabled = true; genBtn.textContent = '⏳ Finding routes…';
    stopsEl.innerHTML = ''; tourStops = []; tourOptions = []; drawTourRoute([]);
    lastTourRequestedMinutes = duration;
    try {
      lastTourPlanBody = {
        center_lat: lat, center_lng: lng, duration_min: duration,
        lenses: lenses.length ? lenses : null, round_trip: roundTrip,
        end_lat: endLat, end_lng: endLng, city_slug: cityName || 'paris',
      };
      lastTourPreviewRequest = lastTourPlanBody;
      const resp = await fetch(`${API_BASE}/trips/preview`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          center_lat: lat, center_lng: lng, duration_min: duration,
          lenses: lenses.length ? lenses : null, round_trip: roundTrip,
          end_lat: endLat, end_lng: endLng,
          city_slug: cityName || 'paris',
        }),
      });
      if (!resp.ok) {
        let detail = null;
        try { detail = (await resp.json()).detail; } catch (_) { /* keep null */ }
        if (detail && typeof detail === 'object' && Array.isArray(detail.alternatives)) {
          renderTourRefusal(detail);
        } else {
          showError(typeof detail === 'string' ? detail : `Could not generate a tour (${resp.status}).`);
        }
        return;
      }
      renderTourOptions(await resp.json(), duration);
    } catch (err) {
      showError('Tour options failed: ' + err.message);
    } finally {
      genBtn.disabled = false; genBtn.textContent = 'Generate tour options';
    }
```

The inline `city_slug` comment block at `:3268-3273` is kept verbatim inside the new fetch
body. The "NO spend confirmation here, ever" comment at `:3245-3250` is kept verbatim above
the `genBtn.disabled` line. This function must contain **no** `/audio/`, no
`/trips/preview/compose`, and no `renderTourStops(`.

### 2.4 `tourOptionMapStops(option)` — NEW

Placement: immediately after `drawTourRoute` (which ends at `frontend/review.html:3400`),
before `function _providerLabel(p)` (`:3406`).

Parameters: `option` — one `RouteOption` wire object, or `undefined`.
Returns: an array of objects in the shape `drawTourRoute` already consumes
(`{lat, lng, band, sort_order, poi_name}`), or `[]`.

```js
  // Adapt a PLAN option's stops to the shape drawTourRoute already draws, so the
  // map sketch is ONE implementation for options and for authored stops.
  function tourOptionMapStops(option) {
    const stops = (option && option.stops) || [];
    return stops.map((s, i) => ({
      lat: s.lat, lng: s.lng,
      band: s.band === 'vignette' ? 'vignette' : 'dwell',
      sort_order: i + 1,
      poi_name: s.name || '',
    }));
  }
```

### 2.5 `renderTourOptions(data, requestedMinutes)` — NEW

Placement: immediately after the closing brace of `renderTourStops`
(`frontend/review.html:3721`), before the `// Step B.7:` comment that introduces
`submitTourFeedback` (`:3723`).

Parameters: `data` — the parsed PLAN response; `requestedMinutes` — integer.
Returns: `undefined`. Issues no network request.

```js
  // The PLAN screen. Three routes over the same start, end, lens and timing —
  // they differ in how many places they stop at and how much of the time is
  // spent walking. NOTHING has been written or voiced yet; the AUTHOR call is
  // made only when the operator picks one.
  function renderTourOptions(data, requestedMinutes) {
    const stopsEl = document.getElementById('tourStops');
    if (!stopsEl) return;
    tourStops = [];
    tourOptions = Array.isArray(data && data.options) ? data.options : [];
    drawTourRoute([]);
    stopsEl.innerHTML = '';

    const head = document.createElement('div');
    head.className = 'tour-options-head';
    head.style.cssText = 'color:var(--muted,#888);font-size:0.85rem;margin:8px 0;';
    head.textContent = `${tourOptions.length} ways to walk this · spine: ${(data && data.spine_area) || '—'}`;
    stopsEl.appendChild(head);

    const note = document.createElement('div');
    note.className = 'tour-options-note';
    note.style.cssText = 'color:var(--text-muted);font-size:0.8rem;margin:0 0 10px;';
    note.textContent = 'Nothing has been written or recorded yet. Pick one and the narration and audio are made for that route.';
    stopsEl.appendChild(note);

    // Anything that went wrong while PLANNING is shown here, before the operator
    // can choose — the same panel the authored view uses.
    const degradePanel = buildDegradationPanel(data);
    if (degradePanel) stopsEl.appendChild(degradePanel);

    if (!tourOptions.length) {
      const empty = document.createElement('div');
      empty.className = 'tour-options-empty db-beat-card';
      empty.textContent = 'No route was found from here for this timing.';
      stopsEl.appendChild(empty);
      return;
    }

    tourOptions.forEach((opt, i) => {
      const dwell = (opt.stops || []).filter(s => s.band !== 'vignette');
      const walkPast = (opt.stops || []).length - dwell.length;
      const dwellMin = dwell.reduce((sum, s) => sum + (s.minutes || 0), 0);
      const totalMin = Math.round((opt.eta_seconds || 0) / 60);
      const walkMin = Math.max(0, totalMin - dwellMin);
      const names = dwell.map(s => s.name || '').filter(Boolean);
      const shown = names.slice(0, 4).join(' · ') + (names.length > 4 ? ` · +${names.length - 4} more` : '');

      const card = document.createElement('div');
      card.className = 'tour-option-card db-beat-card';
      card.dataset.tourOption = String(i);

      const title = document.createElement('h4');
      title.textContent = `Option ${i + 1} · ${dwell.length} stops · ${totalMin} min total`;
      card.appendChild(title);

      const meta = document.createElement('div');
      meta.className = 'meta';
      meta.textContent = `About ${walkMin} min walking and ${dwellMin} min standing still`
        + (walkPast ? ` · ${walkPast} walk-past sight${walkPast === 1 ? '' : 's'}` : '');
      card.appendChild(meta);

      const places = document.createElement('div');
      places.className = 'tour-option-places script-preview';
      places.textContent = shown;
      card.appendChild(places);

      const row = document.createElement('div');
      row.className = 'tts-row';
      const pick = document.createElement('button');
      pick.className = 'btn btn-primary tour-option-pick';
      pick.dataset.tourOption = String(i);
      pick.title = 'Write and voice this route';
      pick.textContent = 'Use this one — write the tour';
      row.appendChild(pick);
      const showOn = document.createElement('button');
      showOn.className = 'btn btn-outline tour-option-map';
      showOn.dataset.tourOption = String(i);
      showOn.title = 'Draw this route on the map — nothing is generated';
      showOn.textContent = 'Show on map';
      row.appendChild(showOn);
      card.appendChild(row);

      stopsEl.appendChild(card);
    });
  }
```

### 2.6 `authorTourOption(index)` — NEW

Placement: immediately after `renderTourOptions`, before the `// Step B.7:` comment.

Parameters: `index` — integer position of the clicked card.
Returns: a Promise resolving to `undefined`. Issues exactly one POST.

```js
  // The AUTHOR call. Exactly the option the operator clicked, identified by its
  // route_id — the endpoint never re-plans and never picks for us.
  async function authorTourOption(index) {
    const stopsEl = document.getElementById('tourStops');
    const opt = tourOptions[index];
    if (!stopsEl || !opt || !lastTourPlanBody) return;
    const buttons = stopsEl.querySelectorAll('.tour-option-pick, .tour-option-map');
    buttons.forEach(b => { b.disabled = true; });
    const picked = stopsEl.querySelector(`.tour-option-pick[data-tour-option="${index}"]`);
    if (picked) picked.textContent = '⏳ Writing the tour…';
    try {
      const resp = await fetch(`${API_BASE}/trips/preview/compose`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.assign({}, lastTourPlanBody, { route_id: opt.route_id })),
      });
      if (!resp.ok) {
        let detail = null;
        try { detail = (await resp.json()).detail; } catch (_) { /* keep null */ }
        showError(typeof detail === 'string' ? detail : `Could not write this tour (${resp.status}).`);
        return;
      }
      tourOptions = [];
      renderTourStops(await resp.json(), lastTourRequestedMinutes);
    } catch (err) {
      showError('Writing the tour failed: ' + err.message);
    } finally {
      buttons.forEach(b => { b.disabled = false; });
      if (picked) picked.textContent = 'Use this one — write the tour';
    }
  }
```

Note the `Object.assign` here is on the REQUEST, never on a response — the ban in
`tests/test_workbench_matches_the_app.py:1879-1887` is on the argument handed to
`renderTourStops`, which stays the bare `await resp.json()`.

### 2.7 DOM added, and the exact strings the operator reads

All of it is created inside `#tourStops` (`frontend/review.html:2184`) by
`renderTourOptions`; no static markup changes except the button label in §2.8 and the CSS
in §2.9.

| Element | Tag / class | Position | Exact text |
| --- | --- | --- | --- |
| header | `div.tour-options-head` | first child of `#tourStops` | `3 ways to walk this · spine: Île de la Cité` |
| explainer | `div.tour-options-note` | after the header | `Nothing has been written or recorded yet. Pick one and the narration and audio are made for that route.` |
| degradation panel | existing `div.tour-degradations` | after the explainer | server-authored, see §5 |
| card | `div.tour-option-card.db-beat-card`, `data-tour-option="0..2"` | one per option, after the panel | — |
| card title | `h4` | first child of the card | `Option 1 · 5 stops · 62 min total` |
| card meta | `div.meta` | after the title | `About 21 min walking and 41 min standing still · 2 walk-past sights` |
| card places | `div.tour-option-places.script-preview` | after the meta | `Notre-Dame · Sainte-Chapelle · Conciergerie · Pont Neuf · +2 more` |
| pick button | `button.btn.btn-primary.tour-option-pick`, `data-tour-option` | in a `div.tts-row` at the card foot | `Use this one — write the tour` |
| map button | `button.btn.btn-outline.tour-option-map`, `data-tour-option` | beside the pick button | `Show on map` |
| empty state | `div.tour-options-empty.db-beat-card` | replaces the cards when `options` is empty | `No route was found from here for this timing.` |

The three cards carry the same lens, start, end and timing, so what tells them apart is the
stop count and the walking/standing split — both are on the title and meta lines in plain
words, and the place names below let an operator recognise the difference at a glance. The
` · N walk-past sights` clause is omitted entirely when the option has none.

### 2.8 The generate button label

`frontend/review.html:2182` currently reads
`<button class="btn btn-primary" id="tourGenerateBtn">Generate preview</button>`.
It becomes `<button class="btn btn-primary" id="tourGenerateBtn">Generate tour options</button>`.
The id is unchanged (every browser test clicks `#tourGenerateBtn`). The in-flight label in
§2.3 is `⏳ Finding routes…`; the restored label is `Generate tour options`.

### 2.9 CSS

Insert after `.tour-stop--vignette .meta { font-style: italic; }`
(`frontend/review.html:198`):

```css
  /* PLAN screen: the three route options an operator chooses between before
     anything is written or voiced. */
  .tour-option-card { border-left: 3px solid var(--accent); }
  .tour-option-card h4 { margin: 0 0 4px; }
  .tour-option-card .tour-option-places { margin: 6px 0 10px; }
```

---

## 3. Reuse — named, with file:line, and how the new flow calls each

| Helper | Where it lives today | How the new flow uses it | Changed? |
| --- | --- | --- | --- |
| `renderTourRefusal(detail)` | `frontend/review.html:3298-3326` | called unchanged from `generateTourPreview`'s non-OK branch, exactly as today; `tourOptions` is emptied by the caller before the fetch so the refusal renderer needs no new knowledge | **UNCHANGED** |
| `drawTourRoute(stops)` | `frontend/review.html:3370-3400` | called with `[]` to clear when options render; called with `tourOptionMapStops(option)` on "Show on map"; called by `renderTourStops` after authoring, as today | **UNCHANGED** |
| `buildDegradationPanel(data)` | `frontend/review.html:3472-3545` | called by `renderTourOptions(data)` on the PLAN response and by `renderTourStops(data)` on the AUTHOR response; it reads only `data.degradations`, so both work | **UNCHANGED** |
| `renderTourStops(data, requestedMinutes)` | `frontend/review.html:3572-3721` | now called from `authorTourOption` with the AUTHOR response, which is the same `TripPreviewResponse` shape it consumes today | **UNCHANGED** |
| `ttsPlayTourStop(i)` / `ttsPlay({...})` | `frontend/review.html:3769-3778` / `3122-3200` | untouched; the per-stop Listen buttons are rendered by `renderTourStops` as today and dispatched by the same delegated listener branch (`:1152-1153`) | **UNCHANGED** |
| `submitTourFeedback(verdict)` | `frontend/review.html:3725-3767` | untouched; it requires `tourStops` to be non-empty, which is true only after authoring, which is correct | **UNCHANGED** |
| `showError` / `showSuccess` / `escHtml` | `frontend/review.html:1214` / `1221` / `1625` | unchanged | **UNCHANGED** |

**Nothing needs to be changed to be reused.** Two adaptations sit outside the reused
helpers on purpose: `tourOptionMapStops` (§2.4) converts a PLAN option to the shape
`drawTourRoute` already draws, rather than teaching `drawTourRoute` a second shape; and the
option cards are built with `createElement` + `textContent`, matching the injection-safe
idiom already used by `buildDegradationPanel` and documented at `frontend/review.html:3305-3312`.

---

## 4. The map on the PLAN screen

`renderTourOptions` clears the map (`drawTourRoute([])`). A route is drawn only when the
operator presses "Show on map" on a card, and that draws that option's stops through the
existing renderer with **zero** network traffic. `window.__lastTourRoute` (set inside
`drawTourRoute`, `frontend/review.html:3381`) therefore reports `{stops: 0, line: false}`
immediately after options render, and the clicked option's pin count after "Show on map" —
which is what the browser tests assert against.

---

## 5. The degradation banner (AC-21)

**Where:** inside `renderTourOptions`, appended to `#tourStops` after the explainer line and
**before the first option card** — so it is on screen before the operator can click
anything. It is the existing panel: `buildDegradationPanel(data)`
(`frontend/review.html:3472`), called with the PLAN response.

**What renders:** the panel's own title (`This tour was built with 1 problem`), then per row
the server's plain-English `human` string in the large, light line
(`frontend/review.html:3531-3534`), then the quieter technical line, then the existing
"Copy report for Claude" button.

**The operator-facing text**, which STEP 14 must emit as the routing degradation's `human`
field (`Degradation.human`, `src/tour/degradations.py:44-57` — "plain English, no
identifiers"):

> Walking times on this route are estimates, not measured street routing — the
> walking-directions service did not answer, so distances were worked out in straight lines
> and the real walk may be longer.

The workbench renders that string verbatim and adds nothing to it. There is no client-side
copy of the sentence and no client-side detection of the condition: the page shows what the
server reports, which is the property `tests/test_workbench_matches_the_app.py:1836` exists
to protect.

---

## 6. The stale stubs in `tests/test_workbench_ui.py`

**17 sites**, not ten. Every one of them fulfils `**/trips/preview` with a payload whose
top level carries `stops` — the AUTHOR shape. Under the split, that payload is what
`/trips/preview/compose` returns, and a PLAN payload has to be added alongside it.

Two more things break at every site and must be fixed with them:

1. `page.expect_response(lambda r: "/trips/preview" in r.url)` now also matches the compose
   URL. Every such predicate that means the PLAN call becomes
   `lambda r: r.url.endswith("/trips/preview")`.
2. A test that asserts on rendered `.tour-stop` cards must click an option card first.

### 6.1 New module-level helpers

Insert immediately after `_stubbed_audio_preview`'s `finally` block ends
(`tests/test_workbench_ui.py:465`) and before `def _declared_audio_registry()` (`:468`):

```python
def _route_option(stops, *, route_id, eta_seconds=None):
    """One PLAN option in the RouteOption wire shape (src/tour/contract.py:564-591).

    ``stops`` are the TripPreviewStop-shaped dicts every stub in this file already
    writes, so a stub author still writes ONE list. band="leg" cards are narration
    heard while walking, not places, and have no counterpart on a RouteOption — they
    exist only in the AUTHOR response, so they are dropped here.
    """
    places = [s for s in stops if s.get("band") != "leg"]
    dwell_minutes = sum(int(s.get("minutes", 0)) for s in places if s.get("band") != "vignette")
    return {
        "route_id": route_id,
        "stops": [
            {
                "poi_id": s.get("poi_id", f"poi-{i}"),
                "name": s["poi_name"],
                "lat": s.get("lat", 48.8566),
                "lng": s.get("lng", 2.3522),
                "lens": None,
                "visit_or_walk_past": "walk_past" if s.get("band") == "vignette" else "visit",
                "minutes": int(s.get("minutes", 0)),
                "band": "vignette" if s.get("band") == "vignette" else "dwell",
                "spotlight": s.get("spotlight", 0.0),
            }
            for i, s in enumerate(places)
        ],
        "stop_audio": {},
        "route_polyline": None,
        "eta_seconds": eta_seconds if eta_seconds is not None else (dwell_minutes + 18) * 60,
        "why_this_works": None,
        "lens_summary": {},
        "flow_score": 0.0,
        "backtrack_ratio": 0.0,
        "degraded": False,
        "profiles": [],
        "offline_package": None,
        "lens_coverage_note": None,
    }


def _plan_payload(stops, *, spine_area="Île de la Cité", degradations=None, options=None):
    """The PLAN response: three routes over the same inputs that differ in how many
    places they stop at and how much of the time is walking."""
    if options is None:
        shorter = [s for s in stops if s.get("band") != "leg"][:-1] or stops
        options = [
            _route_option(stops, route_id="preview-opt1"),
            _route_option(shorter, route_id="preview-opt2"),
            _route_option(stops, route_id="preview-opt3", eta_seconds=None),
        ]
    return {
        "spine_area": spine_area,
        "options": options,
        "tourability": None,
        "lens_coverage_note": None,
        "degradations": degradations or [],
    }


def _route_two_step(page, *, plan, compose):
    """Answer BOTH calls of the two-step flow. The plan pattern cannot match the
    compose URL (a Playwright glob is a full match), so registration order is
    irrelevant."""
    page.route(
        "**/trips/preview",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(plan)
        ),
    )
    page.route(
        "**/trips/preview/compose",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(compose)
        ),
    )


def _unroute_two_step(page):
    page.unroute("**/trips/preview/compose")
    page.unroute("**/trips/preview")


def _generate_options(page):
    """Press generate and wait for the PLAN response only. Renders 3 cards, spends
    nothing, and asks for no audio."""
    with page.expect_response(lambda r: r.url.endswith("/trips/preview")) as ri:
        page.locator("#tourGenerateBtn").click()
    page.locator("#tourStops .tour-option-card").first.wait_for(state="visible", timeout=15000)
    return ri.value


def _pick_option(page, index=0):
    """Click one option card and wait for the AUTHOR response."""
    with page.expect_response(lambda r: "/trips/preview/compose" in r.url) as ri:
        page.locator(
            f'#tourStops .tour-option-pick[data-tour-option="{index}"]'
        ).click()
    page.wait_for_timeout(300)
    return ri.value
```

### 6.2 Every stale site, with its replacement

`_route_tour_preview` (the helper at `:2462-2474`) is replaced wholesale; its three callers
then need only the click-through change.

| # | Line | Test / helper | Replacement |
| --- | --- | --- | --- |
| 1 | 2272-2295 | `test_tour_preview_generates_and_plays` | replace the `page.route(...)` block with `_route_two_step(page, plan=_plan_payload(STOPS), compose=OLD_PAYLOAD)` where `STOPS`/`OLD_PAYLOAD` are the current two stops and the current dict. Replace the `with page.expect_response(...) as ri:` block (`:2300-2302`) with `assert _generate_options(page).status == 200` then `assert _pick_option(page).status == 200`. `finally:` becomes `_unroute_two_step(page)`. |
| 2 | 2355-2362 | `test_tour_preview_renders_basic_lane_honestly` | `_route_two_step(page, plan=_plan_payload([{"sort_order": 1, "poi_name": "Notre-Dame", "minutes": 7}]), compose=payload)` — `payload` (`:2332-2354`) unchanged. Generate/pick via `_generate_options` + `_pick_option`. `finally:` → `_unroute_two_step(page)`. |
| 3 | 2411-2418 | `test_standalone_tour_preview_renders_basic_lane_honestly` | STEP 13 owns this one. Under the re-point contract (§8a): `_route_two_step(standalone, plan=_plan_payload([...]), compose=payload)`, click `#go`, then `standalone.locator('.tour-option-pick').first.click()`. Under the deletion contract (§8b): **delete the whole test (`:2388-2437`)**. |
| 4 | 2442-2449 | `test_tour_preview_untourable_shows_error` | stays a single-call test — the PLAN call is what 422s. Change only the predicate at `:2454` to `lambda r: r.url.endswith("/trips/preview")`. Payload unchanged. |
| 5 | 2464-2474 | `_route_tour_preview(self, page, stops)` helper | replace its body with `_route_two_step(page, plan=_plan_payload(stops), compose={"stops": stops, "spine_area": "Île de la Cité", "total_audio_min": sum(s.get("minutes", 0) for s in stops)})`. |
| 6 | 2494-2545 | `test_leg_cards_render_as_walks_not_stops` | after `_route_tour_preview(...)`, replace `:2512-2514` with `_generate_options(page)` + `_pick_option(page)`. `finally:` → `_unroute_two_step(page)`. The leg card is only in the compose payload, which is what `_plan_payload` already drops from the options. |
| 7 | 2556-2600 | `test_tour_stop_audio_caches_on_replay` | the "generate TWICE" loop (`:2570-2573`) becomes `for _ in range(2): _generate_options(page); _pick_option(page)`. `finally:` → `_unroute_two_step(page)`. |
| 8 | 2612-2642 | `test_tour_stop_long_narration_plays` | `:2621-2622` → `_generate_options(page)` + `_pick_option(page)`. `finally:` → `_unroute_two_step(page)`. |
| 9 | 2678-2724 | `test_tour_preview_ab_destination_sends_end_and_renders` | keep the capturing `_handler`, but have it fulfil the PLAN body: `route.fulfill(..., body=json.dumps(_plan_payload(STOPS)))` with `STOPS` the current two stops; register it with `page.route("**/trips/preview", _handler)` and add `page.route("**/trips/preview/compose", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"stops": STOPS, "spine_area": "Île de la Cité", "total_audio_min": 5})))`. `:2703-2704` → `_generate_options(page)` + `_pick_option(page)`. `finally:` → `_unroute_two_step(page)`. The `end_lat`/`end_lng` assertions (`:2710-2711`) then read the PLAN body, which is the call that must carry the destination. |
| 10 | 2730-2750 | `test_tour_preview_ab_infeasible_shows_alternatives` | single-call, like #4: change the predicate at `:2756` to `r.url.endswith("/trips/preview")`. Payload unchanged. |
| 11 | 2779-2800 | `test_tour_preview_surfaces_spotlight_and_coverage` | `_route_two_step(page, plan=_plan_payload(STOPS), compose=CURRENT_BODY)`, then `_generate_options(page)` + `_pick_option(page)` in place of `:2805-2806`. `finally:` → `_unroute_two_step(page)`. |
| 12 | 2824-2848 | `test_tour_preview_vignette_renders_tag_and_hollow_pin` | same shape as #11. The vignette stop survives into the option (band `vignette`), so the option card's `· 1 walk-past sight` clause is also exercised; the existing assertions all run after the pick. |
| 13 | 2893-2915 | `test_tour_preview_deeper_dive_badge_on_extras_stop` | same shape as #11. |
| 14 | 2974-2979 | `test_tour_preview_yellow_tourability_renders_warning_banner` | `_route_two_step(page, plan=_plan_payload(yellow_payload["stops"]), compose=yellow_payload)`, then `_generate_options(page)` + `_pick_option(page)` in place of `:2984-2985`. `finally:` → `_unroute_two_step(page)`. |
| 15 | 3000-3007 | the control half of the same test | same, with `compose={k: v for k, v in yellow_payload.items() if k != "tourability"}` and `plan=_plan_payload(yellow_payload["stops"])`. |
| 16 | 3050-3057 | `test_tour_preview_thin_delivery_renders_disclosure_note` | `_route_two_step(page, plan=_plan_payload(_payload(2, delivered_thin=True)["stops"]), compose=_payload(2, delivered_thin=True))`, then `_generate_options(page)` + `_pick_option(page)`. |
| 17 | 3081-3088 | the control half of the same test | same, with `_payload(26, delivered_thin=False)` on both sides. |
| 18 | 3107-3114 | `_clear_tour_route_pins` helper | `_route_two_step(page, plan=_plan_payload([]), compose={"stops": [], "spine_area": "-", "total_audio_min": 0})`; the generate step becomes `with page.expect_response(lambda r: r.url.endswith("/trips/preview")): page.locator("#tourGenerateBtn").click()`. No pick — an empty plan renders the empty-state card and clears the pins, which is what this helper wants. `finally:` → `_unroute_two_step(page)`. |
| 19 | 3198-3206 | `_handler` in `test_tour_generate_sends_clicked_coords` | keep capturing; fulfil `_plan_payload([])` instead of the stops body; predicate at `:3208` → `r.url.endswith("/trips/preview")`. No pick needed — this test only inspects the outbound PLAN body. |
| 20 | 3233-3253 | `test_tour_feedback_thumbs_send_context_and_toast` | `_route_two_step(page, plan=_plan_payload(STOPS), compose=CURRENT_BODY)`, then `_generate_options(page)` + `_pick_option(page)` in place of `:3277-3278`. `finally:` gains `_unroute_two_step(page)` alongside the `/feedback` unroute. |

(Sites 1-17 are the seventeen `**/trips/preview` fulfil registrations; 18-20 are the same
change in two helpers and one capturing handler that share the pattern. Twenty edits
total.)

### 6.3 The three unstubbed real-tour tests

`TestRealTourGeneration` (`tests/test_workbench_ui.py:5239-5451`) drives the real endpoint
and must now drive two of them:

- `test_workbench_generates_a_real_tour_unstubbed` (`:5242`): the `expect_response`
  predicate at `:5290` becomes `lambda r: r.url.endswith("/trips/preview")`; after the 200
  assertion, replace the `body.get("stops")`/`basic_tour` lane logic (`:5301-5316`) with an
  assertion that `body["options"]` has 3 entries whose stop names intersect
  `seeded_names`, then click `#tourStops .tour-option-pick[data-tour-option="0"]` inside a
  `page.expect_response(lambda r: "/trips/preview/compose" in r.url, timeout=180000)` and
  keep the existing rendered-stops assertions (`:5318-5328`) after it.
- `test_a_degraded_tour_shows_the_problem_panel_with_a_copy_button` (`:5330`): same
  predicate change at `:5366`. The degradation assertions now run against the PLAN
  response and the panel rendered by `renderTourOptions`, **before** any pick — which is
  exactly AC-21's "before the operator can click an option". No pick is needed at all.
- `test_an_unavailable_voice_refuses_before_spending_a_request` (`:5397`): predicate change
  at `:5427`, then a pick (`page.locator('.tour-option-pick').first.click()` inside a
  `page.expect_response(lambda r: "/trips/preview/compose" in r.url, timeout=180000)`)
  before the `.tts-play-btn[data-tour-stop]` locator at `:5434`, since Listen buttons exist
  only after authoring.

`tests/test_suite_honesty.py:122` stays green: these three still touch `/trips/preview`
without stubbing it.

### 6.4 Other tests that go red and their exact re-points

| Test | File:line | Why it breaks | Re-point |
| --- | --- | --- | --- |
| `test_generate_tour_preview_shows_no_spend_confirmation` | `tests/test_workbench_preview_wiring.py:190-209` | asserts `"renderTourStops(" in body` of `generateTourPreview`; that call moves to `authorTourOption` | change the non-vacuity assertion at `:202` to `assert "/trips/preview" in body and "renderTourOptions(" in body`. The `confirm(` assertion is untouched. |
| `test_the_rendered_tour_is_exactly_the_server_response` | `tests/test_workbench_matches_the_app.py:1836-1902` | asserts the single `renderTourStops` call site is inside `generateTourPreview` | keep `len(call_sites) == 1`; change `body = _js_function_body(html, "async function generateTourPreview()")` (`:1872`) to `body = _js_function_body(html, "async function authorTourOption(")` via `_js_function_body_after_params`-style parenthesis skipping (the declaration takes a plain parameter, so `_js_function_body` is still correct), change `:1877` to `assert "/trips/preview/compose" in body`, and add a second block asserting the same "no response field is written before rendering" scan over `generateTourPreview`'s body with `renderTourOptions(` as its single call site and `await resp.json()` as its first argument. |
| `test_no_consent_gate_between_the_click_and_the_tourist_facing_call` | `tests/test_workbench_matches_the_app.py:1732-1828` | the new pick button is a tourist-facing path with no entry in `TOURIST_FACING_FUNCTIONS` | add `"async function authorTourOption("` to the tuple at `tests/test_workbench_matches_the_app.py:114-118`. The `confirms == 1` pin and the "nothing between the click and `generateTourPreview()`" scan are unchanged and must stay passing. |
| `test_preview_fetch_sends_city_slug` / `test_preview_city_slug_uses_the_canonical_city_variable` | `tests/test_workbench_preview_wiring.py:55-77` | none — the regex anchors on ``/trips/preview` `` with a closing backtick, which the compose URL does not match | no change; verify they still pass. |

---

## 7. STEP 12's proving test — verbatim

Append to `tests/test_workbench_preview_wiring.py`. Command:
`make test-file FILE="tests/test_workbench_preview_wiring.py::test_generate_tour_options_is_a_separate_call_from_authoring"`.

```python
def test_generate_tour_options_is_a_separate_call_from_authoring() -> None:
    """Pressing generate must PLAN and nothing else.

    The two-step split is only real if the generate handler cannot reach the
    authoring endpoint or the audio endpoint. Both halves are asserted, so a
    single function that plans and then authors in the same click cannot pass.

    UNDO TEST: in review.html, change generateTourPreview's
    ``renderTourOptions(await resp.json(), duration);`` to
    ``renderTourStops(await resp.json(), duration);`` -> RED.
    """
    html = REVIEW_HTML.read_text()

    plan = _js_function_body(html, "async function generateTourPreview()")
    assert "/trips/preview" in plan, (
        "the extracted generateTourPreview body issues no preview request, so "
        "this guard is not reading the generate path"
    )
    assert "renderTourOptions(" in plan, (
        "generate must render the three route options; without this the operator "
        "never gets to choose and the preview is whatever the server wrote first"
    )
    assert "renderTourStops(" not in plan, (
        "generate renders narrated stops, so scripts were written before the "
        "operator picked a route — the whole point of the split is that pressing "
        "generate costs nothing"
    )
    assert "/trips/preview/compose" not in plan, (
        "generate calls the authoring endpoint; planning must be one call"
    )
    assert "/audio/" not in plan, (
        "generate reaches an audio endpoint; no voice may be made before a route "
        "is chosen"
    )

    author = _js_function_body(html, "async function authorTourOption(")
    assert "/trips/preview/compose" in author, (
        "authorTourOption does not call the authoring endpoint"
    )
    assert "route_id" in author, (
        "the authoring call does not carry the chosen option's identifier, so the "
        "server cannot know which of the three routes the operator picked"
    )
    assert "renderTourStops(" in author, (
        "authoring does not render the narrated stops"
    )
```

`_js_function_body` already exists at `tests/test_workbench_preview_wiring.py:166-187` and
raises rather than passing vacuously when a declaration is missing.

**The mutation, stated once more as one line:** in `frontend/review.html`, inside
`generateTourPreview`, replace `renderTourOptions(await resp.json(), duration);` with
`renderTourStops(await resp.json(), duration);` — the test goes RED on both the
`renderTourOptions(` and the `renderTourStops(` assertions.

This is a static parse of the HTML. It is not the browser proof: the owner's real-browser
run with screenshots (AC-5, AC-6, AC-21) is the separate gate, and `make test-workbench` is
a phase gate, never this step's gate.

---

## 8. STEP 13 — both contracts, unpicked

The ledger's own step name already carries the fork: "The standalone preview page follows
the same two-step flow, **or is deleted as a duplicate**". The planner-manager recommended
deletion; the owner has not ruled.

**Which contract the ledger's `test_command` matches:** the current command is
`make test-file FILE="tests/test_workbench_preview_wiring.py::test_the_standalone_preview_page_makes_the_same_two_calls"`,
which presumes the page still exists and makes two calls — i.e. **contract (a), the
re-point**. If the owner chooses deletion, that command must change to the one in §8b.

### 8a. Contract (a) — re-point `frontend/tour-preview.html`

Files: `frontend/tour-preview.html`, `tests/test_workbench_preview_wiring.py`,
`tests/test_workbench_ui.py`. Matches the ledger's `files[]` exactly.

**Markup** — inside `<div class="wrap">`, between `<div id="head" class="head"></div>`
(`frontend/tour-preview.html:56`) and `<div id="stops"></div>` (`:57`), insert:

```html
  <div id="options"></div>
```

The submit button's label at `:52` changes from `Generate preview` to
`Generate tour options`.

Add to the `<style>` block after the `.head` rule (`:33`):

```css
  .option { background:var(--card); border:1px solid var(--line); border-left:3px solid var(--accent);
            border-radius:12px; padding:14px 16px; margin-bottom:12px; }
  .option h3 { margin:0 0 2px; font-size:16px; }
  .option .meta { color:var(--mute); font-size:12px; margin-bottom:8px; }
```

**JS** — the submit handler (`frontend/tour-preview.html:65-102`) keeps its identity, its
coordinate parsing and its error branch. From `const data = await resp.json();` (`:87`)
onward, the body is replaced with `renderOptions(await resp.json())`, and the following
three functions are added after it and before `renderStop` (`:104`):

```js
let lastPlanBody = null;
let planOptions = [];

function renderOptions(data) {
  planOptions = Array.isArray(data.options) ? data.options : [];
  $("stops").innerHTML = "";
  $("head").textContent = `${planOptions.length} ways to walk this · spine: ${data.spine_area || "—"}`;
  status("Nothing has been written or recorded yet. Pick one and the narration and audio are made for that route.");
  const box = $("options");
  box.innerHTML = "";
  planOptions.forEach((opt, i) => {
    const dwell = (opt.stops || []).filter((s) => s.band !== "vignette");
    const dwellMin = dwell.reduce((sum, s) => sum + (s.minutes || 0), 0);
    const totalMin = Math.round((opt.eta_seconds || 0) / 60);
    const walkMin = Math.max(0, totalMin - dwellMin);
    const names = dwell.map((s) => s.name || "").filter(Boolean);
    const el = document.createElement("div");
    el.className = "option";
    el.innerHTML = `
      <h3>Option ${i + 1} · ${dwell.length} stops · ${totalMin} min total</h3>
      <div class="meta">About ${walkMin} min walking and ${dwellMin} min standing still</div>
      <div>${escapeHtml(names.slice(0, 4).join(" · "))}</div>
      <button class="pick">Use this one — write the tour</button>`;
    el.querySelector(".pick").addEventListener("click", () => authorOption(i));
    box.appendChild(el);
  });
}

async function authorOption(i) {
  const opt = planOptions[i];
  if (!opt || !lastPlanBody) return;
  status("Writing the tour…");
  try {
    const resp = await fetch(`${API}/trips/preview/compose`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign({}, lastPlanBody, { route_id: opt.route_id })),
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      status(`${resp.status}: ${body.detail || "could not write this tour"}`, true);
      return;
    }
    renderTour(await resp.json());
  } catch (err) {
    status(`Request failed: ${err}`, true);
  }
}

function renderTour(data) {
  $("options").innerHTML = "";
  planOptions = [];
  const basicTour = data.candidate_eligible === false && data.basic_tour;
  const activeTour = basicTour || data;
  const stops = Array.isArray(activeTour.stops) ? activeTour.stops : [];
  $("head").textContent =
    `${stops.length} stops · spine: ${data.spine_area || "—"} · ~${activeTour.total_audio_min || 0} min of audio`;
  status(basicTour
    ? "Basic grounded guide ready — not Premium and not graded. Play any stop below."
    : "Premium candidate ready — eligible for certification. Press “Play narration” on any stop.");
  $("stops").innerHTML = "";
  for (const s of stops) renderStop(s);
}
```

`lastPlanBody` is assigned inside the submit handler, immediately before the fetch, to the
same object literal the fetch sends. `renderStop` (`:104`) and `playStop` (`:119`) are
**UNCHANGED** — `playStop` remains the only caller of `/audio/preview` (`:123`).

**Proving test** (append to `tests/test_workbench_preview_wiring.py`; the ledger's existing
command runs it unchanged):

```python
PREVIEW_HTML = REPO / "frontend" / "tour-preview.html"


def test_the_standalone_preview_page_makes_the_same_two_calls() -> None:
    """The public preview page plans first and authors only on a pick.

    It is the same product as the workbench view, so it gets the same split: one
    free call that returns three routes, and a second, paid call that runs only
    after a human chooses one.

    UNDO TEST: in tour-preview.html, change the submit handler's
    ``renderOptions(await resp.json())`` back to ``renderTour(await resp.json())``
    -> RED.
    """
    html = PREVIEW_HTML.read_text()

    submit = html[html.index('$("f").addEventListener') : html.index("function renderOptions")]
    assert "/trips/preview" in submit, "the submit handler issues no preview request"
    assert "renderOptions(" in submit, (
        "pressing generate does not render the three route options"
    )
    assert "renderTour(" not in submit, (
        "pressing generate renders a written tour, so narration was produced "
        "before anyone chose a route"
    )
    assert "/audio/" not in submit, "generate reaches an audio endpoint"

    author = _js_function_body(html, "async function authorOption(")
    assert "/trips/preview/compose" in author, "authorOption calls no authoring endpoint"
    assert "route_id" in author, "the authoring call omits the chosen route's identifier"
    assert "renderTour(" in author, "authoring renders no tour"
```

Browser test #3 in §6.2 (`tests/test_workbench_ui.py:2388-2437`) is updated as described
there.

### 8b. Contract (b) — delete `frontend/tour-preview.html`

Deleted, exactly and only:

1. `frontend/tour-preview.html` — the whole file (146 lines).
2. `src/api/app.py:91-102` — the `_tour_preview_html` path constant, the
   `@app.get("/tour-preview")` decorator and the `tour_preview_page()` handler.
3. `tests/test_preview_page.py` — the whole file (20 lines); its only test
   (`test_tour_preview_page_is_served`) asserts the deleted route returns 200.
4. `tests/test_workbench_ui.py:2388-2437` — `test_standalone_tour_preview_renders_basic_lane_honestly`,
   the only browser test that opens the page.

Nothing else references the page: the remaining hits are prose in `specs/`, `Docs/` and the
untracked `ondoway-one-engine-handoff.md`, none of which is code.

**Proving test** replacing the ledger's command. New command:
`make test-file FILE="tests/test_workbench_preview_wiring.py::test_the_duplicate_standalone_preview_page_is_gone"`.

```python
def test_the_duplicate_standalone_preview_page_is_gone() -> None:
    """One tour UI, not two.

    The standalone page was a second, thinner copy of the workbench's tour view
    making the same two calls. Two copies means one of them drifts, and the one
    that drifts is the one nobody opens. It is deleted, along with the route that
    served it.

    UNDO TEST: restore frontend/tour-preview.html or the /tour-preview route in
    src/api/app.py -> RED.
    """
    assert not (REPO / "frontend" / "tour-preview.html").exists(), (
        "the duplicate standalone preview page is back"
    )
    assert not (REPO / "tests" / "test_preview_page.py").exists(), (
        "the deleted page's test file is back"
    )
    app_py = (REPO / "src" / "api" / "app.py").read_text()
    assert "tour-preview" not in app_py, (
        "src/api/app.py still serves the deleted standalone preview page"
    )
    ui = (REPO / "tests" / "test_workbench_ui.py").read_text()
    assert "test_standalone_tour_preview_renders_basic_lane_honestly" not in ui, (
        "the browser test for the deleted page is still present and will fail "
        "against a 404"
    )
```

Under this contract the step's `files[]` must gain `src/api/app.py` and
`tests/test_preview_page.py`; the ledger currently lists neither.

**Cost of deletion, stated rather than hidden:** the workbench view is opened `file://` by
`scripts/workbench.sh:13`, so deleting `/tour-preview` removes the only tour UI reachable
from a deployed URL without the workbench checkout. If anyone demos tours from a browser
pointed at the API rather than at a local file, that goes away.

**Recommendation:** delete (contract b). It is a second implementation of the exact flow
STEP 12 is rebuilding, it has one browser test, and keeping it means every future change to
the tour flow is made twice — which is the same duplication this whole ledger exists to
remove.

---

## 9. BLOCKING AMBIGUITY

1. **The AUTHOR endpoint's URL and request shape belong to STEP 11.** This contract pins
   `POST /trips/preview/compose` with the plan body plus `route_id`. If STEP 11 lands
   something else, §1.2, §2.6, §6.1, §7 and §8 change in the URL string and the field name
   only. *Recommendation:* pin `/trips/preview/compose` + `route_id` in STEP 11 as written
   here — `route_id` is already the identifier `TripComposeRequest` uses for the persisted
   twin (`src/api/models/trips.py:172-177`), so the two surfaces name the same thing the
   same way.

2. **Which contract STEP 13 executes is an owner decision** (§8). Both are written. The
   ledger's current `test_command` presumes the re-point; the recommendation is deletion,
   which requires changing that command and widening the step's `files[]`.

3. **The exact routing-degradation sentence is emitted by STEP 14, not by the page.** §5
   pins the string the workbench must display and the browser test must assert. If STEP 14
   writes a different sentence, the assertion in the AC-21 browser proof follows STEP 14's
   text, and no page code changes. *Recommendation:* STEP 14 uses §5's sentence verbatim.
