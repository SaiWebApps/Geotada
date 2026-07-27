// Standalone regression guard for the /team execution engine (./team-engine.js).
//
//   node .claude/team-engine.test.js          human-readable table + check results
//   node .claude/team-engine.test.js --json   machine-readable
//
// Exits 0 if every check passes, 1 otherwise. No pytest, no database, no container,
// no provider, no network — it stubs every agent and runs in ~50ms. It lives beside
// the engine it tests because it guards Claude tooling, not the Ondoway product;
// keeping it out of tests/ is what keeps Node.js off `make test`'s prerequisite list.
//
// WHY THIS EXISTS
// The /team engine replaced a prose orchestrator whose "loop until the team agrees" had
// no terminator — that unbounded loop is the exact defect the rewrite was for. Its hard
// caps are the whole point, and an innocuous edit could silently reintroduce an infinite
// loop or let the paid bar (`make audit`, real money) run inside it. Nothing else guards
// them: no hook fires inside the Workflow runtime, and the engine is never exercised by
// the product suite.
//
// HOW IT WORKS
// Loads the REAL engine source, strips `export` from `export const meta` (the file is an
// ES module fragment executed by the Workflow runtime, not a CommonJS module), wraps it
// in `new Function(...)` and drives its actual control flow with stubbed
// agent()/parallel()/phase()/log(). Stub replies are keyed off `opts.label`, so the
// script's real branching — not a reimplementation of it — is what gets exercised.
//
// COVERAGE, stated as mutations that MUST turn this file red. Each was executed against
// the real source and confirmed discriminating; a cap not listed here is NOT guarded, and
// adding a cap means adding its row.
//
//   maxAttempts                 `cap = Math.min(...)` -> `cap = 99999`        => terminates:*
//   paidGateRun one-shot        drop `anyCompleted &&` at the close gate      => paid-only-on-shipped-work:*
//   PARALLEL_SAFE_REPRO         widen it to include `test-workbench`          => shared-repro-runs-serially
//   FAKE-mutation-is-terminal   accept a FAKE mutation verdict                => ships-nothing:fake-test
//   empty-diff short circuit    remove the zero-file-diff branch              => ships-nothing:empty-diff
//   infraBlind counting         stop counting INFRA-prefixed verdicts         => infra-failure-surfaced
//   ping-pong detection         `if (echo.length && false)`                   => ping-pong-named
//   infra circuit breaker       `infraStrikes >= 2` -> `false`                => infra-breaker-named
//   one phase-repair per run    `phaseRepairs >= 1` -> `false`                => phase-repairs-capped-at-one
//   depends_on live status      delete the `live.status = status` lines       => dependency-unblocks-dependents
//   estimate above every gate   move `if (A.estimateOnly)` below the gate     => estimate-answers-unapproved
//   approval gate still refuses delete the `approved_by_human !== true` gate  => unapproved-run-refused
//   engine self-test at preflight  delete the `engine_guard !== true` gate    => engine-guard-red-stops-the-run
//
// The last five needed dedicated checks on *why* a run stopped: disabling them still
// leaves the run terminating, just by a different route and with a worse explanation, so
// the blanket `terminates:*` check passed straight through them. The final two are a
// matched pair — each alone can be satisfied by breaking the other.
const fs = require('fs')
const path = require('path')

const TARGET = path.join(__dirname, 'team-engine.js')
// Last-resort hang detector only. A real runaway is normally caught far sooner by the
// script's own budget accumulator or this file's 5000-call backstop, and every mode
// completes in ~4ms, so 10s is generous. Kept low deliberately: worst case is
// MODES.length * TIMEOUT_MS, and a broken cap should report as a failed check rather
// than as a wall-clock hang.
const TIMEOUT_MS = 10000

const SRC = fs.readFileSync(TARGET, 'utf8').replace(/^export const meta/m, 'const meta')
const makeRunner = () => new Function('agent', 'parallel', 'phase', 'log', 'args',
  `return (async () => {\n${SRC}\n})()`)

