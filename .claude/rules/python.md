---
paths:
  - "**/*.py"
  - "pyproject.toml"
  - "uv.lock"
---

# Python style and dependencies

## Ruff

Line length 100. Rule sets E, F, I, N, W, UP, B, SIM, RUF. Ignored: B008 (FastAPI
`Depends()`), E402 (conftest import ordering), E741 (`l` for Lens in Cypher).

- Imports in isort order, none unused (F401), no `import *` (F403).
- Modern Python (UP): `dict` and `list` over `Dict` and `List`, `X | None` over `Optional[X]`,
  f-strings over `.format()`.
- Bugbear (B): no mutable default arguments, no bare `except:`, no `assert` outside tests.

## Dependency index

`pyproject.toml` pins public PyPI as the default index (`[[tool.uv.index]]`), so `uv.lock`
stays reproducible on any machine. The committed lock must contain only
`files.pythonhosted.org` URLs and never `pypi.apple.com`. This pin overrides any machine-level
`~/.config/uv/uv.toml` default.

- **Default for everyone: `make sync`**, which installs from public PyPI with zero config.
  Public PyPI is reachable on this user's network whether the Apple VPN is on or off, with
  no proxy env set.
- **Apple corp fallback: `make sync-apple`**, for a network that blocks public PyPI. It backs
  up `uv.lock`, re-resolves and installs from `pypi.apple.com` via `UV_DEFAULT_INDEX`, then
  restores the backed-up public lock from the working tree. It does not use `git checkout`, so
  it is safe when the public lock is uncommitted.

Default to `make sync`. Switch to `make sync-apple` only when a `uv` command fails reaching
public PyPI and `curl -sI --max-time 3 https://pypi.apple.com/simple/` returns a response. Run
re-locking (`uv lock`, after a dependency change) where public PyPI is reachable so the
committed lock stays public.
