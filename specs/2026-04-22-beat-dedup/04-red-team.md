# Red Team: Duplicate Beat Prevention

**Date:** 2026-04-22
**Status:** Blockers surfaced — user must resolve before Stage 5
**Reviewer mode:** Adversarial — fresh read of [01-scope.md](01-scope.md), [02-spec.md](02-spec.md), [03-scopes.md](03-scopes.md) against live codebase
**Sources cross-checked:** `specs/NORTHSTAR.md`, `Docs/Markdown Docs/SECURITY_PRIVACY_PRACTICES.md`, `.claude/commands/unified-beat-extract.md`, `.claude/commands/upload.md`, `src/api/models/nodes.py`, `data/paris/beats.json`, `data/paris/book-log.json`

---

## 1. Blockers

### B-1. `/beat-wipe` has no deterministic chunk → beat_id mapping

**Where:** [03-scopes.md](03-scopes.md#scope-2) lines 87 and [02-spec.md](02-spec.md) AC-2.

**Problem.** The scope says `/beat-wipe` "removes beats matching `book_slug`+`topic_slug` (where `topic_slug` is parsed from chunk → topic mapping at wipe time)." No such mapping exists.

**Evidence.** `book-log.json` records `chunks_processed[].pois_touched` (chunk → POIs), not chunk → beats. 137 of 555 beats (25%) live at POIs mentioned by ≥2 chunks: Les Halles (2 chunks), Ile de la Cite (3), Pont Neuf (3), Place des Vosges (3), etc. Wiping `chunk-01` would also delete Les Halles beats that came from `chunk-02`.

The wipe skill cannot answer "which beats came from chunk-X?" from current data. The refuse-on-reprocess policy (AC-1) turns this into a footgun: a user who hits the refuse, runs wipe, then re-extracts, silently loses beats that came from a different chunk's pass over the same POI.

**Recommended resolution.** Add `source_chunk_slug: str` as a top-level beat field.
- Unified-beat-extract writes it on emission (already knows which chunk it's processing).
- Scope 1 migration backfills it for the 21 legacy chunks by looking up each beat's POI in `book-log.json` and picking the chunk whose `pois_touched` contains that POI. Where ≥2 chunks touch the POI, set `source_chunk_slug: legacy_ambiguous` (distinct sentinel — don't overload `legacy_unknown`).
- `/beat-wipe` then deletes strictly `source_chunk_slug == {target}`. Beats stamped `legacy_ambiguous` are never deleted by wipe (safe default — user deletes them manually if needed).

This is additive (one new field), idempotent to migrate, and makes the refuse→wipe→re-extract loop safe. Update AC-2 to reflect the new field; add coverage to Scope 1's verification (hash count legacy_ambiguous legacy beats).

### B-2. Migration parser is undefined for the 7 unified_v1 beats

**Where:** [03-scopes.md](03-scopes.md#scope-1) lines 37-39.

**Problem.** Scope 1's parser derives `book_slug` and `topic_slug` assuming the legacy format `{poi_slug}_{lens}_{topic_slug}_{book_slug}`. But unified_v1 beats use a different format: `{city}_{poi_slug}_{lens}_{book_slug}_{topic_slug}`. Verified on disk: none of the 7 unified_v1 beats carry `book_slug` in any field (neither top-level nor `_meta`); their `beat_id` order also differs from legacy.

The parser as written will fall through to `legacy_unknown` for all 7 unified_v1 beats, even though the data is recoverable. Worse, unified_v1 beats already have `topic_slug` as a top-level field — the migration would overwrite that with the sentinel if it blindly re-parses.

**Recommended resolution.** Branch the migration on `_meta.prompt_version`:
- If `prompt_version == "unified_v1"`: `topic_slug` is already present — leave it; parse `book_slug` from beat_id (strip `{city}_{poi_slug}_{lens}_` prefix and `_{topic_slug}` suffix).
- Else (legacy): run the existing `{poi_slug}_{lens}_{topic_slug}_{book_slug}` parser; populate both `book_slug` and `topic_slug`.
- Migration idempotency: never overwrite a non-empty, non-sentinel existing value.

Add to Scope 1 verification: `assert all(b.get('book_slug') == 'around_and_about_paris' for b in unified_v1_beats)` — catches parser regression.

### B-3. AC-11 verification plants a test fixture behind a production CLI flag

**Where:** [03-scopes.md](03-scopes.md#scope-2) line 100 — `python -m scripts.beats_io --commit-with-planted-collision`.

**Problem.** This adds a test-only mode to a production module. The flag must never fire in real operation, but it lives in the same entrypoint users can invoke. A typo or a misread hook runs it against live data. Also violates the project CLAUDE.md style rule: don't add backwards-compat/test-only shims to production code.

**Recommended resolution.** Move the rollback-proof to a pytest test:
```python
def test_commit_rollback_leaves_files_byte_identical(tmp_path):
    beats = tmp_path / "beats.json"
    log = tmp_path / "book-log.json"
    beats.write_text(json.dumps(SEED_BEATS))
    log.write_text(json.dumps(SEED_LOG))
    pre = (sha256(beats), sha256(log))
    with pytest.raises(ValidationError):
        beats_io.commit(staging=[COLLIDING_BEAT], beats_path=beats, log_path=log, chunk_entry=...)
    post = (sha256(beats), sha256(log))
    assert pre == post
```

Run it as part of `test_beat_validation.py`. Drop the production CLI flag. Keep the verification command list, but replace the shell invocation with the pytest case.

### B-4. Verification mutates live `data/paris/beats.json`

**Where:** [03-scopes.md](03-scopes.md#scope-2) lines 104-109 (cp/restore round-trip on live data), also Scope 1's migration command (line 53) and Scope 3's VdG live run.

**Problem.** The verification story for Scope 2 is "cp to /tmp, mutate, cp back." If any step in between fails (pytest crash, terminal closed, user Ctrl-C between `wipe --apply` and the restore `cp`), the 555-beat production file is corrupted and the backup is one file deep. A single hiccup during verification causes the very data-loss event the whole spec is trying to prevent.

Scope 1's migration verification (line 53) runs `migrate_beats_dedup_fields.py data/paris/beats.json` directly against production. Idempotency is asserted, but the first run writes. If the parser regresses mid-development, the commit history rescues the file only if git-clean was confirmed first.

**Recommended resolution.**
- Scope 2 wipe-verify: operate on a fixture at `tests/fixtures/beats_multi_chunk.json` that models the chunks_processed edge cases (2+ chunks per POI, legacy_ambiguous, etc.). Don't touch `data/paris/beats.json` in verify commands.
- Scope 1 migration-verify: add an explicit "confirm git status clean, create `data/paris/beats.json.pre-migration` snapshot, proceed only if snapshot write succeeded" pre-flight inside the migration script itself. Run migration verify on a `cp data/paris/beats.json /tmp/migration-test.json` against the copy first; only touch live after copy run passes.
- Scope 3 VdG live: unchanged (it's a one-shot live run with git commit as rollback), but add pre-run `git status` assertion.

---

## 2. Risks (likelihood × mitigation)

### R-1. `legacy_unknown` wildcard leaves 548 legacy beats semi-validated forever

**Likelihood:** Certain. **Impact:** Medium.

The wildcard is pragmatic given the spec's scope (new extraction + VdG cleanup), but it means: two legacy beats at the same POI / same lens / both `legacy_unknown` book_slug / topic_slug don't trigger identity-tuple collision. Only `script_body_hash` catches them — and only if byte-identical post-normalization. The 548 legacy beats escape the semantic pass entirely unless `/beat-dedup paris` is run corpus-wide (spec only runs it on VdG).

**Mitigation.** Add a follow-up scope explicit in [02-spec.md](02-spec.md) "What we're NOT building" → make it an explicit nice-to-have: "corpus-wide `/beat-dedup paris --all` sweep deferred to post-Scope-6 cleanup." Otherwise the spec ships "done" while the 548-beat corpus still has unaddressed overlap. Flag in Scope 6's pre-work too.

### R-2. 5-gram word shingles + Jaccard ≥ 0.5 under-retrieves paraphrases

**Likelihood:** High (~30-50% of semantic pairs below threshold per MinHash literature). **Impact:** Medium.

100-200 word beats with different phrasings but same facts often score Jaccard 0.2-0.4 on 5-gram word shingles. Example: two 1645-Val-de-Grace-founding beats using different sentence structure will share entities but few 5-grams. The spec acknowledges "edge cases may slip through" — honest, but this isn't an edge; it's the common case.

**Mitigation.** Run VdG with threshold 0.3 first to inventory false positives, then tune up. Log every pair the LSH surfaces (not just ≥0.5) as a "near-miss" appendix in the report. A later scope can add normalized-entity-set Jaccard as a complementary signal without violating the "no embeddings" constraint. Don't block Scope 3 on this — ship the pass, tune empirically on real VdG data.

### R-3. NORTHSTAR rule conflict: "keep the miner permissive"

**Likelihood:** Low (interpretive). **Impact:** Low.

NORTHSTAR says: "Extraction philosophy: Constraints belong at the database layer, not the extraction layer. Keep the miner permissive." The spec adds refuse-on-reprocess and end-of-run validation — both extraction-layer gates.

**Mitigation.** The rule's intent was "don't have the LLM extraction prompt enforce uniqueness (causes under-extraction)." The spec's gates run AFTER the LLM has extracted permissively; they validate the write, not the extraction. Add one line to `02-spec.md`'s Purpose section: "The extraction prompt remains permissive per NORTHSTAR; validation runs at the commit-to-disk step, not inside the miner." No code change; removes a future "why does this violate the north star" question.

### R-4. Haiku returns a label outside the 4-value enum

**Likelihood:** Medium (Haiku is generally well-behaved but can drift on JSON). **Impact:** Medium — breaks report structure.

Spec AC-6 requires one of 4 classification labels per pair. No schema enforcement, no retry.

**Mitigation.** Structured output: use the Claude Messages API `response_format` with a schema enforcing `classification` ∈ `{same_story_same_wording, same_story_added_detail, same_story_enhanced_content, different_story}`. On parse fail: one retry with stricter prompt, then fallback to `different_story` + `_parse_failed: true` flag on the pair; report-writer surfaces these at the top for human spot-check. Don't silently accept junk labels.

### R-5. Approval UX is underspecified — markdown editing vs interactive CLI

**Likelihood:** Medium. **Impact:** Medium — flaky or frustrating user workflow.

Scope 3 says the apply step "parses the user-edited approval markdown (or interactive CLI)." Both? Which? Markdown-checkbox parsing is fragile (tabs, case, `[x]` vs `[X]` vs `[✓]`).

**Recommended resolution.** Interactive CLI only. The skill prompts per pair: `Pair 1 (Jaccard 0.74) → recommend INSERT. [a]ccept / [s]kip / [c]ombine / [k]eep-both / [q]uit:`. On quit, writes partial progress to `_dedup_review/_log.jsonl` with `resumed: true` flag and a resumable state file. The markdown file is the *record* (written before apply, read-only), not the input channel. Update [02-spec.md](02-spec.md) AC-7 to say "applied via interactive CLI" explicitly.

### R-6. Haiku response cost under adversarial pair-count growth

**Likelihood:** Low at current scale. **Impact:** Low.

555 beats → ~1-5K candidate pairs max after LSH. At Haiku pricing (~$0.25/1M in, $1.25/1M out) × ~250 tokens/pair → ~$0.30 per city-wide run. Negligible. At book-2 scale (1K+ beats) still well under $1.

**Mitigation.** No change. Flag the cost model in the pipeline report so cost creeps get noticed.

### R-7. `datasketch` dep unpinned

**Likelihood:** Medium (ecosystem churn). **Impact:** Low-medium.

Scope 1/3 adds `datasketch` but doesn't specify a version.

**Mitigation.** Pin in `requirements.txt` (or pyproject / pipfile, whichever project uses — check before writing plan). `datasketch>=1.6.4,<2.0` is reasonable. Add `pip-audit` or `safety check` to Scope 1 verification one-liner for CVE scan.

---

## 3. Open questions (genuine user calls)

### Q-1. Corpus-wide dedup of the 548 legacy beats — in or out?

The spec is explicit that VdG is the workload. The 17 POIs that appear in ≥2 legacy chunks almost certainly carry overlapping beats; they never get the semantic pass. In-scope would push this to 4 scopes; deferred leaves known duplication until someone schedules a follow-up. **Recommendation:** Defer, but add to the `01-scope.md` "What we're NOT building" with an explicit follow-up ticket note. This isn't a best-practices decision — it's a time/risk call only you can make.

### Q-2. `/beat-wipe` at book level — truly never?

The spec bans a `--book` flag "footgun." Reasonable default. But: the dedup-apply step (Scope 3) can produce ~10s of SKIP decisions across a book that each semantically removes a beat. If a user ever wants to re-baseline a whole book (e.g., we discover the book PDF was corrupt and re-chunk it), they'd run 21 wipe commands. Is a `--book --confirm=<typed-book-slug>` escape hatch worth the UX complexity? **Recommendation:** Not now. Accept the 21-line bash loop. Revisit only if we actually hit that scenario.

### Q-3. Does `/upload` hard-block or offer a `--force` override?

AC-9 says "no warn-and-continue mode." I agree the hard block is correct. But when a user is actively cleaning up a dedup violation, being able to upload *other* cities (paris is broken, but london is fine) matters. **Recommendation:** `/upload {city}` already takes a city arg; the validator only runs on the specified city's `beats.json`. That's sufficient isolation — no `--force` needed. Confirm no cross-city dependency in the validator; add a test.

---

## 4. Codebase conflicts

### C-1. `unified-beat-extract.md` current PRE-CHECK says "allow re-run"

**Where:** `.claude/commands/unified-beat-extract.md` lines 38-44.

Current text: "STOP and tell the user: 'This chunk was already processed on [date]. [X] beats were extracted. Run again to re-extract, or skip.'" — this is the soft-stop the spec is explicitly tightening. Scope 2's task must rewrite this section to the hard refuse. Minor — just making sure Stage 5 task list names the edit, not a vague "harden the check."

### C-2. NarrativeBeatCreate model needs `script_body_hash` added but is referenced by non-pipeline code

**Where:** `src/api/models/nodes.py` NarrativeBeatCreate (line 158); used by `/upload`, seed code (`src/seed/narratives.py`), and `test_upload_api.py`.

Adding a required field breaks existing callers. Add it as `script_body_hash: str = ""` with a model_validator that computes on empty and validates on present. That keeps it backward-compatible for Neo4j upload. The uniqueness check lives in `validate_beats.py`, not Pydantic (spec already says this). OK as spec'd; just call it out in Stage 5 tasks so the implementer doesn't hard-require it.

### C-3. `/upload` pre-flight already runs 3 other tests (line 17-20)

`validate_beats.py` must run BEFORE those other tests (the spec says "FIRST pre-flight step"). Clean — but note that `/upload` is a skill (markdown prompt), not code. The "wiring" is editing `.claude/commands/upload.md` to add the validate call as step 0. Low risk; mechanical.

---

## 5. North star check

| NORTHSTAR commitment | Spec posture | Assessment |
|---|---|---|
| "No embedding similarity for MVP" | MinHash + shingling + Haiku judge | ✅ Compliant — explicitly avoids embeddings |
| "MERGE keys must be multi-city safe" | Identity tuple includes `city_name` | ✅ Improves on existing `script_body` MERGE |
| "Never create empty placeholder nodes" | N/A — beats.json hygiene, not graph nodes | ✅ N/A |
| "Extraction philosophy: Constraints at DB layer, not extraction layer" | Validation at commit step, not in LLM prompt | ⚠️ Interpretive — see R-3 above. Recommend adding one-line rationale to 02-spec.md |
| "Two-source minimum for auto-corrections" | Dedup apply requires human approval per pair | ✅ Stronger than two-source (explicit human gate) |
| "Log every auto-correction" | `_dedup_review/_log.jsonl` | ✅ Compliant |
| "Launch city: Paris" | Scoped per-city; Paris is the live workload | ✅ Aligned |

No short-sighted trade-offs against the north star.

---

## 6. Scope review

### Scope 1 — Hash, Validator, Migration, Pre-Upload Gate
- **Boundaries:** Clean — one foundation unit. Folding pre-upload gate is right (validator without gate has no consumer).
- **Verification:** Strong except that blocker B-4 says stop mutating live data during verify. Add a hash-match spot-check for `book_slug` backfill on the 7 unified_v1 beats (per B-2 fix).
- **Ordering:** Correct — no deps.
- **Concern:** "≥85% topic_slug parseability" target is arbitrary. If 84%, does the scope fail? Recommend restating as: "no legacy beat fails parsing silently — any beat that can't be parsed lands in a flagged list printed at migration end; user accepts the list before proceeding." Structural over numeric.

### Scope 2 — Refuse-on-Reprocess, Atomic Write, /beat-wipe
- **Boundaries:** Overloaded — refuse-check is trivial (edit one markdown), atomic-write is the hard work, `/beat-wipe` is a new skill. Consider splitting if sessions stretch. Not a blocker; flag to implementer that `/beat-wipe` might slip to session 4.
- **Verification:** B-1 rewrites the wipe verification around `source_chunk_slug`. B-3 replaces the planted-collision CLI with a pytest case. B-4 moves round-trip off live data.
- **Ordering:** Correct — depends on Scope 1 (validator + fields must exist first).

### Scope 3 — /beat-dedup + VdG Cleanup
- **Boundaries:** Clean. Folding VdG cleanup into the scope is correct — it's the end-to-end test.
- **Verification:** Strong. Add: `test_haiku_response_validation` — mock Haiku returning a 5th label, assert retry + fallback (per R-4).
- **Ordering:** Correct — depends on Scope 1 + 2.

### Cross-scope sessions count
9-10 sessions total across 3 scopes. Consistent with "medium-to-large" complexity. No scope exceeds 4.

---

## 7. Best practices audit

### A) `Docs/Markdown Docs/SECURITY_PRIVACY_PRACTICES.md` (16 sections)

| Section | Status | Notes |
|---|---|---|
| 1. Data Classification & Minimization | ✅ N/A | Offline pipeline, no new user data collected |
| 2. Consent & Transparency | ✅ N/A | No user-facing surface |
| 3. Authentication & Authorization | ✅ N/A | No network endpoints added |
| 4. Secure Session Management | ✅ N/A | No sessions |
| 5. Secrets & Credentials | ⚠️ Address | Haiku API key must be env-var only. Add to Scope 3 task list: "Never log `ANTHROPIC_API_KEY`, never include in error messages, never write to `_dedup_review/*`." |
| 6. Encryption | ✅ N/A | No new data at rest/in transit beyond existing |
| 7. Logging & Monitoring | ⚠️ Address | `_dedup_review/*.md` contains full beat bodies — already in beats.json so no new exposure, but confirm it's gitignored or explicitly tracked. Recommendation: `.gitignore data/*/_dedup_review/*.md` (keep `_log.jsonl` for audit trail). |
| 8. Data Retention & Deletion | ✅ N/A | No PII |
| 9. Third-Party Risk | ✅ Addressed | Haiku (Anthropic) is already the approved provider per NORTHSTAR |
| 10. Secure Development Lifecycle | ⚠️ Address | Add `datasketch` CVE scan; pin version. See R-7. |
| 11. Input Validation & Output Encoding | ⚠️ Address | Haiku response parsing needs strict JSON schema enforcement. See R-4. |
| 12. Infrastructure & Network Security | ✅ N/A | No network changes |
| 13. Privacy by Design | ✅ N/A | No user data |
| 14. Incident Response | ✅ N/A | No user-visible changes |
| 15. Testing & Verification | ✅ Addressed | Tests defined in each scope |
| 16. Compliance & Documentation | ✅ N/A | No regulated data |

**Three items to incorporate into Stage 5 Part D:**
- Haiku API key handling (never logged, env-var only) → Scope 3
- `.gitignore` for `_dedup_review/*.md` reports → Scope 3
- `datasketch` pinned + CVE scan in verification → Scope 1 (pin) + Scope 3 (scan)

### B) Best Practices Library (from skill prompt)

- **Security:** See table above. All applicable items covered.
- **Performance:** MinHash LSH scales linearly in pairs; at 10K-beat corpus, still <10s per run. No concern.
- **Privacy:** N/A — no user data.
- **Accessibility:** N/A — no UI.
- **UX:** R-5 (approval interactive CLI) is the UX call. Resolve per Q-1 recommendation.
- **Data integrity (project-specific top priority):** Blockers B-1 through B-4 + R-1 all fall here. These are the gate.

---

## Summary — what's required before Stage 5

1. **Resolve B-1** — add `source_chunk_slug` field; update scope + AC language.
2. **Resolve B-2** — branch migration parser on `_meta.prompt_version`; verify unified_v1 path.
3. **Resolve B-3** — pytest-based rollback test; remove production CLI flag.
4. **Resolve B-4** — all verification runs against fixtures or `/tmp` copies, not `data/paris/beats.json`.
5. **Answer Q-1, Q-2, Q-3** — explicit user calls on corpus-wide dedup deferral, book-level wipe scope, and `/upload` city isolation.
6. **Incorporate R-3, R-4, R-5** rewording into `02-spec.md` before plan-writing (one-line rationale + structured output + CLI-only approval).
7. **Add** security items (Haiku key, gitignore, pin + scan) into Stage 5 Part D checklist.

Once user records resolutions below, proceed to `/plan`.

---

## User resolutions (2026-04-22)

- **B-1 — accepted.** Add `source_chunk_slug: str` as a top-level beat field. Unified-beat-extract writes it on emission. Scope 1 migration backfills by looking up each beat's POI in `book-log.json`; beats at POIs touched by ≥2 chunks get the distinct sentinel `legacy_ambiguous` (never deleted by wipe). Update AC-2 accordingly.
- **B-2 — accepted.** Migration parser branches on `_meta.prompt_version`: `unified_v1` path preserves existing top-level `topic_slug` and parses `book_slug` from the `{city}_{poi_slug}_{lens}_{book_slug}_{topic_slug}` envelope; legacy path uses the existing `{poi_slug}_{lens}_{topic_slug}_{book_slug}` parser. Idempotent: never overwrite non-empty non-sentinel values. Add verification: all 7 unified_v1 beats end up with `book_slug == "around_and_about_paris"`.
- **B-3 — accepted.** Drop the `--commit-with-planted-collision` production CLI flag. Replace with a pytest case in `test_beat_validation.py` that builds a fixture in `tmp_path`, plants a colliding beat, attempts commit, asserts `ValidationError` and pre/post sha256 equality on both files.
- **B-4 — accepted.** All verification commands run against `tests/fixtures/beats_multi_chunk.json` or `/tmp` copies. Migration script itself adds a `git status` pre-flight and writes a `data/paris/beats.json.pre-migration` snapshot before mutating. Scope 3 VdG live run keeps its production write but asserts git-clean first.
- **Q-1 — defer corpus-wide dedup.** Add to [01-scope.md](01-scope.md) "What we're NOT building" with a follow-up ticket note: "Corpus-wide `/beat-dedup paris --all` sweep deferred to post-Scope-6 cleanup — ~17 POIs with multi-chunk overlap remain semi-validated until then."
- **Q-2 — no `--book` flag for `/beat-wipe`.** Accept the 21-line bash loop. Revisit only if an actual re-baseline scenario lands.
- **Q-3 — no `--force`; rely on natural city isolation.** `/upload {city}` already scopes to the city's `beats.json`. Add a test confirming `validate_beats.py` operates strictly on the file path argument with no cross-city dependency.
- **R-3 — spec edit accepted.** Add one line to [02-spec.md](02-spec.md) Purpose: "The extraction prompt remains permissive per NORTHSTAR; validation runs at the commit-to-disk step, not inside the miner."
- **R-4 — spec edit accepted.** Haiku call uses Messages API structured output with a schema enforcing `classification` ∈ 4-value enum. On parse fail: one retry with stricter prompt; final fallback sets `different_story` + `_parse_failed: true` and surfaces the pair at top of report for human spot-check.
- **R-5 — spec edit accepted.** Interactive CLI only. Skill prompts per pair: `[a]ccept / [s]kip / [c]ombine / [k]eep-both / [q]uit`. On quit, writes progress + `resumed: true` state file. Markdown report is read-only record, not input channel. Update AC-7 to say "applied via interactive CLI" explicitly.

**Status:** Ready for Stage 5 (`/plan`). Stage 5 must also fold in the three security items (Haiku API key handling, `.gitignore data/*/_dedup_review/*.md` excluding `_log.jsonl`, `datasketch` pinned + CVE scan) into Part D.