// `chained` makes every step depend on the one before it. Until 2026-07-26 STEPS()
// emitted NO depends_on at all, so the depends_on guard in the engine's step loop
// was never executed by this harness — which is exactly how the in-memory-status
// bug shipped: `statusOf` read the preflight ledger, the scribe only wrote the
// FILE, and a dependency satisfied mid-run still read 'pending', so every
// dependent was skipped. A real run stranded 8 of 10 steps that way.
const STEPS = (n, chained) => Array.from({ length: n }, (_, i) => ({
  id: String(i + 1), name: `step ${i + 1}`, status: 'pending',
  test_command: `make test-file FILE="tests/test_fx${i + 1}.py::T::t"`,
  criterion_ids: [`AC-${i + 1}`], files: [`src/fx${i + 1}.py`],
  cost_class: '$0', maxAttempts: 2, attempts: 0, command_valid: true,
  gate_commands: ['make lint'],
  ...(chained && i > 0 ? { depends_on: [String(i)] } : {}),
}))

const LEDGER = (n, tier, approved, chained, guard) => ({
  topic: 'termination-harness', dir: 'specs/9999-01-01-harness', tier,
  approved_by_human: approved,
  context_path: 'specs/9999-01-01-harness/run-context.md',
  findings_dir: 'specs/9999-01-01-harness/findings',
  criteria_uncovered: [],
  infra: { test_db: true, dev_data: true, valhalla: true, lint_clean: true, engine_guard: guard },
  steps: STEPS(n, chained),
})

// Each mode is a pathological shape that could plausibly make the loop spin.
const MODES = [
  'happy',                // baseline: everything green first try
  'always-red',           // the per-step gate never passes
  'ping-pong',            // the same verified blocker returns after every rework
  'phantom-repro',        // skeptic claims a break but ran nothing
  'smuggle-paid',         // skeptic offers `make audit` as its "reproduction"
  'fake-test',            // the test still passes with the fix reverted
  'empty-diff',           // developer claims success having changed nothing
  'prove-first-forever',  // the judge never rules PROCEED
  'phase-red',            // the cross-step phase gate stays red
  'infra-down',           // every command fails with connection refused
  'serial-repro',         // shared-resource repro, confirmed by the serial verifier
  'serial-flake',         // shared-resource repro that was really infra, not a defect
  'phase-red-twice',      // first phase gate recovers; a LATER one must not buy a 2nd repair
  'estimate-only',        // pricing query on the UNAPPROVED ledger /team actually has on disk
  'unapproved-run',       // a real run on that same ledger must still refuse to fan out
  'dep-chain',            // every step depends on the previous one and all go green
  'engine-guard-red',     // this very file failed at preflight — the run must not start
]

// Asserted against MODES below so that deleting a pathological shape fails loudly
// instead of silently shrinking coverage. Every name here has a row in the table above.
const REQUIRED_MODES = [
  'happy', 'always-red', 'ping-pong', 'phantom-repro', 'smuggle-paid', 'fake-test',
  'empty-diff', 'prove-first-forever', 'phase-red', 'infra-down', 'serial-repro',
  'serial-flake', 'phase-red-twice', 'estimate-only', 'unapproved-run', 'dep-chain',
  'engine-guard-red',
]

// Shapes where no step may legitimately reach "completed": the run must refuse to ship
// rather than converge on a bad change.
const MUST_SHIP_NOTHING = ['always-red', 'ping-pong', 'fake-test', 'empty-diff', 'prove-first-forever']

// Most modes need 3 steps (one phase gate at K=3). 'phase-red-twice' needs 6 so that
// TWO phase gates fire — the only way to observe that the one-repair-per-RUN cap is a
// run-level counter and not a per-gate one.
const MODE_STEPS = { 'phase-red-twice': 6 }

