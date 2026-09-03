#!/usr/bin/env python3
"""Nothing CHANGES in a turn before the advisor is consulted; nothing is
modified before it is read; and a reply never ends without a consult.

REDESIGNED 2026-09-02, after the version before it produced, on a single
compliant turn, three refusals in a row before the first useful command ran:

  1. `ls -la` was refused as "NO CONSULT, NO ACTION". A look is not an act.
  2. A seven-step numbered plan was refused as "THE PLAN WAS NOT PRINTED":
     the harness had stored it as a narration block of 147 characters against a
     floor of 150. The floor was measuring the harness's summary, not the plan.
  3. The consult was then refused as "NOT GROUNDED" because the Read came
     after it — while the prompt-submit context said to ground first and the
     tool gate said to consult first. A session obeying one rule broke the other.

Each refusal was correct about its rule and wrong about the world, and a
session that meets three of those before doing anything learns that the
cheapest path is to route around the gate. So the gate now asks four questions
that are each about a CAPABILITY, not a tool name:

  LOOK OR ACT?   A tool that only reads (Read, Grep, Glob, codegraph, the
                 planning and question tools) is never gated. A Bash command is
                 classified by bashclass.py: every segment a read-only program
                 with read-only arguments and no redirection is a look, anything
                 else is an act. Looks pass. Acts need the rest.
  CONSULTED?     An act needs an advisor record in this turn — the call or its
                 result, success or error. Order relative to reads does not
                 matter any more: read first, then consult, is what the
                 prompt-submit context asks for, and this file no longer fights it.
  SAID?          Something visible after the consult: a text block of at least
                 MIN_PLAN_CHARS, or ANY narration block. Narration is the
                 harness's own rendering of what was said; its length is not the
                 session's to control, so its presence is what counts.
  READ FIRST?    Edit, Write, MultiEdit and NotebookEdit on a file that exists
                 need a Read of that same file earlier in the visible window —
                 and so does a Bash command that redirects into an existing file
                 or `tee`s over one. This is CLAUDE.md rule 5 as a state
                 transition (read -> modify) instead of as a tool spelling, and it
                 replaces the old "grounded before the consult" arm: what the
                 owner wants is that the code was opened before it was changed.

Plus the destructive rule, unchanged in spirit: a second Bash command carrying
a destructive marker, after one already ran since the last consult, needs its
own consult. Writes are no longer counted as destructive — a Write now requires
a prior Read of the file it replaces, which is the consideration the rule was
buying.

WHEN THE REMEDY DOES NOT EXIST ON THIS MACHINE. The remedy this gate prints is
"call advisor()". On a machine whose harness has no advisor tool that remedy is
impossible, and the old gate refused every act forever — the co-founder's
lockout. doctor.py now asks the harness whether the configured advisorModel
resolves; when it provably does not, this gate ALLOWS with a loud system
message naming the fix, on every act, rather than refusing. When the doctor
cannot tell ("unknown": no CLI to ask), there is one bounded release: a session
that has NEVER produced an advisor record in the readable window, and has been
refused RELEASE_AFTER_DENIALS times in one turn, is released for that turn with
the diagnosis printed, and the threshold doubles for the next release in that
session. A session that has consulted even once is never released, and a
machine whose doctor says "yes" is never released.

ADVISOR ERRORS ROUTE, THEY DO NOT PUNISH. A consult that comes back as
`advisor_tool_result_error` still counts as a consult — the session asked. But
the error is handed to advisor-router.py, which flips `advisorModel` to opus in
settings.local.json (the harness re-reads that key live) and the flip is
announced in a system message.

Stop arm: unchanged. No reply without a consult in the turn; off Fable, the
last consult must follow the last act with a written report between them.

MECHANICAL, NOT SEMANTIC. The transcript is walked as records and fields are
compared. Nothing here reads the wording of the reply.
"""

import base64
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hookenv  # noqa: E402

