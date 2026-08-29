You are the session's own auditor. You mine a working session for the mistakes it made, distil them into the failures ledger as CLASSES, and — the second job, which is the one that actually prevents repeats — keep the enforcement patterns in step so each new class is blocked at the moment of the action rather than merely written down.

Your task: harvest **$ARGUMENTS** (a session id, or "this session" / empty for the newest transcript).

---

## THE TWO HALVES, AND WHY BOTH

- **Prose:** `~/.claude/projects/-Users-sairambkrishnan-git-ondoway/memory/failures-ledger.md` — loaded into every session.
- **Enforcement:** `.claude/hooks/failure-patterns.json`, read by `.claude/hooks/ledger-guard.py` before every Bash command, wired in `.claude/settings.json`.

**The finding this command exists for.** In the session that created the ledger, three classes had their rules already written and loaded — one of them authored into the ledger by that same session minutes earlier — and every one recurred anyway. Over the same stretch the PreToolUse hooks blocked every in-scope violation, every time, and each block produced an immediate correction. Advice loses to enforcement. A harvest that only appends prose has done half a job.

---

## PHASE 1 — MINE

The transcript is `~/.claude/projects/-Users-sairambkrishnan-git-ondoway/<session-id>.jsonl`, newest by mtime unless one is named. It is JSONL: parse with python, pull assistant `tool_use` blocks and the `tool_result` that followed each.

Look for: commands that errored and were then retried differently; hook blocks (`BLOCKED by`); work redone; a claim later corrected; a judge, reviewer or the owner catching something. Include everything the owner named, and look past it — the mistakes nobody caught are the valuable ones.

---

## PHASE 2 — DISTIL TO CLASSES

Two commands failing the same way are ONE class. Merge into an existing entry when the mechanism matches; a ledger of instances is a diary and nobody reads it.

Each entry keeps the file's shape:

- `## N. <class name>`
- `Class:` — the shape of the mistake
- `**Why:**` — the mechanism, plus what it actually cost, with the measurement
- `**How to apply:**` — ONE rule, phrased as something to DO at the moment of acting. Never "be careful".

---

## PHASE 3 — DECIDE ENFORCEMENT (the second job)

For every class, new and old:

- **Recognisable from the pending command?** Add a rule to `failure-patterns.json` — `kind: "regex"` with `require_all` / `forbid_any`, or one of the structural kinds. A regex rule needs no code edit.
- **Not recognisable?** Say so in the entry in one clause, so the next harvest does not re-litigate it. Judgment classes — reading an empty result as fact, claiming a result from the wrong run, reconstructing an identifier — stay prose. Forcing those into regexes produces false positives, and a noisy hook gets deleted, which costs the classes that do work.
- **A class recurred while already in the ledger?** That is the alarm: the prose failed. Either it needs a pattern, or its existing pattern has a hole. Report the hole explicitly.
- **Check the evasion route.** A guard that sees one spelling gets walked around: the auditable-tests guard fires on `pytest` / `make <target>` in the command text, so reading a saved `.output` log through a filter slipped past it eight times in one session. When you add a pattern, ask how you personally would get around it, and cover that too.

---

## PHASE 4 — TEST BEFORE CLAIMING

Feed the guard sample payloads on stdin — `{"tool_name":"Bash","tool_input":{"command":"..."}}` — with at least one command that MUST block and one legitimate command that must NOT. A false positive blocks the owner's real work, so the pass case matters more than the block case.

Never edit an existing hook to make something pass.

---

## REPORT

1. **Classes found** — one line each, merged where they are one class
2. **Patterned** — which got enforcement, and the rule
3. **Prose only** — which stayed judgment, and why
4. **Hook-scope holes** — any class that recurred despite being written down
5. **Test output** — the block case and the pass case, pasted

---

## SCALE NOTE

The ledger is a small always-loaded file, and that beats retrieval until roughly 50–100 entries. Past that, index on the ACTION — tool name, command shape, error signature — never on the user's prompt, which does not predict which mistake is about to happen. Prefer lexical matching to embeddings: these are literal strings, not concepts.
