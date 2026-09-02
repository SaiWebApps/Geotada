export const meta = {
  name: 'team-engine',
  description: 'INTERNAL execution engine for /team — not a command you type. /team invokes it after you approve its plan in chat. Executes an approved feature from the tracker database: per step Build -> Gate -> tier-sized skeptic panel -> Judge -> persist through `track`. Hard-capped, so it always terminates and reports. Does NOT commit.',
  whenToUse: 'Do NOT invoke this directly — use `/team <task>` and say "go"; it calls this for you. Direct invocation is for resuming a partially-run ledger only. Requires a row in the tracker\'s `approvals` table (it refuses to fan out otherwise). args: {spec: ".claude/runs/2026-09-02-slug" (required — a gitignored run folder; `specs/` was deleted 2026-09-02 and is refused by the junk guard), now: ISO-8601 (required — Date.now() is forbidden in workflow scripts), estimateOnly?: bool, maxSteps?: int, maxAttempts?: int (default 2), stepsPerPhase?: int (default 3), retryBlocked?: bool}.',
  phases: [
    { title: 'Preflight', detail: 'load ledger, check approval, validate every command against the LIVE Makefile, probe infra, self-test the engine, print the size of the fan-out' },
    { title: 'Build', detail: 'one developer per step, red-first, minimal diff' },
    { title: 'Gate', detail: 'seconds, not minutes: derived lint + the step node-id test + the undo/mutation test (NOTE: starts/uses the SHARED local containers)' },
    { title: 'Challenge', detail: 'tier-sized hostile panel on different models; only a VERIFIED repro can block' },
    { title: 'Rule', detail: 'judge PROCEED / PROVE-FIRST / STOP, then a courier records the outcome through `track`' },
    { title: 'PhaseGate', detail: 'the fast shards, serialized (they share the 7688 DB, dev data and Valhalla)' },
    { title: 'Close', detail: '`make audit` exactly ONCE, acceptance for tier >= 2, final report' },
  ],
}

// Interpolated into every agent prompt, so it must resolve on any machine — a
// hardcoded home directory hands a fresh clone (or a sibling checkout) a path
// that does not exist. CLAUDE_PROJECT_DIR is set by the harness; cwd is the
// fallback for a bare `node .claude/team-engine.test.js` run from the repo root.
//
// `process` EXISTS under node (the guard) but NOT in the workflow runtime, which
// provides no Node API at all. Reading it unguarded threw `process is not defined`
// on load — before preflight, before any agent — every time the engine was invoked
// as a workflow, which is its only real execution path. It had done so since the
// engine's first commit, and the guard cannot see it: the guard runs under node,
// where this line works. Resolve to null here and take args.repo below instead.
const REPO_FROM_NODE =
  (typeof process !== 'undefined' && process && process.env)
    ? (process.env.CLAUDE_PROJECT_DIR ?? process.cwd())
    : null

// ── BLAST RADIUS — read before changing the gate ladder ──────────────────────
// A cheap rung here is cheap in TIME. It is never read-only.
// `make test-file` (Makefile:276-284) preflights $(PRE_PYTEST) at Makefile:281,
// which Makefile:79 defines as `uv python-deps db-test db-dev dev-data valhalla`,
// so a per-step gate will START the shared 7688/7687 Neo4j
// containers, RUN scripts/ensure_dev_data.py which WRITES to the shared 7687 dev
// graph, and `docker compose up -d valhalla` from the git common dir. That last
// shape is the same one that killed a live Valhalla container in a logged
// incident. Therefore: this engine assumes EXCLUSIVE use of the local test
// containers. Never run it concurrently with `make test`, `make test-workbench`,
// or a sibling session's suite.

// ── Fan-out model ────────────────────────────────────────────────────────────
// The engine reports how many agents a run will spawn, so the SHAPE of the plan
// is visible before it starts. There is deliberately NO spend throttle: a run
// ends on the termination caps below (attempts, ping-pong, circuit breaker), and
// never on a quota, because a run that halts mid-ledger leaves the tree
// half-changed and the human holding the pieces. `closeBarRun` stays a
// structural one-shot for a different reason: the definitive bar returns the
// same answer twice, so a second run buys nothing and costs everyone the wait.
// Only Tier 3 gets a panel. Below it the undo test, the judge and (at Tier 2)
// acceptance already cover what a panel is aimed at, and the panel is the longest
// serial wait in a run. A one-member panel is never an option: "kill a finding if
// a majority refute" needs N>=2, so a worrying Tier 2 change is planned as Tier 3.
const PANEL_MODELS = { 0: [], 1: [], 2: [], 3: ['opus', 'sonnet', 'haiku'] }

// SCOPE FILTER — NOT an execution guard. Be precise about this; overstating it is
// the same sin as the phantom "lint-enforcer hook" that sat in CLAUDE.md for months.
// ALLOWED_REPRO is consulted only when deciding whether a RETURNED finding counts
// (wellFormed / verifyRepros). It cannot stop a command from running: skeptic agents
// have Bash, so one that runs `make test` really does run the whole suite
// (Makefile sets ONDOWAY_LIVE_TESTS=1), holding the shared containers against every
// sibling track, and this regex merely declines to reward the finding afterward.
// The prompt is the only thing ASKING an agent not to,
// and no hook can back it up — PreToolUse was measured NOT to fire inside the
// Workflow runtime. Treat this as "refuses to pay attention", never "refuses to run".
const ALLOWED_REPRO = /^make (lint|flutter-analyze|golden-probe|test-workbench|_test-python|_test-golden|_test-grade|_test-invariants|test-file FILE="[^"]+")\s*$/

// COLLISION GUARD: only these are safe to execute from a skeptic running in
// parallel with the rest of the panel. Everything else in ALLOWED_REPRO starts or
// uses SHARED resources — the 7688 test DB, the 7687 dev graph (ensure_dev_data
// WRITES to it), the Valhalla container, or :8001 — and CLAUDE.md's isolation
// invariant is explicit that concurrent `make test-workbench` is unsupported and
// that pytest full-wipes 7688 per module. Two panel members picking the same
// target would collide, both see a nonzero exit, and manufacture two phantom
// blockers from a collision this design caused. So a container-touching repro is
// PROPOSED by the panel and executed once, serially, by verifyRepros() below.
// `make lint` only: it is pure ruff (Makefile:103-106) with no shared state.
// `make flutter-analyze` is deliberately EXCLUDED — two concurrent runs contend on
// mobile/.dart_tool and the pub lock, and this repo already has a logged Flutter
// concurrency incident (flutter_test.sh cross-talk, fixed with a per-run log +
// scoped kill + lock). Excluding it costs nothing; it routes to the serial verifier.
const PARALLEL_SAFE_REPRO = /^make lint\s*$/

// ── PURE VALIDATORS ──────────────────────────────────────────────────────────
// WHY THIS IS CODE AND NOT PROMPT TEXT. Until 2026-09-01 `command_valid` was decided by
// the preflight AGENT, from prose rules in its prompt, and the engine merely refused on
// the boolean it came back with (see the `badCmd` gate below). Two things were wrong
// with that. It made string checking an LLM judgement — the same class of work the
// scribe does, and the same money. And `team-engine.test.js` STUBS the preflight agent,
// so no check in the guard could ever reach the rule: it was unguarded by construction,
// which is the exact failure the guard's own header exists to prevent.
//
// The one check that CANNOT move here is "does this Make target exist in the live
// Makefile" — that needs a filesystem, and the workflow runtime has none. It stays with
// the agent, and it is the only validation left in the prompt.
//
// These two functions touch nothing outside their arguments on purpose: the guard lifts
// this whole block out between the marker comments and calls them with no engine
// running. Keep them self-contained, or `validator:extractable` goes red.
//
// String operations, not patterns: a spelling the regex did not think of is how the
// sibling flake rule starved (failures ledger), and every rule below is an exact shape.

