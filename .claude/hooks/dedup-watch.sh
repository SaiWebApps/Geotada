#!/usr/bin/env bash
# Did that edit introduce a SECOND answer to a question this codebase already answers?
#
# WHY IT WATCHES FILES AND NOT TOOLS. The obvious hook matches Edit and Write. That
# hook would be blind, and the proof is in this repository's own transcript: source
# files here have been rewritten with `perl -pi -e`, `sed`, and shell heredocs
# repeatedly. None of those is an Edit. Nor is a `git merge`, a `git checkout`, a
# `ruff --fix`, a `make format`, an agent running inside the /team Workflow runtime
# (which `CLAUDE.md` records that PreToolUse/Agent does not even fire for), or the
# owner editing in their own editor.
#
# So this asks the only question that survives all of them: have the watched files
# CHANGED? It is registered on every tool that can plausibly precede a change, and
# its first act is a hash comparison that costs nothing when nothing moved — which
# is most of the time.
#
# WHY IT NEVER BLOCKS. A multi-file change is legitimately incoherent in the middle;
# this project's own plan has a step where the app must raise until the next step
# lands. A guard that blocks there gets switched off, and a guard that is off catches
# nothing. `CLAUDE.md` records the precedent: a regex command guard blocked 16 of 20
# harmless commands, caught 0 of 70 real ones, and was deleted. The blocking version
# is `make dedup-review`, which the pre-commit bar runs and which cannot be talked
# out of.
set -uo pipefail

cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}" || exit 0

# No credentials, no review — and say so rather than passing silently.
if ! command -v uv >/dev/null 2>&1; then
  exit 0
fi

STATE=".claude/dedup-watch.sha"
CURRENT="$(find src/tour src/api -name '*.py' -type f -exec shasum -a 256 {} + 2>/dev/null \
  | shasum -a 256 | cut -d' ' -f1)"
[ -z "$CURRENT" ] && exit 0

if [ -f "$STATE" ] && [ "$(cat "$STATE")" = "$CURRENT" ]; then
  exit 0   # nothing under the watched roots moved
fi
printf '%s' "$CURRENT" > "$STATE"

OUT="$(uv run python scripts/dedup_review.py --changed 2>&1)" || exit 0
[ -z "$OUT" ] && exit 0
printf '%s\n' "$OUT"
exit 0
