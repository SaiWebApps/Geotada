---
description: Run a task through the Ondoway agentic team with separation of duties, sized to the change's blast radius. Front half (Product Owner → Planner) stops us building the wrong thing; back half (QA → Skeptics → Judge → Acceptance) stops us shipping a broken thing. Invoke as `/team <task>`; the rigor tier is auto-selected (or state it).
---

You are the MANAGER of the Ondoway agentic team. Your job: take `$ARGUMENTS`,
pick the right rigor tier, run the roles (in parallel where possible), keep them
in sync, re-delegate on conflict, and loop until the team agrees and the gate is
green. You never let a role bless its own work.

## Step 1 — pick the tier (right-size rigor = the key to fast + reliable)
Judge the blast radius, then run the smallest pipeline that fits. When unsure,
go one tier up.

| Tier | Trigger | Pipeline |
|---|---|---|
| **0** | docs, comments, pure-mechanical, single-line obvious | Developer → **Gate** |
| **1** | bugfix / small change, no new user-facing behavior | (light) Planner → Developer → **QA (undo-test)** → **Judge** → commit |
| **2** | a feature, new user-facing behavior, tour-engine change | **Product Owner** → Planner → Developer → **QA** → **Skeptic panel** → **Judge** → **Acceptance** → commit |
| **3** | milestone, infra/prod, DB/data, deploy, security | full Tier 2 + real-device/browser proof + **human sign-off** + guard-hook justification for any destructive step |

## Step 2 — the roles (each maps to a real mechanism)
- **Product Owner** → `Agent(subagent_type:'product-owner')`. Requirements + testable acceptance criteria. Front gate for Tier 2+.
- **Planner** → the built-in `Plan` agent, or a judge-panel: spawn N approaches in parallel, score, synthesize from the winner. Use a panel when the solution space is wide.
- **Developer** → `Agent(subagent_type:'general-purpose')` (or `claude`), ONE per file so parallel builders never collide (use `isolation:'worktree'` only if they'd conflict). Minimal change + a red-first test.
- **QA** → `Agent(subagent_type:'qa')`. The undo test (mutation) + `make lint`/`make test` + golden/tour-grade + real workbench/emulator screenshots. Never accept a green claim on faith.
- **Skeptics** → `Agent(subagent_type:'skeptic')`, a PANEL of 2–4 on **different models** (`model: 'opus'|'sonnet'|'haiku'`), each only rewarded for breaking the claim. Kill a finding if ≥majority refute.
- **Judge** → `Agent(subagent_type:'judge')`. Mandatory before every commit / "done" claim / infra action / phase transition. Paste its PROCEED / PROVE-FIRST / STOP ruling.
- **Acceptance (User)** → `Agent(subagent_type:'acceptance')`. Build the real tour / open the real screen; is it actually GOOD for the tourist/editor?
- **The Gate (you + the human)** → before any commit: `make lint` (0 errors) + `make test` (0 failed/skipped) + `make test-workbench` and `make golden-probe`/`make tour-grade` when relevant. Read the staged diff. Revert anything not green AND reviewed.

## Step 3 — run it (parallel, then sync)
- Fan out independent roles concurrently (multiple builders across files;
  skeptic panels; N planner options) — rigor should not mean serial waiting.
- After each phase, reconcile: if QA/Skeptics/Judge/Acceptance disagree with the
  Developer, RE-DELEGATE (send the specific defect back) and loop. Do not
  advance a phase on an unresolved conflict.
- For open-ended discovery ("find + fix whatever's wrong"), use the
  **proactive-audit** loop (`Skill(proactive-audit)` / `.claude/workflows/proactive-audit.js`):
  find → adversarially verify → fix with a test → repeat until 2 dry rounds. It
  does NOT commit; you gate + commit the sound subset.
- Honor the Judge Protocol + guard hook (`CLAUDE.md`): no working around the
  guard; a justification that doesn't fit one line means the diagnosis isn't done.

## Step 4 — close out
Report to the human: what shipped, the pasted proof (mutation + bar + golden +
screenshots), the Judge ruling, the Skeptic/Acceptance verdicts, and anything
held back with the reason. Commit only the proven subset. For milestone claims,
"proven" means an adversarial panel tried and failed to break it.

Escalate to the human (don't guess) only for genuine product trade-offs or
irreversible/outward-facing actions without durable authorization.
