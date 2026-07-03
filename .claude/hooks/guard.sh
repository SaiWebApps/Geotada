#!/bin/bash
# PreToolUse guard: BLOCKS high-consequence shell commands unless they carry an
# explicit, logged justification. Installed 2026-07-02 after a session killed
# the Valhalla container (worktree-anchored compose recreate), OOMed dockerd,
# and had its worktree deleted by a sibling session — all via commands that
# would have been caught by a forced "explain yourself first" gate.
#
# To run a blocked command, prepend a justification comment:
#     : JUSTIFY: <why this is safe + what evidence you checked>; <command>
# The justification is appended to .claude/hooks/guard-log.txt for human audit.
#
# Input: PreToolUse JSON on stdin ({"tool_name": "Bash", "tool_input": {"command": ...}}).
# Exit 0 = allow, exit 2 = block (stderr is shown to the model).

INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | /usr/bin/python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get("tool_input", {}).get("command", ""))
except Exception:
    print("")
')

[ -z "$CMD" ] && exit 0

# High-consequence patterns. Deliberately narrow: routine reads/tests never match.
DANGER='(docker[[:space:]]+compose[[:space:]]+(down|rm)|docker[[:space:]]+(volume|system)[[:space:]]+(rm|prune)|docker[[:space:]]+rm[[:space:]]|docker[[:space:]]+rmi|colima[[:space:]]+(stop|restart|delete)|git[[:space:]]+worktree[[:space:]]+(remove|prune)|git[[:space:]]+branch[[:space:]]+-[Dd]|git[[:space:]]+push[[:space:]]+.*(--force|-f[[:space:]])|git[[:space:]]+reset[[:space:]]+--hard|git[[:space:]]+clean[[:space:]]|rm[[:space:]]+-[a-z]*r[a-z]*f|make[[:space:]]+(db-reset|db-test-reset|db-workbench-reset|clean-db)|DETACH[[:space:]]+DELETE)'

if ! printf '%s' "$CMD" | grep -qiE "$DANGER"; then
    exit 0
fi

LOG_DIR="$(cd "$(dirname "$0")" && pwd)"
if printf '%s' "$CMD" | grep -q 'JUSTIFY:'; then
    # Justified: allow, but leave an audit trail for the human.
    printf '%s | %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$CMD" >> "$LOG_DIR/guard-log.txt"
    exit 0
fi

cat >&2 <<'MSG'
BLOCKED by .claude/hooks/guard.sh: this command is in the high-consequence
class (container/volume/worktree/branch destruction, force-push, hard reset,
recursive delete, DB wipe). Before retrying you MUST:
  1. State the evidence that this specific action is correct (what did you
     check? which container/branch/path, owned by whom, holding what?).
  2. Re-run with the justification inline:
         : JUSTIFY: <one line: reason + evidence checked>; <original command>
The justification is logged to .claude/hooks/guard-log.txt for human audit.
If you cannot justify it in one line, you have not diagnosed enough to run it.
MSG
exit 2
