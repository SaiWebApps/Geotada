# The existing anti-mock guard is green while the bug is live

This is the most important finding of the recon, because it is the reason the
defect survived a fix that was explicitly aimed at it.

## Run it yourself — it passes

```
make test-file FILE="tests/test_workbench_preview_wiring.py::test_workbench_defaults_to_the_real_tts_provider_not_mock"
```

```
tests/test_workbench_preview_wiring.py::test_workbench_defaults_to_the_real_tts_provider_not_mock PASSED [100%]
============================== 1 passed in 0.03s ===============================
```

GREEN, in 0.03 s, while `frontend/review.html:3127` sends `provider: 'mock'` on
every TTS request the workbench issues. Nothing about this test is broken in the
usual sense — it does exactly what it says, against the wrong function.

(Useful side effect: this confirms the ledger's `test_command` form works and
that this file is a fast, container-free, $0 target for the new guards.)

## The guard

`tests/test_workbench_preview_wiring.py::test_workbench_defaults_to_the_real_tts_provider_not_mock`

What it actually does:

```python
body = _js_function_body(REVIEW_HTML.read_text(), "async function loadTtsProviders()")
assert "o.value === 'mock'" not in body
assert "o.value === 'openai'" in body
```

It extracts the body of **one function**, `loadTtsProviders()`, and asserts that
that function does not force-select `mock` in the dropdown.

## What it does not do

It never looks at `ttsPlay()` — the function that issues the actual request.
Sixty lines below the code it inspects, `frontend/review.html:3127` reads:

```js
body: JSON.stringify({ text, provider: 'mock' }),
```

So the guard is GREEN while **every** workbench TTS request — beat TTS and
tour-preview stops alike, since `ttsPlay()` is the one shared implementation —
asks for the fake. The dropdown the guard protects is decorative: whatever the
editor selects, the request body is a constant.

The guard's own docstring claims the bug it fixed was "Every workbench 'play'
was a silent mock WAV an editor could mistake for real narration." That
sentence is still true. The fix changed which option was *highlighted*, not
what was *sent*.

This is the "a guard that cannot be turned red does not exist" failure in its
most dangerous form: the guard CAN go red, but only for a mutation of the
dropdown. It is aimed at the symptom's neighbour.

## The docstring is also stale

The same docstring says:

> ``mock`` deliberately stays in the dropdown: the Playwright audio tests
> ``page.select_option("#ttsProviderSelect", "mock")`` to stay $0.

That is no longer true of the current tree:

- `src/audio/provider.py` no longer registers `MockTTSProvider` in `_PROVIDERS`,
  so `GET /audio/providers` cannot offer `mock` and it cannot appear in the
  dropdown at all.
- `frontend/review.html:3078-3079` states the Playwright audio tests now stub
  `POST /audio/preview` in the browser instead of asking the server for a fake.

Per CLAUDE.md ("A doc that contradicts the code gets corrected or deleted.
Never left."), this docstring must be corrected as part of the work.

## Consequence for the plan

Any step that claims to fix `review.html:3127` must ship a guard that inspects
**the request-issuing function**, not the dropdown builder, and that guard must
be demonstrated RED against the current file before the fix lands. Re-using or
extending the existing test without changing what it reads would reproduce the
same blind spot.

Recommended shape (structural, no regex — the project bans regex for
parsing/extraction because it fails silently): parse the page and assert that
the body of `ttsPlay()` contains no string-literal provider name at all, i.e.
that the provider travels in a variable. Asserting merely "the literal 'mock'
is absent" would pass if someone hardcoded `'elevenlabs'`, which is the same
class of defect.

## MEASURED TRAP — naive reuse of the existing helper passes vacuously

`_js_function_body(html, declaration)` locates the body as
`html.index("{", start)` — the FIRST `{` after the declaration. `ttsPlay` is
declared with **destructured parameters**:

```js
async function ttsPlay({ text, cacheKey, btn, audioEl }) {
```

so that first `{` is the parameter object, and brace matching closes on it
immediately. Measured, both with a short anchor and with the full declaration
line as the anchor:

```
NAIVE anchor 'async function ttsPlay('  -> '{ text, cacheKey, btn, audioEl }'
   length: 32 | contains 'mock'? False
CORRECT-looking full-line anchor        -> length: 32 | contains 'mock'? False
```

A guard written as `assert "mock" not in _js_function_body(html, "async
function ttsPlay(")` is therefore **GREEN while the defect is live** — the same
vacuous-pass failure the helper's own docstring was written to prevent, arriving
through a door the docstring did not anticipate. Note the full-line anchor does
not help: `index("{", start)` still finds the parameter brace.

## MEASURED FIX — anchor past the parameter list

Find the declaration, walk the parenthesis depth to the `)` that closes the
parameter list, then brace-match from the first `{` after it:

```
length: 1624
contains 'mock'? True
provider lines: ["body: JSON.stringify({ text, provider: 'mock' }),"]
```

This is the mechanism the guard step must use. It is proven to see the defect,
so its RED is demonstrated rather than assumed. The helper in
`tests/test_workbench_preview_wiring.py` should be extended (not duplicated) so
every existing caller keeps working and no future caller inherits the trap.