// The two modes below are a matched pair, and only the pair discriminates. /team's Step 4
// writes approved_by_human:false and THEN prices the run (commands/team.md Step 4.5), so
// the estimate must answer on an unapproved ledger — while a real run on that identical
// ledger must still be refused. Moving the estimate above the gate is only correct if it
// did not also move the gate; 'unapproved-run' is what proves it didn't.
const MODE_ARGS = { 'estimate-only': { estimateOnly: true } }
const MODE_UNAPPROVED = new Set(['estimate-only', 'unapproved-run'])

// 'dep-chain' is the ONLY mode whose steps carry depends_on. Every step goes green,
// so a correct engine completes all of them; an engine that resolves depends_on
// against a stale preflight snapshot completes exactly ONE and skips the rest with
// 'dependency not completed'. That gap is what let the real run strand 8 of 10 steps.
const MODE_CHAINED = new Set(['dep-chain'])

// The engine runs THIS file at preflight and refuses to fan out if it failed. That is a
// deliberate circularity: the guard is not in `make test`, so preflight is the last point
// before fan-out where a broken cap still costs nothing. Here we simulate the preflight
// agent reporting engine_guard:false and assert the run stops dead.
const MODE_GUARD_RED = new Set(['engine-guard-red'])

function makeAgent(mode, tally) {
  return async (prompt, opts) => {
    const label = (opts && opts.label) || ''
    tally.calls.push(label)
    // Backstop: if a cap is removed, fail loudly here rather than hanging to the timeout.
    if (tally.calls.length > 5000) throw new Error('RUNAWAY: >5000 agent calls — a cap is missing')

    if (label === 'preflight') return LEDGER(tally.steps, tally.tier, tally.approved, tally.chained, tally.guard)
    if (label.startsWith('scribe')) return { ok: true, step_id: 'x', status: 'ok' }

    if (label.startsWith('build')) {
      if (mode === 'empty-diff') {
        return { built: true, files_touched: [], diff_stat: '0 files changed', red_first: { ran: true, was_red: true }, green: { ran: true, was_green: true } }
      }
      return { built: true, files_touched: ['src/fx1.py'], diff_stat: ' 1 file changed, 5 insertions(+)', red_first: { ran: true, was_red: true, output_excerpt: 'FAILED' }, green: { ran: true, was_green: true, output_excerpt: '1 passed' } }
    }

    if (label.startsWith('gate')) {
      if (mode === 'always-red') return { passed: false, checks: [{ command: 'make lint', exit_code: 1, summary: 'still broken' }], mutation: { verdict: 'NOT_RUN' }, unverified: [] }
      if (mode === 'fake-test') return { passed: true, checks: [], mutation: { verdict: 'FAKE', red_on_revert: false }, unverified: [] }
      if (mode === 'infra-down') return { passed: false, checks: [{ command: 'make lint', exit_code: 1, summary: 'Connection refused on 7688' }], mutation: { verdict: 'NOT_RUN' }, unverified: [] }
      return { passed: true, checks: [{ command: 'make lint', exit_code: 0, summary: 'clean' }], mutation: { verdict: 'REAL', red_on_revert: true, green_on_restore: true }, unverified: [] }
    }

    if (label.startsWith('challenge')) {
      // `make lint` is the only PARALLEL_SAFE_REPRO, so this one blocks directly.
      const blocking = { rule: 'REFUTED', title: 'always the same defect', file: 'src/fx1.py', line: 4, repro_command: 'make lint', repro_verified: true, repro_exit_code: 1, severity: 'high', why: 'reproduced' }
      const phantom = { rule: 'REFUTED', title: 'unproven claim', file: 'src/fx1.py', line: 9, repro_command: null, repro_verified: false, repro_exit_code: null, severity: 'high', why: 'vibes' }
      const smuggle = { rule: 'REFUTED', title: 'paid smuggle', file: 'src/fx1.py', line: 9, repro_command: 'make audit', repro_verified: true, repro_exit_code: 1, severity: 'critical', why: 'tries to charge the run' }
      // Container-touching: must be routed to the serial verifier, never trusted inline.
      const proposed = { rule: 'REFUTED', title: 'shared-resource defect', file: 'src/fx1.py', line: 7, repro_command: 'make test-workbench', repro_verified: false, repro_exit_code: null, severity: 'high', why: 'proposed, not run — shared :8001' }
      if (mode === 'ping-pong') return { overall: 'REFUTED', findings: [blocking], attacks_tried: ['x'] }
      if (mode === 'phantom-repro') return { overall: 'REFUTED', findings: [phantom], attacks_tried: ['x'] }
      if (mode === 'smuggle-paid') return { overall: 'REFUTED', findings: [smuggle], attacks_tried: ['x'] }
      if (mode === 'serial-repro' || mode === 'serial-flake') return { overall: 'REFUTED', findings: [proposed], attacks_tried: ['x'] }
      return { overall: 'CONFIRMED', findings: [], attacks_tried: ['read the diff'] }
    }

    if (label.startsWith('verify-repro')) {
      tally.serialVerifies += 1
      if (mode === 'serial-flake') {
        // Environment failure, not a defect: must be demoted to advisory AND counted.
        return { overall: 'UNPROVEN', findings: [{ rule: 'UNPROVEN', title: 'shared-resource defect', file: 'src/fx1.py', line: 7, repro_command: 'make test-workbench', repro_verified: true, repro_exit_code: 1, severity: 'low', why: 'INFRA: connection refused, container not up' }], attacks_tried: ['ran it serially'] }
      }
      return { overall: 'REFUTED', findings: [{ rule: 'REFUTED', title: 'shared-resource defect', file: 'src/fx1.py', line: 7, repro_command: 'make test-workbench', repro_verified: true, repro_exit_code: 1, severity: 'high', why: 'reproduced serially' }], attacks_tried: ['ran it serially'] }
    }

    if (label.startsWith('rule')) {
      if (mode === 'prove-first-forever') return { ruling: 'PROVE-FIRST', evidence_checked: [], missing: ['more proof'], most_likely_failure: 'x', proof_line: '' }
      return { ruling: 'PROCEED', evidence_checked: ['diff'], missing: [], most_likely_failure: 'none', proof_line: 'gate green; mutation REAL; judge PROCEED' }
    }

    if (label.startsWith('phasegate')) {
      const red = { passed: false, checks: [{ command: 'make _test-python', exit_code: 1, summary: 'cross-step break' }], mutation: { verdict: 'NOT_RUN' }, unverified: [] }
      const green = { passed: true, checks: [{ command: 'make _test-python', exit_code: 0, summary: 'ok' }], mutation: { verdict: 'NOT_RUN' }, unverified: [] }
      if (mode === 'phase-red') return red
      if (mode === 'phase-red-twice') {
        // Gate 1 red -> repair -> retry GREEN (run continues). Gate 2 red -> the
        // run-level cap is already spent, so it must STOP without a second repair.
        if (label.endsWith(':retry')) return green
        return red
      }
      return green
    }
    if (label.startsWith('phase-repair')) {
      tally.phaseRepairs += 1
      return { built: true, files_touched: ['src/fx1.py'], diff_stat: ' 1 file changed', red_first: { ran: true, was_red: true }, green: { ran: true, was_green: true } }
    }

    if (label === 'close-gate') {
      tally.paidRuns += 1 // `make audit` — the only real-money command in a run
      return { passed: true, checks: [{ command: 'make audit', exit_code: 0, summary: 'all green' }], mutation: { verdict: 'NOT_RUN' }, unverified: [] }
    }
    if (label === 'acceptance') return { verdict: 'SHIP', artifact_produced: true, evidence: ['read it'], top_improvement: 'none' }
    return {}
  }
}

