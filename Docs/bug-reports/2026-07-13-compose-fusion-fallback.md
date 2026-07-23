# Bug: correct cross-beat fusions are silently discarded → dense stops ship the scattered "shotgun of factoids" stitch

**Reported:** 2026-07-13 · **Surface:** tour compose (AI voice) · **Severity:** High (user-facing tour quality; affects flagship multi-beat stops) · **Status:** SUB-FIX COMMITTED — this documents one *contributing* cause (under-cited cross-beat fusions), now fixed + guarded. **The user-facing Le Meurice symptom is NOT closed.** A live run after the fix showed the stop still reverts for a *different, dominant* cause (the faithfulness gate rejecting faithful rephrasings/long sentences + all-or-nothing stop revert). That real remaining work is tracked in `2026-07-13-compose-stop-revert-haiku-ceiling.md`.

> **Scope of the committed change:** verify.py strict-first + per-stop-union faithfulness fallback, `_populate_also_cites`, and the reported-only `undercited_fusions` metric. Live-verified that the von Choltitz fusion itself now passes; NOT sufficient to keep the stop composed. Committed as a correct sub-fix, not a bug closure.

---

## TL;DR

A tester complained that a stop read like a "shotgun of factoids" — e.g. *"…the German General von Choltitz was quartered when he saved Paris…"* dropped in with no context, disconnected from a second mention of the German occupation three sentences later.

The compose step (LLM "AI voice") **actually fixes this** — on the first try it fuses the two scattered mentions into one complete sentence. **But the faithfulness gate rejects the fused sentence and reverts the whole stop to the scattered stitch**, because the model tagged the fused sentence with only one of its two source beats. The consolidation the user wants is being generated and then thrown away.

Observed on the composed path: **6 of 14 stops fell back to the stitch** (`compose_status: composed_partial`), including the flagship Hotel Le Meurice stop.

---

## Reproduction

**Config** (the smallest one where Le Meurice gets all 3 of its beats — the C9 per-stop audio governor only allocates that many on a long tour):

- `POST /api/v1/trips/preview`
- `center_lat: 48.8635, center_lng: 2.3280` (Tuileries / rue de Rivoli)
- `duration_min: 240`
- `lenses: ["famous_residents", "literary_heritage", "historic_arch"]`
- `round_trip: false`
- `compose: true`  ← live compose (`COMPOSE_PROVIDER=anthropic`)

**Result:** 14-stop tour, `compose_status: composed_partial`. Hotel Le Meurice (stop 2) is **byte-for-byte identical to the stitched scaffold** — it fell back.

Stops that fell back to stitch in this run: **2 (Le Meurice), 3, 4, 7, 12, 13, 14** (7 of 14; the count is stochastic run-to-run but the big multi-beat stops are the consistent victims).

---

## Observed vs expected (Le Meurice stop)

**What SHIPS (stitch fallback)** — two disconnected mentions of the German occupation, from two different lens beats, several sentences apart:

> …It was also where the German General von Choltitz was quartered when he saved Paris from destruction at the end of World War II. …[Orwell passage]… A generation later, the German High Command of the Paris garrison took up residence at the lavish Meurice. One wonders whether any of them had read Down and Out.

**What compose GENERATED and the gate REJECTED** — the two mentions fused into one complete sentence:

> A generation later, the German High Command of the Paris garrison took up residence in the lavish Meurice — **including General von Choltitz**…

That is exactly the consolidation the tester asked for. It was discarded.

---

## Root cause

The compose prompt instructs the model that when it fuses facts from two beats into one sentence, it must keep one beat as the primary `source_id` **and list the other beat id(s) in `also_cites`**, because the faithfulness verifier entails a fused sentence against the **union** of its cited beats' claims+bodies. See:

- Prompt instruction: `src/tour/compose.py:240-244`
- `Sentence.also_cites` / `cited_beat_ids` (= `source_id` + `also_cites`): `src/tour/contract.py:341-349`
- Union entailment ("a cross-beat merge … is faithful instead of failing on the primary beat alone"): `src/tour/verify.py` in `verify_faithfulness` (see the "Multi-beat citation" comment)

