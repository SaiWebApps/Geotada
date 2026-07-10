# Ondoway Tour-Generation Overhaul — Diagnosis of Record

**Date:** 2026-07-09 · **Base:** `main` @ `9160fe6` · **Method:** read-only static +
exported-corpus diagnosis (dev DB was down). 18-agent workflow: corpus forensics →
8 root-causers → 8 adversarial skeptics → synthesis. Every "needs-live" item routed to §5.

**Provenance caveats:**
- `skeptic:RD-1` stalled mid-stream → RD-1 root-cause is **unverified by an adversary**.
- `rc:RD-4` (narrative layer) **succeeded** but its skeptic failed the structured-output
  cap, so the pipeline dropped the RD-4 item to null and the synthesis omitted it. RD-4 is
  re-attached below as §1a (it matches the user's own proposed design and is statically
  confirmable; it still needs a skeptic pass before its slice is built).

---

## 1. Confirmed root-causes (post-skeptic confidence)

- **RD-8 — Audio = 30s of silence. CONFIRMED (config).** Mobile `confirmTripStopAudio`
  POSTs `/audio/generate-trip-stops/{id}` with no body → `get_provider(None)` →
  `os.getenv("TTS_PROVIDER","mock")` (`provider.py:275`) → `MockTTSProvider` writes a
  **silent WAV clamped to 30.0s** (`provider.py:142,154`). `TTS_PROVIDER=mock` in prod
  (`render.yaml:48`) + local (`.env:7`). **Correction:** `render.yaml` declares **no
  `OPENAI_API_KEY`** — a bare provider flip **fails closed** (null audio), so the fix is
  provider flip **+ key**. Latent trap: request-model default `provider="mock"`
  (`models/audio.py`) bites body-sending callers (preview/eval/keep-exploring).

