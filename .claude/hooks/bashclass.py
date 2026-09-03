#!/usr/bin/env python3
"""Does this shell command only LOOK, or does it ACT?

WHY A CLASSIFIER AND NOT A LIST OF BLOCKED NAMES. The advisor gate refused an
`ls` on 2026-09-02 as the first call of a turn, because it gated the Bash TOOL
rather than what the command did. Reading is not acting, and a gate that
refuses a look forces the session to look some other way — which is exactly the
write-your-own-grep behaviour the owner is trying to stop. The capability
worth controlling is CHANGING something before consulting, not the spelling of
a read.

FAILS CLOSED. Every segment of the command must be a program on the
read-only list, with read-only arguments, for the whole command to count as a
look. An unknown program is an act. A redirection is an act. `python3 -c` is
an act, because a one-liner can write. `sed` and `perl` are looks unless they
carry an in-place flag. `git` is a look only for the subcommands that print.
The list of looks is short and a miss costs one consult; the list of acts is
everything else, so there is no spelling to forget.

PARSED, NOT MATCHED. The command is split into segments by ledger-guard.py's
own `_segments` — the shlex-based splitter that already strips heredoc bodies
and cuts at bare newlines — so `foo && rm -rf x` is two segments and the second
one is read on its own terms. If that import fails, everything is an act.

`redirect_targets` is the second question this module answers: which existing
files would `>`, `>>` or `tee` overwrite. The advisor gate uses it to demand
that a file be READ before a shell command rewrites it, the same rule it holds
the Edit and Write tools to. Without it, `cat > file <<EOF` was a way to
rewrite a file nobody had opened.
"""

from __future__ import annotations

from pathlib import Path

from hookenv import load_sibling

_ledger = load_sibling("ledger-guard.py", "ondoway_ledger_guard")

#: Programs that print and change nothing. Short on purpose.
READ_ONLY = {
    "ls", "cat", "head", "tail", "wc", "stat", "file", "echo", "printf", "pwd",
    "which", "whereis", "type", "command", "env", "date", "du", "df", "sort", "uniq",
    "cut", "tr", "diff", "cmp", "md5", "md5sum", "shasum", "sha256sum", "grep",
    "egrep", "fgrep", "rg", "ag", "find", "basename", "dirname", "realpath",
    "readlink", "xxd", "od", "strings", "nl", "jq", "column", "tree", "less",
    "more", "true", "false", "test", "[", "uname", "hostname", "whoami", "id",
    "sw_vers", "sysctl", "ps", "lsof", "netstat", "sleep", "seq", "expr", "bc",
    "awk", "gawk", "sed", "perl", "python3", "python", "node", "uv", "make",
    "timeout", "time", "nice", "xargs",
}

#: Read-only programs that become ACTS with these arguments.
ACT_IF_ANY_ARG = {
    "find": {"-delete", "-exec", "-execdir", "-ok", "-okdir"},
    "python3": {"-c", "-", "-m"},
    "python": {"-c", "-", "-m"},
    "node": {"-e", "--eval", "-p", "-"},
    "uv": {"run", "pip", "sync", "add", "remove", "lock", "venv", "tool"},
    "make": {"*"},  # a make target runs a recipe; only `make -n` is a look
    "xargs": {"*"},
}

#: `python3 some_script.py` runs code that may write: an act. Only version /
#: help style flags are looks.
SCRIPT_RUNNERS = {"python3", "python", "node"}
RUNNER_LOOK_FLAGS = {"--version", "-V", "-VV", "--help", "-h"}

