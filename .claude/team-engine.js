export const meta = {
  name: 'team-engine',
  description: 'INTERNAL execution engine for /team — not a command you type. /team invokes it after you approve its plan in chat. Executes an approved specs/{date}-{slug}/state.json step ledger: per step Build -> $0 Gate -> tier-sized skeptic panel -> Judge -> persist. Cost-laddered and hard-capped, so it always terminates and reports. Does NOT commit.',
  whenToUse: 'Do NOT invoke this directly — use `/team <task>` and say "go"; it calls this for you. Direct invocation is for resuming a partially-run ledger only. Requires a state.json with approved_by_human:true (it refuses to fan out otherwise). args: {spec: "specs/2026-07-25-slug" (required), now: ISO-8601 (required — Date.now() is forbidden in workflow scripts), estimateOnly?: bool, maxSteps?: int, maxAttempts?: int (default 2), stepsPerPhase?: int (default 3), budgetUnits?: int, retryBlocked?: bool}.',
  phases: [
    { title: 'Preflight', detail: 'load ledger, check approval, validate every command against the LIVE Makefile, probe infra, self-test the engine, print the cost estimate' },
    { title: 'Build', detail: 'one developer per step, red-first, minimal diff' },
    { title: 'Gate', detail: 'no provider spend: derived lint + the step node-id test + the undo/mutation test (NOTE: starts/uses the SHARED local containers)' },
    { title: 'Challenge', detail: 'tier-sized hostile panel on different models; only a VERIFIED repro can block' },
    { title: 'Rule', detail: 'judge PROCEED / PROVE-FIRST / STOP, then the scribe rewrites state.json' },
    { title: 'PhaseGate', detail: 'non-paid shards, serialized (they share the 7688 DB, dev data and Valhalla)' },
    { title: 'Close', detail: '`make audit` exactly ONCE (paid), acceptance for tier >= 2, final report' },
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

// ── BLAST RADIUS — read before changing the cost ladder ──────────────────────
// "$0" in this file means ZERO PROVIDER SPEND. It does NOT mean read-only.
// `make test-file` depends on _ensure-test-db + _ensure-dev-data + valhalla-up
// (Makefile:144-146), so a per-step gate will START the shared 7688/7687 Neo4j
// containers, RUN scripts/ensure_dev_data.py which WRITES to the shared 7687 dev
// graph, and `docker compose up -d valhalla` from the git common dir. That last
// shape is the same one that killed a live Valhalla container in a logged
// incident. Therefore: this engine assumes EXCLUSIVE use of the local test
// containers. Never run it concurrently with `make test`, `make test-workbench`,
// or a sibling session's suite.

// ── Cost model ───────────────────────────────────────────────────────────────
// Model-weighted AGENT INVOCATIONS, not dollars and not tokens: the script
// cannot observe real spend. The ONE genuinely structural dollar guard is the
// `paidGateRun` one-shot around `make audit`. ALLOWED_REPRO below is NOT a
// second one — see the note on it.
const WEIGHT = { opus: 5, sonnet: 2, haiku: 1 }
const PANEL_MODELS = { 0: [], 1: [], 2: ['opus', 'sonnet'], 3: ['opus', 'sonnet', 'haiku'] }

// MONEY FILTER — NOT an execution guard. Be precise about this; overstating it is
// the same sin as the phantom "lint-enforcer hook" that sat in CLAUDE.md for months.
// ALLOWED_REPRO is consulted only when deciding whether a RETURNED finding counts
// (wellFormed / verifyRepros). It cannot stop a command from running: skeptic agents
// have Bash, so one that runs `make test` really does spend the money
// (Makefile sets ONDOWAY_ENABLE_PAID_LLM_CALLS=1) and this regex merely declines to
// reward the finding afterward. The prompt is the only thing ASKING an agent not to,
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

// ── Schemas ──────────────────────────────────────────────────────────────────
const STEP_FIELDS = {
  id: { type: 'string' }, name: { type: 'string' },
  status: { type: 'string', enum: ['pending', 'in_progress', 'completed', 'blocked', 'no-op', 'skipped'] },
  test_command: { type: 'string' },
  gate_commands: { type: 'array', items: { type: 'string' } },
  criterion_ids: { type: 'array', items: { type: 'string' } },
  files: { type: 'array', items: { type: 'string' } },
  depends_on: { type: 'array', items: { type: 'string' } },
  cost_class: { type: 'string', enum: ['$0', 'paid'] },
  complexity: { type: 'string', enum: ['low', 'normal', 'high'] },
  maxAttempts: { type: 'integer' }, attempts: { type: 'integer' },
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
    steps: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['id', 'name', 'status', 'test_command', 'criterion_ids', 'files', 'cost_class', 'maxAttempts', 'attempts', 'command_valid'], properties: STEP_FIELDS } },
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

const LEDGER_WRITE = {
  type: 'object', additionalProperties: false, required: ['ok', 'step_id', 'status'],
  properties: { ok: { type: 'boolean' }, step_id: { type: 'string' }, status: { type: 'string' }, path: { type: 'string' }, error: { type: 'string' } },
}

// ── Budget: every agent() in this file goes through call(), nothing escapes ───
let spent = 0
let agentCount = 0
const bank = { total: 0, remaining: () => bank.total - spent, ok: (w) => spent + w <= bank.total }

const call = async (model, opts, prompt) => {
  const w = WEIGHT[model] ?? 2
  if (bank.total > 0 && !bank.ok(w)) throw new Error(`BUDGET_EXHAUSTED before ${opts.label}`)
  spent += w
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
  `Repo: ${REPO}. Read ${SPEC}/state.json (contract: specs/_templates/team-state.schema.json). Do NOT modify any file except as instructed at the end.

1. Report approved_by_human EXACTLY as it appears. Do not infer it, do not set it.
2. For EACH step, validate test_command and set command_valid:
   - It MUST be exactly \`make test-file FILE="<path>::<pytest node id>"\`.
   - REJECT any command containing a bare \`-k\`: Makefile:139-149 is \`$(TEST_EXEC) uv run pytest "$(FILE)" -o addopts= -v\` with NO $(PYTEST_ARGS) passthrough, so make consumes -k as --keep-going and the selector becomes a make goal ("No rule to make target"). Verified behaviour, not theory.
   - REJECT LIVE=1 (routes to test-live -> ONDOWAY_ENABLE_PAID_LLM_CALLS=1, real money).
   - REJECT any Make target absent from the LIVE ${REPO}/Makefile. \`make test-local\` and \`make test-collect\` are cited in older ledgers and NO LONGER EXIST.
   Put the reason in command_problem.
3. Derive gate_commands from each step's files[]: \`make lint\` for src/|tests/|scripts/ (it covers ONLY those — Makefile:103-106); \`make flutter-analyze\` for mobile/ (it is in NEITHER make lint NOR make test, so without this a Dart error survives the whole ladder); a targeted \`make test-file FILE="tests/test_workbench_ui.py::..."\` for frontend/. Never put \`make test\`, \`make audit\`, \`make test-live\` or \`make test-workbench\` (minutes-long) in a per-step gate.
4. criteria_uncovered: acceptance_criteria ids that NO step lists in criterion_ids.
5. Probe infra read-only and cheaply: \`docker ps\`, \`make lint\`, and confirm the 7688 test DB / dev data / Valhalla are reachable. Set the infra booleans honestly; a service whose status answers is not necessarily a service that routes.
6. Run \`node .claude/team-engine.test.js\` and set infra.engine_guard to (exit code == 0). That is THIS engine's own guard: 17 stubbed pathological runs, hermetic, ~50ms, no DB/container/provider. It is the only thing verifying that the termination caps, the paid-bar one-shot and the pre-fan-out gate order still hold — nothing else runs it, so if it is red the caps below are unverified and the run must not fan out. On failure put the NAMED failing checks verbatim into infra.notes. Never edit the engine or the guard to make it pass.
7. Write ${SPEC}/run-context.md (overwrite): tier, decisions, the FULL acceptance-criteria list verbatim, baseline, and the pinned gate commands. Create ${SPEC}/findings/ if absent. Every later agent reads that file BY PATH instead of having it pasted into its prompt.

Return the normalized ledger. dir="${SPEC}", context_path="${SPEC}/run-context.md", findings_dir="${SPEC}/findings".`)

if (!L) return { aborted: 'preflight_failed', detail: 'The preflight agent returned nothing.' }

const P = PANEL_MODELS[L.tier] ?? []
// 'skipped' is re-admitted under retryBlocked too. The engine assigns that status
// for exactly one reason — 'dependency not completed' (see the depends_on guard in
// the step loop) — which is a TRANSIENT condition, not a verdict on the step. Left
// out, a step skipped because its dependency landed later in the same run could
// never be recovered by any re-run, only by hand-editing the ledger.
const todo = L.steps.filter((s) => s.status === 'pending' || s.status === 'in_progress' || ((s.status === 'blocked' || s.status === 'skipped') && A.retryBlocked))
const badCmd = L.steps.filter((s) => !s.command_valid)

// ── Cost estimate BEFORE any fan-out (the PRE-FLIGHT GATE) ───────────────────
// This block sits ABOVE every gate below — the approval gate included — on
// purpose. /team shows the human the plan AND its price and only THEN asks for a
// go-ahead, so the ledger is necessarily `approved_by_human: false` at the moment
// the estimate is requested (`.claude/commands/team.md` Step 4.5). Pricing a run
// must therefore never require prior approval — nor a booted Docker/Neo4j/Valhalla.
// It is pure arithmetic over the ledger and spawns nothing, so answering early is
// free, while refusing early made the documented /team flow impossible (until
// 2026-07-25 the gate below returned first and estimateOnly was dead code).
// Per step: 2 scribes (in_progress + final). Per attempt: dev + QA + panel + judge.
const panelUnits = P.reduce((n, m) => n + WEIGHT[m], 0)
const perAttemptAgents = 3 + P.length
const perAttemptUnits = WEIGHT.sonnet /* dev */ + WEIGHT.sonnet /* qa */ + panelUnits + WEIGHT.opus /* judge */
const perAttemptUnitsRetry = perAttemptUnits + (WEIGHT.opus - WEIGHT.sonnet) // dev escalates to opus
const S = todo.length
const phaseGates = Math.ceil(S / STEPS_PER_PHASE)
const fixed = 1 /* preflight */ + phaseGates + 1 /* close */ + (L.tier >= 2 ? 1 : 0) + 1 /* run scribe */
const fixedUnits = WEIGHT.sonnet + phaseGates * WEIGHT.haiku + WEIGHT.haiku + (L.tier >= 2 ? WEIGHT.opus : 0) + WEIGHT.haiku

const est = {
  steps: S, tier: L.tier, panel: P.length,
  minAgents: fixed + S * (2 + perAttemptAgents),
  maxAgents: fixed + S * (2 + 2 * perAttemptAgents) + 2 /* phase repair */,
  minUnits: fixedUnits + S * (2 * WEIGHT.haiku + perAttemptUnits),
  maxUnits: fixedUnits + S * (2 * WEIGHT.haiku + perAttemptUnits + perAttemptUnitsRetry) + (WEIGHT.haiku + WEIGHT.opus),
  paid_commands: 'exactly one `make audit` at close',
}
bank.total = A.budgetUnits ?? Math.ceil(est.maxUnits * 1.05)
log(`ESTIMATE: ${est.minAgents}-${est.maxAgents} agents, ${est.minUnits}-${est.maxUnits} weighted units (opus 5 / sonnet 2 / haiku 1). Budget ${bank.total}. Paid commands: ${est.paid_commands}.`)

// estimateOnly is a pure planning query, so it ANSWERS instead of aborting: every
// condition that would refuse a real run is reported as a diagnostic field here.
// A planner asking "what would this cost?" needs the price AND the list of things
// to fix before saying go — being handed one refusal at a time costs a round trip
// each and, for approval, could never be satisfied at that point in the flow.
if (A.estimateOnly) return {
  spec: SPEC, ran: false, stopped_because: 'estimate only — no agents were fanned out',
  estimate: est, budget_units: bank.total,
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
    detail: 'state.json has approved_by_human != true. The engine never fans out on an unapproved ledger.',
    next_step: `Human: review ${SPEC}/state.json, then set approved_by_human:true and approved_at, then re-run.` }
}