- **RD-1 — Duplicate consecutive stops (2nd stop beat-starved / "Walk to the next stop.").**
  Mechanism CONFIRMED; **source is HYPOTHESIS (unverified).** Fan-out expands
  `route.pois`/`selected_pois` 1:1 with **no id-dedup** (`generation.py:882`,
  `crud/trips.py:45`); a repeated id → 2nd stop degenerates to transit glue (matches T4
  Rodin stop 2). **But** offline `select_route` on the corpus snapshot yields
  `len(pois)==len(set ids)` for T1–T4, **0/181 on-disk tours** have a dup id, corpus has
  370 unique names. **So the repeat enters `route.pois` from OUTSIDE the committed engine.**
  Leading hypothesis: **live-DB POI twins** (byte-identical id/name/coords from an upload
  fork; `POI` is frozen value-equality, `contract.py:71-82`, so greedy `remove` drops one).
  Alt: Flutter renderer splitting narration into approach+story cards. **Needs live probe (§5 #1-3).**

- **RD-CoLo — Distinct co-located POIs each become an adjacent dwell stop. CONFIRMED (engine).**
  Only guard `apply_co_located_demotion` is **triple-gated** (both tier≥4 `selection.py:1625`
  AND ≤100m `1627` AND `_has_cross_poi_address_overlap` `1630`). Corpus has **54 within-100m
  distinct pairs** with a tier<4 member (Notre-Dame t5 + Rue Chanoinesse t1; Palais-Royal t5
  + Comédie-Française t3; the Île-de-la-Cité cluster) → almost none demote → adjacent
  near-identical stops (drives T1 "ends flat at Notre Dame"). Distinct from RD-1 (real
  distinct nodes, different names).

- **RD-2 — Routing blind to POI density, near-blind to lenses. Structural CONFIRMED (engine);
  the "18-min cold start" example REFUTED.** Greedy value `= base/max(1,extra+1)`
  (`selection.py:1347`), `poi_score` has **no cluster/proximity term**; `held_karp_open` is
  pure travel-time TSP; `corridor_admits` is a pure travel-budget ellipse → nothing rewards
  routing *through* density. Lens is a floored 4× multiplier (`LENS_FLOOR=0.25`,
  `selection.py:96`) swamped by tier×richness + a lens-independent 5× `AREA_ALIGNMENT` spine
  term → **T1≈T2**. **Skeptic downgrades:** (a) the specific Palais-Garnier→Les-Halles 120min
  case is **refused** at the A→B feasibility gate (`t(A→B)=2680s > walk_budget=2390s`), not
  routed — the cold-start shape only appears when A→B is *within* budget; (b) scope lens
  fixes to `LENS_FLOOR`/exponent only (the `AREA_ALIGNMENT` cap is not no-lens-invariant).

- **RD-3 — Thin tours / broken budget / no cruise mode. CONFIRMED delivered ≪ promised;
  binder RE-ATTRIBUTED.** `target_audio ≈ 0.498·d` (`routing.py:42-44`) with **no feedback
  from corpus supply** (Paris ~2 beats/POI) → delivered audio saturates ~30–40 min (181
  tours: max **38.95 min**, median deliver-fraction **0.37**). No mode/pace field
  (`contract.py`); every POI → full dwell stop. **Skeptic:** the 12-anchor cap
  (`HARD_ANCHOR_CAP=12`) **never binds** (max 11 stops on disk) — real binder is **candidate
  supply + AUDIO_FRACTION-vs-corpus mismatch**. Fix = re-calibrate the promise, **not** raise
  the cap.

- **RD-6 — Vignettes shallow + re-absorbed + double-voiced (preview). Core CONFIRMED (engine).**
  Vignette = `sents[0]` only (`generation.py:688`), tagged with the arrival dwell stop's
  `stop_idx` (`generation.py:670,697`); `stop_narration_text` groups by `stop_idx` and joins
  (`render_md.py:132`) → folds the one-liner into the dwell narration (T3 stop 5). Double
  representation is **preview-only**; `/generate` iterates `selected_pois` so vignettes get no
  own stop (single but mis-placed). End-clustering + "bare nav-fragment" are **unproven**,
  DB-order-dependent (`LOAD_PARIS_BEATS_CYPHER` has no `ORDER BY`).

- **RD-5 — Dashes reach TTS; no within-story/proper-noun dedup. Split.** CONFIRMED:
  `normalize_for_tts` has **no dash rule** (`tts_normalize.py:210-211`), em-dashes hardcoded
  into the opener (`generation.py:454,462`), 1005/1562 beats carry a dash; no within-beat /
  proper-noun dedup exists (`claim_dedup.py` is cross-beat only). **Skeptic downgrades:** (a)
  "em-dashes *break* TTS" is HYPOTHESIS (code proves only the dash *reaches* the provider;
  needs A/B listen); (b) **a blanket `— → ,` rewrite is HARMFUL** — every en-dash here is a
  numeric/date/address range (`1615–1630`, `57–59`); must special-case ranges to "to"; (c)
  **priority inverted** — the reported "names the place several times" is the *proper-noun
  repetition* (no pass exists) and is the primary defect; em-dash is secondary.

- **RD-7 — Big areas are single point-dwells; "walk toward {area}" from inside it.
  Engine-gap CONFIRMED; data fact CORRECTED against BOTH reviewers.** `POI` carries only a
  point (`contract.py:74-82`); no traversal/footprint machinery; `find_area_orientation_beat`
  called only for `stop_idx=0` (`generation.py:293`); no inside-area guard on "head for
  {name}" (`generation.py:454,462`) or "Walk on toward {name}." (`generation.py:661`).
  **Data reality (direct verification):** top-level POI dicts have **no `parent_poi`** (0/370),
  but membership lives in `_pipeline.parent_poi` — **5 Tuileries children** (Orangerie,
  Arc du Carrousel, Grand Bassin Rond, Jeu de Paume, Esplanade des Feuillants) + 16 across
  7 other parents (Île de la Cité ×7, Île Saint-Louis ×3…); Angelina/Place des Pyramides
  correctly excluded (proximity would mis-include them). Footprint `trigger_radius`
  (Tuileries=100) **is in Neo4j** (`upload_paris.py:184`) but the loader **drops it**
  (`LOAD_PARIS_POIS_CYPHER` selects id/name/tier/role/lat/lng/areas only, `selection.py:424`);
  `parent_poi` is **never persisted** (lives only in `_pipeline`). **Engine is area-blind
  because the loader discards signals the corpus already carries.**

### 1a. RD-4 — No whole-tour narrative layer (re-attached; matches user's proposal). CONFIRMED (engine), skeptic PENDING.
`generate()` (`generation.py:154-257`) stitches: cold-open → per-stop {transit-glue +
anchor-beats} → closing → claim-dedup. Every narrative element is either **per-stop** or
**globally hardcoded**: intro "Settle in…" (`_build_cold_open` `generation.py:265`,
`GLUE_PACING` 298-305), outro "End the walk here, or carry on at your own pace."
(`_build_closing` `generation.py:755`), nav "Walk on toward {name}." glued to the **front**
of each story (`_build_transit` `generation.py:596,661`). **No pass derives a tour-wide
through-line, generates a fitted intro/outro, or produces inter-stop transitions / arrival
announcements.** User's proposed design (multi-pass: derive through-line → fitted intro+outro
→ connective tissue, nav moved out of the story body) has no current home; would attach as a
post-selection narrative pass (deterministic and/or `/compose`).

