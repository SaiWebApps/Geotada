Check whether this machine has the prerequisites to run the Travlr project, and help install anything missing.

## Prerequisites to check

1. **Python 3.11+** — run `python3 --version` and verify >= 3.11
2. **Docker** — run `docker --version` and verify it's installed
3. **Docker daemon running** — run `docker info` and check it responds (not "Cannot connect to the Docker daemon")
4. **Docker context** — run `docker context ls` and verify the active context (marked with `*`) is NOT "vessel". If it is, switch to "desktop-linux" with `docker context use desktop-linux`

## For each check

- If it passes, report it briefly (one line)
- If it fails, provide the install command for macOS:
  - Python: `brew install python@3.11` (requires Homebrew)
  - Docker: `brew install --cask docker` (installs Docker Desktop)
  - Docker not running: `open -a Docker` to start Docker Desktop
  - Wrong Docker context: `docker context use desktop-linux`

## After all checks

If everything passes, tell the user they can run `make all` to bootstrap the project.

If anything was installed or fixed, re-run the failed checks to confirm they now pass.