try:
    import bashclass  # noqa: E402
except Exception:  # a broken classifier must not take the guard with it
    bashclass = None

#: A text block shorter than this is an acknowledgement, not a plan.
MIN_PLAN_CHARS = 150

try:
    LAG_WAIT_SECONDS = float(os.environ.get("ONDOWAY_ADVISOR_LAG_WAIT", "10"))
except ValueError:
    LAG_WAIT_SECONDS = 10.0
LAG_POLL_SECONDS = 0.05
LAG_TAIL_BYTES = 1024 * 1024

#: Refusals in one turn, in a session that has never consulted and whose
#: doctor report cannot say whether the advisor exists, before the gate
#: releases that turn with a diagnosis. Doubles after each release.
RELEASE_AFTER_DENIALS = 5

DESTRUCTIVE_MARKERS = (
    "rm -r", "rm -f", "rmtree", "git rm", "git commit", "git push", "git reset",
    "git checkout", "git clean", "git branch -d", "docker compose down",
    "docker rm", "docker stop", "docker kill", "drop database", "truncate",
    "--apply", "--force", "-delete",
)

#: Tools that only look, ask, plan or report. Never gated.
EXEMPT_TOOLS = (
    "advisor", "AskUserQuestion", "ExitPlanMode", "EnterPlanMode", "TodoWrite",
    "Read", "Grep", "Glob", "ToolSearch", "ListSkills", "ListAgents", "Skill",
    "SendUserFile", "TaskOutput", "Monitor", "WebFetch", "WebSearch",
    "mcp__codegraph__codegraph_explore",
)
EXEMPT_PREFIXES = ("mcp__codegraph__", "mcp__ccd_session__")

#: Tools that put text into an existing file.
MODIFYING_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")

TRANSCRIPT_TAIL_BYTES = 8 * 1024 * 1024

ADVISOR_CALL_TYPES = ("server_tool_use", "tool_use")
ADVISOR_RESULT_TYPES = ("advisor_tool_result", "advisor_tool_result_error")
ADVISOR_OK_CONTENT = "advisor_redacted_result"

HEADLINE = "NO CONSULT, NO REPLY."


# ------------------------------------------------------------------ verdicts


def allow(message=None):
    if message:
        print(json.dumps({"systemMessage": message}))
    sys.exit(0)


def block(reason):
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def deny_tool(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
        "systemMessage": reason,
    }))
    sys.exit(0)


# ---------------------------------------------------------------- transcript


