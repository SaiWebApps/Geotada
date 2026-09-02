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


# ── the one list a token cannot buy past ─────────────────────────────────────


def _forbidden_hits(paths: list[str], config: dict) -> list[tuple[str, str]]:
    """Paths under a tree this repository has banned outright, with the reason.

    A different question from the two verdicts above, which ask whether a launch
    needs THIS file. This one carries a standing decision about a whole tree, so
    it does not re-litigate the file: being under the prefix is the finding.

    It is checked before the acknowledge token, and that ordering is the entire
    point. Every other refusal here ends `append KEEP-THIS-ARTIFACT and it goes
    in`, which is right for a judgement about one file and wrong for a decision
    meant to outlive the session that made it — a rule one word from being undone
    is a rule the next session never learns was made. `specs/` was re-created and
    re-committed across sessions exactly that way.

    Prefix comparison on the repo-relative path, matching `_kept` above: no
    patterns, so there is no spelling here to misspell. That claim only holds
    because `_would_enter_history` normalizes every path through
    `_repo_relative` first — without it `./specs/x` and `/abs/repo/specs/x` were
    three different strings and only the bare one was judged. The bare directory
    name is matched too, so `git add specs` is refused alongside
    `git add specs/plan.md`.
    """
    rules = [rule for rule in config.get("forbidden", []) if rule.get("prefix")]
    if not rules:
        return []
    out: list[tuple[str, str]] = []
    for path in dict.fromkeys(paths):
        for rule in rules:
            prefix = rule["prefix"]
            if path == prefix.rstrip("/") or path.startswith(prefix):
                out.append((path, rule.get("why", "")))
                break
    return out


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


def _unquote(token: str) -> str:
    """Strip one matched pair of surrounding quotes, if any are left to strip.

    shlex already removes quotes from an ordinary token (posix=True); this is
    only for a spec pulled out of a punctuation-run token by hand (the `<<`
    itself, or its terminator's own leading `-`), which was never a token
    boundary shlex chose on its own and so was never quote-stripped by it.
    """
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        return token[1:-1]
    return token


def _heredoc_terminator(tokens: list[str]) -> str | None:
    """The terminator this line's heredoc redirect names, or None.

    A heredoc token is any token starting with `<<` that is not a here-string
    (`<<<`, which supplies one value, never a multi-line body — shlex groups
    all three characters into one punctuation-run token, so a plain
    `.startswith` check tells them apart). `<<-` never appears as its own
    token: `-` is a shlex wordchar, not punctuation, so it rides on the
    FOLLOWING token instead (`<<-MSG` tokenizes to `['<<', '-MSG']`), and both
    spellings are handled by looking at whatever comes after `<<` and peeling
    one leading `-`.

    The result must be a plain identifier — the same shape a real shell
    requires of a heredoc terminator. Without that check, `$((1<<2))`, a bit
    shift, tokenizes with a `2` sitting right after a `<<` token, and would be
    read as an opener whose terminator is "2" — hunting forever for a
    following line that strips to that.
    """
    for index, token in enumerate(tokens):
        if not token.startswith("<<") or token.startswith("<<<"):
            continue
        spec = token[2:]
        if not spec and index + 1 < len(tokens):
            spec = tokens[index + 1]
        if spec.startswith("-"):
            spec = spec[1:]
        spec = _unquote(spec)
        if spec.isidentifier():
            return spec
        # not identifier-shaped: not a real heredoc terminator, keep scanning
    return None


def _line_tokens(line: str) -> list[str]:
    """One line, tokenized shell-style. Shared by heredoc detection and _segments."""
    try:
        lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        return line.split()


