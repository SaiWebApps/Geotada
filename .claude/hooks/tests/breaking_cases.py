"""Text a guard once got WRONG, kept verbatim, forever.

THE MECHANISM, and why it is not another ban. The owner's ruling on 2026-09-02,
after two guards mistook a web address for a file path and blocked the dashboard
link they had just demanded:

    "THE POINT WAS TO PREVENT ANYTHING THAT WAS NOT TRUE COMPREHENSION. I CANNOT
     JUST PLAY WHACK A MOLE AND BAN YOU FROM EACH AND EVERY CASE."

Banning a case is whack-a-mole because the ban is written by whoever already
failed to imagine the case. This file inverts that: it is not a list of banned
shapes, it is a list of REAL STRINGS FROM REAL SESSIONS together with what each
one actually is. Every guard that decides what a piece of text is must be fed all
of them and must get all of them right.

The list only ever grows, and it grows on incident, not on imagination:

    WHEN A GUARD BLOCKS SOMETHING GOOD, THE EXACT TEXT IT BLOCKED IS ADDED HERE,
    IN THE SAME COMMIT AS THE FIX.

That is what makes this different from a ban list. A ban covers the one shape
somebody thought of. An entry here is checked against EVERY classifier in this
directory, including ones written later by someone who never read the incident.
One incident, permanent coverage, everywhere.

WHAT IT STILL CANNOT DO, said plainly rather than left to be discovered: this
catches kinds already known to have broken something. It cannot catch a kind
nobody has met yet — that needs comprehension, and no test file has any. The
honest claim is narrow, and it is worth having: no guard in this directory can
EVER AGAIN be wrong about a case that has been wrong before.
"""

from __future__ import annotations

#: Every entry: the verbatim text, what it actually is, and the incident.
#: `kind` is the answer a correct classifier must give. `story` is why the entry
#: is here, so nobody deletes it as noise.
BREAKING_CASES = [
    {
        "text": "http://127.0.0.1:8010",
        "kind": "web address",
        "story": (
            "2026-09-02 — the live dashboard the owner had just demanded be put "
            "at the top of every reply. citation-guard split on the last colon, "
            "read 8010 as a line number, and refused the reply with 'no such "
            "file is tracked in this repo'. plain-words-guard saw a slash and a "
            "dot in one word and called it a filename dropped into prose. "
            "Neither used a regular expression."
        ),
    },
    {
        "text": "[Dashboard](http://127.0.0.1:8010)",
        "kind": "web address",
        "story": (
            "2026-09-02 — the SAME address in the form the harness instructs "
            "replies to use for links. The first fix handled only a bare token: "
            "whitespace-splitting leaves `Dashboard](http://127.0.0.1:8010`, and "
            "a URL parser cannot see a scheme through the `](`, so the fix that "
            "closed the bare shape left this one wide open. One shape closed is "
            "not a class closed."
        ),
    },
    {
        "text": "<http://127.0.0.1:8010>",
        "kind": "web address",
        "story": (
            "2026-09-02 — the angle-bracket form, which markdown also renders as "
            "a link. Added beside its siblings rather than after it broke, "
            "because an address arrives wearing whatever punctuation was typed."
        ),
    },
    {
        "text": "https://claude.ai/code/artifacts",
        "kind": "web address",
        "story": (
            "2026-09-02 — an https address with a path and no port, so nothing "
            "in it resembles a line number. It is here to prove a fix reads the "
            "SCHEME rather than noticing the absence of digits after a colon."
        ),
    },
    {
        "text": ".claude/hooks/citation-guard.py:41",
        "kind": "file citation",
        "story": (
            "The other half of the pair. A fix that exempts anything with a "
            "colon and a dot would pass every address above and go blind to "
            "every real citation, which is the failure that matters more: a "
            "citation guard that stops seeing citations still reports success. "
            "Line 41 is where citation-guard names its own enforcer."
        ),
    },
    {
        "text": "[citation-guard.py:41](.claude/hooks/citation-guard.py:41)",
        "kind": "file citation",
        "story": (
            "A citation in the markdown-link form the harness instructs replies "
            "to use for file references. Before 2026-09-02 this reached the "
            "citation guard as one fused token and resolved only by luck, "
            "through a basename fallback that happened to find a single match."
        ),
    },
]

#: The kinds a classifier is expected to tell apart. Kept beside the corpus so a
#: new kind cannot be added to one without the other noticing.
KINDS = sorted({case["kind"] for case in BREAKING_CASES})


def cases_of(kind: str) -> list[dict]:
    """Every recorded case that IS `kind`."""
    return [case for case in BREAKING_CASES if case["kind"] == kind]


def texts_of(kind: str) -> list[str]:
    """Just the verbatim strings for `kind`."""
    return [case["text"] for case in cases_of(kind)]


def story_of(text: str) -> str:
    """Why `text` is in the corpus — for an assertion message worth reading."""
    for case in BREAKING_CASES:
        if case["text"] == text:
            return case["story"]
    return "not a recorded case"