// One step, one kind. A step touching product code AND agent tooling has no unambiguous
// gate — `make lint` cannot prove the engine, and the engine's guard cannot prove src/ —
// so it is refused and split rather than guessed at.
const stepKind = (files) => {
  const list = (files || []).map((f) => String(f))
  if (!list.length) return 'none'
  const tooling = list.filter((f) => f.startsWith('.claude/')).length
  if (tooling === list.length) return 'supervision'
  if (tooling === 0) return 'product'
  return 'mixed'
}

const ENGINE_GUARD_CMD = 'node .claude/team-engine.test.js'
const HOOKS_TEST_PREFIX = 'uv run pytest .claude/hooks/tests/'
const HOOKS_TEST_SUFFIX = ' -o addopts= -v'
const PRODUCT_TEST_PREFIX = 'make test-file FILE="'

// Agent tooling is proved by running it, not by a pytest node id inside `make test-file`.
// `make test-file` pulls in _ensure-test-db, _ensure-dev-data and valhalla-up, none of
// which a `.claude/` change needs or should start; and pyproject sets testpaths=["tests"],
// so a test under .claude/hooks/tests/ is outside the product suite by construction.
const isSupervisionProof = (cmd) =>
  cmd === ENGINE_GUARD_CMD ||
  (cmd.startsWith(HOOKS_TEST_PREFIX) && cmd.endsWith(HOOKS_TEST_SUFFIX) &&
   cmd.slice(HOOKS_TEST_PREFIX.length, -HOOKS_TEST_SUFFIX.length).endsWith('.py'))

const validateCommand = (step) => {
  const cmd = String((step && step.test_command) || '').trim()
  const kind = stepKind(step && step.files)

  if (kind === 'none') {
    return { command_valid: false, command_problem: 'step lists no files, so no gate can be derived for it' }
  }
  if (kind === 'mixed') {
    return {
      command_valid: false,
      command_problem: 'step mixes product files with .claude/ tooling; split it — one step, one kind',
    }
  }
  if (kind === 'supervision') {
    if (isSupervisionProof(cmd)) return { command_valid: true, command_problem: '' }
    return {
      command_valid: false,
      command_problem: `a .claude/ step is proved by \`${ENGINE_GUARD_CMD}\` or by ` +
        `\`${HOOKS_TEST_PREFIX}<file>.py${HOOKS_TEST_SUFFIX}\`, not by ${cmd || '(nothing)'}`,
    }
  }

  // Product. A bare -k is consumed by make as --keep-going and the selector becomes a
  // make goal ("No rule to make target") — measured, not theory. LIVE=1 routes to
  // test-live, which sets ONDOWAY_LIVE_TESTS=1 and serialises the run behind that shard.
  if (cmd.includes(' -k ') || cmd.endsWith(' -k')) {
    return { command_valid: false, command_problem: 'bare -k: make reads it as --keep-going and the selector becomes a make goal' }
  }
  if (cmd.includes('LIVE=1')) {
    return { command_valid: false, command_problem: 'LIVE=1 routes to test-live (ONDOWAY_LIVE_TESTS=1) and serialises the run' }
  }
  if (!cmd.startsWith(PRODUCT_TEST_PREFIX) || !cmd.endsWith('"')) {
    return { command_valid: false, command_problem: `a product step must be exactly ${PRODUCT_TEST_PREFIX}<path>::<pytest node id>"` }
  }
  const inside = cmd.slice(PRODUCT_TEST_PREFIX.length, -1)
  if (!inside.includes('::')) {
    return { command_valid: false, command_problem: 'FILE must carry a pytest node id (path::Class::test), not a whole file' }
  }
  return { command_valid: true, command_problem: '' }
}

// What must go green alongside the step's own proof. A supervision step is gated by the
// thing that proves it; an engine edit ALSO re-runs the engine guard, because the close
// gate never does and a broken cap would otherwise ship inside the same run.
const deriveGates = (step) => {
  const files = ((step && step.files) || []).map((f) => String(f))
  const touches = (prefix) => files.some((f) => f.startsWith(prefix))
  const gates = []
  const add = (g) => { if (g && !gates.includes(g)) gates.push(g) }

  if (stepKind(files) === 'supervision') {
    add(String((step && step.test_command) || '').trim())
    if (touches('.claude/team-engine.js')) add(ENGINE_GUARD_CMD)
    return gates
  }

  // `make lint` is ruff and covers ONLY src/, tests/ and scripts/. `make flutter-analyze`
  // is in NEITHER `make lint` NOR `make test`, so without it a Dart error survives the
  // whole ladder. Never a minutes-long target: those are the close gate's job.
  if (touches('src/') || touches('tests/') || touches('scripts/')) add('make lint')
  if (touches('mobile/')) add('make flutter-analyze')
  if (touches('frontend/')) add('make test-file FILE="tests/test_workbench_ui.py::TestWorkbenchUI::test_review_page_loads"')
  if (!gates.length) add('make lint')
  return gates
}
// ── END PURE VALIDATORS ──────────────────────────────────────────────────────

// ── Schemas ──────────────────────────────────────────────────────────────────
const STEP_FIELDS = {
  id: { type: 'string' }, name: { type: 'string' },
  status: { type: 'string', enum: ['pending', 'in_progress', 'completed', 'blocked', 'no-op', 'skipped'] },
  test_command: { type: 'string' },
  gate_commands: { type: 'array', items: { type: 'string' } },
  criterion_ids: { type: 'array', items: { type: 'string' } },
  files: { type: 'array', items: { type: 'string' } },
  depends_on: { type: 'array', items: { type: 'string' } },
  complexity: { type: 'string', enum: ['low', 'normal', 'high'] },
  maxAttempts: { type: 'integer' }, attempts: { type: 'integer' },
  // Placeholders. The preflight agent transcribes the step; the ENGINE overwrites both
  // of these from validateCommand() before the badCmd gate reads them, so whatever the
  // agent reports here never survives. Kept in the schema because the agent must return
  // a shape the engine can fill in, not because its value is trusted.
  command_valid: { type: 'boolean' }, command_problem: { type: 'string' },
}

const LEDGER = {
  type: 'object', additionalProperties: false,
  required: ['topic', 'dir', 'tier', 'approved_by_human', 'steps', 'infra', 'context_path', 'findings_dir'],
  properties: {
    topic: { type: 'string' }, dir: { type: 'string' },
    tier: { type: 'integer', enum: [0, 1, 2, 3] },
    approved_by_human: { type: 'boolean' },
    context_path: { type: 'string' }, findings_dir: { type: 'string' },
    criteria_uncovered: { type: 'array', items: { type: 'string' }, description: 'Acceptance-criterion ids no step claims. Non-empty = the ledger is incomplete.' },
    infra: {
      type: 'object', additionalProperties: false,
      required: ['test_db', 'dev_data', 'valhalla', 'lint_clean', 'engine_guard'],
      properties: {
        test_db: { type: 'boolean' }, dev_data: { type: 'boolean' }, valhalla: { type: 'boolean' },
        render_auth: { type: 'boolean' }, lint_clean: { type: 'boolean' }, notes: { type: 'string' },
        engine_guard: { type: 'boolean', description: 'Did `node .claude/team-engine.test.js` exit 0? Required, so it cannot be silently skipped.' },
      },
    },
    steps: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['id', 'name', 'status', 'test_command', 'criterion_ids', 'files', 'maxAttempts', 'attempts', 'command_valid'], properties: STEP_FIELDS } },
  },
}

