# S5 skeptic (opus) — NEGATIVE SPACE

**Verified against:** commit `930b1e2` ("refactor: make test and env targets self-contained"),
working tree DIRTY (the load-bearing state per run-context Baseline). Files inspected at their
worktree content, not HEAD.

**Claim under attack:** S5 ("A distinct rejection code for an unresolvable build fingerprint")
satisfies AC-16 and AC-18, proven by
`make test-file FILE="tests/test_trips_spend_and_authz.py::test_unverifiable_build_is_rejected_before_provider_spend"`
plus a QA mutation verdict of REAL.

**Verdict: CONFIRMED for the build-fingerprint clause of AC-16 and for AC-18.** I could not break
it. Four negative-space gaps are recorded below; none of them is a verified reproduction, so none
of them BLOCKS. Two of them (F1, F2) mean the claim "S5 satisfies AC-16" is true only under the
narrow reading of AC-16's second sentence, not its unqualified first sentence.

## What I re-derived myself

- `make lint` — RAN. Exit 0, "All checks passed!" over `src/ tests/ scripts/{5}`. The lint evidence
  reconciles.
- The S5 source diff (`git diff -- src/api/routes/trips.py src/tour/candidate_eligibility.py`) is
  exactly two things: one new `CandidateRejectionCode` member, and the extraction of the existing
  fallback body into a `_basic_tour_fallback` closure plus a new `try/except` around
  `resolve_build_identity()` at trips.py:1102-1112. Field-by-field, the `generation_failed` response
  the closure now builds is byte-identical to the one the old inline `except` block built. No
  hidden behaviour rode along.
- The mutation evidence reconciles with the code. Reverting only the two source files removes
  `BUILD_FINGERPRINT_UNAVAILABLE` and restores the single generic `except`, so the request produces
  `llm_generation_failed`; the FIRST assertion that then fails is
  `tests/test_trips_spend_and_authz.py:243` — which is exactly the assertion and the exact message
  in the pasted RED output. The QA mutation was not a strawman.
- `CandidateRejection` IS imported at trips.py:49 (the closure's annotation and constructor both
  resolve); `TripPreviewBasicTour.reason` is `Literal["llm_generation_failed",
  "llm_candidate_ineligible"]` (src/api/models/trips.py:315), so the new `llm_candidate_ineligible`
  value is an EXISTING model member, not a new artifact and not a pydantic 500.
- Enum-addition blast radius: `grep -rn "CandidateRejectionCode|candidate_rejection"` over
  src/tests/mobile/frontend/Docs/scripts/tools shows NO exhaustive-member test, NO OpenAPI snapshot
  test, and NO docs-sync test. Adding a member cannot break a golden.
- Different entry points for the same fault: `resolve_build_identity` has exactly two call sites
  (`trips.py:1103` and `premium_tour.py:554` as the `build_identity or …` default), and
  `finalize_premium_tour` is called from exactly one place in src/ — `preview_trip`, which always
  passes `build_identity=`. There is no second route that can reach the fault and mislabel it.
- Intra-test state: `_clean_spend_guard` (autouse) resets the module-global counters; the first
  request returns before `_spend_precheck` so it burns no budget, and the second executor is
  `cost_bearing=False` so it is not limited. The second `preview_client(...)` call silently
  re-patches `resolve_build_identity` back to the good lambda — subtle, but it fails LOUDLY (the
  `generation_failed` assertion) rather than going vacuous if that ever changes.

## F1 (medium, advisory) — AC-16's first sentence is only partly satisfied: other environment/config faults still report `llm_generation_failed`

AC-16 verbatim: *"An environment/config fault must NOT be reported as basic_tour.reason
'llm_generation_failed'."* Unqualified. S5 carves out exactly ONE such fault.

Still mislabeled, by code inspection:

- `src/tour/anthropic_client.py:69` `_require_paid_call_permission()` raises `RuntimeError` when
  `ONDOWAY_ENABLE_PAID_LLM_CALLS != "1"`. It is called lazily from
  `certification_provider.py:134 _client_for()`, i.e. INSIDE `executor.execute()`, inside
  `preview_trip`'s remaining try. `RuntimeError` is not in `_PROVIDER_ERRORS`
  (`trips.py:119` = `anthropic.APIError` only), so it lands in the generic `except Exception` →
  `reason="llm_generation_failed"`, `code="generation_failed"`, detail "Premium authoring did not
  produce a complete traced blueprint".
- A MISSING `ANTHROPIC_API_KEY` behaves the same way: `anthropic.Anthropic()` raises
  `TypeError`/`AnthropicError` at construction, neither of which subclasses `APIError`. (An
  INVALID key is different — `AuthenticationError` IS an `APIError`, so it maps to 502.)

Mitigating fact I checked before writing this up: `scripts/workbench.sh:46` sets
`ONDOWAY_ENABLE_PAID_LLM_CALLS=1` and `render.yaml:87` sets it to "1", so the paid-flag variant is
not the default state of the demo path. That is why this is medium and advisory, not a blocker.

Note also that the run's own `S8_dropped_offline_executor` decision asserts "a missing paid flag
currently raises RuntimeError **loudly**". On the preview path it does not: it is swallowed into a
200 with an LLM-blaming label. That decision's premise is wrong in the same direction this finding
points.

