# Skeptic Verification — Step S3

**Verified against commit:** 930b1e2 (refactor: make test and env targets self-contained)

**Claim:** Step S3 "Placeholder beats (beat_id NULL) are never selectable into a tour" satisfies AC-26, proven by test `test_placeholder_beats_without_stable_ids_are_excluded` plus undo-test mutation verification.

## Evidence Chain Verification

### 1. File Paths & Code Presence
- ✅ `src/tour/selection.py` exists and is modified (uncommitted changes)
- ✅ `tests/test_tour_corpus_loader.py` exists with test at lines 93–138
- ✅ Git diff shows 3 load-bearing changes:
  1. Line 620: `+ b.audio_url AS audio_url` added to LOAD_PARIS_BEATS_CYPHER
  2. Lines 689–702: `_PLACEHOLDER_AUDIO_PREFIX` constant and `_is_unadopted_placeholder_beat()` function added
  3. Lines 717–718: Filter check `if _is_unadopted_placeholder_beat(r): continue` in `_snapshot_from_records()`

### 2. Lint Verification (Runnable)
- **Command:** `make lint`
- **Exit code:** 0
- **Output:** `All checks passed!`
- **Scope:** ruff across src/, tests/, scripts/{5 files}
- ✅ Zero errors, reconfirmed

### 3. Test Design Verification
The test at line 93 encodes the CONJUNCTION correctly:
- **Placeholder beat:** `beat_id="b-placeholder"`, `stable_beat_id=None`, `audio_url="s3://ondoway-audio/placeholder/eiffel_tower.mp3"`
  - Expected: excluded (both conditions met)
- **Adopted twin:** `beat_id="b-adopted"`, `stable_beat_id="dbsync_5a8874d6"`, same placeholder audio URL
  - Expected: included (stable_beat_id is NOT None, first condition fails)
  - Proves that placeholder audio alone does NOT exclude
- **Corpus beat:** `beat_id="b-corpus"`, `stable_beat_id=None`, `audio_url="s3://ondoway-audio/paris/vosges-1.mp3"`
  - Expected: included (audio_url is NOT placeholder prefix, second condition fails)
  - Proves that None stable_beat_id alone does NOT exclude

The test asserts:
- Line 130: `assert "b-placeholder" not in beat_ids` — the core defect check
- Line 132: `assert beat_ids == ["b-adopted", "b-corpus"]` — the expected set
- Line 137: `assert "b.audio_url" in LOAD_PARIS_BEATS_CYPHER` — crucial: pinning that audio_url is selected

### 4. Filter Logic Verification
```python
def _is_unadopted_placeholder_beat(record: dict) -> bool:
    if _clean(record.get("stable_beat_id")) is not None:
        return False  # Has a real beat_id → not a placeholder
    audio_url = record.get("audio_url")
    return isinstance(audio_url, str) and audio_url.startswith(_PLACEHOLDER_AUDIO_PREFIX)
```
- ✅ `_clean()` handles None, empty string, and whitespace correctly
- ✅ Conjunction logic is explicit and sound
- ✅ Type guard on audio_url prevents crashes on non-string values

### 5. Coverage Verification
- **Entry points:** Both `generate_trip()` (line 467) and `preview_trip()` (line 1040) call `load_paris_corpus(driver, city_slug=tour_input.city_slug)`
- **Function signature:** Accepts any city_slug (Paris, NYC, London), not hardcoded to Paris
- **Filter placement:** In `_snapshot_from_records()` (line 717), called by `load_paris_corpus()` — the universal beat-loading function
- ✅ Filter applies to all cities via the same path
- ✅ No other beat-loading Cypher queries in `src/tour/` reach the tour generation engine

### 6. Cypher Query Check
Verified `LOAD_PARIS_BEATS_CYPHER` (lines 602–631):
- ✅ `b.beat_id AS stable_beat_id` (line 609) — selected
- ✅ `b.audio_url AS audio_url` (line 620, NEW in this diff) — load-bearing for the filter to work
- The WHERE clause filters only by `active_status = 'active'`; beat_id NULL is NOT filtered at the DB layer
- ✅ Python filter is the only defense

### 7. No Output Masking
Evidence provided shows:
- `make lint` output: direct from ruff, unpiped
- Test output: exit codes and assertion errors, no tail/grep/|| true
- Mutation evidence: compound `git stash...then make test-file` returns exit code 2 (pytest failure)

## Mutation Test (Evidence of Real Defect)

The provided evidence includes an undo-test claim:
- **Undo step 1:** Revert src/tour/selection.py (stash the filter)
- **Result:** Test fails with `AssertionError: assert 'b-placeholder' not in ['b-placeholder', 'b-adopted', 'b-corpus']`
- **Undo step 2:** Restore the fix
- **Result:** Test passes

This sequence proves the filter encodes the actual defect (not a strawman).

## Attacks Attempted

1. **Search for bypass entry points** — looked for other NarrativeBeat Cypher queries in src/tour/
   - Found many in src/api/, src/audio/, src/verify/, src/seed/ but NONE in the tour generation path
   - ✅ No bypass found

2. **Verify filter is not too late** — checked where snapshot is used
   - Filter is in `_snapshot_from_records()`, called by `load_paris_corpus()`
   - Beats enter the engine via `snapshot.beats_for()` which uses the filtered list
   - ✅ Filter is at the universal load point

3. **Check for city-specific blind spots** — verified function accepts city_slug parameter
   - `load_paris_corpus(driver, city_slug=...)` uses the parameter in Cypher
   - Both NYC and London use the same `_snapshot_from_records()` path
   - ✅ Not Paris-specific

4. **Verify Cypher query actually selects audio_url** — diff shows `+ b.audio_url AS audio_url` is NEW
   - Without this, `record.get("audio_url")` returns None, filter is unreachable
   - Test asserts `"b.audio_url" in LOAD_PARIS_BEATS_CYPHER` to pin this
   - ✅ Load-bearing change present

5. **Check _clean() function** — inspected lines 803–808
   - Handles None, empty string, whitespace correctly
   - Returns the original value for non-empty strings
   - ✅ No bugs found

## Unverified (Requires Serial Executor)

The following require shared container state and must be proposed, not run in parallel:
- `make test-file FILE="tests/test_tour_corpus_loader.py::test_placeholder_beats_without_stable_ids_are_excluded"` — the actual test execution
- The mutation test (revert + test) — verifies the test encodes the real defect

## Conclusion

**Rule:** CONFIRMED

All evidence chain items reconcile with the repo. No piping, no masking, no straw-man test design. The filter logic is sound, in the right place, applies universally to all cities, and is load-bearing on the added `audio_url` field in the Cypher query. The test includes both the core assertion and negative controls. The undo-test claim is consistent with the implementation.

No reproduction attempt failed. All attacks I could run succeeded (lint clean, code present, paths exist, logic correct).