const STEP_RESULT = {
  type: 'object', additionalProperties: false,
  required: ['built', 'files_touched', 'diff_stat', 'red_first', 'green'],
  properties: {
    built: { type: 'boolean' },
    files_touched: { type: 'array', items: { type: 'string' } },
    diff_stat: { type: 'string', description: 'Verbatim `git diff --stat` output.' },
    red_first: {
      type: 'object', additionalProperties: false, required: ['ran', 'was_red'],
      properties: { ran: { type: 'boolean' }, was_red: { type: 'boolean' }, output_excerpt: { type: 'string' } },
    },
    green: {
      type: 'object', additionalProperties: false, required: ['ran', 'was_green'],
      properties: { ran: { type: 'boolean' }, was_green: { type: 'boolean' }, output_excerpt: { type: 'string' } },
    },
    blocked_reason: { type: 'string' }, notes: { type: 'string' },
  },
}

const GATE_RESULT = {
  type: 'object', additionalProperties: false,
  required: ['passed', 'checks', 'mutation', 'unverified'],
  properties: {
    passed: { type: 'boolean' },
    checks: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['command', 'exit_code', 'summary'], properties: { command: { type: 'string' }, exit_code: { type: 'integer' }, summary: { type: 'string' }, output_excerpt: { type: 'string' } } } },
    mutation: {
      type: 'object', additionalProperties: false, required: ['verdict'],
      properties: {
        verdict: { type: 'string', enum: ['REAL', 'FAKE', 'NOT_RUN'], description: 'REAL = red on revert AND green on restore. FAKE = still passed with the fix reverted.' },
        red_on_revert: { type: 'boolean' }, green_on_restore: { type: 'boolean' }, evidence: { type: 'string' },
      },
    },
    criteria_uncovered: { type: 'array', items: { type: 'string' } },
    unverified: { type: 'array', items: { type: 'string' } },
    findings_file: { type: 'string' },
  },
}

const PANEL = {
  type: 'object', additionalProperties: false,
  required: ['overall', 'findings', 'attacks_tried'],
  properties: {
    overall: { type: 'string', enum: ['CONFIRMED', 'REFUTED', 'UNPROVEN'] },
    attacks_tried: { type: 'array', items: { type: 'string' } },
    findings_file: { type: 'string' },
    findings: { type: 'array', items: {
      type: 'object', additionalProperties: false,
      required: ['rule', 'title', 'file', 'repro_command', 'repro_verified', 'repro_exit_code', 'severity', 'why'],
      properties: {
        rule: { type: 'string', enum: ['CONFIRMED', 'REFUTED', 'UNPROVEN'] },
        title: { type: 'string' }, file: { type: 'string' }, line: { type: 'integer' },
        repro_command: { type: ['string', 'null'], description: 'The EXACT command you RAN that demonstrates the break, or null. If you did not run it, it MUST be null.' },
        repro_verified: { type: 'boolean', description: 'true ONLY if you executed repro_command in THIS run and observed the failure yourself.' },
        repro_exit_code: { type: ['integer', 'null'] },
        repro_output: { type: 'string' },
        severity: { type: 'string', enum: ['critical', 'high', 'medium', 'low', 'not-a-bug'] },
        why: { type: 'string' },
      } } },
  },
}

// What `track health` prints. Every field is arithmetic over the event log; none
// of it is anybody's opinion, which is why the courier is told not to interpret it.
const HEALTH = {
  type: 'object', additionalProperties: false,
  required: ['progress', 'replan_required'],
  properties: {
    progress: { type: 'integer' },
    issues_total: { type: 'integer' },
    issues_completed: { type: 'integer' },
    replan_required: { type: 'boolean' },
    reason: { type: ['string', 'null'] },
    story: { type: ['string', 'null'] },
  },
}

const VERDICT = {
  type: 'object', additionalProperties: false,
  required: ['ruling', 'evidence_checked', 'missing', 'most_likely_failure', 'proof_line'],
  properties: {
    ruling: { type: 'string', enum: ['PROCEED', 'PROVE-FIRST', 'STOP'] },
    evidence_checked: { type: 'array', items: { type: 'string' } },
    missing: { type: 'array', items: { type: 'string' } },
    criteria_satisfied: { type: 'array', items: { type: 'string' } },
    numbers_reconcile: { type: 'boolean' },
    most_likely_failure: { type: 'string' },
    proof_line: { type: 'string', description: 'ONE dense house-style line for steps[].proof.' },
  },
}

const ACCEPTANCE = {
  type: 'object', additionalProperties: false,
  required: ['verdict', 'artifact_produced', 'evidence', 'top_improvement'],
  properties: {
    verdict: { type: 'string', enum: ['SHIP', 'NEEDS-WORK', 'REJECT', 'UNVERIFIED'] },
    artifact_produced: { type: 'boolean' }, artifact_path: { type: 'string' },
    evidence: { type: 'array', items: { type: 'string' } },
    top_improvement: { type: 'string' },
  },
}

// What a `track` courier hands back: the database's own answer, not a report of it.
// `issues` is the FULL status set — track prints it on every write, including a
// refused one, so the engine never keeps a copy and a caller that loses learns as
// much as one that wins. `refused` carries track's verbatim reason when it declined
// to record a pass, which happens when it ran the step's command and saw non-zero.
const TRACK_WRITE = {
  type: 'object', additionalProperties: false, required: ['ok', 'issues'],
  properties: {
    ok: { type: 'boolean' },
    refused: { type: 'string' },
    issues: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['id', 'status'], properties: { id: { type: 'string' }, status: { type: 'string' } } } },
    stories: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['id', 'state'], properties: { id: { type: 'string' }, state: { type: 'string' }, sent_back: { type: 'integer' } } } },
  },
}

// ── Every agent() goes through call(), so the count is complete by construction ─
let agentCount = 0

const call = async (model, opts, prompt) => {
  agentCount += 1
  // judge.md pins `model: opus` in its own frontmatter; never override it here.
  const o = model === null ? opts : { ...opts, model }
  return agent(prompt, o)
}

// Callers reach us with `args` as either a real object or a JSON-encoded string
// (the Workflow tool stringifies it in some invocation paths). Normalize once so
// A.spec works either way — otherwise every field silently reads as undefined.
const A = (typeof args === 'string')
  ? (() => { try { return JSON.parse(args) } catch (e) { return { __parse_error: String(e) } } })()
  : (args || {})

if (A.__parse_error) return { aborted: 'bad_args', detail: `args was a string that is not valid JSON: ${A.__parse_error}` }
if (!A.spec) return { aborted: 'missing_args', detail: 'args.spec is required, e.g. {spec: "specs/2026-07-25-slug", now: "<ISO-8601>"}.' }
if (!A.now) return { aborted: 'missing_args', detail: 'args.now (ISO-8601) is required — Date.now()/new Date() are forbidden in workflow scripts.' }

// Same shape as args.now: refuse loudly rather than guess. A wrong repo path is
// silently poisonous — it is interpolated into every agent prompt, so agents would
// cd into nothing and report failures that are really a bad path.
const REPO = REPO_FROM_NODE ?? A.repo
if (!REPO) return { aborted: 'missing_args', detail: 'args.repo (absolute path to the checkout) is required — process.env/process.cwd() do not exist in the workflow runtime.' }

