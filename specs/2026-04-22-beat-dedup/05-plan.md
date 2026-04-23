# Plan: Duplicate Beat Prevention

**Date:** 2026-04-22
**Status:** Ready for implementation
**Source artifacts:** [01-scope.md](01-scope.md) · [02-spec.md](02-spec.md) · [03-scopes.md](03-scopes.md) · [04-red-team.md](04-red-team.md)
**Thinking mode:** Implementation engineer

---

## Operating rules

- One scope per session. `/clear` between scopes.
- One commit per scope. Commit message: `Scope N: <scope name>`.
- Two failed corrections in the same session → `/clear`, rewrite scope prompt incorporating the failure, restart.
- All verification commands for the scope and a full `pytest tests/ -x` must pass before committing.
- Never mutate `data/paris/beats.json` during verification. Work against `tests/fixtures/beats_multi_chunk.json` or `/tmp` copies. The live migration in Scope 1 task 5 is the one exception and has its own pre-flight safeguards.

---

## Part D — Best practices implementation checklist (covers all scopes)

Derived from the 04-red-team audit. Each scope's Part C prompt references the applicable rows.

| # | Practice | Where (scope / task) | How to verify |
|---|---|---|---|
| BP-1 | Pin `datasketch` in `requirements.txt` with upper bound; no unpinned deps | Scope 3, Task 1 | `grep '^datasketch' requirements.txt` matches `datasketch>=1.6.4,<2.0` |
| BP-2 | Run dep CVE scan (`pip-audit` or `safety check`) after adding datasketch | Scope 3, Task 1 | CI command exits 0; output attached to scope verify |
| BP-3 | Haiku API key is read only from `ANTHROPIC_API_KEY` env var — never hardcoded, never logged, never written to `_dedup_review/*` | Scope 3, Tasks 3, 4 | `grep -rI "sk-ant\|ANTHROPIC_API_KEY" scripts/ .claude/commands/beat-dedup.md` finds only `os.environ` reads; test verifies report files contain no `sk-` or key-shaped strings |
| BP-4 | `.gitignore` excludes `data/*/_dedup_review/*.md`; keeps `_log.jsonl` tracked | Scope 3, Task 4 | `git check-ignore data/paris/_dedup_review/2026-04-22T*.md` exits 0; `git check-ignore data/paris/_dedup_review/_log.jsonl` exits 1 |
| BP-5 | Haiku response parsed through strict JSON schema enforcing 4-value enum; parse fail → one retry → fallback label + `_parse_failed: true` | Scope 3, Task 3 | `tests/test_beat_dedup.py::test_haiku_parse_fail_falls_back` passes |
| BP-6 | Migration script aborts if `git status --porcelain data/paris/beats.json data/paris/book-log.json` is non-empty; writes `beats.json.pre-migration` snapshot before any mutation | Scope 1, Task 4 | `tests/test_beat_migration.py::test_migration_requires_clean_git` passes |
| BP-7 | Atomic-commit helper rolls back on validator fail, leaving both `beats.json` and `book-log.json` byte-identical | Scope 2, Tasks 1, 2 | `tests/test_atomic_commit.py::test_rollback_byte_identical` asserts pre/post sha256 equality |
| BP-8 | `/beat-wipe` never deletes beats with `source_chunk_slug == legacy_ambiguous` | Scope 2, Task 5 | `tests/test_beat_wipe.py::test_legacy_ambiguous_never_wiped` passes |
| BP-9 | `validate_beats.py` is strictly single-file-path scoped — no cross-city or global state reads | Scope 1, Task 2 | `tests/test_beat_validation.py::test_validator_city_isolated` runs against two different city fixtures in sequence; neither sees the other's beats |
| BP-10 | No production code carries test-only CLI flags (e.g. `--commit-with-planted-collision`) | Scope 2, Task 1 | `grep -rE "planted|test_only|--TEST" scripts/beats_io.py` returns nothing |

---

## Scope 1: Hash, Validator, Migration, Pre-Upload Gate

**Goal:** Land the dedup data hygiene foundation — new fields on `NarrativeBeatCreate`, a strict validator CLI, a branched idempotent migration, and the `/upload` pre-flight gate. After this scope, the 555-beat Paris corpus carries `script_body_hash`, `book_slug`, `topic_slug`, `city_name`, and `source_chunk_slug` on every beat, and `/upload` hard-blocks when the validator fails.

### Part A — Task breakdown (Scope 1)