const parallel = async (thunks) => Promise.all(thunks.map((t) => t().catch(() => null)))

async function runMode(mode) {
  const tally = {
    calls: [], paidRuns: 0, serialVerifies: 0, phaseRepairs: 0,
    steps: MODE_STEPS[mode] || 3, tier: 2, approved: !MODE_UNAPPROVED.has(mode),
    chained: MODE_CHAINED.has(mode), guard: !MODE_GUARD_RED.has(mode),
  }
  const args = { spec: 'specs/9999-01-01-harness', now: '2026-01-01T00:00:00Z', ...(MODE_ARGS[mode] || {}) }
  let out = null
  let error = null
  let timer = null
  try {
    out = await Promise.race([
      makeRunner()(makeAgent(mode, tally), parallel, () => {}, () => {}, args),
      new Promise((_, rej) => {
        timer = setTimeout(() => rej(new Error(`TIMEOUT after ${TIMEOUT_MS}ms — the run did not terminate`)), TIMEOUT_MS)
      }),
    ])
  } catch (e) {
    error = e.message
  } finally {
    // MUST clear: an un-cleared timer keeps node's event loop alive to the full
    // timeout even when the run won the race, adding TIMEOUT_MS of dead wall clock
    // per mode for no work at all.
    if (timer) clearTimeout(timer)
  }

  const completed = (out && out.completed) || 0
  // `estimate_was` on a full run, `estimate` on an early return. Both are the same
  // object; reading only the first would report "no estimate" for every early exit.
  const est = (out && (out.estimate_was || out.estimate)) || null
  return {
    mode,
    terminated: error === null,
    error,
    agents: tally.calls.length,
    paid_runs: tally.paidRuns,
    serial_verifies: tally.serialVerifies,
    phase_repairs: tally.phaseRepairs,
    completed,
    stopped_because: out ? (out.stopped_because || out.aborted || null) : null,
    // Per-step blocked reasons. Exposed so a check can assert WHICH cap fired, not
    // merely that something did — a run reaching the same terminal state by a
    // different route would otherwise look identical.
    step_whys: out && Array.isArray(out.steps) ? out.steps.map((s) => s.why || '').filter(Boolean) : [],
    panel_unverified_infra: out ? (out.panel_findings_unverified_infra || 0) : 0,
    estimate_max_agents: est ? est.maxAgents : null,
    // Approval as the ENGINE reported it back, not as the harness set it: the point
    // of 'estimate-only' is that a price comes back with approval still false.
    approved_by_human: out && 'approved_by_human' in out ? out.approved_by_human : null,
  }
}

