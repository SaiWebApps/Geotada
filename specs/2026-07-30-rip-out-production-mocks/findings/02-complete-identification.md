# Complete identification — every stand-in, found structurally

My first sweep was name-based and it MISSED one (`scripts/tour_build.py`'s canned
glue, caught by the judge). This is the redone version: derive the stand-in
classes from source, then find every instantiation outside `tests/`. No guessing
from names at call sites, no regex.

## The five stand-in classes defined under `src/`

| class | module |
|---|---|
| `MockTTSProvider` | `src/audio/provider.py` |
| `MockBeatDrafter` | `src/onboard/beat_draft.py` |
| `MockGlueClient` | `src/tour/glue_client.py` |
| `MockFaithfulnessChecker` | `src/tour/verify.py` |
| `OfflinePremiumExecutor` | `src/tour/premium_tour.py` |

All five are KEPT deliberately. They are what makes `make test` cost $0 and run
offline. The work was never to delete them — it was to close every door through
which one could be reached without someone asking for it.

## Every instantiation outside `tests/` — exactly two, both now honest

**`src/tour/compose_gate.py`** — `MockFaithfulnessChecker()`.
Reachable ONLY via an explicit `allow_unverified_faithfulness=True`; a bare
`None` now raises, and the resulting report carries
`faithfulness_checked=False`. Rewritten from `x or Mock()` to an if/else so it
cannot read as a silent fallback again — that `or` is the exact spelling that
hid this for months.

**`scripts/tour_build.py`** — `MockGlueClient()` on the non-`--haiku` path.
This is the one the first sweep missed. Every tour built with `make tour-build`
has transition sentences from a fixed table rather than from a model, on the
surface the owner reads tours with. Left as an explicit $0 default (`--haiku` is
the documented opt-in and forcing spend is the owner's call), but the run summary
now prints:

```
glue:        CANNED — transitions are fixed strings from MockGlueClient,
             not written by a model; pass --haiku for real ones
```

alongside the `faithfulness: NOT CHECKED` line. The lie was never the double —
it was `validation: PASS` printed over canned prose with nothing naming it.

## The three with no product call site at all

- **`MockTTSProvider`** — absent from `_PROVIDERS`; `get_provider()` fails
  closed. `register_provider()` is the only door and
  `tests/test_no_doubles_on_human_surfaces.py` now asserts it has zero callers
  under `src/` and `scripts/`.
- **`MockBeatDrafter`** — in `_DRAFTERS`, but `get_drafter()` fails closed on an
  unset or unknown pin, so it can only be chosen by name, explicitly.
- **`OfflinePremiumExecutor`** — instantiated only by `tests/conftest.py:146`.
  `get_premium_compose_executor()` returns `AnthropicPremiumExecutor()`
  unconditionally, with no env-var or config branch anywhere.

## The app

`mobile/lib` names no double and imports nothing from `mobile/test`, now guarded.
Verified behaviourally too, not just by name: no bundled audio assets, and the
tour path surfaces a server error rather than substituting content.

## What the sweep would catch next time

`tests/test_no_doubles_on_human_surfaces.py` holds the two doors nothing else
watched: the app importing from its own test tree, and a server-side call to
`register_provider`. Both were proven RED by ephemeral injection. Neither would
have caught the `tour_build` glue miss — that one is a double passed
*explicitly* by product code, which is legal by design. The defence there is the
printed line, not a guard.
