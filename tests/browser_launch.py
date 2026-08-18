"""How this suite starts Chromium — one question, one answer.

Three modules launch Playwright's Chromium (the workbench UI suite, the
review-regression suite, the deprecation guard) and each spelled the launch
itself, with two byte-identical copies of the binary lookup. Both now live
here, in the ``tests/live_graph.py`` mould: a shared non-test helper module.

THE KEYCHAIN FLAG IS THE LOAD-BEARING PART OF THIS FILE. On macOS, Chromium
asks the login keychain for its "Safe Storage" key on every launch, and a
freshly installed Chrome for Testing carries no standing permission — so each
launch throws a modal password prompt onto the developer's screen, in front of
whatever they were doing, and keeps doing it once per launch forever.

MEASURED 2026-08-11: preflight's Playwright self-repair reinstalled the browser
that afternoon, and every launch afterwards prompted — including a run of
browser demos that put the dialog in the owner's face repeatedly. Nothing under
test needs the real keychain: it encrypts cookies at rest for a throwaway
profile that is destroyed when the test ends. ``--use-mock-keychain`` swaps in
an in-memory stand-in, so the tests behave identically and nobody is
interrupted.

Any new browser launch in this repo goes through here. A launch that spells its
own options is a launch that will start prompting again.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

#: Flags every Chromium launch in this repo carries. See the module docstring:
#: without the keychain stand-in, each launch raises a macOS password dialog.
SHARED_CHROMIUM_ARGS: tuple[str, ...] = ("--use-mock-keychain",)


def find_chromium() -> str | None:
    """A cached Playwright Chromium binary, when the default isn't installed."""
    cache_dir = Path.home() / "Library" / "Caches" / "ms-playwright"
    if not cache_dir.exists():
        return None
    for d in sorted(cache_dir.glob("chromium-*"), reverse=True):
        candidate = (
            d
            / "chrome-mac-arm64"
            / "Google Chrome for Testing.app"
            / "Contents"
            / "MacOS"
            / "Google Chrome for Testing"
        )
        if candidate.exists():
            return str(candidate)
    return None


def chromium_launch_options(**overrides: Any) -> dict[str, Any]:
    """The launch options a test hands ``p.chromium.launch(**...)``.

    Headless by default, pointed at the cached binary when one is needed, and
    always carrying ``SHARED_CHROMIUM_ARGS``. A caller's own ``args`` are
    APPENDED rather than substituted, so no override can silently drop the
    keychain flag and bring the password prompts back.
    """
    caller_args = list(overrides.pop("args", ()))
    options: dict[str, Any] = {"headless": True}
    executable = find_chromium()
    if executable:
        options["executable_path"] = executable
    options.update(overrides)
    options["args"] = [*SHARED_CHROMIUM_ARGS, *caller_args]
    return options