if (badCmd.length) {
  return { aborted: 'invalid_commands', spec: SPEC,
    bad: badCmd.map((s) => ({ id: s.id, test_command: s.test_command, problem: s.command_problem })),
    next_step: 'Fix these test_commands in state.json (pytest node id inside FILE, no -k, no LIVE=1, target must exist in the live Makefile), then re-run.' }
}
if (L.criteria_uncovered?.length) {
  return { aborted: 'criteria_uncovered', spec: SPEC, criteria_uncovered: L.criteria_uncovered,
    next_step: 'Every acceptance criterion needs a covering step, or must be moved out of scope explicitly in state.json. Re-run /team to amend the ledger.' }
}
if (!todo.length) return { spec: SPEC, ran: false, stopped_because: 'no runnable steps — all completed/skipped', steps: L.steps.map((s) => ({ id: s.id, status: s.status })) }

if (est.maxUnits > bank.total) log(`WARNING: worst case ${est.maxUnits} exceeds budget ${bank.total} — the run will stop early if it gets there.`)

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
const statusOf = (id) => (L.steps.find((s) => String(s.id) === String(id)) || {}).status

// Mirror the status onto the in-memory ledger BEFORE handing the write to the
// scribe agent. `statusOf` (and therefore every depends_on check) reads L.steps,
// but the scribe only ever wrote the FILE and state.json is never re-read — so a
// dependency satisfied DURING the run still looked 'pending' and its dependents
// were unconditionally skipped. Measured 2026-07-26: S1 and S3 completed, yet S2
// (depends_on S1) and S4 (depends_on S3) were both skipped 'dependency not
// completed', stranding 8 of 10 steps. The harness never caught it because
// STEPS(n) built no depends_on at all — see the 'dep-chain' mode.
const scribe = (step, status, patch) => {
  const live = L.steps.find((s) => String(s.id) === String(step.id))
  if (live) live.status = status
  return call('haiku',
  { label: `scribe:${step.id}:${status}`, phase: 'Rule', schema: LEDGER_WRITE, agentType: 'general-purpose', effort: 'low' },
  `In ${SPEC}/state.json update ONLY the step whose id == "${step.id}": set status="${status}"${patch ? `, and merge these fields: ${JSON.stringify(patch)}` : ''}.
Preserve every other key and the file's shape byte-for-byte otherwise. Step ids may be non-integer (an existing ledger has id 6.5) — do NOT renumber, reorder, or reformat. commit stays "pending": this workflow never commits. Use a small python/jq edit, never a rewrite from memory. Return {ok, step_id, status, path}.`)
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
let paidGateRun = false

for (const step of todo) {
  if (stopped) break
  if (stepsRun >= (A.maxSteps ?? todo.length)) { stopped = 'maxSteps'; break }
  if (bank.total > 0 && !bank.ok(WEIGHT.opus)) { stopped = 'budget'; break }
  if ((step.depends_on || []).some((id) => statusOf(id) !== 'completed')) {
    await scribe(step, 'skipped', { proof: 'dependency not completed' })
    report.push({ id: step.id, name: step.name, status: 'skipped', why: 'dependency not completed' })
    continue
  }

  const cap = Math.min(step.maxAttempts ?? MAX_ATTEMPTS, MAX_ATTEMPTS)
  const gates = (step.gate_commands || []).join(' && ') || 'make lint'
  let prior = new Set()
  let feedback = ''
  let outcome = null
  let lastQa = null

  await scribe(step, 'in_progress', null)

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
Do NOT commit. Do NOT weaken or delete an existing test to go green. Do NOT run \`make test\`, \`make audit\` or anything with LIVE=1 — they cost real money and are reserved for the close gate.
If the step turns out to be already satisfied or impossible, return built:false with blocked_reason rather than inventing work.${a > 1 ? `\n\nPRIOR ATTEMPT FAILED — fix exactly this:\n${feedback}` : ''}`)

    if (!dev) { outcome = { status: 'blocked', why: 'developer agent returned nothing' }; break }

    // Empty-diff short circuit: never buy QA + panel + judge for zero work.
    if (!dev.built || !(dev.files_touched || []).length || /^\s*0 files? changed/.test(dev.diff_stat || '')) {
      outcome = { status: 'no-op', why: dev.blocked_reason || 'developer produced an empty diff' }
      break
    }

    // ── Gate ($0, seconds) ───────────────────────────────────────────────────
    const qa = await call('sonnet', { label: `gate:${step.id}:a${a}`, phase: 'Gate', schema: GATE_RESULT, agentType: 'qa', effort: 'high' },
      `Repo ${REPO}. ${CTX}
Run EXACTLY these and nothing else — ${gates}, then ${step.test_command}.
Do NOT run \`make test\`, \`make audit\`, \`make test-live\`, or \`make tour-grade\` (that target does not exist; the real ones are \`make _test-grade\` and \`make golden-probe\`). Those are the close gate's job and two of them cost real money.

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
  - NEVER, under any circumstances: \`make test\`, \`make audit\`, \`make test-live\`, or anything with LIVE=1 — those cost real money.
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
  await scribe(step, outcome.status, {
    attempts: outcome.attempts ?? cap, cost: '$0', cost_class: '$0',
    proof: outcome.proof || outcome.why, commit: 'pending',
  })
  report.push({ id: step.id, name: step.name, ...outcome })
  stepsRun += 1
  log(`Step ${step.id} "${step.name}": ${outcome.status}${outcome.why ? ` — ${outcome.why}` : ''} (${agentCount} agents, ${spent}/${bank.total} units)`)

  // ── PhaseGate: non-paid shards, SERIAL (they share 7688 / dev data / Valhalla)
  const last = step === todo[todo.length - 1]
  if (!stopped && (stepsRun % STEPS_PER_PHASE === 0 || last) && report.some((r) => r.status === 'completed')) {
    const g = await call('haiku', { label: `phasegate:${stepsRun}`, phase: 'PhaseGate', schema: GATE_RESULT, agentType: 'general-purpose', effort: 'low' },
      `Repo ${REPO}. Run these IN ORDER, ONE AT A TIME — they all depend on _ensure-test-db, _ensure-dev-data and valhalla-up (Makefile:183-195), so they share the 7688 DB, the dev data and the Valhalla container. NEVER run them concurrently:
  make _test-python
  make flutter-test
  make test-workbench
  make _test-golden
Do NOT run \`make test\`, \`make test-live\`, \`make _test-cloud\` or \`make audit\` — those cost real money and are the close gate's job.
Report each exit code with a verbatim excerpt. Stop at the first failure and paste the full failing test name and traceback. Fix NOTHING. Set mutation.verdict="NOT_RUN".`)
    phaseGateLog.push({ after_steps: stepsRun, passed: !!g?.passed, checks: g?.checks })

    if (g && !g.passed) {
      if (phaseRepairs >= 1) { stopped = 'phase_gate_red'; break }
      phaseRepairs += 1
      log(`Phase gate RED after ${stepsRun} steps — one targeted repair, then re-gate. This never re-enters the step loop.`)
      await call('opus', { label: `phase-repair:${stepsRun}`, phase: 'PhaseGate', schema: STEP_RESULT, agentType: 'general-purpose', effort: 'high' },
        `Repo ${REPO}. ${CTX}
A phase gate went RED after steps that each passed their own $0 gate — so this is very likely a CROSS-STEP interaction, not a single step's bug.
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

if (anyCompleted && !stopped && !paidGateRun) {
  paidGateRun = true // structural one-shot: the paid bar can never run twice
  close = await call('haiku', { label: 'close-gate', phase: 'Close', schema: GATE_RESULT, agentType: 'general-purpose', effort: 'low' },
    `Repo ${REPO}. Run \`make audit\` ONCE. That is \`make lint\` then \`make test\` (Makefile:135-137) — closing on \`make test\` alone would certify green with a dirty linter, since \`test\` does not include \`lint\`.
This is the ONLY paid command of the entire run: test-live sets ONDOWAY_ENABLE_PAID_LLM_CALLS=1 and _test-cloud resumes Aura. Run it EXACTLY once. Do NOT re-run it on failure, do NOT run individual shards to "check", do NOT retry a flake — an intermittent failure is a real signal to report, not to re-roll.
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

await call('haiku', { label: 'scribe:run', phase: 'Close', schema: LEDGER_WRITE, agentType: 'general-purpose', effort: 'low' },
  `In ${SPEC}/state.json merge this into the top-level "run" object (create it if absent), preserving everything else byte-for-byte:
${JSON.stringify({ last_run: A.now, agents: agentCount, budget_units: `${spent}/${bank.total}`, stopped_because: stopped ?? 'all steps processed', paid_gate_runs: paidGateRun ? 1 : 0, panel_findings_unverified_infra: infraBlindTotal, phase_gates: phaseGateLog, close_gate: close ? { passed: close.passed, checks: close.checks } : null, acceptance: accept ? accept.verdict : null })}
Return {ok, step_id:"run", status:"recorded"}.`)

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
  budget_units: `${spent}/${bank.total}`,
  paid_gate_runs: paidGateRun ? 1 : 0,
  // Non-zero means the skeptic panel's verdict is INCOMPLETE, not clean: that many
  // proposed reproductions could not be run because infrastructure was unavailable.
  panel_findings_unverified_infra: infraBlindTotal,
  panel_caveat: infraBlindTotal > 0
    ? `${infraBlindTotal} panel finding(s) went UNJUDGED because infra was unavailable — do NOT read this run as an adversarial all-clear.`
    : null,
  estimate_was: est,
  next_step: 'Human: read `git diff`, confirm every change is intentional, then commit. The engine never commits — same contract as proactive-audit. Anything blocked is recorded in state.json with its reason; re-run with {retryBlocked:true} after addressing it.',
}