// ── Checks ───────────────────────────────────────────────────────────────────
// Collected rather than thrown, so one run reports every broken cap instead of only
// the first — a half-diagnosed regression costs another full round trip.
const failures = []
let checksRun = 0
const check = (name, ok, msg) => {
  checksRun += 1
  if (!ok) failures.push({ name, msg })
}

function runChecks(results) {
  const by = Object.fromEntries(results.map((r) => [r.mode, r]))
  const M = (name) => by[name] || { mode: name, step_whys: [] }

  const missing = REQUIRED_MODES.filter((m) => !(m in by))
  check('covers-every-pathological-mode', missing.length === 0 && MODES.length === REQUIRED_MODES.length,
    `MODES drifted from the coverage table: missing [${missing}], ran ${MODES.length} of ${REQUIRED_MODES.length}. ` +
    'Coverage must not shrink silently — if a shape is genuinely obsolete, delete its row in the header too.')

  for (const r of results) {
    check(`terminates:${r.mode}`, r.terminated && !!r.stopped_because,
      `the engine did NOT terminate, or terminated without recording why (${r.error || 'no stopped_because'}). ` +
      'A termination cap in team-engine.js has been weakened or removed.')

    check(`paid-bar-at-most-once:${r.mode}`, r.paid_runs <= 1,
      `ran the paid close gate ${r.paid_runs} times — the paidGateRun one-shot is broken. ` +
      '`make test` inside it sets ONDOWAY_ENABLE_PAID_LLM_CALLS=1.')

    check(`paid-only-on-shipped-work:${r.mode}`, !(r.completed === 0 && r.paid_runs > 0),
      'completed no steps yet still spent money on the close gate.')

    // A run may finish early, but it may never overrun the worst case it printed.
    check(`within-printed-estimate:${r.mode}`, r.estimate_max_agents === null || r.agents <= r.estimate_max_agents,
      `spawned ${r.agents} agents, over its own printed worst case of ${r.estimate_max_agents} — ` +
      'the estimate under-counts and can no longer be trusted as a pre-flight cost gate.')
  }

  for (const m of MUST_SHIP_NOTHING) {
    check(`ships-nothing:${m}`, M(m).completed === 0,
      `marked ${M(m).completed} step(s) completed, but this shape can never legitimately ` +
      'converge — the gate is accepting unproven work.')
  }

  // A red phase gate buys ONE targeted repair per RUN, not one per gate. 'phase-red'
  // alone cannot discriminate: it fires a single gate whose retry also fails, so the
  // loop breaks for that reason whether or not the cap exists. 'phase-red-twice' runs
  // 6 steps => two gates, the first recovering after its repair.
  const twice = M('phase-red-twice')
  check('phase-repairs-capped-at-one', twice.phase_repairs === 1,
    `two phase gates went red but ${twice.phase_repairs} repairs ran; the cap is 1 per RUN. ` +
    'A per-gate counter would let a long run buy unlimited repairs.')
  check('second-red-phase-gate-stops-the-run', twice.stopped_because === 'phase_gate_red',
    `the second red gate reported '${twice.stopped_because}' instead of stopping the run.`)

  // Asserting only that the run terminated cannot discriminate: without the check the
  // step still ends blocked via maxAttempts, by a different route and with a worse
  // message. The escalation reason is the observable difference.
  check('ping-pong-named', M('ping-pong').step_whys.some((w) => w.includes('ping-pong')),
    `no step reported ping-pong; reasons were ${JSON.stringify(M('ping-pong').step_whys)}. Detection has ` +
    "been removed or weakened — the run still stops, but the human is told 'attempts exhausted' " +
    "instead of 'the rework did not move this defect'.")

  // Without the breaker the run still ends, but it reports 'all steps processed' with
  // every step blocked — reading as a code verdict when the environment was down.
  const down = M('infra-down')
  check('infra-breaker-named', down.stopped_because === 'infra_regressed',
    `expected the run to abort as 'infra_regressed', got '${down.stopped_because}'. The circuit breaker ` +
    'is not firing, so a down container will burn the full worst-case agent count on zero real work.')
  check('infra-breaker-attributed', down.step_whys.some((w) => w.toLowerCase().includes('infra')),
    `no step attributed its failure to infrastructure; reasons were ${JSON.stringify(down.step_whys)}.`)

  // In 'serial-flake' the serial verifier finds the reproduction failed for an
  // environmental reason. That must be counted and reported, not quietly demoted to an
  // advisory that looks like consensus.
  check('infra-failure-surfaced', M('serial-flake').panel_unverified_infra > 0,
    'an infra-caused verification failure was silently dropped; the run would read as a clean ' +
    'adversarial pass when the panel actually judged nothing.')

  // Parallel skeptics racing on the 7688 test DB, :8001, or mobile/.dart_tool would each
  // see a nonzero exit and manufacture blockers from a collision this design caused.
  // Only `make lint` is PARALLEL_SAFE_REPRO.
  for (const m of ['serial-repro', 'serial-flake']) {
    check(`shared-repro-runs-serially:${m}`, M(m).serial_verifies > 0,
      'proposed a `make test-workbench` reproduction that never went through the serial verifier — ' +
      'the collision guard is bypassed.')
  }

  // /team writes approved_by_human:false and THEN prices the run, so an estimate that
  // required approval could never be shown. Until 2026-07-25 the approval gate returned
  // first and the estimateOnly branch was dead code.
  const est = M('estimate-only')
  check('estimate-ran-on-unapproved-ledger', est.approved_by_human === false,
    'the estimate did not come back from an UNAPPROVED ledger, so this mode is no longer ' +
    'exercising the ordering it exists to pin.')
  check('estimate-answers-unapproved', est.stopped_because !== 'not_approved',
    'the pricing query was REFUSED for want of approval; the approval gate has moved back above ' +
    'the estimate block, so /team can never show a cost before asking for a go-ahead.')
  check('estimate-priced-without-fanning-out', est.estimate_max_agents !== null && est.agents === 1,
    `returned estimate=${est.estimate_max_agents} after ${est.agents} agents; only preflight may run, ` +
    'since an estimate that fans out is not an estimate.')

  // The other half of the pair. Without it, deleting the approval gate entirely would
  // look like a valid fix for the estimate ordering: every other check would stay green
  // while a dozen agents executed a ledger nobody approved.
  const unapp = M('unapproved-run')
  check('unapproved-run-refused', unapp.stopped_because === 'not_approved',
    `a run on an unapproved ledger reported '${unapp.stopped_because}' instead of refusing; the human ` +
    'approval gate is the only thing standing between a plan nobody agreed to and a full fan-out.')
  check('unapproved-run-spawned-nothing', unapp.agents === 1 && unapp.completed === 0 && unapp.paid_runs === 0,
    `the refused run still spawned ${unapp.agents} agents / completed ${unapp.completed} steps ` +
    '(only preflight is allowed before the gate).')

  // The engine self-tests at preflight and must refuse to fan out on a red guard. This
  // is what makes the whole file load-bearing rather than advisory: without it, a broken
  // cap is caught only if a human happens to run this command.
  const guard = M('engine-guard-red')
  check('engine-guard-red-stops-the-run', guard.stopped_because === 'engine_guard_red',
    `preflight reported the engine's own guard RED and the run answered '${guard.stopped_because}' ` +
    'instead of refusing. Every cap in this file is then unverified for that run.')
  check('engine-guard-red-spawned-nothing', guard.agents === 1 && guard.completed === 0 && guard.paid_runs === 0,
    `a run on a red guard still spawned ${guard.agents} agents / completed ${guard.completed} steps.`)

  // The engine resolved depends_on via `statusOf`, which reads the in-memory preflight
  // ledger — but the scribe only ever wrote state.json and the engine never re-reads it.
  // A dependency that completed mid-run still read 'pending' and every dependent was
  // skipped. Measured on a real Tier-3 run 2026-07-26: S1 and S3 completed, S2 and S4
  // were skipped 'dependency not completed', and 8 of 10 steps were stranded.
  const dep = M('dep-chain')
  check('dependency-unblocks-dependents', dep.completed === 3,
    `only ${dep.completed} of 3 chained steps completed; depends_on is being resolved against a stale ` +
    `snapshot, so a dependency satisfied mid-run does not unblock its dependents (skips: ${JSON.stringify(dep.step_whys)}).`)
  check('no-phantom-dependency-skip', !dep.step_whys.some((w) => w.includes('dependency')),
    `a step was skipped for an unmet dependency even though every step went green: ${JSON.stringify(dep.step_whys)}.`)
}