---

## 2. Workstreams (8 defects → 5)

- **WS-A · Audio voicing (RD-8).** Independent config/selection. Nothing is judgeable until audio is audible. Ships alone.
- **WS-B · Stop-set integrity (RD-1 + RD-CoLo + RD-6 placement).** Share one seam:
  `route.pois`/`selected_pois` → stops and sentence-grouping by `stop_idx`
  (`generation.py:882`, `crud/trips.py:45`, `render_md.py:132`). Must land together.
- **WS-C · Narration hygiene (RD-5).** Dash+range normalization (`tts_normalize.py`,
  `render_md.py`) + within-story/proper-noun dedup (`claim_dedup.py`). Sequence with/after WS-B.
- **WS-D · Budget & pacing (RD-3).** Re-calibrate the promise + opt-in transit/cruise mode
  (new `TourInput` field). Large blast; re-baselines goldens.
- **WS-E · Route cohesion (RD-2 + RD-7) + narrative layer (RD-4).** The north star.
  Density-seeking + lens-responsive selection, area traversal (needs loader/upload changes),
  and the multi-pass narrative layer. Largest blast; do last.

---

## 3. Sequenced slice plan (correctness first: A → B → C → D → E)

1. **Make audio audible (RD-8, small).** `render.yaml`/`.env` set `TTS_PROVIDER=openai` **+
   add `OPENAI_API_KEY`**; flip 4 request-model `provider="mock"`→`None`. Accept: `get_provider(None).name=="openai"`;
   `/audio/preview` returns non-silent PCM, `duration!=30.0`; mutation → silence returns.
2. **Distinct-stop invariant + fan-out dedup (RD-1, small).** Dedup `selected` by id at the
   post-`held_karp` choke point **merging beats into the survivor**; seen-set at both fan-out
   points. Self-heals a dup from any source (incl. live twins). Red-first: `[Rodin,Rodin,Invalides]`
   → 2 stops with union beats; mutation → RED. *(Live twin/render probe §5 runs in parallel.)*
3. **Fold beatless fixed-end sentinel (RD-1 secondary, small).** `selection.py:820-828`: when
   end-B >150m from all POIs, fold B into nearest stop or carry a real closing beat, not a naked
   "Destination" sentinel. Accept: no empty-`beat_ids` final stop.
