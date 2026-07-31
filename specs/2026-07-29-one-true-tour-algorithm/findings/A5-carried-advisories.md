# A5 — live advisories carried forward (NOT fixed here)

Recorded 2026-07-30 on a judge ruling. A5 was blocked by the engine, hand-fixed out of
band, and marked `completed`. Marking it completed would otherwise bury these two, which
the opus skeptic raised (`findings/step-A5-skeptic-opus.md`) and which remain live.

Neither carried a verified reproduction, so neither blocks under the engine's rules —
that is exactly why they must be written down instead of dropped.

## F4 — de-dup can drop a sentence that carries a NEW fact, and preview will not catch it

`suppress_same_beat_near_duplicates` scores with `fuzz.token_set_ratio`, which returns
**100 when one token set is a superset of the other**. So a longer sentence that repeats
an earlier sentence's tokens *and adds a new fact* can be scored an exact near-duplicate
and dropped — losing the new fact, not a repeat.

Why the surfaces differ:

- On the **persisted** path (`POST /trips/{id}/compose`) A4 wires the coverage baseline
  (`claims_realized_by` over the pre-compose stitch), so a dropped fact is caught.
- On **`/trips/preview`** and the certification replay, `enforce_claim_coverage` defaults
  OFF (`src/tour/authoring.py:563`). Nothing catches the loss there.

This is newly reachable because A5 is what first makes the de-dup pass run on those two
surfaces at all. Before A5 they never de-duped.

**Not fixed here on purpose.** Turning coverage on for preview is a NEW check on that
surface, which ledger decision D3 forbids ("parity with today only — NO new checks"),
and it would put a Haiku entailment call inside an interactive editor request. The honest
options for a later slice: (a) make the near-dup comparison length-aware so a superset
carrying extra content is not a duplicate, or (b) enable coverage on preview and accept
the cost. Option (a) is the smaller, cheaper fix and does not change any surface's gate
profile.

## F7 — a stop emptied by de-dup raises AFTER the money is spent

`finish()` now raises when a stop has no composed text left after de-dup (it cannot build
a `CompositionTrace` with `min_length=1` fields from nothing, and shipping an untraced
stop is worse). On `/trips/preview` that exception lands in the route's catch-all and the
tour degrades to the Basic lane — **after every stop's Opus call has already been billed**.

The refusal is correct; the cost ordering is the defect. It is pre-existing in shape (the
preview path has always billed per stop before finalizing) but A5 adds one more way to
reach it.

**Not fixed here**: retry/cost-recording are explicitly OUT of this ledger (run-context
"Supersession"). Recorded so the next slice sizes it with this case included.