;(async () => {
  const results = []
  for (const mode of MODES) results.push(await runMode(mode))
  runChecks(results)

  if (process.argv.includes('--json')) {
    process.stdout.write(JSON.stringify({ target: TARGET, timeout_ms: TIMEOUT_MS, checks_run: checksRun, failures, results }, null, 2))
    process.exitCode = failures.length ? 1 : 0
    return
  }

  console.log('mode                  term   agents  paid  serialV  repairs  completed  stopped_because')
  console.log('-'.repeat(104))
  for (const r of results) {
    console.log(
      r.mode.padEnd(22) + String(r.terminated).padEnd(7) + String(r.agents).padEnd(8) +
      String(r.paid_runs).padEnd(6) + String(r.serial_verifies).padEnd(9) +
      String(r.phase_repairs).padEnd(9) + String(r.completed).padEnd(11) +
      (r.error || r.stopped_because))
  }
  console.log('-'.repeat(104))
  for (const f of failures) console.log(`FAIL  ${f.name}\n      ${f.msg}`)
  console.log(failures.length
    ? `${failures.length} of ${checksRun} checks FAILED — a guard in team-engine.js is broken.`
    : `all ${checksRun} checks passed across ${MODES.length} pathological shapes.`)
  process.exitCode = failures.length ? 1 : 0
})()
