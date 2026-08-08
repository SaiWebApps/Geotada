"""ONE definition of "the seconds a tour aims to contain", and one of "elapsed".

WHAT THIS GUARDS. Phase 3 made a stop's length what the place and the visitor
jointly justify. Nothing in it changed what the PLANNER budgets against, so the
tourist experiences walk + visit while every gate still checks walk + narration —
the reported bug inverted, on the same quantity. Measured 2026-08-06: a 120-minute
request served 157 minutes while reporting 120.

Phase 3B moves the currency. This file is how that phase is MEASURED rather than
claimed: it fails while any old name survives, and passes only when every site has
moved. It is deliberately committed BEFORE the rename, red, so the phase cannot be
declared finished on a subset.

WHY A NAME GUARD AND NOT A BEHAVIOUR TEST. The defect this phase removes is a
SECOND EXPRESSION of one quantity. Behaviour tests cannot see that: two expressions
agree on every case you thought to write and diverge on the one you did not. The
only reliable signal that a duplicate is gone is that its name is gone.

``planned_total_seconds`` is DELIBERATELY NOT in the list below. No step renames it,
and adding it would make this guard permanently red for no reason.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SEARCH_ROOTS = ("src", "scripts", "tests")

#: Old name -> what it becomes. Every one of these is a name for AUDIO seconds
#: being used as the budget for a STOP, which is the confusion the phase removes.
RENAMES: dict[str, str] = {
    "AUDIO_FRACTION": "DWELL_FRACTION",
    "audio_target_seconds": "dwell_target_seconds",
    "target_audio_seconds": "target_dwell_seconds",
    "_target_audio_seconds": "_target_dwell_seconds",
    "audio_capacity_seconds": "dwell_capacity_seconds",
    "audio_budget": "dwell_budget",
    "consumed_audio": "consumed_dwell",
    "FILL_PASS_AUDIO_FLOOR_FRAC": "FILL_PASS_DWELL_FLOOR_FRAC",
}


def _python_files() -> list[Path]:
    files: list[Path] = []
    for root in SEARCH_ROOTS:
        files.extend((REPO_ROOT / root).rglob("*.py"))
    return [f for f in files if f.resolve() != Path(__file__).resolve()]


def _hits(name: str) -> list[str]:
    """Every line mentioning `name`, outside comment lines and this file.

    Comment-only lines are skipped so a historical note ("was AUDIO_FRACTION until
    2026-08-06") does not keep the guard red forever. A DOCSTRING mention is NOT
    skipped, and that is deliberate: a docstring describing the old currency is
    wrong prose that the rename must fix, not a historical aside.
    """
    pattern = re.compile(rf"\b{re.escape(name)}\b")
    found: list[str] = []
    for path in _python_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if pattern.search(line):
                found.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()[:100]}")
    return found


@pytest.mark.parametrize(("old", "new"), sorted(RENAMES.items()))
def test_the_old_audio_currency_name_is_gone(old: str, new: str) -> None:
    """`old` must not survive anywhere: it named audio where dwell is meant."""
    hits = _hits(old)
    if hits:
        shown = "\n".join(f"  {h}" for h in hits[:25])
        more = f"\n  ... and {len(hits) - 25} more" if len(hits) > 25 else ""
        pytest.fail(
            f"`{old}` still appears in {len(hits)} place(s); it should be `{new}`.\n"
            f"{shown}{more}\n"
            f"A stop's length is what the visitor SPENDS there, not what it SAYS. "
            f"While both names exist, two definitions of the tour's budget exist, "
            f"and they agree only until they do not."
        )


def test_the_new_names_actually_exist_somewhere() -> None:
    """The guard above passes trivially if the rename DELETED rather than moved.

    Every old name has a replacement, and a phase that removed the concept instead
    of renaming it would satisfy every assertion above while leaving the planner
    with no budget at all. This is the other half of the check.
    """
    missing = [new for new in sorted(set(RENAMES.values())) if not _hits(new)]
    assert not missing, (
        f"these replacement names appear nowhere: {missing}. The old names may have "
        f"been deleted rather than renamed, which would leave the planner with no "
        f"definition of what a tour aims to contain."
    )
