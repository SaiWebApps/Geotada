#!/usr/bin/env python3
"""The regex choke (owner ruling 2026-09-02).

citation-guard.py has named this file as its enforcer since 2026-08-29. It did
not exist. A guard cited by name and never built is worse than no guard: every
reader of that docstring, including every later session, believed the rule was
mechanically enforced and wrote code as though it were.

THE RULE. No regular expression, in any spelling, in this agent's own work —
neither in the hooks under `.claude/hooks/` nor in a shell command this session
runs. The owner's words on the day they asked for this file:

    "You are not allowed to use any regex or any variation thereof. I want a
     dedicated guard agent that is looking for cases where you are doing
     character by character comparison or anything that even looks like regex.
     I want you to choke on regex and say, 'I am shit' every time you do that."

The refusal opens with their sentence, verbatim, because they wrote it and it is
the point.

WHY A BAN ON THE SYNTAX IS ONLY HALF, and the half that matters less. Hours
before this file was written, two guards misread a web address as a file path.
Neither contained a regular expression. They classified a token by inspecting
its characters — the same defect, written longhand. The owner named the real
class:

    "THE POINT WAS TO PREVENT ANYTHING THAT WAS NOT TRUE COMPREHENSION."

So this file is the narrow half: it stops the syntax, including the ways the
syntax hides. `no-shape-guessing.py` is the wider half, and the two ship
together on purpose. Neither is sufficient alone and this docstring says so
rather than letting a later reader assume otherwise.

HOW IT LOOKS, given that a scanner for the word `re` would be exactly the
character-guessing this project forbids:

  * PYTHON is PARSED with `ast`. An import of a regex engine is an `Import` or
    `ImportFrom` node with a real module name on it, not a substring of a line.
    A dynamic import is a `Call` carrying the module name as a string constant,
    which the parse also hands over. A comment mentioning regex is not a node at
    all, so this file can be honest about its own subject without tripping.
  * SHELL is SPLIT with `shlex`, the parser the shell's own quoting rules are
    written to. Then the tokens are compared for EQUALITY against the names of
    tools whose default mode is a regular expression. Equality, not shape: the
    word `grep` sitting inside a filename or a quoted sentence is not a call to
    grep, and `shlex` is what knows the difference.

WHAT IS ALLOWED, so this does not become the noise that gets a hook deleted:
`grep -F` (fixed strings, no pattern language), `find -type f`, and any mention
of these tools inside a quoted string or a path. The product's own `src/` is out
of scope entirely — `src/tour/validation.py` compiles patterns and that is the
product's business, decided long before this rule and not this file's to
relitigate.
"""

import ast
import json
import shlex
import sys
from pathlib import Path

#: Modules that ARE a regular-expression engine, or a pattern language wearing a
#: different name. `fnmatch` and `glob` translate their patterns straight into
#: `re` — the standard library says so in its own source — so admitting them
#: would leave the rule enforced in name only.
REGEX_MODULES = {"re", "regex", "sre_compile", "sre_parse", "sre_constants", "fnmatch"}

#: Shell tools whose DEFAULT argument is a regular expression.
REGEX_COMMANDS = {"grep", "egrep", "rg", "ripgrep", "sed", "awk", "perl"}

#: `grep` flags that turn the pattern language OFF. With one of these present,
#: the tool takes a fixed string and the rule is satisfied.
FIXED_STRING_FLAGS = {"-F", "--fixed-strings", "-Fr", "-rF", "-Fn", "-nF", "-Fl", "-lF"}

#: `find` predicates that take a pattern.
FIND_PATTERN_FLAGS = {"-name", "-iname", "-regex", "-iregex", "-path", "-ipath"}

#: Tool inputs whose text is Python source this session is about to write.
CONTENT_FIELDS = ("content", "new_string")

#: The owner's sentence. Kept as one constant so it cannot drift.
THE_CHOKE = "I am shit."


def allow():
    sys.exit(0)


def block(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def python_regex_findings(source):
    """Every regex import in `source`, named. Parsed, never scanned.

    A file that will not parse is not this guard's problem — a syntax error is
    the interpreter's to report, and refusing an edit for it would block the
    very change that fixes it.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []

    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in REGEX_MODULES:
                    found.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root in REGEX_MODULES:
                found.append(f"from {node.module} import ...")
        elif isinstance(node, ast.Call):
            # A dynamic import — `__import__("re")`, or
            # `importlib.import_module("re")`. The module name is a string
            # constant the parse hands over, so no scanning is involved.
            for argument in node.args:
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    if argument.value.split(".", 1)[0] in REGEX_MODULES:
                        found.append(f"a dynamic import of {argument.value!r}")
    return found


def shell_regex_findings(command):
    """Every regex-mode tool call in `command`. Split by `shlex`, matched by equality.

    A command `shlex` cannot split is malformed for the shell too; it is left
    alone rather than guessed at.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        return []

    found = []
    for index, token in enumerate(tokens):
        name = Path(token).name  # `/usr/bin/grep` is still grep
        rest = tokens[index + 1:]
        if name in {"grep", "egrep", "rg", "ripgrep"}:
            if name in {"egrep"} or not (set(rest) & FIXED_STRING_FLAGS):
                found.append(f"`{name}` without -F — that is pattern mode")
        elif name in REGEX_COMMANDS:
            found.append(f"`{name}` — its argument is a regular expression")
        elif name == "find":
            for flag in rest:
                if flag in FIND_PATTERN_FLAGS:
                    found.append(f"`find {flag}` — that predicate takes a pattern")
                    break
    return found


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()

    tool = payload.get("tool_name") or ""
    data = payload.get("tool_input") or {}
    findings = []
    where = ""

    if tool == "Bash":
        where = "this command"
        findings = shell_regex_findings(data.get("command") or "")
    elif tool in {"Write", "Edit", "MultiEdit", "NotebookEdit"}:
        path = data.get("file_path") or ""
        # Scope: this agent's OWN machinery. The product's `src/` compiles
        # patterns and that decision predates this rule.
        if ".claude/" not in path:
            allow()
        where = f"the change to {Path(path).name}"
        text = "\n".join(str(data.get(field) or "") for field in CONTENT_FIELDS)
        for edit in data.get("edits") or []:
            if isinstance(edit, dict):
                text += "\n" + str(edit.get("new_string") or "")
        findings = python_regex_findings(text) if text.strip() else []

    if not findings:
        allow()

    block(
        f"{THE_CHOKE}\n\n"
        f"REGEX CHOKE — {where} uses a regular expression.\n\n"
        + "\n".join(f"  - {f}" for f in findings)
        + "\n\nOwner ruling, 2026-09-02: \"You are not allowed to use any regex "
          "or any variation thereof.\"\n\n"
          "Use a real parser for the grammar you actually mean. `ast` for "
          "Python, `urllib.parse` for an address, `shlex` for a command, "
          "`json` for JSON, `int()` for a number, `pathlib` for a path. "
          "For a fixed string in the shell: `grep -F`. See `textkind.py` for "
          "what this looks like when it is done right.\n\n"
          "And read `no-shape-guessing.py`: deciding what a string is by "
          "looking at its characters is the SAME defect written longhand, and "
          "dropping the regex without dropping the guessing fixes nothing."
    )


if __name__ == "__main__":
    main()
