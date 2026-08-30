#!/usr/bin/env python3
"""Production-junk guard — nothing enters history that a launch does not need.

Two questions decide whether a file belongs in this repo:

  1. Does a build, a test, or the shipped app read it?
  2. Has the repo already declared it junk?

Run screenshots, phase write-ups, handoff notes, ledgers, verdicts, scratch tour
dumps, generated folders, planning documents and packed archives all answer no
to the first and, usually, yes to the second. They are cheap to create and free
to keep, so they accumulate until the repo is mostly sediment — 5.4 GB of
Playwright screenshots on disk, 313 of them in the index, when this was written.

WHY A GUARD RATHER THAN A RULE. .gitignore already named tests/reports/,
data/*/tours/, specs/*/ and Books/**/*.pdf as junk, and 427 files matching those
rules were tracked anyway, 207 MB of them: each rule was added after its files,
and nothing ever went back to remove them. A declaration that is not enforced at
the moment of the action does not hold. This runs at that moment.

HOW IT DECIDES — no name patterns, by design. A pattern catches only the
spellings someone thought of and starves silently. Both verdicts here are
answered by a tool or by the product itself:

  declared_ignorable — `git check-ignore` says the repo already excludes it.
                       Git answers; there is nothing to misspell.
  unreferenced       — its name appears nowhere in the product surface: the
                       app, the suite, the scripts, the Makefile, the build
                       files. If nothing reads it, it cannot affect the product.
                       A bare filename counts only when it is unique in the
                       tree: `tour.json` names 24 files, so it names none.

An explicit `keep` prefix list in production-junk-patterns.json overrides both,
for the files a build or an App Store review needs but never names in text.

WIRED TWO WAYS (.claude/settings.json):

  PreToolUse on Bash — a `git add` or `git commit` that would put junk in the
  index is denied, naming every path and what to do instead. This is the half
  that matters: history is the thing that cannot be cleaned up afterwards.

  Stop — before the turn ends, untracked files that `git add -A` would sweep in
  are listed and the stop is blocked once, so a session deletes its own
  droppings instead of leaving them for the next one.

APPLE APP STORE. Review sees the .ipa, not the repo, so most of this is hygiene
rather than a rejection risk. Two categories are not. Third-party copyrighted
source material is a legal problem wherever it sits — the guard reaches it
through rule 1, since Books/**/*.pdf is already gitignored. And the assets a
review genuinely requires — the AppIcon set, the launch image, the pubspec
assets — are in `keep`, so they can never be flagged.

To keep something the guard flags, append the acknowledge token to the command
and say why. Protocol (stdin JSON, decision by printed JSON, always exit 0)
matches the other guards in this directory.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path, PurePosixPath

CONFIG_PATH = Path(__file__).resolve().parent / "production-junk-patterns.json"
MAX_SURFACE_BYTES = 400_000  # a single file larger than this is data, not a reference


def _load() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        # A broken or absent sidecar must never block the owner's work.
        return {}


def _git(args: list[str], cwd: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=25
        ).stdout
    except Exception:
        return ""


def _repo_root() -> str:
    root = _git(["rev-parse", "--show-toplevel"], cwd=str(Path.cwd())).strip()
    return root or str(Path.cwd())


# ── verdict 1: the repo already declared it ignorable ────────────────────────


def _declared_ignorable(paths: list[str], root: str) -> set[str]:
    """Ask git, in one call. --no-index so a tracked file is still answered."""
    if not paths:
        return set()
    try:
        done = subprocess.run(
            ["git", "check-ignore", "--no-index", "--stdin"],
            cwd=root,
            input="\n".join(paths),
            capture_output=True,
            text=True,
            timeout=25,
        )
    except Exception:
        return set()
    return {line.strip() for line in done.stdout.splitlines() if line.strip()}


# ── verdict 2: nothing in the product names it ───────────────────────────────


def _surface_text(root: str, config: dict) -> str:
    """Everything that builds, tests or ships, concatenated once.

    A candidate is 'referenced' when its name appears anywhere in here. Plain
    substring containment: the language answers, so there is no pattern to get
    wrong, and it errs toward keeping a file rather than flagging it.

    `surface_exclude` drops the guard's OWN payload test. tests/ is surface, and
    that file names junk paths for a living — so writing "this path is junk, and
    the guard must block it" was the act that made the guard stop blocking it.
    Three assertions passed before the cleanup and failed after, not because the
    guard changed but because the only remaining mention of each path was the
    test's own. A file arguing about the guard cannot also be evidence for it.
    """
    suffixes = set(config.get("surface_suffixes", []))
    excluded = set(config.get("surface_exclude", []))
    base = Path(root)
    parts: list[str] = []

    def absorb(path: Path) -> None:
        try:
            if str(path.relative_to(base)) in excluded:
                return
            if path.stat().st_size > MAX_SURFACE_BYTES:
                return
            parts.append(path.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            return

    for name in config.get("surface_files", []):
        candidate = base / name
        if candidate.is_file():
            absorb(candidate)
    for name in config.get("surface_dirs", []):
        directory = base / name
        if not directory.is_dir():
            continue
        for candidate in directory.rglob("*"):
            if candidate.is_file() and candidate.suffix.lower() in suffixes:
                absorb(candidate)

    return "\n".join(parts)


def _ambiguous_names(root: str, candidates: list[str]) -> set[str]:
    """Leaf names carried by more than one file, so a mention identifies none.

    A bare filename was accepted as proof that the product reads a file. That
    holds for `density.py`, which exists once. It fails for `tour.json`, which
    exists 24 times: the source names the SHAPE of a tour file, never one
    particular copy, so every scratch copy in every certification batch
    inherited the pass. Wiring this guard, a throwaway batch of 40 files was
    judged and 32 went through on exactly that collision — and the 8 it did
    catch were caught only because their leaf name, `stop-1.json`, happened
    not to appear anywhere. Which files a guard blocks must not turn on a
    coincidence of spelling.

    The repo answers, so there is nothing here to misspell. A name that is
    unique in the working tree still identifies its file and is still trusted;
    a name that is not stops being evidence, and the file has to be named by
    full path to survive. Counting is one UNPRUNED walk — 36k entries, 0.15s
    on this repo — because pruning would under-count copies and hand back the
    same false pass it exists to remove.
    """
    wanted = {PurePosixPath(path).name for path in candidates}
    wanted.discard("")
    if not wanted:
        return set()

    counts: dict[str, int] = {}
    for _, _, filenames in os.walk(root):
        for filename in filenames:
            if filename in wanted:
                counts[filename] = counts.get(filename, 0) + 1
    return {name for name, count in counts.items() if count > 1}


def _is_referenced(path: str, surface: str, ambiguous: set[str]) -> bool:
    """Does anything in the product name THIS file? `surface` must be lowercased.

    Its own path always counts. Its bare filename counts only when that name
    belongs to a single file in the tree — see _ambiguous_names.

    CASE-INSENSITIVELY, because this filesystem is. The repo holds one `Docs/`
    directory and the source spells it both `Docs/` and `docs/`; comparing
    exactly made `Docs/bug-reports/2026-08-28-flutter-test-chrome-hang.md` look
    unreferenced while `docs/bug-reports/2026-08-28-flutter-test-chrome-hang.md`
    sat in tests/conftest.py, and the first cleanup built on this rule deleted
    the file. A rule that answers differently for two spellings of one path is
    not answering about the path.

    Deliberately NOT its parent directory: `Docs/tour-builder` is named by
    src/tour/density.py, and treating that as a reference to every file
    underneath kept a phase write-up alive.
    """
    lowered = path.lower()
    if lowered in surface:
        return True
    name = PurePosixPath(lowered).name
    if not name or name in ambiguous:
        return False
    return name in surface


# ── classification ───────────────────────────────────────────────────────────


def _kept(path: str, config: dict) -> bool:
    """Product by declaration, or product by being the surface itself.

    The second half is not a convenience. A file INSIDE the product surface is
    reached by a runner, not by a mention: pytest discovers a test, Flutter
    compiles every .dart under lib/, the app reads config/ at boot. Judging
    those by whether something names them flagged a brand-new test file, the
    frontend's own entry page and a live config as unreferenced. The surface
    does not have to justify itself to itself.

    A gitignored path under a surface directory is still caught — git's answer
    is asked before this — which is what keeps tests/reports/ from riding in
    under tests/.
    """
    # .get, not []: the keep list carries explanatory entries with no prefix.
    if any(path.startswith(rule.get("prefix") or "\0") for rule in config.get("keep", [])):
        return True
    return any(
        path.startswith(directory.rstrip("/") + "/")
        for directory in config.get("surface_dirs", [])
    )


def _findings(paths: list[str], root: str, config: dict) -> list[tuple[str, str]]:
    """(path, verdict) for every candidate that a launch does not need.

    Order matters. Git's own answer is asked FIRST, before the keep list: when
    .gitignore already excludes a path, the repo has declared it junk, and a
    broad keep prefix must not quietly readmit it. That ordering is what reaches
    the copyrighted PDF sitting under an otherwise-kept Books/ tree, and the
    guard's own team-gate log sitting under an otherwise-kept .claude/ tree.

    The cost of that order is that a wrong .gitignore rule becomes a wrong
    block — so a rule this guard trusts has to be right. One was not: an
    unanchored `models/` excluded src/api/models/ and mobile/lib/models/, real
    product source. It is anchored now, and any future block naming source is
    the same defect showing itself again.
    """
    candidates = [p for p in dict.fromkeys(paths) if p]
    if not candidates:
        return []

    ignorable = _declared_ignorable(candidates, root)
    surface = _surface_text(root, config)
    ambiguous = {name.lower() for name in _ambiguous_names(root, candidates)}
    surface = surface.lower()  # lowered ONCE here, never per candidate

    out: list[tuple[str, str]] = []
    for path in candidates:
        if path in ignorable:
            out.append((path, "declared_ignorable"))
        elif _kept(path, config):
            continue
        elif not _is_referenced(path, surface, ambiguous):
            out.append((path, "unreferenced"))
    return out


def _render(findings: list[tuple[str, str]], config: dict) -> str:
    """Group by verdict so the reason is stated once, not once per file."""
    limit = int(config.get("max_listed", 12))
    reasons = config.get("reasons", {})
    grouped: dict[str, list[str]] = {}
    for path, verdict in findings:
        grouped.setdefault(verdict, []).append(path)

    blocks = []
    for verdict, paths in grouped.items():
        reason = reasons.get(verdict, {})
        shown = sorted(paths)[:limit]
        more = len(paths) - len(shown)
        listing = "\n".join(f"    {p}" for p in shown)
        if more > 0:
            listing += f"\n    …and {more} more"
        blocks.append(
            f"  [{verdict}] {reason.get('why', '')}\n{listing}\n"
            f"    → {reason.get('instead', '')}"
        )
    return "\n\n".join(blocks)


# ── what a command would put in the index ────────────────────────────────────


def _porcelain(root: str, *, untracked_only: bool) -> list[str]:
    paths = []
    for line in _git(["status", "--porcelain"], cwd=root).splitlines():
        if len(line) < 4:
            continue
        code, path = line[:2], line[3:].split(" -> ")[-1].strip().strip('"')
        if untracked_only and code != "??":
            continue
        if "D" in code:
            # A deletion being staged REMOVES a file from history. Judging it
            # like an addition made the guard deny `git rm -r --cached
            # tests/reports` — the one command that acts on its own findings.
            continue
        if path.endswith("/"):  # an untracked directory — list what is inside
            listing = _git(
                ["ls-files", "--others", "--exclude-standard", "--", path], cwd=root
            )
            paths.extend(p for p in listing.splitlines() if p)
            continue
        paths.append(path)
    return paths


def _expand(root: str, spec: str) -> list[str]:
    """A directory pathspec stages every file under it — judge them all."""
    if not (Path(root) / spec).is_dir():
        return [spec]
    listing = _git(
        ["ls-files", "--others", "--cached", "--exclude-standard", "--", spec], cwd=root
    )
    return [p for p in listing.splitlines() if p] or [spec]


def _is_git_subcommand(tokens: list[str], name: str) -> bool:
    """`git add`, `git -C /path add`, `git --no-pager add` — parsed, not matched."""
    if not tokens or PurePosixPath(tokens[0]).name != "git":
        return False
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token.startswith("-"):
            index += 2 if token in ("-C", "-c", "--git-dir", "--work-tree") else 1
            continue
        return token == name
    return False


def _segments(command: str) -> list[list[str]]:
    """Split a shell line into its separate commands, so `x && git add y` is seen."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        tokens = command.split()

    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in ("&&", "||", ";", "|", "&"):
            segments.append([])
        else:
            segments[-1].append(token)
    return [s for s in segments if s]