#: git subcommands that only print.
GIT_READ = {
    "status", "log", "diff", "show", "ls-files", "rev-parse", "blame", "grep",
    "check-ignore", "describe", "cat-file", "shortlog", "rev-list", "ls-tree",
    "name-rev", "for-each-ref", "reflog", "count-objects", "var", "version",
    "--version", "help", "whatchanged", "diff-tree", "diff-index", "diff-files",
    "merge-base", "show-ref", "symbolic-ref", "stash", "branch", "remote", "tag",
    "worktree", "config", "notes",
}
#: For these, the subcommand prints only without a writing flag/verb.
GIT_READ_UNLESS = {
    "stash": {"push", "pop", "apply", "drop", "clear", "save", "branch"},
    "branch": {"-d", "-D", "-m", "-M", "-c", "-C", "--delete", "--move", "--copy",
               "-u", "--set-upstream-to", "--unset-upstream", "-f", "--force"},
    "remote": {"add", "remove", "rm", "rename", "set-url", "set-head", "prune", "update"},
    "tag": {"-d", "--delete", "-a", "-s", "-f", "-m"},
    "worktree": {"add", "remove", "prune", "move", "lock", "unlock", "repair"},
    "config": {"--unset", "--unset-all", "--add", "--replace-all", "--edit", "-e",
               "--remove-section", "--rename-section"},
    "notes": {"add", "append", "edit", "remove", "prune", "copy", "merge"},
}
#: git global flags that consume the next token.
GIT_VALUE_FLAGS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}

#: Shell control words that open or close a compound command; not programs.
CONTROL_WORDS = {
    "for", "in", "do", "done", "if", "then", "else", "elif", "fi", "while",
    "until", "case", "esac", "{", "}", "!", "function", "select", "time",
}

#: Wrappers whose own arguments are skipped before classifying the real program.
WRAPPERS = {"timeout", "time", "nice", "env", "command", "exec", "sudo"}
WRAPPER_VALUE_FLAGS = {"timeout": {"-s", "--signal", "-k", "--kill-after"},
                       "nice": {"-n"}, "env": {"-u", "-C", "-S"}}

REDIRECT_TOKENS = {">", ">>", ">|", "1>", "2>", "&>", ">&"}


def _is_fd_dup(token: str, following: str) -> bool:
    """`2>&1`, `>&2`, `&>1`: a file-descriptor duplicate, which writes no file.

    shlex's punctuation mode splits `2>&1` into `2`, `>&`, `1`, so the target
    of a `>&`/`&>` token is the NEXT token; a pure digit there means an fd.
    Found 2026-09-02: without this every `cmd 2>&1 | tail` was an act.
    """
    if token in {">&", "&>"}:
        return following.isdigit()
    if token.startswith((">&", "&>")) and token[2:].isdigit():
        return True
    return False


def _redirection_target(tokens: list[str], position: int) -> str | None:
    """The file a redirection token at `position` writes, or None when it is
    an fd duplicate or `/dev/null`."""
    token = tokens[position]
    following = tokens[position + 1] if position + 1 < len(tokens) else ""
    if _is_fd_dup(token, following):
        return None
    if token in REDIRECT_TOKENS:
        target = following
    elif token.startswith(">>"):
        target = token[2:]
    elif token.startswith((">", "2>")):
        target = token.lstrip("12>|&")
    else:
        return None
    if not target or target == "/dev/null" or target.startswith("&"):
        return None
    return target


def _segments(command: str) -> list[list[str]]:
    if _ledger is None:
        return []
    try:
        return _ledger._segments(command)
    except Exception:
        return []


def _unwrap(argv: list[str]) -> list[str]:
    """Strip control words, variable assignments and wrappers off the front."""
    tokens = list(argv)
    while tokens:
        head = tokens[0]
        if head in CONTROL_WORDS:
            tokens = tokens[1:]
            continue
        if "=" in head and not head.startswith("=") and head.split("=", 1)[0].replace("_", "a").isalnum():
            tokens = tokens[1:]  # VAR=value prefix
            continue
        name = Path(head).name
        if name in WRAPPERS:
            rest = tokens[1:]
            value_flags = WRAPPER_VALUE_FLAGS.get(name, set())
            index = 0
            while index < len(rest):
                token = rest[index]
                if name == "timeout" and index == 0 and token[:1].isdigit():
                    index += 1
                    continue
                if token in value_flags:
                    index += 2
                    continue
                if token.startswith("-"):
                    index += 1
                    continue
                if name == "env" and "=" in token:
                    index += 1
                    continue
                break
            tokens = rest[index:]
            continue
        break
    return tokens


