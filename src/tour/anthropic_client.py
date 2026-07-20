"""ONE bounded Anthropic client factory for every model call the tour engine makes.

WHY THIS EXISTS (measured 2026-07-19). Every Anthropic client in the tour engine
was constructed bare — ``anthropic.Anthropic()`` at ``compose.py:536``,
``verify.py:117``, ``compose_correct.py:212``, ``factcheck.py`` x3 and
``claim_repetition.py:349``. A bare client inherits the SDK defaults: a **600 s
timeout with 2 retries**, i.e. **up to 30 minutes for a single stalled call**.

That is not a theoretical bound. A workbench ``POST /trips/preview`` was observed
holding **128 sockets to api.anthropic.com — 91 CLOSE_WAIT, 34 ESTABLISHED and
unmoving — and had not returned after 32 minutes**, against a UI that promises
"~1 min". The Anthropic API itself was healthy throughout (a direct Haiku call
answered in 1.2 s), so the fault was entirely local: unbounded waits with no
ceiling, multiplied by the compose ladder's fan-out.

The fix is deliberately NOT "make it faster" — it is "make it FAIL, visibly and
soon, instead of hanging". A bounded client turns a 30-minute silent hang into a
prompt, catchable error the compose ladder already knows how to degrade from.

THRESHOLD PROVENANCE — measured or reasoned, none invented:

``JUDGE_TIMEOUT_S`` = 45 s. Judge/verify calls are Haiku with ``max_tokens``
between 5 (``factcheck.py:213``, a single-token verdict) and 2048
(``factcheck.py:117``). A round trip on this machine measured **1.2 s**
(2026-07-19, direct SDK call). 45 s is ~37x that — generous headroom for a slow
or contended call, while still bounding a stall.

``COMPOSE_TIMEOUT_S`` = 180 s. Compose is Opus, STREAMING, with
``thinking={"type": "adaptive"}`` and ``max_tokens=COMPOSE_MAX_OUTPUT_TOKENS``
(64 000). Note that 64 000 was sized for the WHOLE-TOUR composer ("16K truncated
a real 45-min Paris compose mid-JSON", ``compose.py:213-217``); the per-chapter
composer this preview actually uses emits ONE stop of roughly 700 words (~1500
tokens). 180 s is therefore already several times a healthy per-stop call.

Retries: judges get 2 (they are cheap, and transient 429/529 is the common
failure), compose gets 1 (an Opus call is expensive; retrying a genuinely stuck
one twice is how the 30-minute wait was built). Worst-case wall clock per call
becomes 135 s for a judge and 360 s for a compose, versus 1800 s before — and
the per-stop pools run these concurrently.

Both are overridable from the environment so an operator can widen them for a
slow link without a code change; the defaults are what the bar and the workbench
run with.
"""

from __future__ import annotations

import os
from typing import Any

#: Haiku judge/verify calls (entailment, coverage, redundancy). See module docstring.
JUDGE_TIMEOUT_S: float = float(os.getenv("ONDOWAY_JUDGE_TIMEOUT_S", "45"))
JUDGE_MAX_RETRIES: int = int(os.getenv("ONDOWAY_JUDGE_MAX_RETRIES", "2"))

#: Opus compose/correction calls (streaming, adaptive thinking). See module docstring.
COMPOSE_TIMEOUT_S: float = float(os.getenv("ONDOWAY_COMPOSE_TIMEOUT_S", "180"))
COMPOSE_MAX_RETRIES: int = int(os.getenv("ONDOWAY_COMPOSE_MAX_RETRIES", "1"))


def _build(timeout_s: float, max_retries: int) -> Any:
    """Construct a real ``anthropic.Anthropic`` with an explicit ceiling.

    Imported INSIDE the function, matching the lazy-import idiom every call site
    here already uses: ``anthropic`` must not become an import-time dependency of
    the tour package (the hermetic bar constructs these classes with stub clients
    and never touches the SDK).
    """
    import anthropic

    return anthropic.Anthropic(timeout=timeout_s, max_retries=max_retries)


def judge_client() -> Any:
    """A bounded client for Haiku judge/verify calls."""
    return _build(JUDGE_TIMEOUT_S, JUDGE_MAX_RETRIES)


def compose_client() -> Any:
    """A bounded client for Opus compose/correction calls."""
    return _build(COMPOSE_TIMEOUT_S, COMPOSE_MAX_RETRIES)


__all__ = [
    "COMPOSE_MAX_RETRIES",
    "COMPOSE_TIMEOUT_S",
    "JUDGE_MAX_RETRIES",
    "JUDGE_TIMEOUT_S",
    "compose_client",
    "judge_client",
]