const SPEC = A.spec
const MAX_ATTEMPTS = A.maxAttempts ?? 2
const STEPS_PER_PHASE = A.stepsPerPhase ?? 3

// ── Preflight ────────────────────────────────────────────────────────────────
phase('Preflight')
const L = await call('sonnet', { label: 'preflight', phase: 'Preflight', schema: LEDGER, agentType: 'general-purpose', effort: 'medium' },
  `Repo: ${REPO}. Read the plan with \`python3 .claude/ledger/track.py show --json\` (the SQLite schema in that file IS the contract; there is no schema template any more). Do NOT modify any file except as instructed at the end.

1. Report approved_by_human EXACTLY as it appears. Do not infer it, do not set it.
2. TRANSCRIBE each step's test_command and files[] EXACTLY as written. Do NOT judge whether a command is valid: the engine overwrites command_valid and command_problem with its own \`validateCommand\` before anything reads them, so an opinion here is discarded. The schema requires command_valid, so return it as true — a placeholder, not a verdict; writing false there changes nothing. command_problem is optional; leave it off.
   ONE check is still yours, because it needs a filesystem this engine does not have: if a step's command names a Make target, confirm that target EXISTS in the LIVE ${REPO}/Makefile. \`make test-local\` and \`make test-collect\` are cited in older ledgers and NO LONGER EXIST. Report a missing target in infra.notes — do not silently fix the step.
3. Do NOT derive gate_commands. The engine derives them from files[] itself (\`deriveGates\`). Leave the field off, or empty.
4. criteria_uncovered: acceptance_criteria ids that NO step lists in criterion_ids.
5. Probe infra read-only and cheaply: \`docker ps\`, \`make lint\`, and confirm the 7688 test DB / dev data / Valhalla are reachable. Set the infra booleans honestly; a service whose status answers is not necessarily a service that routes.
6. Run \`node .claude/team-engine.test.js\` and set infra.engine_guard to (exit code == 0). That is THIS engine's own guard: a set of stubbed pathological runs plus direct checks on the validators, hermetic, no DB/container/provider. It prints how many shapes it ran — do not assume a count. It is the only thing verifying that the termination caps, the paid-bar one-shot and the pre-fan-out gate order still hold — nothing else runs it, so if it is red the caps below are unverified and the run must not fan out. On failure put the NAMED failing checks verbatim into infra.notes. Never edit the engine or the guard to make it pass.
7. Write ${SPEC}/run-context.md (overwrite): tier, decisions, and the FULL acceptance-criteria list verbatim. Do NOT write gate commands into it — the engine derives those, and a stale copy in a file agents read by path is a second answer to a settled question. Create ${SPEC}/findings/ if absent. Every later agent reads that file BY PATH instead of having it pasted into its prompt.

Return the normalized ledger. dir="${SPEC}", context_path="${SPEC}/run-context.md", findings_dir="${SPEC}/findings".`)

if (!L) return { aborted: 'preflight_failed', detail: 'The preflight agent returned nothing.' }

// THE ENGINE DECIDES VALIDITY, NOT THE AGENT. Whatever command_valid and gate_commands
// the preflight agent reported are overwritten here by the pure validators above. The
// agent still reports the step's test_command and files verbatim — that is transcription,
// which it cannot get wrong in a way this cannot see — but the judgement is code, so the
// guard can exercise it and no prompt rewording can change the answer.
for (const s of L.steps || []) {
  const v = validateCommand(s)
  s.command_valid = v.command_valid
  s.command_problem = v.command_problem
  s.gate_commands = deriveGates(s)
}

const P = PANEL_MODELS[L.tier] ?? []
// 'skipped' is re-admitted under retryBlocked too. The engine assigns that status
// for exactly one reason — 'dependency not completed' (see the depends_on guard in
// the step loop) — which is a TRANSIENT condition, not a verdict on the step. Left
// out, a step skipped because its dependency landed later in the same run could
// never be recovered by any re-run, only by hand-editing the ledger.
const todo = L.steps.filter((s) => s.status === 'pending' || s.status === 'in_progress' || ((s.status === 'blocked' || s.status === 'skipped') && A.retryBlocked))
const badCmd = L.steps.filter((s) => !s.command_valid)

// ── Fan-out size BEFORE any fan-out (the PRE-FLIGHT GATE) ────────────────────
// This block sits ABOVE every gate below — the approval gate included — on
// purpose. /team shows the human the plan AND its size and only THEN asks for a
// go-ahead, so the ledger is necessarily `approved_by_human: false` at the moment
// the estimate is requested (`.claude/commands/team.md` Step 4.5). Sizing a run
// must therefore never require prior approval — nor a booted Docker/Neo4j/Valhalla.
// It is pure arithmetic over the ledger and spawns nothing, so answering early is
// free, while refusing early made the documented /team flow impossible (until
// 2026-07-25 the gate below returned first and estimateOnly was dead code).
// Per step: 2 scribes (in_progress + final). Per attempt: dev + QA + panel + judge.
const perAttemptAgents = 3 + P.length
const S = todo.length
const phaseGates = Math.ceil(S / STEPS_PER_PHASE)
const fixed = 1 /* preflight */ + phaseGates + 1 /* close */ + (L.tier >= 2 ? 1 : 0) + 1 /* run scribe */

const est = {
  steps: S, tier: L.tier, panel: P.length,
  minAgents: fixed + S * (2 + perAttemptAgents),
  maxAgents: fixed + S * (2 + 2 * perAttemptAgents) + 2 /* phase repair */,
}
log(`PLAN: ${S} step(s), tier ${L.tier}, panel of ${P.length} — ${est.minAgents}-${est.maxAgents} agents.`)

// estimateOnly is a pure planning query, so it ANSWERS instead of aborting: every
// condition that would refuse a real run is reported as a diagnostic field here.
// A planner asking "how big is this?" needs the size AND the list of things
// to fix before saying go — being handed one refusal at a time costs a round trip
// each and, for approval, could never be satisfied at that point in the flow.
if (A.estimateOnly) return {
  spec: SPEC, ran: false, stopped_because: 'estimate only — no agents were fanned out',
  estimate: est,
  approved_by_human: L.approved_by_human === true,
  invalid_commands: badCmd.map((s) => ({ id: s.id, test_command: s.test_command, problem: s.command_problem })),
  criteria_uncovered: L.criteria_uncovered ?? [],
  runnable_steps: todo.length,
  infra: L.infra,
  agents_spawned_after_preflight: 0,
}

// THE GATE. A Workflow cannot pause for approval, so this refusal is the mechanism.
if (L.approved_by_human !== true) {
  return { aborted: 'not_approved', spec: SPEC, estimate: est,
    detail: 'No row in the approvals table for this feature. The engine never fans out on an unapproved plan.',
    next_step: `Human: review the plan with python3 .claude/ledger/track.py show, then record your go-ahead with python3 .claude/ledger/track.py approve --feature <slug> --by <you>, then re-run. That command is the only way a row lands in approvals, and it records who and when.` }
}

