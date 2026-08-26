#!/bin/bash
# PostToolUse(Bash) hook: after any `git push`, watch the Render deploy until
# it reaches a terminal state. Exit 0 when live; exit 2 (asyncRewake -> wakes
# Claude to diagnose and fix) when the deploy fails, the watch times out, or
# the render CLI is unusable. Run standalone via `make render-watch`
# (RENDER_WATCH_FORCE=1 skips the stdin git-push gate).
set -u

SERVICE_ID="${RENDER_WATCH_SERVICE:-srv-d7qnivjbc2fs73fr6tqg}"  # Ondoway web service
POLL_SECS="${RENDER_WATCH_POLL_SECS:-20}"
MAX_POLLS="${RENDER_WATCH_MAX_POLLS:-45}"  # 15 min
# How long to wait for Render to register a deploy for HEAD before giving up.
MAX_NO_MATCH_POLLS="${RENDER_WATCH_MAX_NO_MATCH_POLLS:-10}"

# Gate: only act on git push (hook fires for every Bash call in this project).
# Two stages, so the common case costs no interpreter at all: a pure-shell scan of the
# raw payload rules out every call that never mentions a push, and only a possible
# match pays for python3 to confirm it was the COMMAND and not echoed output.
if [ "${RENDER_WATCH_FORCE:-0}" != "1" ]; then
  payload=$(cat 2>/dev/null)
  case "$payload" in
    *"git push"*) ;;
    *) exit 0 ;;
  esac
  # Stage 2 must decide whether the command PERFORMS a push, not whether it mentions
  # one. MEASURED 2026-08-24: a substring test fired on `git diff` of this very file,
  # because the diff text contains "git push" — and on any script, test or doc that
  # quotes the phrase. So: drop quoted spans, then require `git push` to open a segment.
  if ! printf '%s' "$payload" | python3 -c "
import json, re, sys
try:
    cmd = (json.load(sys.stdin).get('tool_input') or {}).get('command') or ''
except Exception:
    sys.exit(1)
bare = re.sub(r\"'[^']*'|\\\"[^\\\"]*\\\"\", ' ', cmd)
sys.exit(0 if re.search(r'(?:^|[;&|)]|\n)\s*(?:sudo\s+)?git\s+push\b', bare) else 1)
" 2>/dev/null; then
    exit 0
  fi
fi

if ! command -v render >/dev/null 2>&1; then
  echo "render CLI not installed — Render deploy NOT monitored; check it manually." >&2
  exit 2
fi

head_sha=$(git rev-parse HEAD 2>/dev/null || echo "")
# Fail closed: without HEAD we cannot tell the pushed deploy from a stale one,
# so we must never render a verdict about "the" deploy.
if [ -z "$head_sha" ]; then
  echo "could not resolve HEAD — Render deploy NOT monitored; check it manually." >&2
  exit 2
fi

latest_deploy() {
  render deploys list "$SERVICE_ID" -o json --confirm 2>/dev/null | python3 -c "
import json, sys
try:
    ds = json.load(sys.stdin)
    dp = ds[0].get('deploy', ds[0])
    print(dp.get('id',''), dp.get('status',''), (dp.get('commit') or {}).get('id',''))
except Exception:
    pass"
}

# Can the CLI read this service AT ALL? One real read before committing to a
# 15-minute watch, using the SAME call the loop makes so the two can never disagree.
# It separates "the CLI cannot talk to Render" — fail now, in a second, with the
# remedy — from "the deploy is not registered yet", which is what the loop is for.
# MEASURED 2026-08-24: `render workspace current` is the WRONG probe. It fails with
# "no workspace set" on a CLI that lists this service's deploys perfectly well, and
# an unauthenticated CLI otherwise burns all 45 polls before saying anything.
if [ -z "$(latest_deploy)" ]; then
  echo "render CLI cannot read deploys for $SERVICE_ID — Render deploy NOT monitored. Fix: run 'render login', then 'make render-watch' to check this deploy." >&2
  exit 2
fi

for i in $(seq 1 "$MAX_POLLS"); do
  read -r dep_id status commit <<<"$(latest_deploy)"
  if [ -z "${dep_id:-}" ]; then
    echo "[render-watch $i/$MAX_POLLS] could not read deploy status (render CLI auth?)" >&2
    sleep "$POLL_SECS"
    continue
  fi
  short_commit=$(printf '%.9s' "$commit")
  # Commit identity is a PRECONDITION for any verdict, never a grace period:
  # a stale `live` deploy must never be reported as the pushed commit's result.
  if [ "$commit" != "$head_sha" ]; then
    no_match=$((${no_match:-0} + 1))
    if [ "$no_match" -ge "$MAX_NO_MATCH_POLLS" ]; then
      echo "❌ no Render deploy was created for $head_sha — autoDeploy off, untracked branch, or ignored paths? (latest deploy $dep_id is $short_commit)" >&2
      exit 2
    fi
    echo "[render-watch $i/$MAX_POLLS] latest deploy $dep_id ($short_commit) predates push; waiting for $head_sha"
    sleep "$POLL_SECS"
    continue
  fi
  case "$status" in
    live)
      echo "✅ Render deploy $dep_id ($short_commit) is LIVE."
      exit 0
      ;;
    *failed*|canceled|deactivated)
      {
        echo "❌ Render deploy $dep_id ($short_commit) ended as: $status"
        echo "Recent service logs:"
        render logs -r "$SERVICE_ID" --limit 40 --confirm 2>/dev/null | tail -25
        echo "Diagnose the failure and fix it (see CLAUDE.md Judge Protocol)."
      } >&2
      exit 2
      ;;
    *)
      echo "[render-watch $i/$MAX_POLLS] $dep_id ($short_commit): $status"
      sleep "$POLL_SECS"
      ;;
  esac
done

echo "⏱ Render deploy still not terminal after 15 min — investigate manually." >&2
exit 2
