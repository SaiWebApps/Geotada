#!/bin/sh
# The one launcher every Python hook goes through.
#
# WHY. settings.json used to run `python3 "$CLAUDE_PROJECT_DIR"/.claude/hooks/x.py`.
# On a harness that does not export CLAUDE_PROJECT_DIR that is
# `python3 /.claude/hooks/x.py`: python exits 2, and exit 2 from a PreToolUse hook
# is BLOCK — every tool refused with a traceback as the reason. Measured
# 2026-09-02 with the variable unset. That is the shape of a session that "breaks
# for unknown reasons" on another machine.
#
# So this script resolves the hooks directory from ITS OWN PATH ($0), never from
# an environment variable or the working directory; picks the first python that is
# at least 3.9; runs the doctor once if its report is missing; and only then runs
# the hook. If no usable python exists it prints a system message naming the fix
# and exits 0, because a hook that cannot run must say so rather than block.
#
# Invoked from settings.json as:
#   ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "${CLAUDE_PROJECT_DIR:-.}"); \
#   sh "$ROOT/.claude/hooks/run.sh" <hook.py>
# `sh` so the executable bit does not matter; git answers for the root first
# (right in a worktree or a subdirectory), the variable second, the session's
# working directory last. Whatever path reached this script, the hooks
# directory is taken from $0 below, never from any of those.
set -u

hook="${1:-}"
[ -n "$hook" ] || exit 0
shift

here=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd) || exit 0
root=$(CDPATH= cd -- "$here/../.." 2>/dev/null && pwd) || exit 0

py=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 \
     && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
    py=$(command -v "$candidate")
    break
  fi
done

if [ -z "$py" ]; then
  # Swallow stdin so the harness never sees a broken pipe.
  cat >/dev/null 2>&1
  printf '%s\n' "{\"systemMessage\": \"ONDOWAY HOOKS DISARMED on this machine: no python3 of at least 3.9 on PATH, so $hook did not run. On macOS run: xcode-select --install (or install python3), then start a new session.\"}"
  exit 0
fi

export ONDOWAY_HOOK_ROOT="$root"
export PYTHONDONTWRITEBYTECODE=1

if [ ! -f "$root/.claude/state/doctor.json" ] && [ "$hook" != "doctor.py" ]; then
  "$py" "$here/doctor.py" --quiet </dev/null >/dev/null 2>&1 || true
fi

exec "$py" "$here/$hook" "$@"
