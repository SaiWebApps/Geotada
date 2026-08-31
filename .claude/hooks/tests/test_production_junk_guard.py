"""Payload tests for .claude/hooks/production-junk-guard.py.

The guard answers one question — would this command put something into git
history that a launch does not need — and it answers it two ways: git's own
ignore rules, and whether anything that builds, tests or ships names the file.

Both arms have gone wrong in ways that LOOK like working. A bare filename was
accepted as proof the product reads a file, which is true for `density.py` and
false for `tour.json`, a name 24 files carried when this was found: judging a
throwaway batch of 40, the guard passed 32 of them on that collision and caught 8
only because their leaf name happened to be spelled differently. And the guard read a
staged DELETION the same as a staged addition, so the first `git rm -r --cached
tests/reports` after a finding would have been denied by the guard that found it.

Neither failure shows up in a test that only checks that junk is blocked. So
every arm here gets a payload that must block AND a payload that must not, and
the two repaired holes get a test each, named for what went wrong.

Two harnesses, on purpose. `decide` runs the guard against THIS repository, so
"a real product file is allowed" is asserted about the real product and cannot
drift from it; it is read-only. `decide_in` builds a throwaway git repository,
so the arms about command parsing — sweeps, deletions, commit flags — can stage
and unstage freely without touching the owner's index.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

# Beside the hook it tests, not in the product's tests/ tree — the subject is
# agent supervision, not Ondoway, so it must never run inside `make test`.
REPO = Path(__file__).resolve().parents[3]
GUARD = REPO / ".claude" / "hooks" / "production-junk-guard.py"
CONFIG = json.loads((GUARD.parent / "production-junk-patterns.json").read_text())
TOKEN = CONFIG["acknowledge_token"]


def _guard_module():
    """The guard imported as a module, for the two verdicts that are pure rules.

    Driving those through a subprocess would make them depend on whichever junk
    happened to be lying around, and the cleanup this guard demanded has since
    removed it. The rule is the thing under test, so the rule is what is called.
    """
    spec = importlib.util.spec_from_file_location("junk_guard", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(command, cwd, event="PreToolUse"):
    """Feed the guard one payload and return its decision dict ({} = allowed)."""
    payload = {
        "hook_event_name": event,
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }
    done = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd),
        timeout=120,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout) if done.stdout.strip() else {}


def decide(command):
    """Judge a command against the real repository. Read-only."""
    return run(command, REPO)


def reason(decision):
    out = decision.get("hookSpecificOutput", {})
    return out.get("permissionDecisionReason") or decision.get("reason", "")


def denied(decision):
    return decision.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


def scratch_repo(tmp_path):
    """A repository of our own, so staging and unstaging costs the owner nothing."""
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@t")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "kept.txt").write_text("content\n")
    git(tmp_path, "add", "kept.txt")
    git(tmp_path, "commit", "-qm", "first")
    return tmp_path


def decide_in(tmp_path, command, event="PreToolUse"):
    return run(command, tmp_path, event=event)


# ---------------------------------------------------------- arm 1: git already said no


def test_a_gitignored_screenshot_directory_is_refused():
    """tests/reports/ was in .gitignore the whole time. 313 files went in anyway.

    Each rule in this repo was written after its files, and nothing ever went back
    to remove them. A declaration that is not enforced at the moment of the action
    does not hold, which is the whole reason this hook exists. The directory is
    gone now; the RULE that named it is not, and it is what must still bite.
    """
    decision = decide("git add tests/reports/screenshots")
    assert denied(decision)
    assert "declared_ignorable" in reason(decision)


def test_a_gitignored_path_under_a_kept_tree_is_still_refused(tmp_path):
    """Git is asked BEFORE the keep list, so a broad prefix cannot readmit junk.

    `data/paris/` is kept — it is the Paris corpus — but the scratch tour output
    underneath it is gitignored and has to stay caught. Built here rather than
    pointed at the real repo, because the real scratch output is now DELETED and
    an ignore rule ending in `/` matches only a directory that exists: the test
    would have passed against thin air, via the other arm, while claiming to
    prove this one.
    """
    repo = scratch_repo(tmp_path)
    (repo / ".gitignore").write_text("data/*/tours/\n")
    corpus = repo / "data" / "paris"
    (corpus / "tours").mkdir(parents=True)
    (corpus / "tours" / "day.json").write_text("{}")
    (corpus / "areas.json").write_text("{}")

    scratch = decide_in(repo, "git add data/paris/tours")
    assert denied(scratch)
    assert "declared_ignorable" in reason(scratch), "the ignore arm, not the other one"
    assert not denied(decide_in(repo, "git add data/paris/areas.json")), "the corpus survives"


# ------------------------------------------------- arm 2: nothing in the product names it


def test_a_packed_archive_nothing_reads_is_refused():
    assert denied(decide("git add spec-pm-skill.zip"))


def test_a_citation_that_spells_the_directory_differently_still_counts():
    """One Docs directory, two spellings, and a deleted file to show for it.

    The repo has a single `Docs/`. The source spells it both ways —
    tests/conftest.py cites `docs/bug-reports/...` in lower case — and this
    filesystem does not distinguish them. Comparing exactly, the guard called
    the capital-D path unreferenced, and the first cleanup built on that rule
    deleted a file the suite points at. It was recovered from the index; the
    rule that lost it is what this pins.
    """
    guard = _guard_module()
    surface = guard._surface_text(str(REPO), CONFIG).lower()
    cited = "Docs/bug-reports/2026-08-28-flutter-test-chrome-hang.md"
    assert cited.lower() in surface, "the premise: the suite really does cite it"
    assert cited not in guard._surface_text(str(REPO), CONFIG), "and only in lower case"
    assert guard._is_referenced(cited, surface, set())
    assert not denied(decide(f"git add {cited}"))


# ------------------------------- the hole: a name many files share proves nothing


def test_a_name_many_files_carry_is_not_evidence_that_the_product_reads_one():
    """The repair, called directly, because it is a rule and not a fixture.

    `stop-0.json` and `tour.json` each name 16 files; the source names the SHAPE
    of a tour dump, never one copy. Accepting the bare name let every scratch
    copy in every certification batch inherit the pass held by the one the code
    actually reads — judging a 40-file throwaway batch, 32 went through on that
    collision alone.
    """
    guard = _guard_module()
    candidates = [
        "data/certification/tour-batch-v1/paris/paris-ile-open-90/stop-0.json",
        "somewhere/else/entirely/tour.json",
        "src/tour/density.py",
    ]
    ambiguous = guard._ambiguous_names(str(REPO), candidates)
    assert "stop-0.json" in ambiguous
    assert "tour.json" in ambiguous
    assert "density.py" not in ambiguous, "a unique name still identifies its file"

    surface = guard._surface_text(str(REPO), CONFIG).lower()
    assert "stop-0.json" in surface, "the premise: the source really does say this name"
    assert not guard._is_referenced(candidates[1], surface, ambiguous)


def test_naming_a_junk_path_in_this_very_file_does_not_launder_it():
    """The guard must not read its own payload test as evidence.

    tests/ is product surface, and this file names junk paths for a living. So
    the act of asserting "this path is junk, block it" put the path into the
    surface and made the guard call it referenced. Three assertions here passed
    before the repo was cleaned and failed afterwards — not because the guard
    changed, but because the test's own mention became the last one standing.
    A file arguing about the guard cannot also be evidence for it.
    """
    guard = _guard_module()
    surface = guard._surface_text(str(REPO), CONFIG)
    assert "spec-pm-skill.zip" not in surface, "this file is being read as surface again"
    assert denied(decide("git add spec-pm-skill.zip"))


def test_a_filename_only_one_file_carries_still_proves_it():
    """The repair must not cost the arm its reach: a unique name is still evidence."""
    assert not denied(decide("git add src/tour/density.py"))


def test_the_root_page_keeps_the_page_it_redirects_to():
    """A kept page must not be left pointing at nothing.

    index.html is in `keep` as the deployed root page, and it exists only to
    redirect to ondoway-journey-wireframes.html. Nothing else in the surface
    named that target, so the guard called it unreferenced junk — and a sweep
    of 513 files came within one judgement of deleting the page the kept root
    points at three times. index.html is surface now: its meta-refresh is a
    link the browser EXECUTES, not a write-up mentioning an artefact, which is
    the line `_comment_surface` draws.
    """
    guard = _guard_module()
    surface = guard._surface_text(str(REPO), CONFIG).lower()
    assert "ondoway-journey-wireframes.html" in surface, "index.html is not being read"
    assert not denied(decide("git add ondoway-journey-wireframes.html"))


# ----------------------------------------------------------- the product is never touched


def test_real_product_source_is_allowed():
    for path in [
        "src/tour/density.py",
        "mobile/lib/main.dart",
        "tests/conftest.py",
        "frontend",
        "config",
        "Makefile",
    ]:
        assert not denied(decide(f"git add {path}")), path


def test_the_city_corpora_are_allowed():
    """The product builds these paths from a city name and never names a leaf.

    Judging them by whether something spells them out flagged 424 real files —
    every Wikipedia extract, every areas.json, every export chunk.
    """
    for path in [
        "data/london/areas.json",
        "data/paris/beats.json",
        "data/new_york/wikipedia",
        "data/paris/export",
        "data/certification/tour-batch-v1",
    ]:
        assert not denied(decide(f"git add {path}")), path


def test_the_flutter_project_files_are_allowed():
    """Flutter finds these by convention; no file in the repo mentions them."""
    for path in ["mobile/pubspec.lock", "mobile/analysis_options.yaml", "mobile/.metadata"]:
        assert not denied(decide(f"git add {path}")), path


def test_a_command_that_is_not_git_is_ignored():
    assert not denied(decide("ls -la tests/reports"))


def test_the_acknowledge_token_lets_a_deliberate_keep_through():
    assert not denied(decide(f"git add tests/reports  # {TOKEN} — the owner asked"))


# ---------------------------------------------- the hole: the guard blocked its own cleanup


def test_a_commit_of_pure_deletions_is_allowed(tmp_path):
    """`git rm -r --cached <junk>` then commit is the guard acting on its own findings.

    Two bugs made that commit impossible. The staged diff counted deletions, and
    an empty staged list was read as "this must be `commit -a`" and fell back to
    judging the whole worktree — which a pure-deletion commit always triggers.
    """
    repo = scratch_repo(tmp_path)
    (repo / "junk.bin").write_text("x")
    git(repo, "add", "-f", "junk.bin")
    git(repo, "commit", "-qm", "junk lands")
    git(repo, "rm", "-q", "--cached", "junk.bin")

    assert not denied(decide_in(repo, "git commit -m cleanup"))


def test_a_commit_that_sweeps_the_worktree_still_judges_it(tmp_path):
    """`commit -a` and `commit -am` sweep, so they must still be judged."""
    repo = scratch_repo(tmp_path)
    (repo / "leftover.bin").write_text("x")
    assert denied(decide_in(repo, "git commit -am wip"))
    assert denied(decide_in(repo, "git commit -a -m wip"))


def test_add_all_is_judged_however_it_is_spelled(tmp_path):
    repo = scratch_repo(tmp_path)
    (repo / "leftover.bin").write_text("x")
    for spelling in ["git add -A", "git add .", "git add --all", "git -C . add -A"]:
        assert denied(decide_in(repo, spelling)), spelling


def test_a_junk_add_hidden_later_in_a_shell_line_is_still_seen(tmp_path):
    repo = scratch_repo(tmp_path)
    (repo / "leftover.bin").write_text("x")
    assert denied(decide_in(repo, "echo hello && git add -A"))


def test_a_clean_worktree_ends_the_turn_without_a_word(tmp_path):
    """The Stop arm must be silent when there is nothing to clean up."""
    repo = scratch_repo(tmp_path)
    assert decide_in(repo, "", event="Stop") == {}


def test_the_stop_arm_names_what_add_all_would_sweep_in(tmp_path):
    repo = scratch_repo(tmp_path)
    (repo / "leftover.bin").write_text("x")
    decision = decide_in(repo, "", event="Stop")
    assert decision.get("decision") == "block"
    assert "leftover.bin" in reason(decision)


def test_a_stop_already_blocked_once_does_not_block_again(tmp_path):
    """Blocking a stop that is itself the result of a block loops forever."""
    repo = scratch_repo(tmp_path)
    (repo / "leftover.bin").write_text("x")
    payload = {"hook_event_name": "Stop", "stop_hook_active": True}
    done = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(repo),
        timeout=120,
    )
    assert done.returncode == 0
    assert not done.stdout.strip()
