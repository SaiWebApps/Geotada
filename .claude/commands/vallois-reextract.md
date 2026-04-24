---
description: Orchestrate one chunk of the Vallois (Around and About Paris) re-extraction campaign under the unified_v2 prompt. Reads specs/2026-04-23-vallois-reextract/state.json, picks the next pending chunk (or a user-specified one), runs /beat-wipe + /unified-beat-extract, validates, and commits atomically with state update.
---

You are the orchestrator for the **Vallois re-extraction campaign** — applying the unified_v2 extraction prompt to the 22 chunks of *Around and About Paris* (Thirza Vallois), one chunk per invocation.

The v2 prompt and all B-rules live in `.claude/commands/unified-beat-extract.md`. This skill adds a thin state+pacing layer on top of it.

## Preflight (every invocation)

1. Read `specs/2026-04-23-vallois-reextract/state.json` — campaign state.
2. Run `git status --porcelain data/paris/beats.json data/paris/book-log.json specs/2026-04-23-vallois-reextract/state.json` — all three must be clean. If dirty, stop and surface to the user.

## Pick the chunk

- If the user passed an argument (e.g. `05`, `chunk-05`, or a full slug), target that chunk specifically.
- Otherwise, pick the first chunk with `status: "pending"` from the `chunks` array in state.json.
- If no pending chunks remain → report campaign complete. Suggest running `/beat-dedup paris` to reconcile the 92 legacy_ambiguous Vallois beats and the legacy-vs-v2 duplicates from chunks 01–04 (notably the Conciergerie Sanson beat).

Surface the plan to the user before executing: *"About to re-extract chunk-N ({title}). Wipe → read → extract → commit. Proceed?"* — wait for confirmation on the first run; subsequent runs in the same session can proceed directly if user said "continue".

## Execute

1. **Wipe** the chunk (removes any clean-chunk-assigned beats + the chunk's book-log entry; per BP-8 the `legacy_ambiguous` beats survive):

   ```bash
   .venv/bin/python scripts/wipe_beats.py paris/around-and-about-paris \
     --chunk {slug} --apply
   ```

2. **Read** the chunk file in full: `Books/Paris/around-and-about-paris/{file}`. Note that some chunk files contain OCR garbage past their real content end — mentally truncate at the last coherent paragraph.

3. **Extract** following the full `/unified-beat-extract` prompt in `.claude/commands/unified-beat-extract.md`. Apply phases 1–4, every B-rule, Fix 1 (one source sentence → one beat, source_passage minimum span), Fix 2 (trigger_address → non-empty physical_cues), asymmetric re-class per B5, B9 location-anchoring, the 5 new fields, the 3 new beat_types. Target 15–30 beats depending on source density.

4. **Dry-run validate** the in-memory beats list before writing:
   - Pydantic `NarrativeBeatCreate` accepts every beat (no schema errors).
   - Every beat's word count falls inside its declared `beat_length_class` range (anchor 200–400, mid 80–200, seasoning 20–80, micro <20). If out of range, re-class per the asymmetric rule.
   - No two beats share the first real sentence of `source_passage` (Fix 1 regression).
   - Every beat with non-null `trigger_address` has non-empty `physical_cues` (Fix 2 regression).
   - Every inline_foreign_phrases entry's `phrase` appears verbatim in `script_body` (B3 regression).
   - `subject_tag` ≤ 3 space-separated words — use kebab-hyphenation for proper-noun French compounds (`poule-au-pot`, `pavillon-de-la-reine`).

5. **Commit atomically** via `scripts.beats_io.commit` — writes `data/paris/beats.json` and `data/paris/book-log.json` together, or rolls back cleanly on validator fail.

6. **Post-commit check:** `.venv/bin/python scripts/validate_beats.py data/paris/beats.json` — must exit 0 (PASS).

## Update state + single git commit

Update the chunk's entry in `specs/2026-04-23-vallois-reextract/state.json`:
- `status` → `"complete"`
- `commit` → new sha (set after the git commit; easiest to run `git commit` first with just the two data files, then edit state.json and amend OR commit state.json separately — choose the latter to keep commits small and atomic per step).

Cleanest pattern:
1. `git add data/paris/beats.json data/paris/book-log.json`
2. `git commit -m "Vallois chunk-N ({title}) re-extract — N beats"` (with body below)
3. Get the new sha, update state.json's `commit` and `beats` fields
4. `git add specs/2026-04-23-vallois-reextract/state.json && git commit --amend --no-edit` to fold state into the same commit

Commit message template:
```
Vallois chunk-N ({title}) re-extract — N beats

length-class: a anchor / b mid / c seasoning / d micro
pois: <list, noting any new_pois_flagged>
sub_locations: <list>
notable: <anything worth calling out — preserved-verbatim quotes,
         split patterns, unusual anecdotes, B9 reassignments, etc.>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Handoff report

After commit, report to the user:
- Commit sha.
- Beats count + length-class distribution.
- POIs touched + any `new_pois_flagged`.
- Any notable preservations, B9 reassignments, or source-material surprises.
- Suggest the next chunk (or flag campaign complete).

## Rules

- **One chunk per invocation.** Never batch. Each chunk gets a fresh mental pass; context degrades across a long session.
- **Never mutate beats.json outside `beats_io.commit`**. The atomic helper is the only safe write path.
- **If any validator fails** — stop, report, do not proceed to the next chunk.
- **Must-preserve elements.** When a chunk contains material of the Sanson caliber (specific numbers + named quotes + traceable chains), apply the v2 split-and-preserve pattern: one anchor for the main narrative, one mid/seasoning for the standalone anecdote, with `narrative_function: callback` wiring the second to the first. Document preserved specifics in the commit body.
- **B9 vigilance.** The Fersen fix (chunk-02) was the canonical case: a beat thematically about one POI but physically at another. If a similar pattern surfaces, use `poi_name` for physical location, `entities` for thematic links, and flag in the commit body.
- **Slug integrity.** Use the slug from state.json — it matches book-log.json's in-data form, which may differ from the on-disk filename (chunk-01 is the only known case currently).