if (badCmd.length) {
  return { aborted: 'invalid_commands', spec: SPEC,
    bad: badCmd.map((s) => ({ id: s.id, test_command: s.test_command, problem: s.command_problem })),
    next_step: 'Fix these test_commands, then re-run. A PRODUCT step needs a pytest node id inside FILE, no bare -k, no LIVE=1. A step touching only .claude/ needs `node .claude/team-engine.test.js` or `uv run pytest .claude/hooks/tests/<file>.py -o addopts= -v`. A step mixing the two must be split. (A missing Make target is NOT one of these reasons — validateCommand never reads the Makefile; the preflight agent reports that in infra.notes.)' }
}
if (L.criteria_uncovered?.length) {
  return { aborted: 'criteria_uncovered', spec: SPEC, criteria_uncovered: L.criteria_uncovered,
    next_step: 'Every acceptance criterion needs a covering step, or must be moved out of scope explicitly. Re-run /team to amend the plan.' }
}
if (!todo.length) return { spec: SPEC, ran: false, stopped_because: 'no runnable steps — all completed/skipped', steps: L.steps.map((s) => ({ id: s.id, status: s.status })) }


// Every cap below this line rests on guards that only ONE thing verifies:
// `node .claude/team-engine.test.js`. It is deliberately not in `make test` (it is agent
// tooling, not product, and keeping it out is what keeps Node.js off the product suite's
// prerequisite list), so this is the moment it gets run — the last point before fan-out,
// which is also the first moment a broken cap can cost anything. It catches breakage this
// session never saw: a sibling session's edit, a hand edit, a fresh clone.
// `!== true` and not `=== false` on purpose: the schema REQUIRES engine_guard, so a
// missing value means the preflight agent misbehaved, and an unanswered guard is not a
// passed one. Refusing costs one wasted preflight; proceeding risks an unbounded loop or
// a double-charged `make audit`.
if (L.infra.engine_guard !== true) {
  return { aborted: 'engine_guard_red', spec: SPEC, infra: L.infra, estimate: est,
    detail: 'The engine\'s own guard did not pass, so its termination caps, paid-bar one-shot and gate ordering are unverified. Refusing to fan out on an engine that cannot prove it still stops.',
    next_step: 'Run `node .claude/team-engine.test.js`, read the NAMED failing check (its header lists the mutation each one catches), fix .claude/team-engine.js, then re-run. Never edit the guard to make it pass.' }
}

// Infra is checked only once real work is about to start. Fanning out with a
// container down burns the full worst-case agent count on zero work — every
// command fails identically (LEARNINGS.md records exactly this incident).
if (!L.infra.test_db || !L.infra.dev_data || !L.infra.valhalla) {
  return { aborted: 'infra_down', spec: SPEC, infra: L.infra, estimate: est,
    next_step: 'Run `make db-up DB=test && make db-up DB=dev && make valhalla-up`, then re-run.' }
}

// ── Helpers ──────────────────────────────────────────────────────────────────
const CTX = `Read ${L.context_path} FIRST — it holds the tier, decisions, the full acceptance criteria, and the pinned gate commands. Do not re-derive that context.`
const norm = (t) => (t || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim().slice(0, 60)
const dkey = (f) => `${f.file}:${norm(f.title)}` // line-free: lines shift after a fix
// THE ONE PLACE STATUS LIVES IN THIS PROCESS: the answer the database gave last.
// Seeded once from preflight (which reads the database) and refreshed from every
// `track` response after that. It is not a mirror the engine maintains — nothing
// here ever assigns a status it invented, so there is nothing to go stale.
//
// The predecessor WAS a mirror: `scribe` wrote `live.status = status` into
// L.steps and separately asked a haiku agent to edit state.json. The two drifted.
// Measured 2026-07-26: S1 and S3 completed, yet S2 (depends_on S1) and S4
// (depends_on S3) were both skipped 'dependency not completed', stranding 8 of 10
// steps, because `statusOf` read a snapshot the scribe never touched.
const liveStatus = new Map((L.steps || []).map((s) => [String(s.id), s.status]))
const statusOf = (id) => liveStatus.get(String(id))

// Every `track` write prints the full status set, so a caller never keeps a copy.
const absorb = (reply) => {
  for (const issue of (reply && reply.issues) || []) {
    if (issue && issue.id !== undefined) liveStatus.set(String(issue.id), issue.status)
  }
  return reply
}

// A COURIER, NOT A SCRIBE. The old one was handed prose — "update ONLY the step
// whose id ==…, preserve every other key byte-for-byte" — and an agent obeying
// prose is an agent that can get it wrong, or say it did it when it did not. This
// one is handed a command line. It runs it and hands back what the command
// printed. There is nothing in the instruction for it to interpret, and `track`
// re-derives a pass claim by running the test itself, so the courier cannot
// promote a step by asserting anything.
const writeStatus = async (step, status, patch) => {
  const flags = [
    `--id ${JSON.stringify(String(step.id))}`,
    `--status ${JSON.stringify(status)}`,
    `--who ${JSON.stringify('engine')}`,
  ].join(' ')
  const reply = await call('haiku',
    { label: `track:${step.id}:${status}`, phase: 'Rule', schema: TRACK_WRITE, agentType: 'general-purpose', effort: 'low' },
    `Run EXACTLY this command in ${REPO}, once, and nothing else:

    python3 .claude/ledger/track.py step-status ${flags}

Then return what it printed on stdout, parsed: {ok, refused, issues, stories}. Set ok=false and copy the "refused" string verbatim if the command exited non-zero — a refusal is the command telling you the step is NOT done, and it is information, not a problem to work around. Do NOT edit any file, do NOT retry with different flags, and do NOT run anything else.${patch ? `\n\nContext for the log, not a flag to pass: ${JSON.stringify(patch)}` : ''}`)
  return absorb(reply)
}

const failureBrief = (qa) => `GATE RED. ${(qa.checks || []).filter((c) => c.exit_code !== 0).map((c) => `\`${c.command}\` exit ${c.exit_code}: ${c.summary}`).join(' | ')}${(qa.unverified || []).length ? ` UNVERIFIED: ${qa.unverified.join('; ')}` : ''}`
const reworkBrief = (bs) => `VERIFIED BLOCKERS (each was reproduced by a skeptic — re-run the repro yourself FIRST; if it does not reproduce, say so and stop):\n${bs.map((b, i) => `${i + 1}. [${b.severity}] ${b.title} @ ${b.file}${b.line ? `:${b.line}` : ''} — ${b.why}\n   repro: ${b.repro_command} (exit ${b.repro_exit_code})`).join('\n')}`

// Shape checks a finding must pass before it can block anything.
const wellFormed = (f) => f.rule === 'REFUTED' && !!f.repro_command && ALLOWED_REPRO.test(f.repro_command)
// Directly trustworthy: the skeptic ran it itself AND it was safe to run in parallel.
const isBlocking = (f) => wellFormed(f) && f.repro_verified === true
  && f.repro_exit_code !== 0 && f.repro_exit_code !== null && PARALLEL_SAFE_REPRO.test(f.repro_command)
// Well-formed but touches a shared resource: must be re-run serially before it counts.
const needsSerialCheck = (f) => wellFormed(f) && !PARALLEL_SAFE_REPRO.test(f.repro_command)

// Run proposed container-touching repros ONE AT A TIME in a single agent, so the
// panel's parallelism can never turn into a shared-resource collision.
const verifyRepros = async (step, a, cands) => {
  if (!cands.length) return { confirmed: [], infraBlind: 0, proposed: 0 }
  const r = await call('sonnet', { label: `verify-repro:${step.id}:a${a}`, phase: 'Challenge', schema: PANEL, agentType: 'skeptic', effort: 'high' },
    `Repo ${REPO}. ${CTX}