def _would_enter_history(command: str, root: str) -> list[str]:
    """Paths this command line would add to, or commit from, the index."""
    paths: list[str] = []
    for tokens in _segments(command):
        if _is_git_subcommand(tokens, "commit"):
            # --diff-filter=d drops staged deletions, for the same reason.
            paths.extend(
                p
                for p in _git(
                    ["diff", "--cached", "--name-only", "--diff-filter=d"], root
                ).splitlines()
                if p
            )
            # `git commit -a` also sweeps the worktree. Asked as a flag, not
            # inferred from an empty staged list: a commit that stages only
            # DELETIONS has an empty list too, and inferring there turned the
            # cleanup commit into a full-worktree judgement that denied it.
            if any(
                token == "--all"
                or (token.startswith("-") and not token.startswith("--") and "a" in token[1:])
                for token in tokens
            ):
                paths.extend(_porcelain(root, untracked_only=False))
        elif _is_git_subcommand(tokens, "add"):
            rest = tokens[tokens.index("add") + 1 :]
            specs = [t for t in rest if not t.startswith("-")]
            sweeps = any(t in ("-A", "--all", ".", "-u", ":/", "*") for t in rest)
            if sweeps or not specs:
                paths.extend(_porcelain(root, untracked_only=False))
            else:
                for spec in specs:
                    paths.extend(_expand(root, spec.rstrip("/")))
    return paths