def _strip_heredoc_bodies(command: str) -> str:
    """Drop heredoc BODIES before anything reads the command as argv.

    `<<'MSG' … MSG` hands everything between the opener and the terminator to
    a program as DATA — a commit message, a config file, a prompt — never a
    command and never a pathspec. Tokenizing it anyway let an ordinary English
    sentence in a commit message ("specs are not touched") become a pathspec
    token that _expand() turned into every file under a same-named directory,
    and let a hex id and a couple of proper nouns in the same message get
    judged as unreferenced files in their own right. Measured 2026-08-31:
    _would_enter_history on a 3-file `git add` followed by `git commit -F -
    <<'MSG'` carrying this shape of message returned 3481 paths instead of 3
    (see test_a_multiline_add_and_heredoc_commit_yields_only_the_staged_paths
    for the exact command).

    The opener line itself is KEPT — `git commit -F - <<'MSG'` is a real
    command line, only what follows it up to the terminator is data.

    This is parsing the shell's OWN heredoc syntax to know what counts as a
    command, the same job `shlex` already does for quoting and operators
    elsewhere in this file — it is not a name-matching pattern over file
    content and must not be read as an exception to this guard's
    no-filename-patterns rule. It reads shlex TOKENS rather than a regex over
    the raw text on purpose: this file's own guard hooks refuse an `import
    re` here, and the tokenizer already at the center of _segments answers
    the same question — "is this a heredoc opener, and what terminator does
    it name" — without re-deriving quote and escape handling by hand. Do not
    "simplify" this back to a regex; it will not pass.
    """
    lines = command.split("\n")
    kept: list[str] = []
    terminator: str | None = None
    for line in lines:
        if terminator is not None:
            if line.strip() == terminator:
                terminator = None
            continue
        kept.append(line)
        found = _heredoc_terminator(_line_tokens(line))
        if found:
            terminator = found
    return "\n".join(kept)


def _bare_newline_positions(text: str) -> list[int]:
    """Indices of newlines that end a command, as opposed to sitting inside one.

    A newline inside '...'/"..." is DATA — part of a quoted multi-line
    argument — not a separator, exactly as a `;` inside those same quotes is
    not an operator; shlex already gets the `;` case right because its quote
    state never consults punctuation_chars. This walks the same quoting rules
    (plus a `#` comment, which also runs to end of line) so a newline counts
    as a boundary only where a shell would actually start a new command,
    never one that a quoted argument or a trailing comment merely happens to
    contain.
    """
    positions: list[int] = []
    quote: str | None = None
    escaped = False
    in_comment = False
    for index, char in enumerate(text):
        if char == "\n":
            if not escaped and quote is None:
                positions.append(index)
            escaped = False
            in_comment = False
            continue
        if escaped:
            escaped = False
            continue
        if in_comment:
            continue
        if char == "\\" and quote != "'":
            escaped = True
        elif quote is None and char in ("'", '"'):
            quote = char
        elif quote is not None and char == quote:
            quote = None
        elif quote is None and char == "#":
            in_comment = True
    return positions


def _split_on_bare_newlines(text: str) -> list[str]:
    """`text`, cut at every boundary _bare_newline_positions finds."""
    positions = _bare_newline_positions(text)
    if not positions:
        return [text]
    pieces = []
    start = 0
    for pos in positions:
        pieces.append(text[start:pos])
        start = pos + 1
    pieces.append(text[start:])
    return pieces