The panel PROPOSED these reproductions but did not run them — they touch shared resources (the 7688 test DB, the 7687 dev graph, the Valhalla container, :8001) and running them concurrently would collide. You are the ONLY agent running them, so run them STRICTLY ONE AT A TIME, in order, waiting for each to finish:
${cands.map((f, i) => `${i + 1}. "${f.title}" (${f.file}) -> ${f.repro_command}`).join('\n')}

For EACH: run it, record the REAL exit code, and set repro_verified=true only if YOU ran it and observed the result. A nonzero exit that is explained by infrastructure (connection refused, container not up, port in use, service half-started) is NOT a confirmed defect — set rule=UNPROVEN and begin \`why\` with the literal token "INFRA:" so the run can count how much of the panel went unverified. Do not let an environment failure masquerade as a code defect, and do not let it masquerade as a clean bill either. Keep rule=REFUTED only for a genuine, reproduced break.
Never run \`make test\`, \`make audit\`, \`make test-live\`, or anything with LIVE=1.`)
  const found = r?.findings || []
  return {
    proposed: cands.length,
    confirmed: found.filter((f) => f.rule === 'REFUTED' && f.repro_verified === true && f.repro_exit_code !== 0 && f.repro_exit_code !== null && ALLOWED_REPRO.test(f.repro_command)),
    // Findings the verifier could not judge because the environment was broken.
    // Surfaced explicitly: silent advisories must never read as consensus.
    infraBlind: found.filter((f) => f.rule === 'UNPROVEN' && /^\s*INFRA:/i.test(f.why || '')).length,
  }
}

const ANGLE = [
  'NEGATIVE SPACE — what states of the world were NOT tested? concurrency and sibling sessions, empty/oversized/degraded input, services half-started, the same code path reached via a different entry point, the fix\'s own side effects on infrastructure.',
  'FIX CORRECTNESS — is the change itself right, and does the red-first test encode the ORIGINAL failure mode or a strawman? Would a plausible neighbouring input still break it?',
  'EVIDENCE CHAIN ONLY — do the pasted numbers reconcile with the repo (test counts, SHAs, ports, file paths)? Was any output piped through tail/grep/|| true, or otherwise able to mask a failure? Do NOT review the design; check the arithmetic and the provenance.',
]

// ── The step loop ────────────────────────────────────────────────────────────
const report = []
const phaseGateLog = []
let stepsRun = 0
let phaseRepairs = 0
let infraStrikes = 0
let infraBlindTotal = 0 // panel findings left unjudged because infra was unavailable
let stopped = null
let closeBarRun = false

