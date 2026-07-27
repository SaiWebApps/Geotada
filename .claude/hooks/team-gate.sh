#!/bin/bash
# PreToolUse(Agent) hook: refuse to fan out back-half work against a /team ledger
# the human has NOT approved.
#
# SCOPE IS DELIBERATELY NARROW. The removed guard.sh blocked 16/20 harmless
# commands and 0/70 destructive ones (CLAUDE.md, commit 643d0d9); a hook that
# blocks agent spawns broadly would repeat exactly that failure. This one fires
# ONLY when all three hold:
#   1. the spawn prompt names a specs/<dir> path,
#   2. that directory has a state.json,
#   3. that state.json says "approved_by_human": false.
# Every other Agent spawn — Explore, Plan, proactive-audit, ordinary work — is
# untouched (exit 0).
#
# It FAILS OPEN on any internal error. A gate that cannot read its input must not
# become a gate on all work. The load-bearing approval check is structural and
# lives in .claude/team-engine.js preflight, which refuses to fan out on
# approved_by_human != true; this hook is a second gate on main-agent spawns.
#
# MEASURED 2026-07-25, both directions:
#   - Main-agent spawn: FIRES. A real Agent tool call naming an unapproved ledger
#     was refused with this script's exact reason string.
#   - Inside the Workflow runtime: DOES NOT FIRE. An engine run against the same
#     unapproved ledger spawned its preflight agent (sonnet, 12 tool calls) and
#     this hook logged nothing for it; the run was stopped by the engine's own
#     approval check instead.
# So this hook covers MAIN-AGENT spawns only, and the engine's preflight is the
# load-bearing gate. The log below is what makes that answerable; keep it.
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

# Candidate spec dirs named anywhere in the prompt.
specs=$(printf '%s' "$prompt" | grep -oE 'specs/[0-9]{4}-[0-9]{2}-[0-9]{2}-[A-Za-z0-9_-]+' | sort -u)
[ -n "$specs" ] || exit 0

root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
for spec in $specs; do
  state="$root/$spec/state.json"
  [ -f "$state" ] || continue

  approved=$(python3 -c \
    "import json,sys
try:
    print(json.load(open(sys.argv[1])).get('approved_by_human'))
except Exception:
    print('ERROR')" "$state" 2>/dev/null)

  # Unreadable or missing key -> fail open. Only an explicit False blocks.
  [ "$approved" = "False" ] || continue

  reason="Refusing to spawn an agent against ${spec}: its state.json is not approved (approved_by_human: false). Show the human the plan in ${spec}/state.json and wait for them to say go — that go-ahead is what authorises execution. Do not hand-edit the file on their behalf, and do not ask them to. (Gate: .claude/hooks/team-gate.sh)"

  printf '%s\tDENY\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$spec" >>"$LOG" 2>/dev/null || true

  python3 -c \
    "import json,sys
print(json.dumps({'hookSpecificOutput': {
    'hookEventName': 'PreToolUse',
    'permissionDecision': 'deny',
    'permissionDecisionReason': sys.argv[1]}}))" "$reason" 2>/dev/null && exit 0

  # JSON path unavailable — fall back to the exit-2 block contract.
  echo "$reason" >&2
  exit 2
done

printf '%s\tALLOW\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(printf '%s' "$specs" | tr '\n' ',')" >>"$LOG" 2>/dev/null || true
exit 0