def _segments(command: str) -> list[list[str]]:
    """Split a shell line into its separate commands, so `x && git add y` is seen.

    Two steps run before the operator split that always lived here. First,
    heredoc bodies are stripped (_strip_heredoc_bodies) — they are DATA, never
    a command, and tokenizing one fed a commit message's own English words
    into _would_enter_history as pathspecs. Second, the (heredoc-stripped)
    command is cut at every BARE newline (_split_on_bare_newlines) and each
    piece is tokenized on its own, because a newline ends a command exactly
    like `;` does, and shlex — configured with `whitespace_split = True` —
    otherwise treats a bare newline as insignificant space between two words
    on the SAME command. So a two-line `git add …` / `git commit …` read as
    one command, and every token from line 2 onward became an extra argument
    to line 1.

    Adding '\\n' to shlex's own punctuation_chars was tried and rejected: an
    operator glued directly to a newline with no space (`foo &&\\nbar` — valid
    bash, since `&&` alone at end of line continues onto the next) merges
    into a single token, `'&&\\n'`, that matches neither operator string and
    would have been kept as a literal word instead of splitting anything.
    Splitting the TEXT first, before either tokenizer runs, avoids that merge
    entirely.

    Measured 2026-08-31: a 3-file `git add` followed by `git commit -F -
    <<'MSG'` carrying a multi-line message returned 3481 paths from
    _would_enter_history instead of 3, because the whole thing — both real
    commands and the heredoc body between them — was one segment.
    """
    stripped = _strip_heredoc_bodies(command)
    segments: list[list[str]] = [[]]
    for line in _split_on_bare_newlines(stripped):
        for token in _line_tokens(line):
            if token in ("&&", "||", ";", "|", "&"):
                segments.append([])
            else:
                segments[-1].append(token)
        segments.append([])  # a bare newline ends a command exactly like `;`
    return [s for s in segments if s]


def _repo_relative(root: str, path: str) -> str:
    """The path as git names it in the index: repo-relative, no `./`, not absolute.

    A pathspec on a command line is whatever the typist wrote. Git resolves
    `specs/x`, `./specs/x` and `/Users/…/ondoway/specs/x` to ONE entry in the
    index; every rule in this file compares strings, so without this they are
    three different files and only the first is ever judged.

    Measured 2026-09-02, against the forbidden arm: `git add -f specs/plan.md`
    was refused and `git add -f ./specs/plan.md` was allowed — and really staged
    it, exit 0. The absolute spelling is the likelier one here, not a corner
    case: `.claude/hooks/ledger-guard.py` refuses a bare `make`/`pytest`/`uv`
    command and demands an absolute path, so this repo actively trains every
    session toward writing them.

    Normalizing HERE rather than in each comparator is the point — `_kept`,
    `_findings` and `_forbidden_hits` all read this function's output, so one
    fix covers three rules instead of racing them. A path outside the repo, or
    one that will not resolve, is returned untouched: git would not stage it
    either, and guessing is worse than passing it through.
    """
    try:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = Path(root) / path
        return str(candidate.resolve().relative_to(Path(root).resolve()))
    except Exception:
        return path


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
    # ONE normalization point for all three rules below. See _repo_relative.
    return [_repo_relative(root, p) for p in paths]


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


def _handle_forbidden(payload: dict, config: dict) -> None:
    """Refuse a banned tree outright. Runs BEFORE the acknowledge token is read."""
    if (payload.get("tool_name") or "") != "Bash":
        return
    command = str((payload.get("tool_input") or {}).get("command") or "")
    if not command:
        return

    hits = _forbidden_hits(_would_enter_history(command, _repo_root()), config)
    if not hits:
        return

    limit = int(config.get("max_listed", 12))
    paths = sorted(path for path, _why in hits)
    shown = "\n".join(f"    {path}" for path in paths[:limit])
    if len(paths) > limit:
        shown += f"\n    …and {len(paths) - limit} more"
    whys = sorted({why for _path, why in hits if why})

    _deny_tool(
        "BLOCKED by the production-junk guard "
        "(.claude/hooks/production-junk-guard.py). This command would commit "
        f"{len(hits)} file(s) under a tree this repository has banned "
        "outright:\n\n"
        + shown
        + "\n\n"
        + "\n".join(f"  {why}" for why in whys)
        + "\n\n  → Do not commit it. The acknowledge token does NOT lift this "
        "one — it is checked first, on purpose, so a standing decision cannot "
        "be undone by one word appended to a command. Put the file where the "
        "reason above says it belongs."
    )


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

    # ABOVE THE TOKEN, DELIBERATELY. A banned tree is a standing decision, and a
    # decision that any command can append one word to undo is not standing.
    if (payload.get("hook_event_name") or "") != "Stop":
        _handle_forbidden(payload, config)

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
