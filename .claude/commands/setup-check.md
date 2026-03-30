Check whether this machine has the prerequisites to run the Travlr project, and help install anything missing.

## Core Prerequisites

1. **Python 3.11+** — run `python3 --version` and verify >= 3.11
2. **Docker** — run `docker --version` and verify it's installed
3. **Docker daemon running** — run `docker info` and check it responds (not "Cannot connect to the Docker daemon")
4. **Docker context** — run `docker context ls` and verify the active context (marked with `*`) is NOT "vessel". If it is, switch to "desktop-linux" with `docker context use desktop-linux`

## Audio Pipeline Prerequisites

5. **OPENAI_API_KEY** — check if set in `.env` file (grep for `OPENAI_API_KEY=sk-`). Required for TTS generation and Whisper evaluation.
6. **OpenAI API reachable** — if key is set, run `make setup-audio` to test connectivity. If blocked by proxy, guide the user through proxy configuration.
7. **httpx installed** — run `python -c "import httpx"` and verify it imports (required for TTS API calls)
8. **Audio storage directory** — verify `audio_store/` exists and is writable (or check `AUDIO_STORAGE_PATH` env var)
9. **(Optional) ELEVENLABS_API_KEY + ELEVENLABS_VOICE_ID** — check if set in `.env`. Only needed for ElevenLabs provider.

## For each check

- If it passes, report it briefly (one line)
- If it fails, provide the fix:
  - Python: `brew install python@3.11` (requires Homebrew)
  - Docker: `brew install --cask docker` (installs Docker Desktop)
  - Docker not running: `open -a Docker` to start Docker Desktop
  - Wrong Docker context: `docker context use desktop-linux`
  - Missing OPENAI_API_KEY: Guide user to https://platform.openai.com/api-keys, then add to `.env`
  - OpenAI unreachable: Check proxy settings, try `curl -I https://api.openai.com`
  - Missing httpx: `pip install httpx`
  - Audio dir not writable: `mkdir -p audio_store && chmod 755 audio_store`

## After all checks

If everything passes, tell the user they can run:
- `make all` to bootstrap the full project
- `make setup-audio` to verify audio-specific prerequisites in detail
- `python -m pytest tests/test_audio_functional.py -v -s` to run the E2E audio tests

If anything was installed or fixed, re-run the failed checks to confirm they now pass.