1. **Extend `NarrativeBeatCreate`** (`src/api/models/nodes.py`)
   - **Do:** Add fields `script_body_hash: str = ""`, `book_slug: str = ""`, `topic_slug: str = ""`, `city_name: str = ""`, `source_chunk_slug: str = ""`. Add `@model_validator(mode="after")` that computes `script_body_hash` from `script_body` when empty, and raises if present-but-wrong.
   - **Don't touch:** Existing field defaults; other Pydantic models in the file; the `CREATE_MODELS` dict mapping (fields flow through automatically).
   - **Success check:** `.venv/bin/python -c "from src.api.models.nodes import NarrativeBeatCreate; b=NarrativeBeatCreate(script_body='Hello world'); assert b.script_body_hash; print(b.script_body_hash)"` prints the SHA-256 of `hello world`.

2. **Build `scripts/validate_beats.py`**
   - **Do:** CLI takes one positional arg (path to a beats.json). Loads JSON, applies two checks: (a) `script_body_hash` uniqueness across all beats; (b) identity-tuple `(city_name, poi_name, lens, book_slug, topic_slug)` uniqueness with `legacy_unknown` wildcard semantics (two rows both `legacy_unknown` in `book_slug` OR `topic_slug` position do NOT collide with each other). Prints each collision with full beat IDs on failure; exits 1. Single-file-path scoped — no global reads (BP-9).
   - **Don't touch:** `src/api/models/nodes.py` validators (the collection-level check lives in this script, not Pydantic).
   - **Success check:** Runs on `tests/fixtures/beats_multi_chunk.json` (built in task 3) and a single-beat valid fixture.

3. **Build `tests/test_beat_validation.py` + fixtures**
   - **Do:** Create `tests/fixtures/beats_multi_chunk.json` (hand-crafted: 4 beats, covering valid, identity-collision, hash-collision, legacy-wildcard-no-collision cases) and `tests/fixtures/beats_london_min.json` (2 beats for BP-9 cross-city isolation test). Write pytest cases for: Pydantic field validation (hash auto-compute, hash-wrong rejection), CLI validator behavior (exit codes, wildcard semantics, hash uniqueness), and city isolation (`test_validator_city_isolated`).
   - **Don't touch:** Live data files.
   - **Success check:** `.venv/bin/pytest tests/test_beat_validation.py -v` all green.

4. **Build `scripts/migrate_beats_dedup_fields.py`**
   - **Do:** CLI takes path to a beats.json. Pre-flight: `git status --porcelain <beats.json> <book-log.json>` must be empty; writes `{beats.json}.pre-migration` snapshot before any mutation; both must succeed or script exits non-zero (BP-6). Then for each beat:
     - Branch on `_meta.prompt_version`:
       - `unified_v1` → `topic_slug` stays; `book_slug` parsed from `{city}_{poi_slug}_{lens}_{book_slug}_{topic_slug}` envelope by stripping known prefix/suffix.
       - Else (legacy) → parse both `book_slug` (suffix) and `topic_slug` (middle) from `{poi_slug}_{lens}_{topic_slug}_{book_slug}`. Slugify supports `Place de la Concorde` → `place_concorde` (drop common stopwords: de/la/du/des/le/les/l/d) AND `Châtelet` → `chatelet` (strip diacritics via `unicodedata.normalize('NFKD')`). Unparseable → `legacy_unknown`.
     - `city_name` ← `paris` (hard-code for this migration; only Paris is live).
     - `source_chunk_slug` ← scan the co-located `book-log.json`; for this beat's `poi_name`, find chunks in `chunks_processed` whose `pois_touched` contains it. If exactly one chunk → that chunk's `chunk` value. If ≥2 chunks → `legacy_ambiguous`. If zero → `legacy_unknown`.
     - `script_body_hash` ← SHA-256 of `re.sub(r'\s+', ' ', body.lower().strip())`.
     - Idempotent: never overwrites non-empty non-sentinel values.
   - **Don't touch:** `beats.json` entries that already carry all non-sentinel fields.
   - **Success check:** Against `/tmp/paris-beats-copy.json` (cp before running), after migration: `validate_beats.py` exits 0 and all 7 unified_v1 beats carry `book_slug == "around_and_about_paris"`.

5. **Run migration on live data, commit**
   - **Do:** Verify `git status` clean. `cp data/paris/beats.json /tmp/paris-beats-copy.json; cp data/paris/book-log.json /tmp/paris-log-copy.json`. Run migration against `/tmp/paris-beats-copy.json` first; assert validator passes post-migration on the copy. Only then run against live `data/paris/beats.json`. Commit the migrated file as part of Scope 1.
   - **Don't touch:** `poi-raw.json`, `areas.json`, `export/*` (unchanged).
   - **Success check:** `.venv/bin/python scripts/validate_beats.py data/paris/beats.json` exits 0.