for (const step of todo) {
  if (stopped) break
  if (stepsRun >= (A.maxSteps ?? todo.length)) { stopped = 'maxSteps'; break }
  if ((step.depends_on || []).some((id) => statusOf(id) !== 'completed')) {
    await writeStatus(step, 'skipped', { proof: 'dependency not completed' })
    report.push({ id: step.id, name: step.name, status: 'skipped', why: 'dependency not completed' })
    continue
  }

  const cap = Math.min(step.maxAttempts ?? MAX_ATTEMPTS, MAX_ATTEMPTS)
  const gates = (step.gate_commands || []).join(' && ') || 'make lint'
  let prior = new Set()
  let feedback = ''
  let outcome = null
  let lastQa = null

  await writeStatus(step, 'in_progress', null)

  for (let a = (step.attempts || 0) + 1; a <= cap && !outcome; a++) {
    // ── Build ────────────────────────────────────────────────────────────────
    const devModel = (a > 1 || step.complexity === 'high') ? 'opus' : 'sonnet'
    const dev = await call(devModel, { label: `build:${step.id}:a${a}`, phase: 'Build', schema: STEP_RESULT, agentType: 'general-purpose', effort: 'high' },
      `Implement ONE atomic step in ${REPO}. ${CTX}

STEP ${step.id} — ${step.name}
Files you may touch: ${step.files.join(', ')}. Touch NOTHING else.
Satisfies acceptance criteria: ${step.criterion_ids.join(', ')} (their verbatim text is in run-context.md).
ACCEPTANCE COMMAND — must be RED before your change and GREEN after:
    ${step.test_command}

Protocol, in order: (1) write the test FIRST, run the acceptance command, PASTE the red output; (2) make the MINIMAL change; (3) run it again, PASTE the green output; (4) run ${gates}; (5) \`git diff --stat\`.
Do NOT commit. Do NOT weaken or delete an existing test to go green. Do NOT run \`make test\`, \`make audit\` or anything with LIVE=1 — they take minutes, they hold the shared containers against every parallel track, and they are the close gate's job.
If the step turns out to be already satisfied or impossible, return built:false with blocked_reason rather than inventing work.${a > 1 ? `\n\nPRIOR ATTEMPT FAILED — fix exactly this:\n${feedback}` : ''}`)

    if (!dev) { outcome = { status: 'blocked', why: 'developer agent returned nothing' }; break }

    // Empty-diff short circuit: never buy QA + panel + judge for zero work.
    if (!dev.built || !(dev.files_touched || []).length || /^\s*0 files? changed/.test(dev.diff_stat || '')) {
      outcome = { status: 'no-op', why: dev.blocked_reason || 'developer produced an empty diff' }
      break
    }

    // ── Gate (seconds) ───────────────────────────────────────────────────────
    const qa = await call('sonnet', { label: `gate:${step.id}:a${a}`, phase: 'Gate', schema: GATE_RESULT, agentType: 'qa', effort: 'high' },
      `Repo ${REPO}. ${CTX}
Run EXACTLY these and nothing else — ${gates}, then ${step.test_command}.
Do NOT run \`make test\`, \`make audit\`, \`make test-live\`, or \`make tour-grade\` (that target does not exist; the real ones are \`make _test-grade\` and \`make golden-probe\`). Those are the close gate's job: they take minutes and hold the shared containers.

Then the UNDO TEST on the developer's change in ${(dev.files_touched || []).join(', ')}: revert ONLY the source fix (not the test), re-run ${step.test_command} — it MUST go RED; restore, it MUST go GREEN. Paste both. A test that still passes with the fix reverted is FAKE.
Developer's diff: ${dev.diff_stat}
Developer's claimed red-first: ${JSON.stringify(dev.red_first)}
Name any criterion in ${step.criterion_ids.join(', ')} that has no covering check, and list anything you could not verify by running something.`)

    if (!qa) { outcome = { status: 'blocked', why: 'QA agent returned nothing' }; break }

    // Infra circuit breaker: a down container fails every command identically.
    const infraHit = (qa.checks || []).some((c) => /Connection refused|Cannot connect to the Docker daemon|no such container|7688|7689/i.test(`${c.summary} ${c.output_excerpt || ''}`))
    if (infraHit && !qa.passed) {
      infraStrikes += 1
      if (infraStrikes >= 2) { outcome = { status: 'blocked', why: 'infra regressed mid-run (2 consecutive steps)' }; stopped = 'infra_regressed'; break }
    } else if (qa.passed) { infraStrikes = 0 }

    // A FAKE test is terminal, not retryable — retrying one rewards producing it.
    if (qa.mutation?.verdict === 'FAKE') { outcome = { status: 'blocked', why: 'FAKE test — it still passed with the fix reverted', qa }; break }

    lastQa = qa
    if (!qa.passed) {
      feedback = failureBrief(qa)
      if (a === cap) outcome = { status: 'blocked', why: 'gate still red at max attempts', qa }
      continue // cheapest path: no panel, no judge
    }

    // ── Challenge ────────────────────────────────────────────────────────────
    let blockers = []
    let advisory = []
    if (P.length) {
      const panels = (await parallel(P.map((m, i) => () =>
        call(m, { label: `challenge:${step.id}:a${a}:${m}`, phase: 'Challenge', schema: PANEL, agentType: 'skeptic', effort: m === 'haiku' ? 'medium' : 'high' },
          `Repo ${REPO}. ${CTX}
CLAIM: step ${step.id} "${step.name}" satisfies ${step.criterion_ids.join(', ')}, proven by ${step.test_command} plus a QA mutation verdict of ${qa.mutation?.verdict}.
Evidence: ${JSON.stringify(qa.checks)}
Mutation evidence: ${qa.mutation?.evidence || '(none pasted)'}

YOUR ANGLE: ${ANGLE[i] || ANGLE[0]}

CRITICAL RULE: a finding BLOCKS only on a real reproduction. Never fabricate one — a fabricated repro buys a wasted rework cycle and will be caught.
You are running CONCURRENTLY with ${P.length - 1} other skeptic(s), so what you may execute yourself is limited:
  - SAFE TO RUN NOW (no shared state): \`make lint\` only — it is pure ruff. Run it yourself; set repro_verified=true and the real exit code.
  - PROPOSE ONLY, DO NOT RUN: \`make test-file FILE="..."\`, \`make golden-probe\`, \`make test-workbench\`, \`make flutter-analyze\`, \`make _test-python\`, \`make _test-golden\`, \`make _test-grade\`, \`make _test-invariants\`. These start or use the SHARED 7688 test DB, the 7687 dev graph, the Valhalla container, :8001, or mobile/.dart_tool — running one while a sibling skeptic runs another corrupts both results. Put the exact command in repro_command, set repro_verified=false, and a single serial verifier will run it for you. It still counts if it reproduces.
  - NEVER, under any circumstances: \`make test\`, \`make audit\`, \`make test-live\`, or anything with LIVE=1 — you run in parallel with the rest of the panel, and those hold the shared containers for minutes.
If you have no reproduction at all, set repro_command to null. An honest advisory finding is worth more than a fake blocker.
Write your full write-up to ${L.findings_dir}/step-${step.id}-skeptic-${m}.md, stamped with the commit you verified against.`)
      ))).filter(Boolean)

      const seen = new Set()
      const serialCands = []
      panels.flatMap((p) => p.findings || []).forEach((f) => {
        const k = dkey(f)
        if (seen.has(k)) return
        seen.add(k)
        if (isBlocking(f)) blockers.push(f)
        else if (needsSerialCheck(f)) serialCands.push(f)
        else advisory.push(f)
      })
      // Shared-resource repros are re-run once, serially. Only survivors block;
      // the rest are advisory, so a collision or a flake can never force rework.
      if (serialCands.length) {
        const sv = await verifyRepros(step, a, serialCands)
        const ck = new Set(sv.confirmed.map(dkey))
        blockers.push(...sv.confirmed)
        advisory.push(...serialCands.filter((f) => !ck.has(dkey(f))))
        if (sv.infraBlind > 0) {
          infraBlindTotal += sv.infraBlind
          log(`Step ${step.id}: panel could NOT verify ${sv.infraBlind}/${sv.proposed} proposed reproductions — infrastructure unavailable. Those are unjudged, not cleared.`)
        }
      }

      // Ping-pong: a blocker from the previous attempt is back after rework.
      const echo = blockers.filter((f) => prior.has(dkey(f)))
      if (echo.length) {
        outcome = { status: 'blocked', escalate: true, blockers: echo,
          why: `ping-pong: ${echo.map((f) => f.title).join('; ')} reappeared after rework — the fix is not converging` }
        break // skip the judge; saves an opus call and gives a better message
      }
      if (blockers.length) {
        prior = new Set(blockers.map(dkey))
        feedback = reworkBrief(blockers)
        if (a === cap) outcome = { status: 'blocked', why: 'verified repro still unresolved at max attempts', blockers }
        continue
      }
    }

    // ── Rule ─────────────────────────────────────────────────────────────────
    const v = await call(null, { label: `rule:${step.id}:a${a}`, phase: 'Rule', schema: VERDICT, agentType: 'judge', effort: 'high' },
      `Judge Protocol checkpoint: step ${step.id} "${step.name}" of ${L.topic} (tier ${L.tier}), attempt ${a}/${cap}. ${CTX}
Rule PROCEED / PROVE-FIRST / STOP.
Developer: ${dev.diff_stat}; red-first ${JSON.stringify(dev.red_first)}; green ${JSON.stringify(dev.green)}.
QA: ${JSON.stringify(qa.checks)}; mutation ${JSON.stringify(qa.mutation)}; could not verify: ${JSON.stringify(qa.unverified)}.
ADVISORY findings (no verified reproduction — do NOT treat these as blocking, but say if one changes your ruling): ${advisory.map((f) => f.title).join('; ') || 'none'}
Verify the numbers reconcile against the repo yourself. Confirm every criterion in ${step.criterion_ids.join(', ')} has a covering check.
Note: this run has NOT executed the full bar — that is the close gate, deliberately run once. Judge this step against its own acceptance command, not against \`make test\`.
If PROCEED, return proof_line: ONE dense line in the house style used by existing steps[].proof entries.`)

    if (!v) { outcome = { status: 'blocked', why: 'judge agent returned nothing' }; break }
    if (v.ruling === 'STOP') { outcome = { status: 'blocked', why: `judge STOP: ${(v.missing || []).join('; ')}`, verdict: v }; stopped = 'judge_stop'; break }
    if (v.ruling === 'PROVE-FIRST') {
      feedback = `JUDGE PROVE-FIRST. Missing: ${(v.missing || []).join('; ')}`
      if (a === cap) outcome = { status: 'blocked', why: 'judge PROVE-FIRST at max attempts', verdict: v }
      continue
    }
    outcome = { status: 'completed', proof: v.proof_line, verdict: v, advisory: advisory.map((f) => f.title), attempts: a }
  }

  outcome ||= { status: 'blocked', why: 'attempts exhausted' }
  await writeStatus(step, outcome.status, {
    attempts: outcome.attempts ?? cap,
    proof: outcome.proof || outcome.why, commit: 'pending',
  })
  report.push({ id: step.id, name: step.name, ...outcome })
  stepsRun += 1
  log(`Step ${step.id} "${step.name}": ${outcome.status}${outcome.why ? ` — ${outcome.why}` : ''} (${agentCount} agents)`)

  // ── PhaseGate: the fast shards, SERIAL (they share 7688 / dev data / Valhalla)
  const last = step === todo[todo.length - 1]
  if (!stopped && (stepsRun % STEPS_PER_PHASE === 0 || last) && report.some((r) => r.status === 'completed')) {
    const g = await call('haiku', { label: `phasegate:${stepsRun}`, phase: 'PhaseGate', schema: GATE_RESULT, agentType: 'general-purpose', effort: 'low' },
      `Repo ${REPO}. Run these IN ORDER, ONE AT A TIME — they all depend on _ensure-test-db, _ensure-dev-data and valhalla-up (Makefile:183-195), so they share the 7688 DB, the dev data and the Valhalla container. NEVER run them concurrently:
  make _test-python
  make flutter-test
  make test-workbench
  make _test-golden
Do NOT run \`make test\`, \`make test-live\`, \`make _test-cloud\` or \`make audit\` — those are the close gate's job and hold the shared containers for minutes.
Report each exit code with a verbatim excerpt. Stop at the first failure and paste the full failing test name and traceback. Fix NOTHING. Set mutation.verdict="NOT_RUN".`)
    phaseGateLog.push({ after_steps: stepsRun, passed: !!g?.passed, checks: g?.checks })

    // ── The manager ──────────────────────────────────────────────────────────
    // Progress is COMPUTED, never reported. `track health` reads the event log and
    // the recorded exit codes and answers three arithmetic questions: was a story
    // sent back twice without moving, did something already proved go green then
    // red, is one issue piling up attempts with nothing changing. The courier here
    // runs the command and hands back what it printed — it does not judge, and
    // there is no prompt wording that could make it judge.
    //
    // The REPLAN is an agent. The DECISION to replan is never an agent. That
    // separation is the whole reason this exists: a manager that could be talked
    // round is the same manager that let a run spin for an afternoon.
    const h = await call('haiku', { label: `health:${stepsRun}`, phase: 'PhaseGate', schema: HEALTH, agentType: 'general-purpose', effort: 'low' },
      `Run EXACTLY this in ${REPO}, once, and nothing else:

    python3 .claude/ledger/track.py health

Return what it printed, parsed. Do not interpret it, do not decide whether the run should continue, and do not run anything else.`)
    if (h && h.replan_required) {
      stopped = 'replan_required'
      report.push({ id: `manager:${stepsRun}`, name: 'manager called a replan',
        status: 'blocked', why: `${h.story ? `story ${h.story}: ` : ''}${h.reason || 'progress went backwards'}` })
      log(`Manager: replan required — ${h.reason}. The plan is wrong; the run stops here.`)
      break
    }

    if (g && !g.passed) {
      if (phaseRepairs >= 1) { stopped = 'phase_gate_red'; break }
      phaseRepairs += 1
      log(`Phase gate RED after ${stepsRun} steps — one targeted repair, then re-gate. This never re-enters the step loop.`)
      await call('opus', { label: `phase-repair:${stepsRun}`, phase: 'PhaseGate', schema: STEP_RESULT, agentType: 'general-purpose', effort: 'high' },
        `Repo ${REPO}. ${CTX}
A phase gate went RED after steps that each passed their own per-step gate — so this is very likely a CROSS-STEP interaction, not a single step's bug.
Failing checks: ${JSON.stringify(g.checks)}
Diagnose the root cause (read the exact error and traceback first — do not guess), then apply the MINIMAL fix. Touch only what the diagnosis requires. Do NOT commit, do NOT weaken a test, do NOT run \`make test\`/\`make audit\`. Re-run only the specific failing shard to confirm.`)
      const g2 = await call('haiku', { label: `phasegate:${stepsRun}:retry`, phase: 'PhaseGate', schema: GATE_RESULT, agentType: 'general-purpose', effort: 'low' },
        `Repo ${REPO}. Re-run the same four shards IN ORDER, one at a time: make _test-python, make flutter-test, make test-workbench, make _test-golden. Nothing else, nothing paid. Report exit codes verbatim. Fix nothing. mutation.verdict="NOT_RUN".`)
      phaseGateLog.push({ after_steps: stepsRun, retry: true, passed: !!g2?.passed, checks: g2?.checks })
      if (!g2 || !g2.passed) { stopped = 'phase_gate_red'; break }
    }
  }
}