4. **Dash normalization with range preservation (RD-5 em-dash, medium).** Add spaced `—`→", "
   at the provider seam + generation join; **special-case numeric/date/address ranges → "to"**;
   do NOT blanket-rewrite `–`. Accept: `'1615–1630'`→"1615 to 1630", no U+2014 at seam; mutation → RED.
5. **Within-story + proper-noun repetition pass (RD-5 primary, medium).** Same-beat
   surface-similarity + light sentence-Jaccard (not gated on `key_claims`) + proper-noun/anaphora
   elision. Accept: no two same-`source_id` sentences >0.7 overlap; POI proper noun not restated
   across >1 of {opener, transit, first beat}.
6. **Vignette own-slot (RD-6, medium).** Own `stop_idx`/fractional slot; richer self-contained
   hook (>1 sentence); deterministic beat order. Accept: dwell narration no longer contains the
   vignette sentence; each one-liner appears once; sits between bounding stops; mutation → RED.
7. **Co-located demotion widening (RD-CoLo, medium).** Relax triple gate so tier<4 near-identical
   pairs demote/merge; loosen address-overlap. Accept: the 54 pairs no longer all surface as
   adjacent dwell stops.
8. **Budget re-calibration + opt-in transit/cruise mode (RD-3, large).** (a) "Planned total" =
   deliverable audio+walk (stop over-promising), **not** raise the cap; (b) opt-in transit-forward
   mode raises cap + demotes most stops to pass-through so walking fills the time. Accept:
   deliver/plan ratio improves OR promise==deliverable; cruise req total≈requested.
9. **Density-seeking + lens-responsive selection (RD-2, large).** Multiply candidate value by
   local-density `(1+k·D)` (precompute D = eligible candidates within 250–400m); lower `LENS_FLOOR`
   toward 0.05–0.10 / raise exponent (scope to `LENS_FLOOR`/exponent only). Accept: on a **feasible**
   dense req, first-leg <40% of avg leg; two disjoint lens sets → selected-id Jaccard <0.6 +
   different order; no-lens path byte-identical; goldens re-baselined.
10. **Area traversal + inside-area guard (RD-7, medium-large).** Persist `_pipeline.parent_poi`
    (`upload_paris.py`); load `trigger_radius`+`parent_poi` (`selection.py:424`); carry both
    (`contract.py:74-82`); guard "head for/Walk toward {area}" when prev coord is within the area
    `trigger_radius`; thread `parent_poi` children as an ordered viewpoint chain; call
    `find_area_orientation_beat` at non-zero index. Accept: no "toward an area you're inside";
    large-area stop yields >1 in-footprint viewpoint sentence.

*(Slice for RD-4 narrative layer to be authored after the WS-E product decision — deterministic vs `/compose` vs hybrid.)*

---

## 4. Open product trade-offs (for the human)

1. **Cruise-through: explicit mode vs auto-triggered budget behavior.** *Rec: one opt-in
   `TourInput.mode` the engine can ALSO auto-set when `target_audio` is unreachable.*
2. **Stop over-promising vs re-calibrate the audio target.** Corpus funds ~30–40 min max; a
   "250-min tour" honestly reads ~90 min (audio+walk). *Rec: report deliverable, stop the
   duration-derived promise.* (Alt = months of content growth.)
3. **How aggressive should lens-routing be.** *Rec: `LENS_FLOOR≈0.10` + modest exponent, keep a
   tier floor so a "nature" lens biases but never starves Notre-Dame/Louvre.*
4. **Full `/compose` narrative rewrite vs targeted deterministic fixes.** Every defect lives in
   the deterministic engine; `/compose` only narrates the stop set handed to it. *Rec:
   deterministic Slices 1-10; reserve `/compose` for optional polish of already-placed text.*
5. **Raise the 12-anchor cap?** *Rec: NO — never binds; fix supply/budget. Confirm with the
   §5 d=250 live run before spending effort.*
