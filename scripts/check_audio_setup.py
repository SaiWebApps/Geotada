#!/usr/bin/env python3
"""Check audio pipeline prerequisites and report pass/fail for each.

Exit code 0 = all checks passed, 1 = at least one failed.
Designed to be run standalone or via `make setup-audio`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Load .env if present
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())


def _check(label: str, passed: bool, fix: str) -> bool:
    if passed:
        print(f"  ✓ {label}")
    else:
        print(f"  ✗ {label}")
        print(f"    → {fix}")
    return passed


def main() -> int:
    print("Audio Pipeline Prerequisites")
    print("=" * 40)
    all_ok = True

    # 1. OPENAI_API_KEY
    openai_key = os.getenv("OPENAI_API_KEY", "")
    all_ok &= _check(
        "OPENAI_API_KEY is set",
        bool(openai_key) and not openai_key.startswith("sk-REPLACE"),
        "Add OPENAI_API_KEY=sk-... to your .env file (get one at https://platform.openai.com/api-keys)",
    )

    # 2. Optional: ELEVENLABS_API_KEY
    el_key = os.getenv("ELEVENLABS_API_KEY", "")
    if el_key:
        el_voice = os.getenv("ELEVENLABS_VOICE_ID", "")
        _check("ELEVENLABS_API_KEY is set", True, "")
        _check(
            "ELEVENLABS_VOICE_ID is set",
            bool(el_voice),
            "Add ELEVENLABS_VOICE_ID=... to your .env file",
        )
    else:
        print("  - ELEVENLABS_API_KEY not set (optional — only needed for ElevenLabs provider)")

    # 3. OpenAI API connectivity
    if openai_key and not openai_key.startswith("sk-REPLACE"):
        try:
            import httpx

            resp = httpx.head(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {openai_key}"},
                timeout=10.0,
            )
            # 200 = valid key, 401 = invalid key but reachable, 403 = proxy block or forbidden
            reachable = resp.status_code in (200, 401)
            if resp.status_code == 403:
                all_ok &= _check(
                    "OpenAI API is reachable",
                    False,
                    "Got HTTP 403 — likely blocked by corporate proxy. "
                    "Try: export HTTPS_PROXY=... or check VPN settings.",
                )
            else:
                all_ok &= _check(
                    "OpenAI API is reachable",
                    reachable,
                    f"Got HTTP {resp.status_code} — check API key and network settings",
                )
        except Exception as e:
            all_ok &= _check(
                "OpenAI API is reachable",
                False,
                f"Connection failed: {e}. Check network/proxy settings.",
            )
    else:
        print("  - Skipping OpenAI connectivity check (no API key)")

    # 4. Audio storage directory
    storage_path = Path(os.getenv("AUDIO_STORAGE_PATH", "audio_store"))
    if not storage_path.is_absolute():
        storage_path = Path(__file__).resolve().parent.parent / storage_path
    try:
        storage_path.mkdir(parents=True, exist_ok=True)
        test_file = storage_path / ".write_test"
        test_file.write_text("ok")
        test_file.unlink()
        all_ok &= _check(f"Audio storage directory writable ({storage_path})", True, "")
    except Exception as e:
        all_ok &= _check(
            f"Audio storage directory writable ({storage_path})",
            False,
            f"Cannot write to {storage_path}: {e}",
        )

    # 5. httpx installed
    try:
        import httpx  # noqa: F811

        all_ok &= _check("httpx installed", True, "")
    except ImportError:
        all_ok &= _check(
            "httpx installed",
            False,
            "Run: pip install httpx",
        )

    print()
    if all_ok:
        print("All checks passed! You can run functional tests:")
        print("  python -m pytest tests/test_audio_functional.py -v -s")
    else:
        print("Some checks failed. Fix the issues above and re-run:")
        print("  make setup-audio")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