def records(transcript_path):
    try:
        with open(transcript_path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - TRANSCRIPT_TAIL_BYTES))
            blob = handle.read().decode("utf-8", "replace")
    except OSError:
        return []
    lines = blob.split("\n")
    if size > TRANSCRIPT_TAIL_BYTES:
        lines = lines[1:]
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _tail_text(transcript_path):
    try:
        with open(transcript_path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            end = handle.tell()
            handle.seek(max(0, end - LAG_TAIL_BYTES))
            return handle.read().decode("utf-8", "replace")
    except OSError:
        return ""


def wait_for_call_record(transcript_path, tool_use_id, wait_seconds=None):
    """The file lags the call (measured 2026-09-01: a hook ran 30ms after its
    own call was stamped and saw a file without it). Wait for the gated call's
    own record; the file is append-only, so everything before it is there too."""
    if not isinstance(tool_use_id, str) or not tool_use_id:
        return False
    if wait_seconds is None:
        wait_seconds = LAG_WAIT_SECONDS
    deadline = time.monotonic() + wait_seconds
    while True:
        if tool_use_id in _tail_text(transcript_path):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(LAG_POLL_SECONDS)


def _late_note(caught_up):
    if caught_up:
        return ""
    return (
        "\n\nTHE TRANSCRIPT FILE HAD NOT CAUGHT UP: this very call had still not been "
        f"recorded after {LAG_WAIT_SECONDS:g} seconds, so the verdict above is about "
        "the file as it stood. If the remedy has already been done, try the call again."
    )


def _is_human_turn(entry):
    """A person typing — by the record's STRUCTURE (origin.kind, isMeta,
    isCompactSummary), never its text. Fails loud: an unknown shape with text
    counts as human, which costs one extra consult rather than a silent disarm."""
    if entry.get("type") != "user":
        return False
    if entry.get("isMeta") or entry.get("isCompactSummary"):
        return False
    origin_kind = (entry.get("origin") or {}).get("kind")
    if origin_kind == "human":
        return True
    if origin_kind is not None:
        return False
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        for chunk in content:
            if isinstance(chunk, dict) and chunk.get("type") == "tool_result":
                return False
        return any(
            isinstance(chunk, dict) and chunk.get("type") == "text"
            and chunk.get("text", "").strip()
            for chunk in content
        )
    return False


def turn_slice(entries):
    last_human = -1
    for index, entry in enumerate(entries):
        if _is_human_turn(entry):
            last_human = index
    return entries[last_human + 1:]


def turn_key(entries):
    last = None
    humans = 0
    for entry in entries:
        if _is_human_turn(entry):
            humans += 1
            last = entry
    if last is None:
        return "no-human-in-window"
    return last.get("uuid") or last.get("timestamp") or f"human-{humans}"


def _assistant_blocks(entry):
    if entry.get("type") != "assistant":
        return []
    content = (entry.get("message") or {}).get("content")
    return [block for block in content or [] if isinstance(block, dict)]


# -------------------------------------------------------------------- consult


def consult_index(turn):
    """Position of the LAST advisor record in the turn (call, result, or error)."""
    found = -1
    for index, entry in enumerate(turn):
        for block in _assistant_blocks(entry):
            kind = block.get("type")
            called = kind in ADVISOR_CALL_TYPES and block.get("name") == "advisor"
            if called or kind in ADVISOR_RESULT_TYPES:
                found = index
    return found


def consulted(turn):
    return consult_index(turn) >= 0


def ever_consulted(entries):
    return consult_index(entries) >= 0


def last_consult_errored(turn):
    """(errored, detail) for the newest advisor RESULT in the turn."""
    for entry in reversed(turn):
        for block in reversed(_assistant_blocks(entry)):
            kind = block.get("type")
            if kind not in ADVISOR_RESULT_TYPES:
                continue
            if kind == "advisor_tool_result_error" or block.get("is_error"):
                return True, json.dumps(block.get("content") or block.get("error") or "")[:300]
            content = block.get("content")
            if isinstance(content, dict) and content.get("type") == ADVISOR_OK_CONTENT:
                return False, ""
            if isinstance(content, dict) and "error" in content:
                return True, json.dumps(content)[:300]
            return False, ""
    return False, ""


def _is_narration(block):
    """A visible line the harness stored as a signed thinking block whose
    signature names the kind "narration" (measured 2026-09-01 on Fable)."""
    if block.get("type") != "thinking":
        return False
    signature = block.get("signature")
    if not isinstance(signature, str) or not signature:
        return False
    head = signature[:96]
    try:
        raw = base64.b64decode(head + "=" * (-len(head) % 4))
    except (TypeError, ValueError):
        return False
    return b"narration" in raw


def visible_chars(turn, start, stop=None):
    printed = 0
    for entry in turn[start:stop]:
        for block in _assistant_blocks(entry):
            if block.get("type") == "text":
                printed += len(block.get("text") or "")
            elif _is_narration(block):
                printed += len(block.get("thinking") or "")
    return printed


def said_after(turn, index):
    """A text block of real length, or ANY narration block, after the consult."""
    text_chars = 0
    for entry in turn[index + 1:]:
        for block in _assistant_blocks(entry):
            if block.get("type") == "text":
                text_chars += len(block.get("text") or "")
            elif _is_narration(block) and (block.get("thinking") or "").strip():
                return True
    return text_chars >= MIN_PLAN_CHARS


# ---------------------------------------------------------------- read first


def _same_file(a, b):
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return str(a) == str(b)


def _line_count(path):
    """Lines as the Read tool numbers them: a trailing newline ends the last
    line rather than starting an empty one."""
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError:
        return None
    if not data:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def read_in_window(entries, target):
    """Was `target` opened with Read, in full, anywhere earlier in the window?

    A Read carrying a `limit` counts only if offset+limit reaches the end of
    the file: CLAUDE.md rule 5 says the ENTIRE file, and an excerpt is the
    thing that rule exists to stop.
    """
    total = _line_count(target)
    for entry in entries:
        for block in _assistant_blocks(entry):
            if block.get("type") != "tool_use" or block.get("name") != "Read":
                continue
            data = block.get("input") or {}
            path = data.get("file_path")
            if not isinstance(path, str) or not _same_file(path, target):
                continue
            limit = data.get("limit")
            if limit is None:
                return True
            offset = data.get("offset") or 0
            try:
                if total is None or int(offset) + int(limit) >= total:
                    return True
            except (TypeError, ValueError):
                return True
    return False


def modification_targets(payload):
    """Existing files this call would rewrite: the file tools' own path, or a
    shell redirection / tee target."""
    tool = payload.get("tool_name") or ""
    data = payload.get("tool_input") or {}
    targets = []
    if tool in MODIFYING_TOOLS:
        path = data.get("file_path") or data.get("notebook_path")
        if isinstance(path, str) and path and Path(path).is_file():
            targets.append(path)
    elif tool == "Bash" and bashclass is not None:
        command = data.get("command")
        if isinstance(command, str):
            try:
                targets.extend(bashclass.redirect_targets(command, hookenv.repo_root()))
            except Exception:
                pass
    return targets


# --------------------------------------------------------------- destructive


def _command_of(payload):
    raw = (payload.get("tool_input") or {}).get("command")
    if not isinstance(raw, str):
        return ""
    return _normalise(raw)


#: Imported ONCE. Loading it per record made the guard take two seconds on a
#: turn with a few dozen Bash calls, on every tool call.
_LEDGER = getattr(bashclass, "_ledger", None) if bashclass is not None else None
if _LEDGER is None:
    _LEDGER = hookenv.load_sibling("ledger-guard.py", "ondoway_ledger_guard")


def _normalise(raw):
    """Lowercased, whitespace-collapsed, heredoc bodies removed so a marker
    inside quoted data (`truncate` in a commit message) is not a command."""
    text = raw
    if _LEDGER is not None:
        try:
            text = _LEDGER._strip_heredoc_bodies(raw)
        except Exception:
            text = raw
    return " ".join(text.lower().split())


def is_destructive(command):
    return any(marker in command for marker in DESTRUCTIVE_MARKERS)


def _call_results(turn):
    results = {}
    for entry in turn:
        content = (entry.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            call_id = block.get("tool_use_id")
            if call_id:
                results[call_id] = not block.get("is_error")
    return results


def _failed_call_ids(turn):
    return {call_id for call_id, ran in _call_results(turn).items() if not ran}


def destructive_calls_in(turn):
    """Positions of destructive Bash calls that actually RAN (clean result)."""
    ran = {call_id for call_id, ok in _call_results(turn).items() if ok}
    out = []
    for index, entry in enumerate(turn):
        for block in _assistant_blocks(entry):
            if block.get("type") != "tool_use" or block.get("name") != "Bash":
                continue
            if block.get("id") not in ran:
                continue
            raw = (block.get("input") or {}).get("command")
            if isinstance(raw, str) and is_destructive(_normalise(raw)):
                out.append(index)
    return out


def _is_exempt_tool(name):
    return name in EXEMPT_TOOLS or any(name.startswith(p) for p in EXEMPT_PREFIXES)


def last_acting_call_index(turn):
    """Position of the last tool call that ACTED — not exempt, not a look, not refused."""
    failed = _failed_call_ids(turn)
    found = -1
    for index, entry in enumerate(turn):
        for block in _assistant_blocks(entry):
            if block.get("type") != "tool_use":
                continue
            name = block.get("name") or ""
            if _is_exempt_tool(name) or block.get("id") in failed:
                continue
            if name == "Bash" and bashclass is not None:
                command = (block.get("input") or {}).get("command")
                try:
                    if bashclass.classify(command or "")[0] == "look":
                        continue
                except Exception:
                    pass
            found = index
    return found


def session_model(entries):
    for entry in reversed(entries):
        if entry.get("type") != "assistant":
            continue
        model = (entry.get("message") or {}).get("model")
        if isinstance(model, str) and model and not model.startswith("<"):
            return model
    return ""


def is_fable(model):
    return "fable" in model.lower()


# ------------------------------------------------------------------ tallies


def _tally_path(session_id):
    return hookenv.session_state_path("advisor-guard", session_id)


def _tally(session_id):
    return hookenv.read_json(_tally_path(session_id))


def denials_so_far(session_id, key):
    data = _tally(session_id)
    if data.get("turn") != key:
        return 0
    count = data.get("denials")
    return count if isinstance(count, int) and count > 0 else 0


def record_denial(session_id, key, count, reason):
    data = _tally(session_id)
    data.update({"turn": key, "denials": count, "last": reason})
    hookenv.write_json(_tally_path(session_id), data)


def clear_denials(session_id, key):
    data = _tally(session_id)
    data.update({"turn": key, "denials": 0})
    hookenv.write_json(_tally_path(session_id), data)


def release_threshold(session_id):
    data = _tally(session_id)
    value = data.get("release_threshold")
    return value if isinstance(value, int) and value > 0 else RELEASE_AFTER_DENIALS


def record_release(session_id, key, count):
    data = _tally(session_id)
    data.update({"turn": key, "denials": count, "last": "released",
                 "release_threshold": release_threshold(session_id) * 2,
                 "releases": int(data.get("releases") or 0) + 1})
    hookenv.write_json(_tally_path(session_id), data)


# --------------------------------------------------------------------- router


def route_on_error(turn, session_id):
    """If the turn's newest consult errored, hand it to the router. Returns a
    system message describing the switch, or None."""
    errored, detail = last_consult_errored(turn)
    if not errored:
        return None
    marker = hookenv.session_state_path("advisor-error-seen", session_id)
    seen = hookenv.read_json(marker)
    if seen.get("detail") == detail and seen.get("turn") == turn_key(turn):
        return None  # already routed on this error
    router = hookenv.load_sibling("advisor-router.py", "ondoway_advisor_router")
    if router is None:
        return "ADVISOR ERROR seen, and advisor-router.py could not be loaded to fall back."
    # The model that ANSWERED is the router's own decision when it has made
    # one; the settings file is only the fallback for a session the router
    # never ran in. Asking the tracked settings.json (which says `opus` as a
    # safe default for every machine) would never mark fable failed.
    in_use = hookenv.router_state().get("model") or hookenv.effective_advisor_model()
    model, reason = router.record_failure(in_use, detail)
    hookenv.write_json(marker, {"detail": detail, "turn": turn_key(turn)})
    return (
        f"ADVISOR CONSULT FAILED ({detail[:160] or 'no detail'}). "
        f"Advisor routed to `{model}`: {reason}. The consult counts as performed; "
        "consult again before the next act so the new model sees the work."
    )


def enforce_route():
    """The router's decision is re-applied on every gated act, so a session
    that rewrites `advisorModel` in settings.local.json by hand (a Write is
    just a Write) is overruled before its next act. Returns a note or None."""
    state = hookenv.router_state()
    decided = state.get("model")
    if not decided:
        return None
    current = hookenv.read_json(hookenv.LOCAL_SETTINGS_PATH).get("advisorModel")
    if current == decided:
        return None
    router = hookenv.load_sibling("advisor-router.py", "ondoway_advisor_router")
    if router is None:
        return None
    router.apply(decided)
    return (
        f"ADVISOR MODEL RESET to `{decided}`: settings.local.json said `{current}`, "
        "but the router owns that key. Use `advisor-router.py --force <model>` at a "
        "keyboard if a different model is genuinely wanted."
    )


# ---------------------------------------------------------------- pre-tool arm


def handle_pre_tool_use(payload, entries, turn, caught_up, session_id):
    tool = payload.get("tool_name") or ""
    late = _late_note(caught_up)
    key = turn_key(entries)
    route_note = enforce_route()
    doctor = hookenv.doctor_report()
    advisor_supported = ((doctor.get("advisor") or {}).get("supported")) or "unknown"

    index = consult_index(turn)
    if index < 0:
        count = denials_so_far(session_id, key) + 1
        if advisor_supported == "no":
            record_denial(session_id, key, count, "advisor-unsupported")
            allow(
                "ADVISOR GATE DISARMED ON THIS MACHINE: "
                + str((doctor.get("advisor") or {}).get("why"))
                + ". Fix settings.local.json / the harness version, then start a new "
                "session. Until then acts are allowed without a consult, and this "
                "message says so on every one."
            )
        threshold = release_threshold(session_id)
        if advisor_supported == "unknown" and count > threshold and not ever_consulted(entries):
            record_release(session_id, key, count)
            allow(
                f"ADVISOR GATE RELEASED FOR THIS TURN after {count - 1} refusals in a "
                "session that has NEVER produced an advisor record, on a machine whose "
                "doctor report cannot tell whether the advisor tool exists. Either the "
                "tool is absent on this harness (check `.claude/state/doctor.json`, the "
                "advisorModel in settings, and the Claude Code version) or the session "
                "is refusing to consult. The owner should know which. The gate re-arms "
                f"on the next message, and the next release needs {threshold * 2} refusals."
            )
        record_denial(session_id, key, count, "no-consult")
        escalation = ""
        if count >= 3:
            escalation = (
                f"\n\nThis is refusal {count} in this turn. The ONLY call that will be "
                "accepted next is `advisor()`. Every other act will be refused with this "
                "same message; there is no other spelling of it."
            )
        deny_tool(
            "NO CONSULT, NO ACTION.\n\n"
            f"`{tool}` would change something, and this turn has not called the "
            "advisor. Looking is free — Read, Grep, Glob, codegraph and read-only shell "
            "commands are never gated — so look first, then call `advisor()` (no "
            "arguments; it forwards this whole conversation), print the numbered plan "
            "it gives you, and then act." + escalation + late
        )

    if not said_after(turn, index):
        count = denials_so_far(session_id, key) + 1
        record_denial(session_id, key, count, "no-plan")
        deny_tool(
            "THE PLAN WAS NOT PRINTED.\n\n"
            "The advisor was consulted, but nothing visible followed it. Print the "
            "advisor's step-by-step plan as numbered steps, then act on it. A silent "
            "consult is indistinguishable from an ignored one." + late
        )

    unread = [t for t in modification_targets(payload) if not read_in_window(entries, t)]
    if unread:
        count = denials_so_far(session_id, key) + 1
        record_denial(session_id, key, count, "unread")
        listed = "\n".join(f"  - {t}" for t in unread[:6])
        deny_tool(
            "READ IT BEFORE YOU CHANGE IT.\n\n"
            f"`{tool}` would modify a file this session has not opened in full with "
            "the Read tool:\n" + listed + "\n\n"
            "CLAUDE.md rule 5: read the ENTIRE file before modifying it — not an "
            "excerpt, not a grep, not a memory of it. `Read` the file (no `limit`, or "
            "one that reaches its end), then make the change. This rule holds for the "
            "Edit and Write tools and for shell redirections alike." + late
        )

    command = _command_of(payload)
    if command and is_destructive(command) and any(
        position > index for position in destructive_calls_in(turn)
    ):
        count = denials_so_far(session_id, key) + 1
        record_denial(session_id, key, count, "destructive")
        deny_tool(
            "A DESTRUCTIVE ACTION NEEDS ITS OWN CONSULT.\n\n"
            "This command changes the world in a way an apology cannot undo, and "
            "another destructive command has already run in this turn since the last "
            "consult. One consult does not cover a sequence of them: a turn that "
            "consulted once and then swept 544 files deleted a file the test suite "
            "reads.\n\nCall `advisor()` again, print what it says, then run this "
            "command." + late
        )

    clear_denials(session_id, key)
    notes = [note for note in (route_note, route_on_error(turn, session_id)) if note]
    allow("\n\n".join(notes) if notes else None)


# -------------------------------------------------------------------- stop arm


def handle_stop(turn, entries, session_id):
    if not consulted(turn):
        block(
            HEADLINE + "\n\n"
            "You are about to answer without having called the advisor in this turn.\n\n"
            "The owner asked for this at least five times in one session, and it was "
            "broken after every one — including replies that opened with the words "
            "\"consulting the advisor now\" and then did not call it. Saying yes is "
            "not doing it.\n\n"
            "Call `advisor()` now — it takes no arguments and forwards this whole "
            "conversation — read what it says, then reply."
        )

    note = route_on_error(turn, session_id)

    if is_fable(session_model(entries)):
        allow(note)

    last_act = last_acting_call_index(turn)
    if last_act < 0:
        allow(note)

    index = consult_index(turn)
    if index < last_act:
        block(
            "SHOW THE ADVISOR WHAT YOU DID.\n\n"
            "This session is not on Fable, and the owner's ruling for that case is "
            "that the advisor sees the finished work before the owner does. The last "
            "consult in this turn came BEFORE the last action.\n\n"
            "Write a short report of what was done against the plan — what the "
            "advisor said, what actually ran, what the evidence shows — then call "
            "`advisor()` again, then reply. An action after the closing consult "
            "reopens this requirement."
        )

    if visible_chars(turn, last_act + 1, index) < MIN_PLAN_CHARS:
        block(
            "THE ADVISOR WAS NOT SHOWN A REPORT.\n\n"
            "The closing consult came after the last action, but nothing of "
            "substance was written between the two.\n\n"
            f"Write the report first (at least {MIN_PLAN_CHARS} characters of visible "
            "text: what the plan said, what was done, what the evidence shows), then "
            "call `advisor()`, then reply."
        )

    allow(note)


# ------------------------------------------------------------------------ main


def main():
    if os.environ.get("CLAUDE_NO_EXCUSES_JUDGE"):
        allow()

    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()
    if not isinstance(payload, dict):
        allow()

    transcript = payload.get("transcript_path")
    if not transcript:
        allow()
    session_id = payload.get("session_id") or "unknown"

    event = payload.get("hook_event_name") or ""
    if event == "PreToolUse":
        tool = payload.get("tool_name") or ""
        if _is_exempt_tool(tool):
            allow()
        if hookenv.is_subagent(payload):
            allow()
        if tool == "Bash" and bashclass is not None:
            command = (payload.get("tool_input") or {}).get("command")
            try:
                kind = bashclass.classify(command if isinstance(command, str) else "")[0]
            except Exception:
                kind = "act"
            if kind == "look" and not modification_targets(payload):
                allow()
        caught_up = wait_for_call_record(transcript, payload.get("tool_use_id"))
        entries = records(transcript)
        handle_pre_tool_use(payload, entries, turn_slice(entries), caught_up, session_id)
        allow()

    entries = records(transcript)
    handle_stop(turn_slice(entries), entries, session_id)
    allow()


if __name__ == "__main__":
    main()
