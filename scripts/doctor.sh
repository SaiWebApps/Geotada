#!/usr/bin/env bash
# Ondoway prerequisite doctor — pure diagnostic, never fails hard.
# Prints an OK/MISSING table so a brand-new developer knows what to install
# before running `make bootstrap`. Exit code is always 0.
set -u

# ── tiny helpers ──────────────────────────────────────────────
green() { printf '\033[32m%s\033[0m' "$1"; }
red()   { printf '\033[31m%s\033[0m' "$1"; }
yellow(){ printf '\033[33m%s\033[0m' "$1"; }

row() { # name  status  detail
  printf '  %-22s %-24s %s\n' "$1" "$2" "$3"
}

have() { command -v "$1" >/dev/null 2>&1; }

echo ""
echo "Ondoway doctor — prerequisite check (diagnostic only, nothing is changed)"
echo "──────────────────────────────────────────────────────────────────────────"
printf '  %-22s %-24s %s\n' "TOOL" "STATUS" "DETAIL"
echo "  ----------------------------------------------------------------------"

miss=0

# uv (Python package/venv manager) ─────────────────────────────
if have uv; then
  row "uv" "$(green OK)" "$(uv --version 2>/dev/null | head -1)"
else
  row "uv" "$(red MISSING)" "install: curl -LsSf https://astral.sh/uv/install.sh | sh"
  miss=$((miss+1))
fi

# docker CLI ───────────────────────────────────────────────────
if have docker; then
  ver="$(docker --version 2>/dev/null)"
  if docker info >/dev/null 2>&1; then
    row "docker" "$(green OK)" "$ver (daemon running)"
  else
    row "docker" "$(yellow "CLI ok / daemon DOWN")" "start Docker Desktop or Colima, then re-run"
    miss=$((miss+1))
  fi
else
  row "docker" "$(red MISSING)" "install Docker Desktop or Colima"
  miss=$((miss+1))
fi

# docker compose (v2 subcommand) ───────────────────────────────
if docker compose version >/dev/null 2>&1; then
  row "docker compose" "$(green OK)" "$(docker compose version --short 2>/dev/null)"
else
  row "docker compose" "$(red MISSING)" "needs Docker Compose v2 (bundled with modern Docker)"
  miss=$((miss+1))
fi

# flutter ──────────────────────────────────────────────────────
if have flutter; then
  fver="$(flutter --version 2>/dev/null | head -1)"
  row "flutter" "$(green OK)" "$fver"
  # one-line doctor summary (count issues), don't block
  fsum="$(flutter doctor 2>/dev/null | grep -E '^\[' | sed 's/^\[//;s/\].*//' | sort | uniq -c | tr '\n' ' ')"
  [ -n "$fsum" ] && row "  flutter doctor" "$(yellow summary)" "$fsum (✓=ok ✗=fail !=warn) — run 'flutter doctor' for detail"
else
  row "flutter" "$(red MISSING)" "install Flutter SDK (needed for the mobile app)"
  miss=$((miss+1))
fi

# node / npx (Playwright for the workbench UI suite) ───────────
if have node; then
  detail="node $(node --version 2>/dev/null)"
  have npx && detail="$detail, npx present"
  row "node/npx" "$(green OK)" "$detail (Playwright: make test-workbench)"
else
  row "node/npx" "$(yellow MISSING)" "only needed for 'make test-workbench' (Playwright)"
fi

# macOS iOS toolchain ─────────────────────────────────────────
if [ "$(uname)" = "Darwin" ]; then
  if have xcodebuild; then
    row "xcodebuild" "$(green OK)" "$(xcodebuild -version 2>/dev/null | head -1)"
  else
    row "xcodebuild" "$(red MISSING)" "install Xcode (needed for make flutter-ios)"
    miss=$((miss+1))
  fi
  if have xcrun && xcrun simctl help >/dev/null 2>&1; then
    booted="$(xcrun simctl list devices booted 2>/dev/null | grep -c Booted || true)"
    row "xcrun simctl" "$(green OK)" "${booted} simulator(s) currently booted"
  else
    row "xcrun simctl" "$(red MISSING)" "install Xcode command-line tools (xcode-select --install)"
    miss=$((miss+1))
  fi
else
  row "xcodebuild" "$(yellow "n/a")" "macOS only (iOS build)"
  row "xcrun simctl" "$(yellow "n/a")" "macOS only (iOS simulator)"
fi

# render CLI (deploy status) ──────────────────────────────────
if have render; then
  row "render" "$(green OK)" "$(render --version 2>/dev/null | head -1) — auth: make render-status"
else
  row "render" "$(yellow OPTIONAL)" "only for 'make render-status' (brew install render)"
fi

echo "  ----------------------------------------------------------------------"
if [ "$miss" -eq 0 ]; then
  echo "  $(green "All required prerequisites present.")  Next: make bootstrap"
else
  echo "  $(yellow "$miss required tool(s) missing or not ready") — install them, then re-run 'make doctor'."
  echo "  (node/npx and render are optional; they only gate specific targets.)"
fi
echo ""
exit 0
