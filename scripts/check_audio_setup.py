#!/usr/bin/env python3
"""Check audio pipeline prerequisites and report pass/fail for each.

Exit code 0 = all checks passed, 1 = at least one failed.
Designed to be run standalone or via `make setup-audio`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _check(label: str, passed: bool, fix: str) -> bool:
    if passed:
        print(f"  ✓ {label}")
    else:
        print(f"  ✗ {label}")
        print(f"    → {fix}")
    return passed


def _check_local_voice() -> bool:
    """The local Kokoro tier needs BOTH its packages and its weights on disk.

    Checked separately from the credential loop above because it has no
    credential: what it needs is an install and a download, and the remedy is a
    different sentence. Asks the provider itself what is missing so this and
    GET /audio/providers can never disagree about whether it can speak.
    """
    ok = True
    try:
        import lameenc  # noqa: F401
        import sherpa_onnx  # noqa: F401

        ok &= _check("local voice packages installed (sherpa-onnx, lameenc)", True, "")
    except ImportError as exc:
        ok &= _check(
            "local voice packages installed (sherpa-onnx, lameenc)",
            False,
            f"Run `make sync-local-tts` ({exc.name} is not installed).",
        )

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from src.audio.provider import KokoroTTSProvider

    missing = KokoroTTSProvider.missing_pieces()
    return ok & _check(
        "local voice weights present",
        not missing,
        "; ".join(missing) + ". Run `make fetch-kokoro`, then set KOKORO_MODEL_DIR."
        if missing
        else "",
    )


def main() -> int:
    print("Audio Pipeline Prerequisites")
    print("=" * 40)
    all_ok = True

    # 1. OPENAI_API_KEY
    openai_key = os.getenv("OPENAI_API_KEY", "")
    all_ok &= _check(
        "OPENAI_API_KEY is set",
        bool(openai_key) and not openai_key.startswith("sk-REPLACE"),
        "Configure OPENAI_API_KEY on Render, then run `make setup-audio`.",
    )

    # 2. The understudies named by TTS_FALLBACK must actually be able to speak.
    #    A chain whose credentials are missing is decoration: it fails the moment
    #    the primary does, which is precisely the outage it exists to survive. So
    #    a NAMED fallback is a hard check, while an unnamed one stays optional.
    credentials = {
        "openai": ["OPENAI_API_KEY"],
        "elevenlabs": ["ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID"],
    }
    fallbacks = [part.strip() for part in os.getenv("TTS_FALLBACK", "").split(",") if part.strip()]
    if fallbacks:
        for name in fallbacks:
            for var in credentials.get(name, []):
                all_ok &= _check(
                    f"{var} is set (TTS_FALLBACK -> {name})",
                    bool(os.getenv(var)),
                    f"Configure {var} on Render, or drop {name} from TTS_FALLBACK. "
                    "Without it the fallback fails the moment the primary voice does.",
                )
            if name == "kokoro":
                all_ok &= _check_local_voice()
    else:
        print("  - TTS_FALLBACK not set (no understudy: a provider outage means no audio)")
        el_key = os.getenv("ELEVENLABS_API_KEY", "")
        if el_key:
            _check("ELEVENLABS_API_KEY is set", True, "")
            _check(
                "ELEVENLABS_VOICE_ID is set",
                bool(os.getenv("ELEVENLABS_VOICE_ID")),
                "Configure ELEVENLABS_VOICE_ID on Render.",
            )
        else:
            print(
                "  - ELEVENLABS_API_KEY not set "
                "(optional — only needed for the ElevenLabs provider)"
            )

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
        import httpx

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
        print("  make test-live")
    else:
        print("Some checks failed. Fix the issues above and re-run:")
        print("  make setup-audio")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
