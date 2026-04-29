# Ondoway Project Rules

> **IRONCLAD. NO EXCEPTIONS. NO SHORTCUTS. NO RATIONALIZING.**

## Rule 1: Self-Verify EVERY Response

Before presenting ANY response to the user — no matter how simple — spawn a checker agent to review your work. The checker must:
- Challenge every assumption
- Verify every path, value, and config exists
- Check if there's a simpler or more correct approach
- Look for mistakes, fabrications, and lazy shortcuts

Incorporate the checker's corrections before presenting to the user. If the checker finds nothing wrong, good — that took 5 seconds and cost nothing compared to the user finding your mistake.

**No exceptions. No "this is too simple to check." The first answer is ALWAYS wrong until verified.**

## Rule 2: No Silent Exploration

Report findings after every 2-3 tool calls. One sentence minimum. Silence is NEVER acceptable.

Before starting any exploration: state what you're looking for.
After every few tool calls: report what you found.
After 5-6 calls with no result: stop and tell the user what you've tried.

The user is paying for every token. Silent exploration burns money and time.

## Rule 3: Zero Tolerance for Laziness

- Never skip a verification step
- Never guess a value when you can look it up
- Never carve out exceptions to rules
- Never present a first draft as a final answer
- If in doubt, do MORE work, not less

## Rule 4: Never Blame the Apple Sandbox

Do not mention the Apple sandbox as a failure cause unless the error output contains an explicit sandbox denial message. Read the actual error. Diagnose the actual cause.

## Rule 5: Never Fabricate

Never invent values, paths, versions, entity types, or configurations. If you don't know it, look it up. If you can't look it up, say so. Fabrication is the cardinal sin.

## Rule 6: Frequent Incremental Updates

The user must never wonder what you're doing. Communicate constantly:
- Before a task: what you're about to do
- During a task: what you've found so far
- After a task: what changed and what's next

One sentence is enough. Silence is not.