# ── decisions ────────────────────────────────────────────────────────────────


def _deny_tool(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                },
                "systemMessage": reason,
            }
        )
    )
    sys.exit(0)


def _block_stop(reason: str) -> None:
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def _handle_pre_tool_use(payload: dict, config: dict) -> None:
    if (payload.get("tool_name") or "") != "Bash":
        return
    command = str((payload.get("tool_input") or {}).get("command") or "")
    if not command:
        return

    root = _repo_root()
    candidates = _would_enter_history(command, root)
    if not candidates:
        return
    findings = _findings(candidates, root, config)
    if not findings:
        return

    token = config.get("acknowledge_token", "")
    _deny_tool(
        "BLOCKED by the production-junk guard "
        "(.claude/hooks/production-junk-guard.py). This command would put "
        f"{len(findings)} file(s) into git history that a launch does not "
        "need:\n\n"
        + _render(findings, config)
        + "\n\nDelete them, or add them to .gitignore, then run the command "
        f"again. To keep one deliberately, append '{token}' to the command and "
        "say why in your report."
    )


def _handle_stop(payload: dict, config: dict) -> None:
    # Fire once. Blocking a stop that is itself the result of a block loops.
    if payload.get("stop_hook_active"):
        return

    root = _repo_root()
    findings = _findings(_porcelain(root, untracked_only=True), root, config)
    if not findings:
        return

    _block_stop(
        f"Production-junk guard: this working tree holds {len(findings)} "
        "untracked file(s) that a launch does not need, and `git add -A` would "
        "sweep every one of them into history:\n\n"
        + _render(findings, config)
        + "\n\nDelete them, or add them to .gitignore, before ending the turn, "
        "and say in one line what you removed."
    )


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    config = _load()
    if not config:
        sys.exit(0)

    token = config.get("acknowledge_token", "")
    command = str((payload.get("tool_input") or {}).get("command") or "")
    if token and token in command:
        sys.exit(0)  # deliberate, acknowledged, and visible in the transcript

    if (payload.get("hook_event_name") or "") == "Stop":
        _handle_stop(payload, config)
    else:
        _handle_pre_tool_use(payload, config)

    sys.exit(0)


if __name__ == "__main__":
    main()
