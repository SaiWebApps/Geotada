# Extraction Requirements — handoff to `/unified-beat-extract` update

**Purpose:** Translate the observations in `source-study.md` into concrete changes to the beat extraction pipeline. This doc is the handoff artifact for the parallel work updating the extraction model.
**Source:** every requirement below traces back to a specific observation in `Docs/tour-builder/source-study.md`. The source-study is the "why"; this doc is the "what to change."
**Created:** 2026-04-22.
**Scope:** changes to `/unified-beat-extract` prompt and the beat schema. No tour-builder work — that comes after the corpus is right.

---

## Why these changes exist (the short version)

We read three Paris guidebooks and diagnosed that our 555 existing beats can support Rough-Guide-quality tours but not Pariswalks-quality. Then we realized: *the Pariswalks-quality material is literally in the source books being ingested.* Our extractor just loses it — paraphrases away inline French, flattens sub-location structure, ignores address-level seasoning, produces uniform 75-word beats regardless of source role.

**This is an extraction-recovery problem, not a source-scarcity problem.** The data is there. The extractor needs to preserve it.

The book ingest is rebuilding the corpus from scratch on 6 more books. This is the right moment to upgrade the extractor before the batch runs.

---

## Field additions to the beat schema

### 1. `sub_location` (string | null)

Within-POI spatial tag. Only populated for tier-4/5 POIs where the source treats sub-locations as distinct. Examples: `"façade"`, `"central-portal"`, `"rose-window-north-transept"`, `"interior-nave"`, `"choir"`, `"towers"`, `"crypt"`, `"exterior-east-side"`, `"salle-des-gens-darmes"`, `"marie-antoinette-cell-mockup"`.

**Why:** Rough Guide's Notre-Dame entry has explicit sub-headings — *Cathédrale → Façade → Towers → Interior → Kilomètre zéro → Crypte archéologique*. Our current extraction flattens all of these into one lens-indexed pool, losing the ability to sequence the user around the building. An audio tour of Notre-Dame needs to walk the listener façade → central portal → rose window → interior → crypt in a meaningful order. Without `sub_location`, the runtime can't do that.

**Traceability:** source-study.md §"Question 1: length scales" — the 4-sub-entry Rough Guide Notre-Dame structure.

### 2. `trigger_address` (string | null)

An address-level or micro-location string that GPS/geocoding can resolve to a specific point the user walks past. Examples: `"no. 6 place des Vosges"`, `"no. 115 rue Saint-Honoré"`, `"4 rue des Saints-Pères"`. When populated, `poi_name` is the containing anchor (Place des Vosges); `trigger_address` is the listening trigger.