// ── Close ────────────────────────────────────────────────────────────────────
phase('Close')
const anyCompleted = report.some((r) => r.status === 'completed')
let close = null
let accept = null

if (anyCompleted && !stopped && !closeBarRun) {
  closeBarRun = true // structural one-shot: the definitive bar never runs twice
  close = await call('haiku', { label: 'close-gate', phase: 'Close', schema: GATE_RESULT, agentType: 'general-purpose', effort: 'low' },
    `Repo ${REPO}. Run \`make audit\` ONCE. That is \`make lint\` then \`make test\` (Makefile:135-137) — closing on \`make test\` alone would certify green with a dirty linter, since \`test\` does not include \`lint\`.
Run it EXACTLY once: it is the slowest rung and it serializes against every other track (test-live sets ONDOWAY_LIVE_TESTS=1 and _test-cloud resumes Aura). Do NOT re-run it on failure, do NOT run individual shards to "check", do NOT retry a flake — an intermittent failure is a real signal to report, not to re-roll.
Also run \`make flutter-analyze\` (it is in neither \`lint\` nor \`test\`, so a Dart analyzer error would otherwise survive the whole ladder).
Report every shard's result verbatim, including any skips (a skip is a failure in disguise — say which and why). Fix NOTHING. Set mutation.verdict="NOT_RUN".`)
} else if (!anyCompleted) {
  log('Close gate SKIPPED: no step completed, so there is nothing to certify. The paid bar was not run.')
} else {
  log(`Close gate SKIPPED: run stopped early (${stopped}). The paid bar is not run on an incomplete run.`)
}

if (L.tier >= 2 && close?.passed) {
  accept = await call('opus', { label: 'acceptance', phase: 'Close', schema: ACCEPTANCE, agentType: 'acceptance', effort: 'high' },
    `Repo ${REPO}. ${CTX}
Steps shipped this run: ${report.filter((r) => r.status === 'completed').map((r) => `${r.id} ${r.name}`).join('; ')}.
Produce the REAL artifact and judge it as the end user would. Note \`make tour-grade\` does NOT exist — use \`make golden-probe\` (confirm Valhalla tiles are READY first, or the haversine fallback gives false numbers) and \`make _test-grade\`.
If you cannot produce the artifact, return UNVERIFIED — do not vouch for an experience you did not have.
Write your write-up to ${L.findings_dir}/acceptance.md.`)
}

// THE RUN SUMMARY IS NOT WRITTEN BY AN AGENT ANY MORE. It used to be: a haiku
// agent was handed a JSON blob and asked to merge it into state.json's "run" key.
// That store is gone, and with it the reason for the call. Everything the summary
// held is already recorded by something that observed it — every status change is
// an `events` row written by `track`, every command's real exit code is a
// `test_runs` row — and the rest is returned below, where /team reports it. One
// fewer agent per run, and a summary nobody had to be trusted to transcribe.

return {
  spec: SPEC,
  tier: L.tier,
  stopped_because: stopped ?? 'all steps processed',
  steps: report.map((r) => ({ id: r.id, name: r.name, status: r.status, why: r.why, proof: r.proof })),
  completed: report.filter((r) => r.status === 'completed').length,
  blocked: report.filter((r) => r.status === 'blocked').map((r) => ({ id: r.id, why: r.why })),
  close_gate: close ? { passed: close.passed, checks: close.checks, unverified: close.unverified } : null,
  acceptance: accept,
  agents: agentCount,
  close_bar_runs: closeBarRun ? 1 : 0,
  // Non-zero means the skeptic panel's verdict is INCOMPLETE, not clean: that many
  // proposed reproductions could not be run because infrastructure was unavailable.
  panel_findings_unverified_infra: infraBlindTotal,
  panel_caveat: infraBlindTotal > 0
    ? `${infraBlindTotal} panel finding(s) went UNJUDGED because infra was unavailable — do NOT read this run as an adversarial all-clear.`
    : null,
  estimate_was: est,
  next_step: 'Human: read `git diff`, confirm every change is intentional, then commit. The engine never commits — same contract as proactive-audit. Anything blocked is recorded in the tracker with its reason; re-run with {retryBlocked:true} after addressing it.',
}