6. **Area traversal via `parent_poi` needs a re-upload** (persist `_pipeline.parent_poi`,
   re-run parity — Tier-3 infra). *Rec: ship the `trigger_radius`-only inside-area guard first
   (data already in Neo4j), defer true traversal.*

---

## 5. Live-repro matrix (bring up: Colima → Neo4j 7687 → Valhalla)

**Harness gap:** the tour-build CLI has **no `--end` flag**; all 4 symptom tours had an explicit
destination and were never persisted. Add `--end LAT,LNG` (or drive `POST /trips/generate`).

| # | Item (confidence) | Probe | Expected vs actual |
|---|---|---|---|
| 1 | RD-1 source (HYP — engine exoneration) | `POST /trips/generate` T1 `start=48.8656,2.3210 end=48.852966,2.349902 dur=250`; assert `len(route.pois)==len({id})`. Repeat T2/T3/T4. | PASS (no dup) ⇒ source is OFF the engine. A FAIL ⇒ log ids after spine/greedy/endpoint-pull/fill/`_materialize_fixed_end_b` to find the stage. |
| 2 | RD-1 DB twins (HYP) | Cypher `MATCH (p:POI{city_name:'paris'}) WITH p.id id,count(*) c WHERE c>1 RETURN id,c` (and by name). | Any row ⇒ live twins. Cross-check 2026-07-06 parity (370 nodes). |
| 3 | RD-1 render vs data | For one symptom trip: `MATCH (t:Trip)-[:HAS_STOP]->(i) RETURN i.sort_order,i.poi_name,i.beat_ids`. | Doubled rows ⇒ data. Unique rows but app doubles ⇒ Flutter renderer. |
| 4 | RD-2 density+lens | **Feasible** T3 (Palais Garnier→Les Halles at **dur≥135**); once null, once nature; log `poi_score` components for top-20 + `corridor_admits` for Galeries Lafayette/Garnier. | Density: first-leg large fraction, near-start t5 absent. Lens: selected-id Jaccard >0.8 + identical order ⇒ lens doesn't steer. |
| 5 | RD-3 thin+cap | `POST /generate` T1 d=250; assert unique `route.pois`≤12 and `audio/target≈0.4`. Unit: `max_anchors(250)==12`, `max_anchors(600)==12`. | deliver/target≈0.4 (median 0.37). unique<12 ⇒ binder is supply not cap. |
| 6 | RD-5 em-dash reaches TTS (CONF) + breaks TTS (HYP) | Unit `'—' not in normalize_for_tts('A — B')` (FAILS today). With `TTS_PROVIDER=openai` capture `_split_for_tts` output. A/B listen spaced-em-dash vs comma. | Char-presence confirmable now; "mis-voices" only via A/B listen. |
| 7 | RD-6 re-absorb+double | `/trips/preview` feasible T3: assert a dwell stop's narration contains a vignette POI's first sentence AND the same one-liner appears as a vignette card. `/generate` T1: log `route.vignettes`. | Substring match both places = confirmed. Clustering resolves from leg-idx distribution. |
| 8 | RD-7 runtime symptom | `POST /generate` T2 `dur=250 lenses=[parks_gardens,waterways_views,social_change]`; log `(id,name,lat,lng)` after `select_route`. | (1) Tuileries dwell at ~48.8636,2.3274; (2) a sentence says "walk toward" Tuileries while prev coord within ~250m; (3) no Orangerie/Grand Bassin/Feuillants viewpoints. |
| 9 | RD-8 provider (CONF static; prod) | `python -c "from src.audio.provider import get_provider; print(get_provider(None).name)"` → mock. Prod: `render env` for `TTS_PROVIDER` + `OPENAI_API_KEY`. | Local mock/silent confirmed. Prod: no `OPENAI_API_KEY` ⇒ flip alone fails closed — confirm key first. |