6. **Wire `validate_beats.py` into `.claude/commands/upload.md`**
   - **Do:** Insert a new FIRST pre-flight step (before `pytest tests/test_export_consistency.py ...`): run `.venv/bin/python scripts/validate_beats.py data/{city_slug}/beats.json`. If exit code non-zero: STOP, print the validator's output verbatim, do not proceed.
   - **Don't touch:** The rest of `upload.md`; the other pre-flight tests; the MERGE/upload logic.
   - **Success check:** `grep -q "validate_beats" .claude/commands/upload.md`.

7. **Run full test suite**
   - **Do:** `.venv/bin/pytest tests/ -x`. All green.
   - **Success check:** Exit 0.

### Part B — Test definitions (Scope 1)

- **test_hash_auto_computed** — AC-4. `NarrativeBeatCreate(script_body="Foo")` produces correct SHA-256 of `foo` in `script_body_hash`.
- **test_hash_present_wrong_rejected** — AC-4. Passing `script_body_hash="bogus"` with mismatching body raises `ValidationError`.
- **test_validator_hash_collision** — AC-5. Fixture with two beats sharing `script_body_hash` → exit 1.
- **test_validator_identity_collision** — AC-3. Fixture with two beats sharing all 5 identity-tuple fields → exit 1.
- **test_validator_legacy_unknown_wildcard** — AC-12. Fixture with two legacy beats both `topic_slug=legacy_unknown`, same POI/lens/book → exit 0 (wildcard doesn't collide). But same hash → exit 1.
- **test_validator_city_isolated** — BP-9. Sequentially validate Paris fixture then London fixture; neither triggers errors from the other.
- **test_migration_branches_on_prompt_version** — AC-12. Fixture with 2 unified_v1 + 2 legacy beats → unified_v1 preserves `topic_slug`, parses `book_slug`; legacy parses both.
- **test_migration_requires_clean_git** — BP-6. Mock non-empty `git status` → migration exits non-zero, no mutation, no snapshot written.
- **test_migration_idempotent** — AC-12. Run twice, second run leaves file byte-identical.
- **test_migration_source_chunk_ambiguous** — AC-12. Fixture where a POI appears in 2 chunks' `pois_touched` → migrated beats for that POI get `source_chunk_slug: legacy_ambiguous`.

### Part C — Claude Code prompt (Scope 1)

```
You are implementing Scope 1 of the beat-dedup spec at
specs/2026-04-22-beat-dedup/. Goal: land the dedup data hygiene foundation
(hash, identity fields, validator, migration, upload gate) in one commit.

Read before starting:
- specs/2026-04-22-beat-dedup/01-scope.md
- specs/2026-04-22-beat-dedup/02-spec.md (acceptance criteria AC-3, AC-4, AC-5, AC-9, AC-12)
- specs/2026-04-22-beat-dedup/04-red-team.md (B-2, B-4 resolutions + BP-6, BP-9 items)
- specs/2026-04-22-beat-dedup/05-plan.md (this scope's Part A task list)
- src/api/models/nodes.py (NarrativeBeatCreate at line 158)
- .claude/commands/upload.md (pre-flight block at lines 14-23)
- data/paris/beats.json (first 3 entries — understand legacy vs unified_v1 shapes)
- data/paris/book-log.json (the POI→chunk mapping for migration task 4)

Tasks (follow Part A from 05-plan.md, in order):
1. Extend NarrativeBeatCreate with 5 new fields + computed-hash model validator.
2. Build scripts/validate_beats.py (identity-tuple + hash uniqueness, legacy_unknown wildcard, city-isolated).
3. Build tests/test_beat_validation.py + tests/fixtures/beats_multi_chunk.json + tests/fixtures/beats_london_min.json.
4. Build scripts/migrate_beats_dedup_fields.py (branched parser, git-clean preflight, snapshot, idempotent).
5. Run migration on /tmp copy first, assert passes, then run on live data/paris/beats.json.
6. Edit .claude/commands/upload.md to add validate_beats.py as the FIRST pre-flight step.
7. Run full test suite — all green.

What NOT to touch:
- Any file in data/ other than data/paris/beats.json (one mutation, in task 5, with a /tmp dry-run first).
- Other Pydantic models (POICreate, AreaCreate, etc.).
- The MERGE/upload logic in /upload beyond adding the pre-flight line.
- poi-raw.json, areas.json, export/*.

Best practices to apply (from 05-plan.md Part D):
- BP-6: migration script pre-flights git clean + writes snapshot.
- BP-9: validator is single-file-path scoped; test proves city isolation.
- BP-10: no test-only CLI flags in production scripts.

Verification commands (run all before committing):
.venv/bin/pytest tests/test_beat_validation.py -v
.venv/bin/python scripts/validate_beats.py data/paris/beats.json
.venv/bin/python -c "import json,hashlib,re; d=json.load(open('data/paris/beats.json')); n=lambda s: re.sub(r'\s+',' ',s.lower().strip()); bad=[b['beat_id'] for b in d if b['script_body_hash']!=hashlib.sha256(n(b['script_body']).encode()).hexdigest()]; assert not bad, bad; print('all hashes correct')"
.venv/bin/python -c "import json; d=json.load(open('data/paris/beats.json')); uni=[b for b in d if b.get('_meta',{}).get('prompt_version')=='unified_v1']; assert all(b['book_slug']=='around_and_about_paris' for b in uni); print('unified_v1 book_slug: PASS')"
.venv/bin/python -c "import json; d=json.load(open('data/paris/beats.json')); assert all(b.get('city_name')=='paris' for b in d); print('city_name: PASS')"
.venv/bin/python -c "import json; d=json.load(open('data/paris/beats.json')); parseable=sum(1 for b in d if b['topic_slug']!='legacy_unknown'); print(f'topic parseability: {parseable}/{len(d)}')"
grep -q "validate_beats" .claude/commands/upload.md && echo "upload gate: PASS"
.venv/bin/pytest tests/ -x

Commit message: "Scope 1: Hash, validator, migration, pre-upload gate"

Before starting, confirm you understand the full scope and flag any conflicts
with the existing codebase or assumptions you are making.
```

---

## Scope 2: Refuse-on-Reprocess, Atomic Write, /beat-wipe

**Goal:** Harden the extraction path to hard-refuse on re-process, commit new beats atomically (rollback on validator fail), and provide a safe `/beat-wipe` skill for the chunks users need to re-extract. After this scope, the refuse→wipe→re-extract loop is safe; a mid-commit failure leaves both `beats.json` and `book-log.json` byte-identical.

### Part A — Task breakdown (Scope 2)

1. **Build `scripts/beats_io.py` — atomic commit helper**
   - **Do:** Export `commit(new_beats, beats_path, log_path, chunk_entry)` function:
     - Write merged list (existing + new) to `{beats_path}.staging`.
     - Run `validate_beats.py` against the staged file.
     - On pass: `os.replace(staging, beats_path)` (atomic on same filesystem), then append `chunk_entry` to log file atomically (write log to `.staging`, replace).
     - On fail: delete staging, do NOT touch `beats_path` or `log_path`. Raise `ValidationError` with conflict report.
   - **Don't touch:** `data/paris/*` during dev; operate on fixtures/tmpdir only.
   - **Don't add:** Any `--test-only` or `--planted-collision` CLI flag (BP-10). The rollback proof lives in pytest, not a prod flag.
   - **Success check:** Module imports cleanly; pytest case (task 2) demonstrates rollback.

2. **Write `tests/test_atomic_commit.py` — rollback proof**
   - **Do:** `test_rollback_byte_identical` (BP-7): seed `tmp_path/beats.json` + `tmp_path/book-log.json` with known-valid content; record pre-sha256 of both; call `beats_io.commit(...)` with a new-beats list containing a hash-collision against the seed; assert `ValidationError` raised; assert post-sha256 equals pre-sha256 for both files; assert no `beats.json.staging` lingers.
   - Also: `test_commit_happy_path` (both files update atomically on valid input).
   - **Success check:** `pytest tests/test_atomic_commit.py -v` green.

3. **Harden `.claude/commands/unified-beat-extract.md` PRE-CHECK (AC-1)**
   - **Do:** Replace the "If the EXACT same chunk was already processed, STOP and tell the user..." paragraph (lines 38-44) with hard-refuse language: "If this `{book_title, author, chunk}` tuple already appears in `book-log.json`, STOP, print `'Refused: {chunk} was processed on {date} ({N} beats extracted). Run /beat-wipe {book_slug} --chunk {chunk_slug} first if you want to re-extract.'`, and exit non-zero. Do not proceed to any extraction work."
   - **Don't touch:** The rest of the skill prompt (extraction rules, PHASE 1-4, enrichment fields).
   - **Success check:** `grep -q "Refused:" .claude/commands/unified-beat-extract.md`.

4. **Integrate `beats_io.commit` into unified-beat-extract write step**
   - **Do:** In the skill's output-writing instructions (the "Write output" section near the end), replace the direct append-to-beats.json language with: "Call `scripts.beats_io.commit(new_beats=..., beats_path='data/{city_slug}/beats.json', log_path='data/{city_slug}/book-log.json', chunk_entry={...})`. If commit raises, do NOT retry or partial-write; print the conflict report and stop."
   - **Don't touch:** The new-beats generation logic upstream.
   - **Success check:** `grep -q "beats_io.commit\|beats_io\\.commit" .claude/commands/unified-beat-extract.md`.

5. **Build `.claude/commands/beat-wipe.md` + `scripts/wipe_beats.py`**
   - **Do:** Create the skill (markdown prompt) and the backing script. Script signature: `wipe_beats.py {book_slug} --chunk {chunk_slug} --apply`. Semantics:
     - Select beats where `book_slug == {book_slug}` AND `source_chunk_slug == {chunk_slug}` AND `source_chunk_slug != 'legacy_ambiguous'` (BP-8).
     - Remove them from `beats.json` via `beats_io.commit`'s atomic write helper (reuse from task 1 — new-list = remaining-beats, log_entry = remove-the-matching-chunk-entry).
     - Print summary (beats removed, chunk entry removed).
     - Re-run on already-wiped chunk → print `already clean: no matching beats or log entry` and exit 0.
     - Without `--apply`: dry-run, prints what would be removed.
   - **Don't touch:** Any beat whose `source_chunk_slug == legacy_ambiguous` (enforced by the selection filter).
   - **Success check:** `scripts/wipe_beats.py paris/around-and-about-paris --chunk chunk-15-5th-arr-val-de-grace` against `/tmp/beats-copy.json` shows the 7 unified_v1 VdG beats in the plan.

6. **Write `tests/test_beat_wipe.py` + `tests/test_extract_refuse.py`**
   - **Do:** wipe tests: `test_wipe_removes_exact_chunk`, `test_wipe_ignores_legacy_ambiguous` (BP-8), `test_wipe_idempotent_byte_identical`, `test_wipe_dry_run_no_mutation`. Refuse tests are assertions about the `.claude/commands/unified-beat-extract.md` text (the skill itself isn't runnable in pytest, so test that the required string tokens exist): `test_refuse_check_present_in_skill`, `test_refuse_message_includes_wipe_command`.
   - **Success check:** Both test files green.

7. **Run full test suite**
   - **Do:** `.venv/bin/pytest tests/ -x`.
   - **Success check:** Exit 0.

### Part B — Test definitions (Scope 2)

- **test_rollback_byte_identical** — AC-11. Proof of atomic rollback on validator fail.
- **test_commit_happy_path** — AC-11. Valid new-beats list → both files update; new-beat hashes match.
- **test_wipe_removes_exact_chunk** — AC-2. Fixture with beats from 3 chunks; wipe one → exactly those beats removed.
- **test_wipe_ignores_legacy_ambiguous** — AC-2 + BP-8. Fixture with a `legacy_ambiguous` beat whose `book_slug` matches the wipe target → beat survives.
- **test_wipe_idempotent_byte_identical** — AC-2. Re-running on already-wiped → pre/post sha256 equal.
- **test_wipe_dry_run_no_mutation** — AC-2. Without `--apply` → file unchanged, output shows plan.
- **test_refuse_check_present_in_skill** — AC-1. Grep-style assertion that the PRE-CHECK section contains hard-refuse language.
- **test_refuse_message_includes_wipe_command** — AC-1. Required error string format.

### Part C — Claude Code prompt (Scope 2)

```
You are implementing Scope 2 of the beat-dedup spec at
specs/2026-04-22-beat-dedup/. Scope 1 must be committed and green before you
start. Goal: refuse-on-reprocess + atomic commit + /beat-wipe, so the
refuse→wipe→re-extract loop is safe.

Read before starting:
- specs/2026-04-22-beat-dedup/02-spec.md (AC-1, AC-2, AC-11)
- specs/2026-04-22-beat-dedup/04-red-team.md (B-1, B-3, B-4 resolutions + BP-7, BP-8, BP-10 items)
- specs/2026-04-22-beat-dedup/05-plan.md (this scope's Part A task list)
- .claude/commands/unified-beat-extract.md (PRE-CHECK at lines 38-44; output-writing section near end)
- scripts/validate_beats.py (Scope 1 output — will be called by the new beats_io.commit)
- src/api/models/nodes.py (NarrativeBeatCreate extended in Scope 1)

Tasks (follow Part A from 05-plan.md, in order):
1. Build scripts/beats_io.py with the atomic commit() helper. NO --test-only CLI flags.
2. Write tests/test_atomic_commit.py (rollback-byte-identical proof + happy path).
3. Harden .claude/commands/unified-beat-extract.md PRE-CHECK from soft-stop to hard-refuse.
4. Integrate beats_io.commit into the skill's write step.
5. Build .claude/commands/beat-wipe.md + scripts/wipe_beats.py (chunk-only, dry-run default, never touches legacy_ambiguous).
6. Write tests/test_beat_wipe.py + tests/test_extract_refuse.py.
7. Run full test suite.

What NOT to touch:
- data/paris/* during development — all tests against tests/fixtures/ or tmp_path.
- scripts/validate_beats.py (Scope 1's deliverable — only call it, don't edit it).
- .claude/commands/upload.md (Scope 1 wired it; out of scope here).
- /beat-dedup skill and scripts (Scope 3).
- Any --book flag on /beat-wipe (user Q-2: explicitly rejected — chunk-level only).

Best practices to apply (from 05-plan.md Part D):
- BP-7: atomic rollback byte-identical.
- BP-8: /beat-wipe never deletes legacy_ambiguous beats.
- BP-10: no test-only CLI flags in production scripts. The rollback proof
  is a pytest case that uses tmp_path, not a production --planted-collision
  flag.

Verification commands (run all before committing):
.venv/bin/pytest tests/test_atomic_commit.py tests/test_beat_wipe.py tests/test_extract_refuse.py -v
grep -q "Refused:" .claude/commands/unified-beat-extract.md && echo "refuse wording: PASS"
grep -q "beats_io" .claude/commands/unified-beat-extract.md && echo "atomic write wired: PASS"
test -f .claude/commands/beat-wipe.md && echo "wipe skill: PASS"
grep -Ev "planted|test_only|--TEST" scripts/beats_io.py > /dev/null && echo "no test-only flags: PASS"
# Wipe dry-run against /tmp copy:
cp data/paris/beats.json /tmp/beats-wipe-test.json
cp data/paris/book-log.json /tmp/log-wipe-test.json
.venv/bin/python scripts/wipe_beats.py paris/around-and-about-paris --chunk chunk-15-5th-arr-val-de-grace --beats-path /tmp/beats-wipe-test.json --log-path /tmp/log-wipe-test.json
# (no --apply; expect dry-run output listing the 7 unified_v1 VdG beats)
.venv/bin/pytest tests/ -x

Commit message: "Scope 2: Refuse-on-reprocess, atomic write, /beat-wipe"

Before starting, confirm you understand the full scope and flag any conflicts
with the existing codebase or assumptions you are making.
```

---

## Scope 3: /beat-dedup + VdG Cleanup

**Goal:** Ship the human-reviewed semantic dedup pass — MinHash candidate-pair finder, Haiku-as-judge with strict enum enforcement, markdown report + interactive-CLI apply. Then run it live against Val-de-Grace's 12 beats as end-to-end validation. After this scope, AC-8 holds: no two VdG beats score Jaccard ≥ 0.8 without explicit `dedup_reviewed: true KEEP BOTH`.

### Part A — Task breakdown (Scope 3)

1. **Add `datasketch` to `requirements.txt`; run CVE scan**
   - **Do:** Append `datasketch>=1.6.4,<2.0` to `requirements.txt`. Run `.venv/bin/pip install -r requirements.txt`. Run `.venv/bin/pip install pip-audit && .venv/bin/pip-audit --desc` (or `safety check`) — attach output to commit.
   - **Success check:** `.venv/bin/python -c "import datasketch; print(datasketch.__version__)"` prints a version ≥ 1.6.4.

2. **Build `scripts/dedup_pairs.py`**
   - **Do:** CLI: `dedup_pairs.py {city} [--threshold 0.5] [--num-perm 128] [--shingle-size 5]`. Reads `data/{city}/beats.json`. For each beat: normalize body (`re.sub(r'\s+',' ', body.lower().strip())`), generate 5-gram word shingles, build MinHash. Insert all into a `MinHashLSH` with the threshold. Query each beat against the LSH, collect candidate pairs (deduplicate by sorted-tuple). For each pair compute exact Jaccard on shingle sets. Emit JSON to stdout: `[{"beat_a": id, "beat_b": id, "jaccard": 0.74}, ...]`.
   - **Don't touch:** `beats.json` itself; this is read-only.
   - **Success check:** On `tests/fixtures/beats_multi_chunk.json`, with 2 deliberately near-duplicate beats → pair surfaced with Jaccard ≥ 0.5.

3. **Build `scripts/beat_dedup_judge.py`** (Haiku caller)
   - **Do:** Function `classify_pair(beat_a, beat_b) -> {classification: enum, reasoning: str, _parse_failed: bool}`. Uses `anthropic.Anthropic()` client reading `ANTHROPIC_API_KEY` from env (BP-3). Uses Messages API with structured output — tool-use pattern: define a tool `record_classification` with an `input_schema` that enforces `classification` ∈ the 4-value enum. Model: `claude-haiku-4-5-20251001`. On tool-call response missing/invalid: one retry with stricter prompt ("You MUST return one of exactly these four values: ..."). On second fail: return `{classification: "different_story", reasoning: "parse failed: <error>", _parse_failed: true}`. Never logs the API key or any env value; error messages contain no secrets.
   - **Don't touch:** Shared state beyond the function's locals.
   - **Success check:** Pytest (task 6) with a mocked `anthropic.Anthropic` client verifies happy path, retry, and final fallback.

4. **Build `.claude/commands/beat-dedup.md` + orchestrator `scripts/beat_dedup.py`**
   - **Do:** Skill markdown describes the workflow. Orchestrator script runs: `dedup_pairs.py {city}` → for each pair, `beat_dedup_judge.classify_pair(...)` → write markdown report to `data/{city}/_dedup_review/{iso_ts}.md` (matching the spec's example format, with parse-failed pairs at top). Then enter interactive CLI loop — for each pair print summary + recommendation + prompt `[a]ccept / [s]kip / [c]ombine / [k]eep-both / [q]uit:`. On each decision, apply the mutation to an in-memory beats list; on `q`, write resumable state file `{iso_ts}.state.json` with remaining pairs and exit. After all pairs decided (or resumed to completion), call `beats_io.commit(new_beats=mutated_list, ...)` for atomic write; append one line per applied decision to `data/{city}/_dedup_review/_log.jsonl`. Add `.gitignore` entry for `data/*/_dedup_review/*.md` (keep `_log.jsonl` tracked) (BP-4).
   - **Don't touch:** Existing beats that aren't in any ≥0.5 pair.
   - **Apply semantics:** SKIP → remove the new beat (the one with the newer `_meta.generated_at`); INSERT → no-op; COMBINE → prompt user to paste merged text via stdin multi-line input, replace both with one new beat carrying the merged text, new hash, user's approved lens/tags, and both prior `beat_id`s in a new field `merged_from: [id_a, id_b]`; KEEP BOTH → set `dedup_reviewed: true` on both.
   - **Success check:** `grep -q "_dedup_review" .gitignore`; `test -f .claude/commands/beat-dedup.md`.

5. **Build `scripts/verify_vdg_ac8.py`**
   - **Do:** Reads `data/paris/beats.json`, filters to Val-de-Grace beats, computes exact pairwise Jaccard on 5-gram shingles, asserts no pair ≥ 0.8 unless both beats carry `dedup_reviewed: true` with action `KEEP BOTH` (look in `_dedup_review/_log.jsonl` to confirm action).
   - **Success check:** Exits 0 after the live VdG cleanup (task 7).

6. **Write `tests/test_beat_dedup.py`**
   - **Do:**
     - `test_minhash_surfaces_known_pair` — fixture with 2 deliberately-near-duplicate beats → pair found ≥0.5.
     - `test_minhash_ignores_distant_beats` — fixture with 2 beats sharing no 5-grams → no pair.
     - `test_judge_happy_path` — mocked Haiku tool-call returns valid classification → function returns it.
     - `test_haiku_parse_fail_falls_back` (BP-5) — mocked Haiku returns junk first, valid on retry → retry succeeds; mocked Haiku returns junk both times → fallback with `_parse_failed: true`.
     - `test_apply_skip_removes_newer` — fixture with two beats, older + newer `_meta.generated_at`; SKIP action → newer beat gone, older remains.
     - `test_apply_combine_replaces_both` — fixture pair + user merged-text input → one beat remains with `merged_from` field.
     - `test_apply_keep_both_flags_both` — KEEP BOTH → both beats survive with `dedup_reviewed: true`.
     - `test_audit_log_matches_mutation` — after apply, `_log.jsonl` lines 1:1 match applied mutations.
     - `test_report_contains_no_api_key` — BP-3 regression: `ANTHROPIC_API_KEY=sk-ant-TEST-KEY-DO-NOT-LEAK` in env during a dedup run against fixtures → `_dedup_review/*.md` + `_log.jsonl` contain no occurrence of `sk-ant`.
   - **Success check:** All green.

7. **Live VdG cleanup run**
   - **Do:** Verify `git status` clean. Run `.venv/bin/python scripts/beat_dedup.py paris`. Review report with user; user approves each pair interactively. Apply runs atomically. Commit resulting `beats.json` + `_dedup_review/_log.jsonl` as part of this scope.
   - **Don't touch:** Non-VdG beats (only expected dedup candidates are at VdG per 01-scope context; if the LSH surfaces unexpected non-VdG pairs, stop and ask the user).
   - **Success check:** `.venv/bin/python scripts/verify_vdg_ac8.py` exits 0.

8. **Run full test suite**
   - **Do:** `.venv/bin/pytest tests/ -x`.
   - **Success check:** Exit 0.

### Part B — Test definitions (Scope 3)

- **test_minhash_surfaces_known_pair** — AC-6.
- **test_minhash_ignores_distant_beats** — AC-6.
- **test_judge_happy_path** — AC-6.
- **test_haiku_parse_fail_falls_back** — BP-5 + R-4.
- **test_apply_skip_removes_newer** — AC-7.
- **test_apply_combine_replaces_both** — AC-7.
- **test_apply_keep_both_flags_both** — AC-7.
- **test_audit_log_matches_mutation** — AC-7.
- **test_report_contains_no_api_key** — BP-3.
- **test_vdg_ac8_holds** (live assertion, run once after cleanup) — AC-8.

### Part C — Claude Code prompt (Scope 3)

```
You are implementing Scope 3 of the beat-dedup spec at
specs/2026-04-22-beat-dedup/. Scopes 1 and 2 must be committed and green
before you start. Goal: semantic dedup pass (MinHash + Haiku) with interactive-
CLI approval, followed by live Val-de-Grace cleanup.

Read before starting:
- specs/2026-04-22-beat-dedup/02-spec.md (AC-6, AC-7, AC-8; interactive-CLI-only approval per AC-7)
- specs/2026-04-22-beat-dedup/04-red-team.md (R-4, R-5 resolutions + BP-1..5 items)
- specs/2026-04-22-beat-dedup/05-plan.md (this scope's Part A task list)
- scripts/beats_io.py (Scope 2 — atomic commit helper, reused for apply)
- scripts/validate_beats.py (Scope 1 — called by commit)
- data/paris/beats.json (12 Val-de-Grace beats — 5 legacy + 7 unified_v1 — are the live workload in task 7)

Tasks (follow Part A from 05-plan.md, in order):
1. Pin datasketch in requirements.txt; install; run pip-audit.
2. Build scripts/dedup_pairs.py (MinHash LSH, 5-gram word shingles, configurable threshold).
3. Build scripts/beat_dedup_judge.py (Haiku with structured tool-call output, retry, fallback).
4. Build .claude/commands/beat-dedup.md + scripts/beat_dedup.py orchestrator; add .gitignore entry.
5. Build scripts/verify_vdg_ac8.py (live AC-8 assertion).
6. Write tests/test_beat_dedup.py (all 9 test cases listed in Part B).
7. Run the dedup skill live against VdG — user approves pairs interactively; apply atomically via beats_io.commit.
8. Run full test suite.

What NOT to touch:
- scripts/validate_beats.py, scripts/beats_io.py, migration script (all from Scopes 1 & 2).
- /unified-beat-extract, /beat-wipe (Scopes 1 & 2).
- Non-VdG beats in task 7 — if the LSH surfaces pairs outside VdG, STOP and
  ask the user before proceeding.

Best practices to apply (from 05-plan.md Part D):
- BP-1: datasketch pinned with upper bound.
- BP-2: run pip-audit; attach clean output to commit or raise any findings.
- BP-3: ANTHROPIC_API_KEY read only from env; never logged; never in report
  files. Test test_report_contains_no_api_key enforces this.
- BP-4: .gitignore data/*/_dedup_review/*.md; keep _log.jsonl tracked.
- BP-5: Haiku structured output; retry once; fallback label + _parse_failed.

Verification commands (run all before committing):
.venv/bin/python -c "import datasketch; print('datasketch:', datasketch.__version__)"
.venv/bin/pip-audit --desc | grep -E "datasketch|anthropic" || echo "no dep CVEs in our new deps"
.venv/bin/pytest tests/test_beat_dedup.py -v
.venv/bin/python scripts/verify_vdg_ac8.py
git check-ignore data/paris/_dedup_review/2026-04-22T00-00-00Z.md && echo "report gitignored: PASS"
git check-ignore data/paris/_dedup_review/_log.jsonl && echo "UNEXPECTED: log gitignored" || echo "log tracked: PASS"
.venv/bin/python -c "import json; lines=[json.loads(l) for l in open('data/paris/_dedup_review/_log.jsonl')]; req={'ts','pair','jaccard','classification','action'}; assert all(req <= set(l) for l in lines); print(f'audit log well-formed: {len(lines)} entries')"
.venv/bin/pytest tests/ -x

Commit message: "Scope 3: /beat-dedup skill + Val-de-Grace cleanup"

Before starting, confirm you understand the full scope and flag any conflicts
with the existing codebase or assumptions you are making.
```

---

## North star final gate

All three scopes have been re-checked against `specs/NORTHSTAR.md` per 04-red-team Section 5. No conflicts. The "permissive miner" principle is honored: validation runs at the commit-to-disk boundary, not inside the extraction LLM prompt.

## Next step

`/clear`, then start Scope 1 by pasting its Part C prompt into a fresh Claude Code session.
