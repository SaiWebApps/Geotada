#!/bin/bash
# PreToolUse(Agent) hook: refuse to fan out back-half work against a /team plan
# the human has NOT approved.
#
# WHAT CHANGED ON 2026-09-02, AND WHY IT MATTERED. This hook used to scan the
# spawn prompt for `specs/<dated-dir>` and read `<dir>/state.json`. Both are
# gone: `state.json` was replaced by the SQLite tracker on 2026-09-01
# (.claude/ledger/track.py, commit 9525b4a5), and `specs/` was deleted by owner
# ruling on 2026-09-02. So the pattern matched nothing, the state file was never
# found, and every branch fell through to `exit 0` — a gate that could not
# refuse anything while still reading, in a diff, as though it did. That is
# worse than no gate: it is a guard someone would trust.
#
# It now asks the same question of the store that actually holds the answer: the
# tracker's `approvals` table, which `track approve` is the only writer of, and
# which records who approved and when.
#
# SCOPE IS DELIBERATELY NARROW. The removed guard.sh blocked 16/20 harmless
# commands and 0/70 destructive ones (commit 643d0d9); a hook that blocks agent
# spawns broadly would repeat exactly that failure. This one fires ONLY when all
# three hold:
#   1. the spawn prompt names a `.claude/runs/<dated-dir>` run folder,
#   2. the tracker holds at least one feature (there IS a plan to approve),
#   3. the tracker holds NO approval row.
# Every other Agent spawn — Explore, Plan, proactive-audit, ordinary work — is
# untouched (exit 0). Condition 2 is the analogue of the old "state.json exists":
# an empty tracker means no plan has been written yet, which is not a refusal.
#
# It FAILS OPEN on any internal error. A gate that cannot read its input must not
# become a gate on all work.
#
# MEASURED 2026-07-25, both directions, and still true of the mechanism:
#   - Main-agent spawn: FIRES.
#   - Inside the Workflow runtime: DOES NOT FIRE. PreToolUse hooks do not run
#     there (.claude/team-engine.js records the same measurement).
# So this hook covers MAIN-AGENT spawns only, and the load-bearing gate is the
# engine's own preflight, which refuses to fan out unless the tracker says
# approved (.claude/team-engine.js, the `not_approved` abort). The log below is
# what makes that answerable; keep it.
#
# TEAM_GATE_TRACKER_DB overrides which tracker database is consulted. It exists
# for .claude/hooks/tests/test_team_gate.py, which must be able to build a plan
# with and without an approval row without touching the owner's real run.
set -u

LOG="${CLAUDE_PROJECT_DIR:-.}/.claude/hooks/team-gate-log.txt"
payload=$(cat 2>/dev/null) || exit 0
[ -n "$payload" ] || exit 0

# Extract the spawn prompt. Fail open if anything is unreadable.
prompt=$(printf '%s' "$payload" | python3 -c \
  "import json,sys
try:
    d = json.load(sys.stdin)
    ti = d.get('tool_input') or {}
    print(ti.get('prompt') or '')
except Exception:
    pass" 2>/dev/null) || exit 0
[ -n "$prompt" ] || exit 0

# Candidate run folders named anywhere in the prompt. `.claude/runs/` and not
# `specs/`: a run folder is gitignored scratch under the `.claude/*` rule, and
# `specs/` is a `forbidden` prefix in production-junk-patterns.json.
runs=$(printf '%s' "$prompt" \
  | grep -oE '\.claude/runs/[0-9]{4}-[0-9]{2}-[0-9]{2}-[A-Za-z0-9_-]+' \
  | sort -u)
[ -n "$runs" ] || exit 0

root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
tracker="$root/.claude/ledger/track.py"
[ -f "$tracker" ] || exit 0

# One question, asked of the tracker: is there a plan, and has anyone approved
# it? `show --json` prints the whole current picture and never writes.
if [ -n "${TEAM_GATE_TRACKER_DB:-}" ]; then
  raw=$(python3 "$tracker" show --json --db "$TEAM_GATE_TRACKER_DB" 2>/dev/null)
else
  raw=$(python3 "$tracker" show --json 2>/dev/null)
fi

verdict=$(printf '%s' "$raw" | python3 -c \
  "import json,sys
try:
    d = json.load(sys.stdin)
    if not (d.get('features') or []):
        print('NO_PLAN')
    else:
        print('APPROVED' if d.get('approved') else 'UNAPPROVED')
except Exception:
    print('ERROR')" 2>/dev/null) || exit 0

# Anything but an explicit UNAPPROVED lets the spawn through.
if [ "$verdict" != "UNAPPROVED" ]; then
  printf '%s\tALLOW\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "$(printf '%s' "$runs" | tr '\n' ',')" "$verdict" >>"$LOG" 2>/dev/null || true
  exit 0
fi

first_run=$(printf '%s' "$runs" | head -n 1)
reason="Refusing to spawn an agent against ${first_run}: the tracker holds a plan nobody has approved. Show the human the plan (\`python3 .claude/ledger/track.py show\`) and wait for them to say go in chat — that go-ahead is what authorises execution, and \`track approve\` is how it is recorded. Do not record the approval on their behalf, and do not ask them to run it for you. (Gate: .claude/hooks/team-gate.sh)"

printf '%s\tDENY\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$first_run" >>"$LOG" 2>/dev/null || true

python3 -c \
  "import json,sys
print(json.dumps({'hookSpecificOutput': {
    'hookEventName': 'PreToolUse',
    'permissionDecision': 'deny',
    'permissionDecisionReason': sys.argv[1]}}))" "$reason" 2>/dev/null && exit 0

# JSON path unavailable — fall back to the exit-2 block contract.
echo "$reason" >&2
exit 2
