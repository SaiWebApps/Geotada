# Scopes: Duplicate Beat Prevention

**Date:** 2026-04-22
**Status:** Approved — ready for Stage 4 (red team)
**Source spec:** [02-spec.md](02-spec.md)

---

## AC → scope mapping

| AC | Scope |
|---|---|
| AC-3, AC-4, AC-5, AC-9, AC-12 | Scope 1 |
| AC-1, AC-2, AC-11 | Scope 2 |
| AC-6, AC-7, AC-8 | Scope 3 |
| AC-10 | Cross-cutting (in every scope's verify block) |

3 scopes total, ~10 focused Claude Code sessions. Each scope = one commit. `/clear` between scopes.

## Challenger-driven changes from initial draft

- Old Scope 2 (pre-upload validator gate) folded into Scope 1 — the validator and the gate that uses it must ship together or `/upload` breaks against legacy data.
- Old Scope 5 (Val-de-Grace cleanup) folded into Scope 3 — the live run is the end-to-end verification of the dedup skill, not a separate commit.
- Scope 1 explicitly backfills `city_name` (only 7/555 beats currently carry it).
- Scope 1 migration parser uses deterministic strip of the known `{poi_slug}_{lens}_…_{book_slug}` envelope (≥85% of legacy beats parse cleanly; remainder fall back to `legacy_unknown`).
- Scope 2 verify uses external `sha256sum` before/after a deliberately-failing run, not a script-self-check.
- Scope 3 mocks Haiku in pytest; real Haiku call only during the VdG live run. Scope 3 reuses Scope 2's atomic-write helper so apply mutations roll back cleanly. Verify includes mutation-matches-action assertions.

---

### Scope 1: Hash, Validator, Migration, Pre-Upload Gate

**What:** Land the dedup data hygiene foundation in one shippable unit:
- Add `script_body_hash`, `book_slug`, `topic_slug`, `city_name` to `NarrativeBeatCreate` (city_name moves from `_meta` to top-level for legacy beats).
- Build `scripts/validate_beats.py` enforcing identity-tuple and hash uniqueness, with `legacy_unknown` wildcard semantics (a `legacy_unknown` value in `book_slug` or `topic_slug` does not collide with another `legacy_unknown` in the same position; `script_body_hash` uniqueness still strict).
- Build `scripts/migrate_beats_dedup_fields.py`:
  - `city_name` ← `paris` (or `_meta.city_name` if present); idempotent.
  - `book_slug` ← `around_and_about_paris` for all 548 legacy beats (only book in current dataset; book-log confirms).
  - `topic_slug` ← deterministic strip: given `book_slug` (suffix) and `slugify(poi_name) + "_" + lens + "_"` (prefix), extract the middle. Slugification must handle `Place de la Concorde` → `place_concorde` (drop common stopwords) AND `Châtelet` → `chatelet` (strip diacritics). On any prefix/suffix mismatch → `legacy_unknown`.
  - `script_body_hash` ← SHA-256 of `re.sub(r'\s+', ' ', body.lower().strip())`.
- Wire `validate_beats.py` as the FIRST PRE-FLIGHT step in `/upload` (before pytest), fail-closed.

**Acceptance criteria:** AC-3, AC-4, AC-5, AC-9, AC-12.

**Depends on:** None.

**Verification commands:**
```bash
# Validator detects synthetic collisions:
.venv/bin/pytest tests/test_beat_validation.py -v

# Migration leaves post-state passing the validator:
.venv/bin/python scripts/migrate_beats_dedup_fields.py data/paris/beats.json
.venv/bin/python scripts/validate_beats.py data/paris/beats.json && echo "post-migration validator: PASS"

# Hash correctness on every beat (not just sample):
.venv/bin/python -c "import json,hashlib,re; d=json.load(open('data/paris/beats.json')); n=lambda s: re.sub(r'\s+',' ',s.lower().strip()); bad=[b['beat_id'] for b in d if b['script_body_hash']!=hashlib.sha256(n(b['script_body']).encode()).hexdigest()]; assert not bad, bad; print('all 555 hashes correct')"

# Migration idempotency (re-run is a no-op):
md5 data/paris/beats.json > /tmp/m1
.venv/bin/python scripts/migrate_beats_dedup_fields.py data/paris/beats.json
md5 data/paris/beats.json > /tmp/m2
diff /tmp/m1 /tmp/m2 && echo "idempotent: PASS"

# city_name coverage:
.venv/bin/python -c "import json; d=json.load(open('data/paris/beats.json')); assert all(b.get('city_name')=='paris' for b in d); print('city_name backfilled: PASS')"

# topic_slug parseability target (≥85%):
.venv/bin/python -c "import json; d=json.load(open('data/paris/beats.json')); n=sum(1 for b in d if b['topic_slug']!='legacy_unknown'); print(f'topic parseability: {n}/{len(d)} = {n/len(d):.0%}'); assert n/len(d)>=0.85"

# Upload gate wired:
grep -q "validate_beats" .claude/commands/upload.md && echo "upload gate wired: PASS"

# Full suite (AC-10):
.venv/bin/pytest tests/ -x
```

**Estimated sessions:** 3.

---

### Scope 2: Refuse-on-Reprocess, Atomic Write, /beat-wipe

**What:**
- Update `/unified-beat-extract`: harden book-log pre-check from "tell user, allow re-run" to "STOP, exit non-zero, name prior run date and beats count." User must wipe before re-extracting.
- Build atomic-write helper in `scripts/beats_io.py` (reused by Scope 3): writes new beats to `data/{city}/beats.staging.json`, runs `validate_beats.py` on merged result, atomic `os.replace(staging, beats.json)` only on pass. On fail: delete staging, leave both `beats.json` and `book-log.json` byte-identical, exit non-zero with conflict report.
- Build `/beat-wipe {book_slug} --chunk {chunk_slug}` skill: removes beats matching `book_slug`+`topic_slug` (where `topic_slug` is parsed from chunk → topic mapping at wipe time); removes the chunk entry from `book-log.json`. Chunk-level only; no book-wide flag (user can bash-loop). Idempotent: re-run on already-wiped chunk prints "already clean" and exits 0.

**Acceptance criteria:** AC-1, AC-2, AC-11.

**Depends on:** Scope 1.

**Verification commands:**
```bash
# Refuse-on-reprocess harness:
.venv/bin/pytest tests/test_extract_refuse.py -v

# AC-11 atomic rollback — external sha256, deliberate fail:
shasum data/paris/beats.json data/paris/book-log.json > /tmp/pre.sha
.venv/bin/python -m scripts.beats_io --commit-with-planted-collision  # CLI flag added in this scope; plants a colliding-hash beat in staging, attempts commit, must fail-and-rollback
shasum data/paris/beats.json data/paris/book-log.json > /tmp/post.sha
diff /tmp/pre.sha /tmp/post.sha && echo "rollback byte-identical: PASS"

# Wipe round-trip (with backup safety):
cp data/paris/beats.json /tmp/beats.bak
.venv/bin/python -m scripts.wipe_beats paris/around-and-about-paris --chunk chunk-15-5th-arr-val-de-grace --apply
.venv/bin/python scripts/validate_beats.py data/paris/beats.json && echo "post-wipe valid: PASS"
.venv/bin/python -m scripts.wipe_beats paris/around-and-about-paris --chunk chunk-15-5th-arr-val-de-grace --apply | grep -q "already clean\|no-op" && echo "idempotent: PASS"
cp /tmp/beats.bak data/paris/beats.json  # restore

# Full suite (AC-10):
.venv/bin/pytest tests/ -x
```

**Estimated sessions:** 3.

---

### Scope 3: /beat-dedup Skill + Val-de-Grace Cleanup

**What:**
- New `scripts/dedup_pairs.py` (called by skill): MinHash/LSH via `datasketch`, Jaccard ≥ 0.5 default, 128 perms, 5-gram word-shingles, all CLI-overridable.
- New `/beat-dedup {city}` skill: candidate pairs → Haiku 4-way classifier (`same_story_same_wording` / `same_story_added_detail` / `same_story_enhanced_content` / `different_story`) → markdown report at `data/{city}/_dedup_review/{ts}.md` matching the spec's example.
- `scripts/apply_dedup_decisions.py`: parses the user-edited approval markdown (or interactive CLI), mutates `beats.json` via the Scope 2 staging helper (atomic), appends jsonl audit entries.
- Apply semantics: SKIP removes the new beat; INSERT no-op; COMBINE replaces both with user-supplied merged text; KEEP BOTH sets `dedup_reviewed: true` on both.
- Run on Val-de-Grace's 12 beats end-to-end; user reviews recommendations; apply approved actions.

**Acceptance criteria:** AC-6, AC-7, AC-8.

**Depends on:** Scope 1 (data hygiene), Scope 2 (atomic helper).

**Verification commands:**
```bash
# Hand-built fixture with 4 pairs, mocked Haiku — verifies report structure + every action mutation:
.venv/bin/pytest tests/test_beat_dedup.py -v  # includes test_apply_skip_removes_beat, test_apply_combine_replaces_both, test_apply_keep_both_flags, test_audit_log_matches_mutation

# Datasketch dep present:
.venv/bin/python -c "import datasketch; print('dep ok')"

# AC-8 on Val-de-Grace (real run, real Haiku, executed in this scope):
.venv/bin/python scripts/verify_vdg_ac8.py  # built in this scope; computes pairwise Jaccard on VdG beats, asserts no pair ≥0.8 unless both flagged dedup_reviewed=true with KEEP BOTH

# Audit log present and well-formed:
.venv/bin/python -c "import json; lines=[json.loads(l) for l in open('data/paris/_dedup_review/_log.jsonl')]; assert all({'ts','pair','jaccard','classification','action'} <= set(l) for l in lines); print('audit lines:', len(lines))"

# Full suite (AC-10):
.venv/bin/pytest tests/ -x
```

**Estimated sessions:** 4.

---

## Hammer-check (none marked `~`)

- **Scope 1:** No — foundation. Folds the pre-upload gate because validator + gate must ship together.
- **Scope 2:** No — addresses the immediate concrete pain (Scope 6 of pipeline-spatial-precision blocks here). `/beat-wipe` bundled because it's the operational counterpart to refuse-on-reprocess.
- **Scope 3:** No — without the semantic pass, legacy duplicates persist. VdG cleanup folded because it IS the end-to-end test of the skill on real data.

## Next step

Run `/red-team` with a fresh `/clear` against this scopes file + the spec + the codebase. Stage 4 must audit against `Docs/Markdown Docs/SECURITY_PRIVACY_PRACTICES.md` and the Best Practices Library, with explicit Pass/Fail/N/A per checklist item.
