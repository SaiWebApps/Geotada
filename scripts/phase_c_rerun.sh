#!/bin/bash
# Phase-C slate re-run — the decisive proof that the engine fixes moved the tours.
# Authors the SAME 4 tours as 2026-07-18 Phase C, through the fixed engine, in PARALLEL.
#
# SPENDS THE USER'S ANTHROPIC CREDITS (~$8 total, ~$2/tour). Double-gated on purpose:
#   ONDOWAY_DEMO_APPROVE=1 AND --live are both required by scripts/author_tour.py,
#   and this wrapper additionally requires ONDOWAY_RERUN_APPROVED=1 so it can never
#   fire from a stray invocation. Per-run approval is the user's standing rule.
#
# Usage:  ONDOWAY_RERUN_APPROVED=1 ONDOWAY_DEMO_APPROVE=1 scripts/phase_c_rerun.sh [outdir]
set -uo pipefail
cd "$(dirname "$0")/.."

if [ "${ONDOWAY_RERUN_APPROVED:-}" != "1" ] || [ "${ONDOWAY_DEMO_APPROVE:-}" != "1" ]; then
  echo "REFUSED: needs ONDOWAY_RERUN_APPROVED=1 and ONDOWAY_DEMO_APPROVE=1 (real money, ~\$8)." >&2
  exit 3
fi

OUT="${1:-/tmp/ondoway-phase-c-rerun}"
mkdir -p "$OUT"
echo "Phase-C re-run -> $OUT   (4 tours in PARALLEL, ~\$2 each)"

run() { # name, then author_tour.py args
  local name="$1"; shift
  uv run python scripts/author_tour.py "$@" --live > "$OUT/$name.txt" 2>&1
  local code=$?
  echo "$code" > "$OUT/.exit-$name"
  echo "  done: $name (exit $code)"
  return $code
}

run ile-90     --city paris    --start "48.8530,2.3499"  --duration 90 &
run pdv-60     --city paris    --start "48.8555,2.3655"  --duration 60 --lenses dark_history,social_change &
run nyc-90     --city new_york --start "40.7033,-74.0170" --duration 90 &
run london-75  --city london   --start "51.5007,-0.1246"  --duration 75 &
wait

# A backgrounded tour that dies still costs real money — surface it LOUDLY instead of
# leaving a stack trace in a file that reads as "done".
FAILED=""
for name in ile-90 pdv-60 nyc-90 london-75; do
  code="$(cat "$OUT/.exit-$name" 2>/dev/null || echo 127)"
  [ "$code" = "0" ] || FAILED="$FAILED $name(exit=$code)"
done
if [ -n "$FAILED" ]; then
  echo
  echo "!! TOURS FAILED:$FAILED — money spent, output unusable. Inspect $OUT/*.txt before re-running." >&2
fi

echo
echo "=== CONVERGENCE (was: 7 stitch fallbacks across the 4 tours) ==="
for f in "$OUT"/*.txt; do
  echo "-- $(basename "$f")"
  grep -E "^STOP [0-9]+ —|\[widen retry\]|\[recheck|\[excis|CROSS-STOP" "$f" || true
done
echo
echo "fallbacks now: $(grep -c 'GROUNDED-STITCH FALLBACK' "$OUT"/*.txt | awk -F: '{s+=$2} END {print s+0}')  (Phase C baseline: 7)"
echo "widen rescues: $(grep -ch 'widen retry' "$OUT"/*.txt | awk '{s+=$1} END {print s+0}')"
