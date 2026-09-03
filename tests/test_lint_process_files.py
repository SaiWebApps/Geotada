"""The process-file lint: no dangling references, no dated scars.

Two mechanical checks over the repo's process files (CLAUDE.md, .claude/
agents|commands|rules, settings.json, .gitignore, Makefile):

- every repo path a process file references must exist, so removing a thing
  forces removing every mention of it in the same change;
- no ISO date in a process file, so rules state the present constraint rather
  than the incident that motivated it (LEARNINGS.md, the incident log, is
  exempt by not being scanned).

Runs inside `make lint` via scripts/lint_process_files.py; these tests pin the
extraction rules and the exit contract.
"""

from __future__ import annotations

from pathlib import Path

from scripts.lint_process_files import (
    check_repo,
    find_dates,
    find_refs,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestFindRefs:
    def test_finds_a_dot_claude_path_in_prose(self) -> None:
        refs = find_refs("the engine is `.claude/team-engine.js` here")
        assert ".claude/team-engine.js" in refs

    def test_finds_a_backticked_repo_path(self) -> None:
        refs = find_refs("see `scripts/preflight.py` for the probe")
        assert "scripts/preflight.py" in refs

    def test_skips_placeholders_and_globs(self) -> None:
        text = "write to `.claude/runs/{YYYY-MM-DD}-{slug}/plan.md` or `data/*/tours/`"
        assert find_refs(text) == set()

    def test_skips_urls_and_bare_words(self) -> None:
        text = "see https://claude.ai/code and src alone and `and/or` prose"
        assert find_refs(text) == set()

    def test_strips_trailing_punctuation(self) -> None:
        refs = find_refs("registered in .claude/settings.json, then loaded")
        assert ".claude/settings.json" in refs


class TestFindDates:
    def test_finds_an_iso_date(self) -> None:
        assert find_dates("Owner ruling 2026-09-02: deleted.") == ["2026-09"]

    def test_ignores_the_date_placeholder(self) -> None:
        assert find_dates("runs/{YYYY-MM-DD}-{slug}") == []


class TestCheckRepo:
    def test_the_real_repo_is_clean(self) -> None:
        violations = check_repo(REPO_ROOT)
        assert violations == [], "\n".join(violations)

    def test_a_dangling_reference_is_reported(self, tmp_path: Path) -> None:
        (tmp_path / ".claude" / "commands").mkdir(parents=True)
        (tmp_path / ".claude" / "commands" / "x.md").write_text(
            "run `.claude/hooks/gone.py` first"
        )
        violations = check_repo(tmp_path)
        assert any("gone.py" in v for v in violations)

    def test_a_dated_scar_is_reported(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text("Measured 2026-08-31, which is why.")
        violations = check_repo(tmp_path)
        assert any("2026-08" in v for v in violations)

    def test_a_gitignore_negation_must_resolve(self, tmp_path: Path) -> None:
        (tmp_path / ".gitignore").write_text("!.claude/hooks/\n")
        violations = check_repo(tmp_path)
        assert any("hooks" in v for v in violations)