**The failure:** the model produced the correct fusion but **did not populate `also_cites`** with the second beat. The fused sentence was tagged with only `source_id = 85ebe707` (the Orwell/`literary_heritage` beat, which says "German High Command took up residence"). The "von Choltitz" fact comes from a **different** beat, `c3d4a78a` (the Frommer's/`famous_residents` beat). So the verifier entailed "von Choltitz" against a beat that never mentions him → `unfaithful` → the sentence is dropped → the stop reverts to the stitch.

### Live diagnostic evidence

Composing only the Le Meurice stop (candidates=2, matching the route) and running the gate's own local checks (`verify_faithfulness` + `verify_claim_coverage`):

```
Le Meurice stop beats: c9c90a74 (English corridor/haute couture),
                       c3d4a78a (Dickens + von Choltitz),
                       85ebe707 (Orwell + German High Command)

candidate 1: faithfulness_failures=3  coverage_failures=0
  FAITH[unfaithful:c3d4a78a]: "On the corner of rue de Castiglione and rue de Rivoli, its discreet entrance at no. 228 facing the Tuileries Gardens…"
  FAITH[unfaithful:c3d4a78a]: "Charles Dickens stayed here in the 19th century — as did Thackeray — while Dickens researched his novel…"
  FAITH[unfaithful:85ebe707]: "A generation later, the German High Command…took up residence…including General von Choltitz…"

candidate 2: faithfulness_failures=1  coverage_failures=0
  FAITH[unfaithful:85ebe707]: "A generation later, the German High Command…took up residence…among them General von Choltitz…"
```

**Key signals:**
- `coverage_failures = 0` in both candidates → compose is **not dropping facts**. This is not a content-loss failure.
- Every failure is a **cross-beat fusion** where the asserted fact is true but lives in a beat that the sentence didn't cite in `also_cites` (Thackeray+Dickens, address+entrance, High Command+von Choltitz).
- **Best-of-N doesn't help:** both candidates make the same under-citation mistake on the von Choltitz sentence, so the lower-penalty candidate 2 still has 1 faithfulness failure → still reverts.

So the gate is working *as designed* — it correctly refuses a sentence whose declared citations don't entail it. The defect is that **the fusion's citation bookkeeping is unreliable, so factually-correct consolidations are structurally rejected.**

---

## Why this matters

- It hits the **big, multi-beat stops** — exactly the ones where fusion/de-duplication matters most, and the flagship POIs (Le Meurice).
- The user pays for "AI voice" and silently receives the un-voiced scaffold on ~40%+ of stops.
- It masquerades as unrelated complaints ("shotgun of factoids", "AI voice does nothing here") when it's one root cause.

---

## Proposed fix (smallest change first)

**Primary — union re-check in the repair path.** Before reverting an `unfaithful` composed sentence to the stitch, re-run its entailment against the **union of ALL the beats at that stop** (not just its declared `cited_beat_ids`). Every beat at a stop describes the same POI and is co-located, so a sentence entailed by the stop's combined beats is faithful regardless of the model's `also_cites` bookkeeping. On pass, accept the sentence and auto-populate `also_cites` from the matching beats.
- Touch points: the per-stop repair in `src/tour/compose.py` (`compose_script_per_chapter`, the `_bad_stops` / `repair_composed` path, ~`src/tour/compose_gate.py:76-114`) and/or `verify_faithfulness` support for a stop-union fallback.
- Risk to weigh: a fabricated fact that happens to appear in a *different* beat at the same stop would pass — but that's still a true corpus fact at that POI (low risk). Keep the strict per-citation check as the primary path; the union is only a fallback before reverting.

**Secondary (complementary):** post-parse, auto-infer `also_cites` by matching each composed sentence's facts to the stop's beats, so bookkeeping doesn't depend on model compliance; and/or harden the prompt.

## Proposed regression guard (deterministic — no rubric needed)

Add a metric: for a composed candidate, flag any sentence that is **unfaithful under its declared `cited_beat_ids` but faithful under the union of its stop's beats**. That count = "under-cited correct fusions." The fix should drive it to zero on the Le Meurice fixture. This is a deterministic detector (given a candidate), suitable for `src/tour/compose_metrics.py` + a test in `tests/test_compose_quality_eval.py` using a replay fixture of the candidate above (no live call in the bar).

---

## Explicitly NOT in scope

Pulling contextualizing beats **across different POIs** (e.g. the von Choltitz story is further explained by beats on Square Raoul Nordling, the Eiffel Tower, and Jardin Atlantique) is a separate, larger capability (cross-POI entity-thread gathering) and is **not** this bug. This bug is purely about **within-stop** fusions that already exist being wrongly discarded.

---

## Environment / how it was diagnosed

- API: `COMPOSE_PROVIDER=anthropic`, dev Neo4j (Paris corpus, :7687), preview endpoint `src/api/routes/trips.py:709` (`preview_trip`), per-chapter compose `src/tour/compose.py:533` (`compose_script_per_chapter`), route calls it with `candidates=2` at `src/api/routes/trips.py:769`.
- Diagnostic harness (rebuilds the tour, composes only the Le Meurice stop, dumps the local report): kept in the session scratchpad — reproducible against the dev graph.
- No production/source code was changed to diagnose this. (A UI-only change was made to `frontend/review.html` + `frontend/tour-preview.html` to expose an "AI voice (compose)" toggle + a `voice: composed/stitched` badge so testers stop mistaking the scaffold for the shipped tour — orthogonal to this bug, ship or drop independently.)