**Proposed reproduction (I did not run it — new node, needs to be written first):** a sibling of the
S5 test that overrides `get_premium_compose_executor` with the REAL
`premium_tour.AnthropicPremiumExecutor()` and `monkeypatch.delenv("ONDOWAY_ENABLE_PAID_LLM_CALLS",
raising=False)`, then asserts `body["basic_tour"]["reason"] != "llm_generation_failed"`. It will be
RED today. Cheapest honest fix: route the RuntimeError/AnthropicError family through
`_basic_tour_fallback(reason="llm_candidate_ineligible", …)` with a `provider_unavailable`-style
code, reusing the closure S5 already built.

## F2 (medium, advisory) — "two different causes must not produce byte-identical payloads" is still false on the generic branch

AC-16 also says *"Two different causes must not produce byte-identical payloads."* The surviving
handler is `except Exception:` with the exception UNBOUND (trips.py:1132) and a hardcoded detail
string. Therefore `RuntimeError("boom")`, `KeyError('x')`, a missing API key and a genuine Opus
malformed-response all serialize to the SAME bytes. S5 separated one cause out of N; the remaining
N-1 are still indistinguishable to the caller and to the human reading the workbench.

This is a code-read certainty (the response cannot depend on an object the handler never binds), not
a run, so it is advisory. It is also cheap to close, and it is the same one-line change AC-15/S7
needs anyway: bind `exc` and put `type(exc).__name__` in the detail.

## F3 (low, advisory) — the fault S5 names is the one fault that will have NO server-side log

`grep -n "logger|logging" src/api/routes/trips.py` returns ZERO matches today: AC-15 is unimplemented
and is S7's step (`test_premium_generation_failure_is_logged_with_its_cause`). AC-15 is worded
"Given the premium path **inside preview_trip's try block** raises for any reason…". S5 moved
`resolve_build_identity()` OUT of that try block into its own. If S7 implements AC-15 literally in
the generic `except`, the build-fingerprint downgrade — the exact fault this whole run is about —
returns 200, logs nothing, and satisfies AC-10's "log contains no traceback" vacuously. Recommend
S7 put the log record inside `_basic_tour_fallback` (one place, both branches) rather than in the
generic `except`.

## F4 (low, advisory) — `detail=str(exc)` echoes an arbitrary internal exception string on a deliberately UNAUTHENTICATED endpoint, and only a curated `ValueError` was tested

The test injects `ValueError("dirty build")` — a friendly, curated message. The real
`resolve_build_identity` (premium_tour.py:510-536) can also raise from
`subprocess.run(["git", …], cwd=REPO_ROOT, check=True)`: `FileNotFoundError: [Errno 2] No such file
or directory: 'git'`, a bad-cwd `FileNotFoundError` carrying an absolute filesystem path, or
`CalledProcessError` carrying the argv. The state of the world that makes this reachable in
production is untested and real: `.dockerignore` excludes `.git/`, and the Dockerfile installs no
git, so a Render process where `RENDER_GIT_COMMIT`/`GIT_COMMIT_SHA` is absent hits the subprocess
branch in a container with no repo and probably no git binary. `trips.py:148` states the endpoint is
"deliberately unauthenticated", so that string goes to anonymous callers. AC-16 *mandates* "a detail
containing the raised message", so S5 complies with the AC — the gap is in the AC. Suggested bound:
echo `str(exc)` for the curated `ValueError` branch and `f"{type(exc).__name__}: build fingerprint
unresolvable"` otherwise.

## F5 (low, advisory) — states not exercised by the pinned single-node gate

The gate ran ONE node id in isolation. Not run, all $0-but-shared-container, all propose-only for me:

1. `make test-file FILE="tests/test_trips_spend_and_authz.py"` — whole-file run: module-global spend
   guard ordering plus the double-`preview_client` re-patch inside the S5 test.
2. `make test-file FILE="tests/test_trip_preview_contract.py"` — the neighbour file that pins the
   preview wire shape, including `candidate_rejection["code"] == "generation_failed"` at :532. Its
   `make_client` fixture DOES patch `resolve_build_identity`, so I expect green; it is the file most
   likely to encode an assumption S5 changed.
3. `make test-file FILE="tests/test_trip_api.py::TestPreviewTrip"` — the ONLY test I found that hits
   `POST /trips/preview` WITHOUT patching `resolve_build_identity`, i.e. the only end-to-end
   exercise of the new branch through the real dirty-tree fault. It is branch-tolerant, so I expect
   green, but it is the honest integration check the node-id gate skipped.

## Not S5's defect, but load-bearing for the run

`grep -c candidate_rejection frontend/review.html` is **0** today, and `review.html:3441-3445`
renders a fixed "Basic grounded guide — … Premium narration is ineligible." with no cause. Until S9
lands, S5's distinction is invisible to the human, so AC-17 (and the user-visible half of AC-16) is
unmet by the run, not by S5. Additionally `frontend/tour-preview.html:83` has the identical blind
spot and is NOT in S9's file scope — the second UI entry point onto the same payload will still show
no rejection code after S9.
