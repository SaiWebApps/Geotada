"""The workbench preview must send what it means and reject what it cannot honour.

THREE MEASURED DEFECTS (2026-07-19), all of which made "tour preview" look broken
to a human pressing the button:

1. ``city_slug`` was never sent by ``generateTourPreview`` (``frontend/review.html``),
   so ``TripPreviewRequest``'s default of "paris" applied to EVERY preview. A
   London or New York workbench session previewed the PARIS corpus from a
   London/NY start, found nothing reachable, and 422'd.

2. An unknown lens string was silently ignored. ``_lens_relation``
   (``selection.py:2451-2477``) classifies every POI as a "miss" for an
   unrecognised lens, so ``lens_relevance`` returns the uniform ``LENS_FLOOR``
   (0.25). A uniform MULTIPLICATIVE factor leaves relative ranking identical to
   passing no lens, so a typo produced the un-lensed tour with no signal at all.

3. The lens input offered its vocabulary only as a ``placeholder`` — which is not
   a value — so the default request sent NO lenses.

TWO OWNER RULINGS (2026-07-31), both the same principle — the workbench must
replicate the tourist's app experience as closely as possible:

4. ``generateTourPreview`` opened a ``window.confirm`` spend warning before every
   preview. A tourist is never asked to approve spend, so the workbench must not
   ask either. Removed; section 4 below keeps it removed.

5. ``loadTtsProviders`` force-selected the ``mock`` TTS provider after fetching
   the provider list, silently overriding the ``openai`` default. Every workbench
   "play" was therefore a silent WAV that an editor could mistake for real
   narration — the audio twin of the standing never-mock-in-the-workbench rule.

These tests are cheap, hermetic and $0.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from pydantic import ValidationError

from src.api.models.trips import TripPreviewRequest
from src.schema.definitions import TAGGABLE_LENSES

REPO = pathlib.Path(__file__).resolve().parents[1]
REVIEW_HTML = REPO / "frontend" / "review.html"


# --------------------------------------------------------------------------
# 1. city_slug is actually sent
# --------------------------------------------------------------------------


def test_preview_fetch_sends_city_slug() -> None:
    """UNDO TEST: delete the ``city_slug:`` line from the plan-body builder and
    this goes RED. Without it every city previews Paris.

    Since W4.2 the plan request is built ONCE, stored as ``lastTourPlanBody``
    (the object every dial writes into and the author call replays verbatim),
    and the fetch sends exactly that object — so the guard reads the builder
    and the send, not a second body literal that no longer exists.
    """
    html = REVIEW_HTML.read_text()
    plan = _js_function_body(html, "async function generateTourPreview()")
    assert "/trips/preview" in plan, (
        "the extracted generateTourPreview body issues no plan request, so this "
        "guard is not reading the plan path"
    )
    assert "city_slug:" in plan, (
        "generateTourPreview does not send city_slug — every preview silently "
        "falls back to TripPreviewRequest's 'paris' default, so a London/NY "
        "workbench session previews the wrong corpus and 422s."
    )
    assert "JSON.stringify(lastTourPlanBody)" in plan, (
        "the plan fetch does not send lastTourPlanBody — the ONE body the dials "
        "write into and the author call replays. A second body literal here is "
        "exactly the drift the one-body rule exists to prevent."
    )


def test_preview_city_slug_uses_the_canonical_city_variable() -> None:
    """It must send the same key the rest of the page uses, not a fresh guess."""
    html = REVIEW_HTML.read_text()
    plan = _js_function_body(html, "async function generateTourPreview()")
    assert re.search(r"city_slug:\s*cityName", plan), (
        "city_slug must come from cityName, the canonical key every other "
        "workbench fetch already sends."
    )


# --------------------------------------------------------------------------
# 2. unknown lenses are rejected loudly
# --------------------------------------------------------------------------


def _req(**kw: object) -> TripPreviewRequest:
    base = {"center_lat": 48.8546, "center_lng": 2.3477}
    base.update(kw)
    return TripPreviewRequest(**base)  # type: ignore[arg-type]


def test_every_taggable_lens_is_accepted() -> None:
    for lens in TAGGABLE_LENSES:
        assert _req(lenses=[lens]).lenses == [lens]


def test_unknown_lens_is_rejected_not_silently_ignored() -> None:
    """UNDO TEST: remove ``validate_lenses`` and this goes RED.

    Before the validator this request was ACCEPTED and produced the un-lensed
    tour — the exact silent failure being guarded against.
    """
    with pytest.raises(ValidationError) as exc:
        _req(lenses=["dark_histry"])  # a plausible typo
    assert "Unknown lens" in str(exc.value)


def test_rejection_names_the_valid_vocabulary() -> None:
    """An error a human can act on names what they should have typed."""
    with pytest.raises(ValidationError) as exc:
        _req(lenses=["not_a_lens"])
    msg = str(exc.value)
    assert "dark_history" in msg and "historic_arch" in msg


def test_one_bad_lens_among_good_ones_still_rejects() -> None:
    with pytest.raises(ValidationError):
        _req(lenses=["dark_history", "totally_made_up"])


def test_blank_and_none_lenses_remain_permissive() -> None:
    """An absent lens is a legitimate request (the un-lensed tour), unchanged."""
    assert _req(lenses=None).lenses is None
    assert _req(lenses=[]).lenses is None
    assert _req(lenses=["  ", ""]).lenses is None
    assert _req(lenses=["  dark_history  "]).lenses == ["dark_history"]


# --------------------------------------------------------------------------
# 3. the UI offers the real vocabulary
# --------------------------------------------------------------------------


def test_lens_datalist_matches_the_canonical_vocabulary_exactly() -> None:
    """The picker must not drift from TAGGABLE_LENSES in either direction.

    An option the server rejects is a trap; a valid lens missing from the list is
    invisible to the editor.
    """
    html = REVIEW_HTML.read_text()
    block = re.search(r'<datalist id="tourLensOptions">(.*?)</datalist>', html, re.S)
    assert block, "the lens datalist is missing from review.html"
    offered = set(re.findall(r'value="([^"]+)"', block.group(1)))
    canonical = set(TAGGABLE_LENSES)
    assert offered == canonical, (
        f"lens picker drifted from TAGGABLE_LENSES. "
        f"offered-but-invalid={sorted(offered - canonical)}, "
        f"valid-but-missing={sorted(canonical - offered)}"
    )


def test_lens_input_is_wired_to_the_datalist() -> None:
    html = REVIEW_HTML.read_text()
    tag = re.search(r'<input[^>]*id="tourLenses"[^>]*>', html)
    assert tag, "the #tourLenses input is missing"
    assert 'list="tourLensOptions"' in tag.group(0), (
        "#tourLenses is not bound to the datalist, so the vocabulary stays "
        "invisible and typos stay easy."
    )


# --------------------------------------------------------------------------
# 4 & 5. the workbench behaves like the app (owner rulings, 2026-07-31)
# --------------------------------------------------------------------------


def _js_function_body(html: str, declaration: str) -> str:
    """Return one JS function's source, located by plain brace matching.

    Deliberately NOT a regex: a regex that matches nothing returns a plausible
    empty string, and an "absence" assertion over an empty string passes
    vacuously — it would report the defect as fixed no matter what the file
    says. This raises instead, and every caller additionally asserts a known
    anchor is present before asserting anything is absent.
    """
    start = html.find(declaration)
    if start == -1:
        raise AssertionError(f"{declaration!r} is missing from review.html")
    open_brace = html.index("{", start)
    depth = 0
    for i in range(open_brace, len(html)):
        if html[i] == "{":
            depth += 1
        elif html[i] == "}":
            depth -= 1
            if depth == 0:
                return html[open_brace : i + 1]
    raise AssertionError(f"{declaration!r} is never closed in review.html")


def test_generate_tour_preview_shows_no_spend_confirmation() -> None:
    """OWNER RULING (2026-07-31): the cost dialog is removed and stays removed.

    ``generateTourPreview`` used to open ``window.confirm('Generate a Premium
    candidate? ... spends real money on your API key.')`` and return early on
    Cancel. The owner ordered it gone: the workbench exists to replicate the
    tourist's app experience, and a tourist never sees a spend prompt.

    UNDO TEST: paste any ``confirm(...)`` back into the function -> RED.
    """
    body = _js_function_body(REVIEW_HTML.read_text(), "async function generateTourPreview()")
    # Prove we sliced the real function, so an absence is a real absence. Plan
    # renders THE day (the one-route plan, design §8.1); the narrated stops moved
    # to authorTourDay when planning and authoring became two calls.
    assert "/trips/preview" in body and "renderTourDay(" in body, (
        "the extracted generateTourPreview body is not the real function"
    )
    assert "confirm(" not in body, (
        "generateTourPreview must never show a spend-confirmation dialog. The "
        "owner ordered it removed on 2026-07-31 so the workbench matches the "
        "experience a tourist gets in the app."
    )


def test_planning_the_day_is_a_separate_call_from_writing_it() -> None:
    """Pressing plan must PLAN and nothing else.

    The two-step split is only real if the plan handler cannot reach the
    authoring endpoint or the audio endpoint. Both halves are asserted, so a
    single function that plans and then writes in the same click cannot pass.
    Since W4.2 there is no pick — the plan reply carries exactly one route —
    but the split stands: planning is free and immediate (it IS the live dial
    replan), and writing is the one deliberate action, taken by
    ``authorTourDay`` with the day's ``route_id``.

    The authoring route is ``/trips/preview/author``. It is NOT
    ``/trips/preview/compose``: that name is already taken by the authenticated
    saved-trip route ``/trips/{trip_id}/compose``, so the anonymous twin could
    never have used it.

    UNDO TEST: in review.html, change generateTourPreview's
    ``renderTourDay(await resp.json(), duration);`` to
    ``renderTourStops(await resp.json(), duration);`` -> RED.
    """
    html = REVIEW_HTML.read_text()

    plan = _js_function_body(html, "async function generateTourPreview()")
    assert "/trips/preview" in plan, (
        "the extracted generateTourPreview body issues no preview request, so "
        "this guard is not reading the plan path"
    )
    assert "renderTourDay(" in plan, (
        "plan must render THE day; without this the operator never sees what a "
        "dial did, and the preview is whatever the server wrote first"
    )
    assert "renderTourStops(" not in plan, (
        "plan renders narrated stops, so scripts were written before the "
        "operator chose to write — the whole point of the split is that "
        "planning costs nothing"
    )
    assert "/trips/preview/author" not in plan, (
        "plan calls the authoring endpoint; planning must be one call"
    )
    assert "/audio/" not in plan, (
        "plan reaches an audio endpoint; no voice may be made before the operator "
        "chooses to write the day"
    )

    author = _js_function_body(html, "async function authorTourDay(")
    assert "/trips/preview/author" in author, (
        "authorTourDay does not call the authoring endpoint"
    )
    assert "route_id" in author, (
        "the authoring call does not carry the day's route identifier, so the "
        "server cannot prove it is writing the day the operator saw"
    )
    assert "renderTourStops(" in author, (
        "authoring does not render the narrated stops"
    )


def test_the_authored_tour_renders_the_stops_of_the_day_that_was_written() -> None:
    """The authored reply has no top-level stop list, so the renderer must read one.

    There is exactly one interleave now, and the authored tour IS the day the
    operator wrote: its stops arrive on ``option.stops``. A renderer that reads
    only a top-level ``stops`` array draws an EMPTY tour against the real
    endpoint while every stubbed browser test stays green, because a stub is free
    to fulfil a shape the server can no longer produce. That gap is exactly what
    this guard closes, and it is why it reads the page rather than a fixture.

    The Basic fallback lane keeps its own flat ``stops``, so both are read.

    UNDO TEST: in review.html, change renderTourStops's
    ``tourStops = Array.isArray(activeTour.stops) ? activeTour.stops :
    tourOptionMapStops(activeTour.option);`` back to ``... : [];`` -> RED.
    """
    body = _js_function_body(REVIEW_HTML.read_text(), "function renderTourStops(")

    # Non-vacuity: prove we sliced the renderer before asserting what it reads.
    assert "tourStops =" in body, (
        "the extracted renderTourStops body never assigns the stop list, so this "
        "guard is not reading the renderer and would pass regardless"
    )
    assert "activeTour.option" in body, (
        "renderTourStops takes no stops from the authored option, so an authored "
        "tour renders zero stops: the reply carries them on option.stops, and the "
        "top-level stop list it used to read no longer exists"
    )


def test_the_plan_screen_shows_what_degraded_before_anything_can_be_written() -> None:
    """A problem the operator cannot see before writing is a problem they cannot act on.

    Walking legs fall back to straight-line estimates when the routing service is
    unavailable, and that is reported as a degradation on the PLAN response. It
    has to be on screen ABOVE the "Write the tour" action: once that is clicked
    the tour is written and paid for, so a warning that only appears afterwards
    arrives too late to change anything. (W4.2 panel: the pick is gone, but the
    money moment moved onto the one write action — it did not go away.)

    UNDO TEST: move the ``buildDegradationPanel`` block in renderTourDay below
    the block that creates the ``tourWriteBtn`` button, or delete it -> RED.
    """
    body = _js_function_body(REVIEW_HTML.read_text(), "function renderTourDay(")

    # Non-vacuity: prove we sliced the day renderer before asserting ordering.
    assert "tourWriteBtn" in body, (
        "the extracted renderTourDay body never creates the write action, so this "
        "guard is not reading the plan screen"
    )
    panel_at = body.find("buildDegradationPanel(")
    write_at = body.find("tourWriteBtn")
    assert panel_at != -1, (
        "the plan screen never builds the degradation panel, so a tour planned on "
        "estimated walking times looks exactly like a measured one"
    )
    assert panel_at < write_at, (
        "the degradation panel is built after the write action, so what went wrong "
        "renders below the button that spends money on a tour"
    )


# --------------------------------------------------------------------------
# 6. the dials (W4.2 panel) — every control writes into the ONE plan body,
#    every change replans automatically, and the day is honest about itself
# --------------------------------------------------------------------------


# (control id, locked wire field) — the dial vocabulary the W4.2 panel ruled.
TOUR_DIALS = [
    ("tourDate", "start_datetime"),
    ("tourTime", "start_datetime"),
    ("tourFinish", "end_hardness"),
    ("tourParty", "party"),
    ("tourMaxLeg", "max_leg_minutes"),
    ("tourRestCadence", "rest_cadence_minutes"),
    ("tourStopDensity", "stop_density"),
    ("tourNarrationDensity", "narration_density"),
    ("tourAvoidQueues", "avoid_queues"),
    ("tourCategoryMinus", "category_minus"),
    ("tourWeather", "weather"),
]


def test_every_dial_writes_into_the_one_plan_body() -> None:
    """W4.2 panel: the author call replays ``lastTourPlanBody`` verbatim, so a
    dial that skips the body authors yesterday's knobs and 409s. Three couplings
    are asserted per dial: the control exists on the page, the plan builder
    reads it, and the locked wire field is written in the same function that
    assigns ``lastTourPlanBody`` and sends it.

    UNDO TEST: delete any ``body.<field> =`` line (or the ``lastTourPlanBody =
    body`` assignment) from generateTourPreview -> RED.
    """
    html = REVIEW_HTML.read_text()
    plan = _js_function_body(html, "async function generateTourPreview()")
    assert "lastTourPlanBody = body" in plan, (
        "generateTourPreview no longer stores the one body it builds, so the "
        "author call would replay something other than what was sent"
    )
    assert "JSON.stringify(lastTourPlanBody)" in plan, (
        "the plan fetch does not send the stored body, so what the dials wrote "
        "and what the server saw can drift"
    )
    for control_id, field in TOUR_DIALS:
        assert f'id="{control_id}"' in html, (
            f"the #{control_id} control is missing from the page"
        )
        assert control_id in plan, (
            f"generateTourPreview never reads #{control_id}; that dial can be "
            f"turned without ever reaching the request"
        )
        assert re.search(rf"body\.{field}\s*=|\b{field}:", plan), (
            f"generateTourPreview never writes {field!r} into the plan body, so "
            f"the #{control_id} dial is decorative"
        )


def test_dial_changes_replan_the_day_automatically() -> None:
    """W4.2 panel: turning a dial IS asking for a new day. Every change on the
    tour form funnels into one ~400ms debounce that re-runs the plan; while the
    replan is in flight the dials are disabled and a small "replanning…" note
    shows, so the screen is never silently stale.

    UNDO TEST: remove the ``scheduleTourReplan()`` call from the form's change
    listener, or the debounce body's ``generateTourPreview()`` call -> RED.
    """
    html = REVIEW_HTML.read_text()
    sched = _js_function_body(html, "function scheduleTourReplan()")
    assert "generateTourPreview()" in sched, "the debounce never re-plans the day"
    assert "setTimeout" in sched and "400" in sched, (
        "the replan is not debounced at ~400ms; either every change plans "
        "immediately or the burst-folding is gone"
    )
    # The declaration alone is dead code: a call site must exist beyond it.
    assert html.count("scheduleTourReplan(") >= 2, (
        "scheduleTourReplan is declared but never called; no dial replans anything"
    )
    assert re.search(r"addEventListener\('change',", html), (
        "no change listener exists, so no dial change can reach the debounce"
    )
    plan = _js_function_body(html, "async function generateTourPreview()")
    assert 'id="tourReplanNote"' in html and "tourReplanNote" in plan, (
        "the replanning note is missing, so a replan is invisible while in flight"
    )
    assert "disabled = true" in plan, (
        "the dials stay live during a replan, so two plans can race each other"
    )


def test_queue_waits_are_spelled_min_wait() -> None:
    """W4.2 panel: a queue price reads "12 min wait" — NEVER "12m", which a
    reader takes for metres or a timestamp. Every render of ``queue_minutes``
    must couple the number directly to the words " min wait".
    """
    html = REVIEW_HTML.read_text()
    renders = list(re.finditer(r"\$\{s\.queue_minutes\}", html))
    assert renders, "no card renders queue_minutes at all"
    for m in renders:
        following = html[m.end() : m.end() + len(" min wait")]
        assert following == " min wait", (
            f"a queue render is followed by {following!r} rather than ' min wait' "
            f"— the panel-locked spelling"
        )


def test_the_plan_screen_renders_the_honesty_surface_when_present() -> None:
    """W4.2 panel (deviation v): promises, day notes and unplanned slack render
    from the plan response — conditionally, because the server lands those
    fields in its own step and a missing field must never crash the screen.
    """
    body = _js_function_body(REVIEW_HTML.read_text(), "function renderTourDay(")
    for field in ("promises", "day_notes", "slack_minutes"):
        assert field in body, (
            f"renderTourDay never reads {field!r}; the day renders without the "
            f"honesty the panel ruled it owes"
        )
    assert "minutes unplanned — yours." in body, (
        "the slack line lost its panel-locked wording"
    )


def test_workbench_defaults_to_the_real_tts_provider_not_mock() -> None:
    """OWNER RULING (2026-07-31): the workbench plays REAL audio by default.

    ``loadTtsProviders`` rebuilt the dropdown from GET /audio/providers and then
    force-selected ``mock``, overriding the ``openai`` default declared both in
    the static <select> and in ``let ttsProvider``. Every workbench "play" was a
    silent mock WAV an editor could mistake for real narration — the audio twin
    of the never-mock-in-the-workbench rule, which had only covered narration.

    ``mock`` deliberately stays in the dropdown: the Playwright audio tests
    ``page.select_option("#ttsProviderSelect", "mock")`` to stay $0. What is
    forbidden is selecting it FOR the human.

    UNDO TEST: restore the ``mockOpt.selected = true`` line -> RED.
    """
    body = _js_function_body(REVIEW_HTML.read_text(), "async function loadTtsProviders()")
    assert "/audio/providers" in body and "ttsProviderSelect" in body, (
        "the extracted loadTtsProviders body is not the real function"
    )
    assert "o.value === 'mock'" not in body, (
        "loadTtsProviders must not select the mock TTS provider for the editor; "
        "a silent WAV that looks like real narration is the exact lie the "
        "never-mock-in-the-workbench rule exists to prevent."
    )
    assert "o.value === 'openai'" in body, (
        "loadTtsProviders must explicitly select the real provider. The list is "
        "sorted, so without this the first option ('elevenlabs') would win by "
        "accident rather than by the deployed TTS_PROVIDER=openai pin."
    )


def test_openai_is_a_real_registered_tts_provider() -> None:
    """The default the workbench picks must actually exist in the registry.

    Guards the pair: if ``openai`` were ever renamed or dropped from
    ``src/audio/provider.py``, the test above would still pass while the
    workbench silently fell through to whatever option happened to be first.
    """
    from src.audio.provider import list_providers

    providers = list_providers()
    assert "openai" in providers, (
        f"the workbench defaults to the 'openai' TTS provider, which is not "
        f"registered; available: {providers}"
    )


ONBOARD_HTML = REPO / "frontend" / "onboard.html"


def test_drafting_beats_shows_no_spend_confirmation() -> None:
    """OWNER DECISION (2026-07-31): no spend dialog on the workbench, here either.

    ``draftBeats`` used to POST with ``confirm_cost: false``, catch the API's 409
    cost estimate, and raise a modal the operator had to accept. That is the same
    two-step confirm the owner removed from ``generateTourPreview`` above, for the
    same reason: the workbench replicates the tourist's app experience, and a
    tourist is never asked to approve spend.

    The page now confirms on the operator's behalf. The API's ``confirm_cost``
    contract is deliberately UNCHANGED — this asserts the dialog is gone from the
    page, not that the server stopped defending other callers.

    Spend note, stated rather than hidden: with the modal gone, one click drafts a
    whole city's beats against the real Opus drafter that
    ``scripts/workbench.sh`` now pins. That is the owner's explicit decision.

    UNDO TEST: put any confirm/modal back into ``draftBeats`` -> RED.
    """
    html = ONBOARD_HTML.read_text()
    body = _js_function_body(html, "async function draftBeats(")

    # Non-vacuity: prove we extracted the real function before asserting absence.
    assert "draft-beats" in body, (
        "the extracted draftBeats body does not contain the /draft-beats POST, so "
        "this guard is not reading the drafting code and would pass regardless"
    )

    assert "confirm_cost: true" in body, (
        "draftBeats must confirm on the operator's behalf; sending false is what "
        "made the API answer 409 and the page raise a cost modal"
    )
    # NOT a ban on "409": draftBeats legitimately reports a 409 in its
    # generic-failure branch ("not assembled yet"), and banning the number would
    # fail on correct code — measured, it did. What must be absent is the modal
    # itself and any interactive confirmation.
    for banned in ("costModal", "confirm(", "costConfirmBtn"):
        assert banned not in body, (
            f"draftBeats still references {banned!r} — the spend-confirmation "
            f"flow is back. The workbench must never ask a human to approve "
            f"spend; that is the tourist-parity ruling."
        )
    assert "costModal" not in html, (
        "the cost-confirmation modal markup is still in onboard.html; remove the "
        "element too, or a later change can wire it back up unnoticed"
    )


def _js_function_body_after_params(html: str, declaration: str) -> str:
    """Return one JS function's body, skipping a DESTRUCTURED parameter list.

    ``_js_function_body`` above takes the first ``{`` after the declaration,
    which is right only for ``function f() {``. ``ttsPlay`` is declared
    ``async function ttsPlay({ text, cacheKey, btn, audioEl }) {``, so that first
    ``{`` is the PARAMETER object: brace matching closes on it immediately and
    yields the 32-character parameter list, which contains no request at all. A
    guard built on it passes vacuously while the defect is live — the very
    failure the sibling helper's docstring exists to prevent, arriving through a
    door that docstring did not anticipate. Using the full declaration line as
    the anchor does not help; the parameter brace is still first.

    So walk parenthesis depth from the declaration to the ``)`` that closes the
    parameter list, and only then brace-match. Still no regex.
    """
    start = html.find(declaration)
    if start == -1:
        raise AssertionError(f"{declaration!r} is missing from review.html")
    i = html.index("(", start)
    depth = 0
    while True:
        if html[i] == "(":
            depth += 1
        elif html[i] == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
        if i >= len(html):
            raise AssertionError(f"{declaration!r} has an unclosed parameter list")
    open_brace = html.index("{", i)
    depth = 0
    for j in range(open_brace, len(html)):
        if html[j] == "{":
            depth += 1
        elif html[j] == "}":
            depth -= 1
            if depth == 0:
                return html[open_brace : j + 1]
    raise AssertionError(f"{declaration!r} is never closed in review.html")


def test_ttsplay_sends_the_resolved_provider_not_a_literal() -> None:
    """The Play button must ask for the provider the editor actually chose.

    ``loadTtsProviders`` only decides which option is SELECTED. ``ttsPlay`` is
    what issues ``POST /audio/preview``, and it is the ONE shared TTS path for
    both beat playback and the tour-preview stops. A literal provider name here
    makes the dropdown decorative: whatever the editor picks, the request is a
    constant.

    That is exactly how ``provider: 'mock'`` reached the working tree while
    ``test_workbench_defaults_to_the_real_tts_provider_not_mock`` stayed green in
    0.03s — that test reads the dropdown builder, this one reads the request.

    A literal is rejected whatever it names. Pinning ``'openai'`` in the page
    would be the same defect: the editor's choice silently ignored.

    UNDO TEST: put ``provider: 'mock'`` back in ``ttsPlay``'s fetch -> RED.
    """
    html = REVIEW_HTML.read_text()
    body = _js_function_body_after_params(html, "async function ttsPlay")

    # Non-vacuity first: prove we extracted the request-issuing code before
    # asserting anything is absent from it.
    assert "/audio/preview" in body, (
        "the extracted ttsPlay body contains no /audio/preview fetch, so this "
        "guard is not reading the request-issuing code and would pass no "
        "matter what review.html says"
    )

    marker = "provider:"
    at = body.find(marker)
    assert at != -1, "ttsPlay's request body names no provider at all"
    value = body[at + len(marker) : body.index("}", at)].strip().rstrip(",").strip()

    assert not value.startswith(("'", '"', "`")), (
        f"ttsPlay hardcodes the TTS provider as the literal {value} instead of "
        f"sending the one the editor selected. The dropdown is then decorative "
        f"— every play asks for {value} whatever the human picked."
    )
    assert value == "ttsProvider", (
        f"ttsPlay sends {value!r}; it must send the 'ttsProvider' variable the "
        f"page keeps in sync with the dropdown and already uses in both audio "
        f"cache keys."
    )