def _git_is_look(argv: list[str]) -> bool:
    index = 1
    while index < len(argv) and argv[index].startswith("-"):
        index += 2 if argv[index] in GIT_VALUE_FLAGS else 1
    if index >= len(argv):
        return True
    sub = argv[index]
    rest = argv[index + 1:]
    if sub not in GIT_READ:
        return False
    for forbidden in GIT_READ_UNLESS.get(sub, set()):
        if forbidden in rest:
            return False
    return True


#: Compound-command HEADERS: the words after them are names, not a program.
#: `for f in a b`, `case $x in`, `select opt in a b`.
HEADER_WORDS = {"for", "case", "select"}
#: Shell builtins that read or test and change nothing.
READ_ONLY.update({"read", "[[", "]]", "let", "local", "return", "break", "continue", ":"})


def _segment_is_look(argv: list[str]) -> tuple[bool, str]:
    if argv and argv[0] in HEADER_WORDS:
        return True, ""
    tokens = _unwrap(argv)
    if not tokens:
        return True, ""
    for position, token in enumerate(tokens):
        if token in REDIRECT_TOKENS or token.startswith((">", "2>", "&>")):
            target = _redirection_target(tokens, position)
            if target is not None:
                return False, f"`{token}` redirects output into {target}"
    name = Path(tokens[0]).name
    if name == "git":
        return (True, "") if _git_is_look(tokens) else (False, f"`git {' '.join(tokens[1:3])}` changes state")
    if name not in READ_ONLY:
        return False, f"`{name}` is not on the read-only list"
    if name in ACT_IF_ANY_ARG:
        flags = ACT_IF_ANY_ARG[name]
        if "*" in flags and name == "make":
            if "-n" in tokens or "--dry-run" in tokens or "--version" in tokens:
                return True, ""
            return False, "`make <target>` runs a recipe"
        if "*" in flags:
            return False, f"`{name}` runs whatever it is given"
        for token in tokens[1:]:
            if token in flags:
                return False, f"`{name} {token}` runs code"
    if name in SCRIPT_RUNNERS:
        args = [token for token in tokens[1:] if not token.startswith("-")]
        if args:
            return False, f"`{name} {args[0]}` runs a script"
        if not any(token in RUNNER_LOOK_FLAGS for token in tokens[1:]):
            return False, f"`{name}` with no script is an interpreter session"
    if name in {"sed", "awk", "gawk", "perl"} and _ledger is not None:
        if any(_ledger._is_inplace_flag(name, token) for token in tokens[1:]):
            return False, f"`{name}` in place rewrites a file"
    if name == "tee":
        return False, "`tee` writes a file"
    return True, ""


def classify(command: str) -> tuple[str, str]:
    """("look", "") when every segment only reads; ("act", why) otherwise."""
    if not isinstance(command, str) or not command.strip():
        return "look", ""
    segments = _segments(command)
    if not segments:
        return "act", "the command could not be parsed into segments"
    for argv in segments:
        ok, why = _segment_is_look(argv)
        if not ok:
            return "act", why
    return "look", ""


def redirect_targets(command: str, root: Path | None = None) -> list[str]:
    """Absolute paths of EXISTING files this command would write through
    `>`, `>>` or `tee`. Empty when the command creates only new files."""
    targets: list[str] = []
    base = Path(root) if root else Path.cwd()
    for argv in _segments(command):
        tokens = _unwrap(argv)
        candidates: list[str] = []
        for index, token in enumerate(tokens):
            if token in REDIRECT_TOKENS or token.startswith((">", "2>", "&>")):
                target = _redirection_target(tokens, index)
                if target is not None:
                    candidates.append(target)
        if tokens and Path(tokens[0]).name == "tee":
            candidates.extend(token for token in tokens[1:] if not token.startswith("-"))
        for raw in candidates:
            if not raw:
                continue
            path = Path(raw)
            if not path.is_absolute():
                path = base / raw
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if resolved.is_file() and str(resolved) not in targets:
                targets.append(str(resolved))
    return targets


if __name__ == "__main__":
    import sys

    for line in sys.stdin:
        kind, why = classify(line.rstrip("\n"))
        print(kind, why, "|", line.rstrip("\n"))