**Why:** Pariswalks Walk 4 circumnavigates Place des Vosges house by house — no. 2 (Restaurant Coconnas), no. 6 (Hugo's house), no. 8 (Gautier), no. 14 (Abbé de la Riviére / synagogue), no. 16 (le Roux). Each is a self-contained 50–200-word vignette. Currently our 17 Place des Vosges beats are all attached to the square as a whole, so we cannot do Pariswalks-style circumnavigation. Every book contains address-level seasoning material; our extractor doesn't know to capture it.

**Traceability:** source-study.md §"Question 4: Seasoning" — the four example seasoning vignettes at specific addresses.

### 3. `beat_length_class` (enum)

Values: `anchor` | `mid` | `seasoning` | `micro`.

- **anchor**: 200–400 words. Tier-5 POI main historical narrative. Audio ~90–180s. Used for stops where the listener is stationary. Example: Pariswalks' 1000-word Place des Vosges opener (would be 2–3 anchor beats).
- **mid**: 80–200 words. Tier-3/4 primary beat, or tier-5 secondary beat. Audio ~30–90s. Example: Rough Guide's Conciergerie entry (180w).
- **seasoning**: 20–80 words. Address-level vignette or walk-by callout. Audio ~10–30s. Example: "No. 8 place des Vosges was the home of the poet Théophile Gautier, who lent his name to the technical high school next door."
- **micro**: <20 words. One-liner factoids that play during transit. Audio <10s. Example: "On your right, the oldest tree in Paris."

**Why:** current corpus has median 75 words across all beats — clustered in "mid" with no anchors or seasoning-class beats. That's wrong for **both** roles: anchor stops sound thin; seasoning stops sound bloated. The extractor should produce different lengths on purpose, matched to the source passage's role.

**Traceability:** source-study.md §"Question 1: length scales" and §"Data diagnostic, gap #4."

### 4. `inline_foreign_phrases` (list of `{phrase, gloss}`)

Structured record of foreign words + inline gloss preserved from the source. Example:
```json
[
  {"phrase": "pailleux", "gloss": "prisoners who couldn't afford to bribe a guard for their own cell and had to sleep on straw"},
  {"phrase": "paille", "gloss": "straw"}
]
```

**Preservation rule:** the foreign word MUST remain in `script_body` as the book wrote it. This field is the *structured* companion, not a replacement. Extractor must NOT paraphrase `"pailleux, prisoners who slept on straw"` into `"poor prisoners who slept on straw."` The French word is an audio-tour asset.

**Why:** every guidebook teaches French inline — *pailleux, paille, marais, hôtel, ravalement, pavillon, oeil-de-boeuf, trompe-l'oeil, tricoteuses, bon-bec*. Pariswalks does pronunciation on top (*plass-day-voge*). Current extractor paraphrases these away. The "you are abroad" register depends on them.

**Traceability:** source-study.md §"Construction patterns shared by all three" item 3; §"Question 5: grounding" (entire French vocabulary list).

### 5. `physical_cues` — enforce populated on tier-3+

Currently 61% populated corpus-wide. New rule: **physical_cues MUST be populated on every beat at a POI with `importance_tier >= 3`** if the source passage references a visible feature. No physical cue → the extractor either found none in the source (acceptable) or failed to capture one (not acceptable — reprompt or flag).

Each physical cue is a short string describing what the listener can see from the beat's location. Example: `"the brass stud in the pavement in front of the cathedral marks the Zero Point of Paris"`, `"the iron grille separating off the pailleux section at the far end of the hall"`, `"Viollet-le-Duc's statue of himself among the angels on the roof, the only one looking heavenward"`.

**Why:** physical cues are the #1 audio-tour quality signal across every source we studied. Currently 4/5 Conciergerie beats have zero physical cues. Rough Guide and Frommer's are packed with them; we're losing them in extraction.

**Traceability:** source-study.md §"Construction patterns" item 4; §"Data diagnostic gap #1."

### 6. `pronunciation` (string | null)

Phonetic or approximate spelling for a proper noun or foreign word the listener needs to say. Example: `pronunciation: "plass-day-voge"` for `"Place des Vosges"`. Populated when the source provides it or when the extractor judges the listener would benefit. Downstream stitcher/TTS can use this to insert a modeling beat ("That's pronounced plass-day-voge").

**Why:** Pariswalks consistently adds pronunciation. The Travlr use case amplifies this — listener hears the foreign word spoken for the first time and may want to repeat it.

**Traceability:** source-study.md §"Question 3: Pariswalks Walk 4 opening" item 6.

---

## New `beat_type` values

Extend current enum (`anecdote | architectural_detail | character_story | event | sensory_observation | factoid | establishing`) with:

### `stop_orientation`

The sit-down-and-look pattern. Tells the listener where to stand, which direction to face, what to look at, with optional weather/comfort alternatives. Lands before narrative content at a stop.

**Source example** (Pariswalks Walk 4 opening): *"Sit in the garden near the children's area so that you can watch the children play à la française (despite the mix of Hebrew, Yiddish, and Arabic you'll hear). If it is cold, try the café Ma Bourgogne, on the northwest corner of the place."*

This is physical staging, not narrative. Distinct extraction target.

**Traceability:** source-study.md §"Question 3: Opening patterns — Pariswalks Walk 4."

### `transit`

Walking directions between stops, optionally carrying walk-by seasoning. The audio plays while the listener is moving, not stationary.

**Source example** (Frommer's Walk 1): *"From the statue, cross the road into place Dauphine and turn left into rue de Harlay, walking around the Conciergerie. Turn right into boulevard du Palais, cross over to place Louis Lepine, stopping to admire the Conciergerie and the Sainte-Chapelle."*

Extract these from Frommer's and Rick Steves (the two walk-scripted books). Pariswalks also has them but less bold-formatted. Rough Guide has none — it's a reference.

**Traceability:** source-study.md §"Genre table" row "Turn-by-turn directions."

### `sidebar`

Self-contained tangent that can be played (long-tour mode) or skipped (short-tour mode) without breaking the main flow. References a POI but is not part of its primary narrative arc.

**Source example** (Rough Guide): the "School for Scandal" box on Abélard and Héloïse dropped next to the Notre-Dame entry. ~120 words. Self-contained.

**Traceability:** source-study.md §"Question 1: Rough Guide scaling" and §"Question 4: Seasoning in Rough Guide."

---

## Behavioral rules for the extractor

### B1. Replace the lens ceiling with a (lens, sub_location) ceiling

**Old rule:** max 1 beat per taggable lens per POI (North Star-locked, line 3 of schema rules).

**Proposed new rule:** max 1 beat per `(lens, sub_location)` tuple per POI. For POIs without sub_location distinctions the old rule still applies. For tier-4/5 POIs where the source treats sub-locations as distinct, this allows Notre-Dame to carry multiple `historic_arch` beats (one for façade, one for towers, one for interior, one for crypt).

**Why:** current cap of 16 beats per POI is a hard ceiling that clips richness at exactly the POIs where richness matters most. Pariswalks Walk 4 contains ~25–30 vignettes for Place des Vosges alone. The new rule respects spatial diversity within a POI.

**This is a North Star change.** Flag to the CTO as a candidate revision to the "1 beat per taggable lens per POI" commitment before shipping. Don't implement silently.

### B2. Extract at multiple granularities from a single passage

A Rough Guide Notre-Dame entry with sub-heads should emit **multiple beats**, not one. An extractor seeing *"The facade is Notre-Dame's most impressive exterior feature..."* followed by *"If you climb the towers..."* followed by *"Inside Notre-Dame, you're struck immediately..."* should produce at minimum 3 beats with sub_location = façade / towers / interior, each with its own script_body pulled from the relevant passage.

**Current behavior:** the extractor appears to merge or summarize these into fewer, lens-indexed beats. The sub-location granularity is lost.

### B3. Preserve-don't-paraphrase on inline foreign phrases

When the source contains `"foreign-word (inline-gloss)"` or `"foreign-word, meaning X"`, the extractor MUST:

1. Keep the foreign word in `script_body` verbatim.
2. Keep the gloss clause in `script_body` verbatim.
3. Also record the pair in `inline_foreign_phrases` (field #4 above).

Paraphrasing `"pailleux, prisoners who slept on straw (paille)"` into `"poor prisoners who slept on straw"` is a regression.

### B4. Address recognition for seasoning beats

When a passage matches patterns like `"At no. X [street/square]"`, `"No. X was..."`, `"At [address]..."` AND a micro-narrative follows, emit a **seasoning beat** with:

- `poi_name` = the containing anchor (the square, the street, the neighborhood)
- `trigger_address` = the specific "no. X ..." string
- `beat_length_class` = `seasoning` (20–80 words)
- `beat_type` = `anecdote` / `character_story` / `architectural_detail` as appropriate

These seasoning beats are the Pariswalks-style circumnavigation primitive. Every book contains them; the extractor must know to produce them rather than conflating them into the parent POI's main beat.

### B5. Length discipline matched to source role

The extractor must NOT produce uniform ~75-word beats. It must:

- Produce **anchor-class beats (200–400w)** when the source provides a deep historical narrative on a major POI. Break only at natural transitions in the source prose.
- Produce **seasoning-class beats (20–80w)** when the source provides a one- or two-sentence vignette tied to an address or feature.
- Produce **micro-class beats (<20w)** when the source provides a walk-by factoid.

The current 75-word median is evidence that extraction compresses everything to a middle length. Prompt the extractor to read the source's own structural signals (paragraph length, sub-heads, whether the passage is a main narrative vs an aside) and match them.

### B6. Sidebar detection

Boxed content in the source (visual sidebars, typographically distinct inserts, parenthetical story blocks that digress from the main narrative) should be extracted as `beat_type: sidebar`. These are skippable in short-tour mode.

Heuristics for detection:
- Visually offset in the source (boxed, indented, different font in the PDF)
- Self-contained (doesn't reference surrounding narrative)
- Typically 80–200 words
- Example: Rough Guide "School for Scandal" on Abélard.

### B7. Source passage verbatim preservation

`source_passage` is already a field. Ensure:
- It contains the full verbatim source sentence(s) that the beat derives from, not a summary.
- Length sufficient for a downstream stitcher to re-read the original if it needs to retrieve detail the extraction compressed away.
- Ideally the minimum span that a neutral reader could map back to the beat's claims.

### B8. Cross-book claim deduplication (detail-preserving)

When the same POI is covered by multiple books, the extractor (or a post-extraction merge pass) must:

1. Deduplicate on **canonical claim form**, not raw text. "Marie-Antoinette imprisoned here 1793" is one claim, regardless of which book said it.
2. **Preserve complementary detail.** Book A's "peeling fleur-de-lys wallpaper" and Book B's "2 August to 16 October 1793" and Book C's "Danton and Robespierre occupying the cells adjacent to the Queen's" are different claims about the same cell — all three stay.
3. Record which books contributed which claims via `source_attribution` (already exists — may need per-claim granularity instead of per-beat).

**Why:** this is the superpower of multi-book ingest. Rough Guide + Frommer's + Pariswalks + Vallois each contribute *different* angles on the Conciergerie. Naive dedup would drop 3/4 of the material. Claim-level dedup keeps complementary detail while eliminating actual repetition.

### B9. POI assignment must be location-anchored

Current data has the Fersen/invisible-ink beat attached to the Conciergerie, but the anecdote happens at no. 115 rue Saint-Honoré. If a listener stops at the Conciergerie, this audio plays at the wrong place.

**Rule:** a beat's `poi_name` + optional `trigger_address` must identify the **geographic location where the listener should be when this beat plays**. Thematic association is captured via `entities` and `lens`, not via `poi_name`.

If the Fersen anecdote is thematically about Marie-Antoinette's Conciergerie imprisonment but physically happens at no. 115 rue Saint-Honoré, extract it as a seasoning beat at rue Saint-Honoré with `entities: [Marie-Antoinette, Fersen, Conciergerie]` — not attached to the Conciergerie POI.

---

## Validation checklist (before running the full batch)

Before committing the updated extractor to all 6 remaining books, validate on one test book. Recommend **Pariswalks** as the test — it's the hardest case for the new requirements (address-level seasoning, long anchor essays, inline French texture, sit-down staging). If the extractor handles Pariswalks Walk 4 well, it will handle the others.

Pass the following checks on a single-book extraction of Pariswalks:

- [ ] **Sub-location coverage:** Place des Vosges produces ≥5 beats with distinct `sub_location` values (at minimum: square-center, NW-corner-Ma-Bourgogne, synagogue-no-14, Hugo-museum-no-6, Pavillon-du-Roi). Not all on same sub_location.
- [ ] **Address-level seasoning:** ≥10 beats with `trigger_address` populated (no. 2, 6, 8, 14, 16, etc.), regardless of length class. Rationale: Pariswalks delivers some addresses as genuine one-liner vignettes (Gautier plaque, Vieux-Pont one-sentence mention) AND some as 150–300w essays (Hotel de Chaulnes at no. 9, Rochebaron at no. 13, Hugo's residence at no. 6). Per B5's asymmetric rule (don't demote richer content to fit a seasoning target), the longer address-anchored beats correctly land in `mid` or `anchor`. The underlying intent — Pariswalks-style circumnavigation primitive with address-level GPS triggers — is satisfied as long as ≥10 beats carry `trigger_address`.
- [ ] **Length distribution:** corpus has a mix — some `anchor` class (200–400w), plenty of `mid` and `seasoning`. Not all clustered at 75w. Rough target: anchor 10%, mid 40%, seasoning 45%, micro 5%.
- [ ] **Inline French preservation:** spot-check 10 beats. If the source contained `"pailleux (straw-sleeper prisoners)"` or similar, the word `pailleux` is in `script_body` AND in `inline_foreign_phrases`. Paraphrases away = fail.
- [ ] **Physical cues:** every beat at a tier-3+ POI with a visible feature in the source passage has `physical_cues` populated. 100% on tier-3+, not 61%.
- [ ] **Sit-down staging:** at least one `stop_orientation` beat at Place des Vosges. Text matches Pariswalks' opening sensory-staging pattern.
- [ ] **POI assignment geography:** spot-check beats with named addresses. `poi_name` matches the physical location where audio should play, not the thematic topic.
- [ ] **Claim dedup (pending book 2):** run ingest of Rough Guide Walk or chapter on Place des Vosges; verify beats about facts already covered by Pariswalks merge into multi-book-attributed claims, while genuinely new detail (a new date, a new named person) survives.

If any of these fail, iterate the prompt before the batch.

---

## What this explicitly is NOT

- **Not a new tour-builder design.** Zero changes to runtime selection, scoring, routing, or voice rules.
- **Not a schema overhaul.** Adding 6 fields, 3 beat types, 9 behavior rules. Existing fields unchanged.
- **Not a rules-from-observations translation.** Each requirement is traced to a specific source-study observation and a specific current gap. If an observation hasn't mapped cleanly to a field/rule, it stays in `source-study.md` as a future consideration.
- **Not a commitment to implement all 9 rules before shipping.** B1 (lens ceiling revision) is a North Star question and needs a separate decision. B8 (cross-book claim dedup) may live in a post-extraction merge pass rather than the extractor itself. B9 (POI location-anchoring) requires audit of existing 555 beats.

---

## Handoff

This doc is ready to share with the extractor-update chat. The extractor chat should:

1. Read this file and `source-study.md` for context.
2. Propose a revised `/unified-beat-extract` prompt implementing fields #1–#6 and behaviors B2, B3, B4, B5, B6, B7, B9.
3. Flag B1 (lens ceiling) to the user for a North Star decision before implementing.
4. Plan B8 (cross-book dedup) as a separate merge pass, not an in-extractor change.
5. Run the validation checklist on a single-book test (Pariswalks) before batch.

No tour-builder work until the new extractor ships and the validation checklist passes.
