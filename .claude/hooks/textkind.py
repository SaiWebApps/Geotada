#!/usr/bin/env python3
"""What a piece of text IS — answered by a parser, never guessed from its shape.

WHY THIS MODULE EXISTS (owner ruling, 2026-09-02). Two guards blocked a reply
carrying `http://127.0.0.1:8010`, the address of the live dashboard the owner
had just demanded be put at the top of every reply:

  * citation-guard.py read the `:8010` as a line number and refused the reply
    with "no such file is tracked in this repo";
  * plain-words-guard.py saw a slash and a dot in one word and called it a
    filename dropped into prose.

Neither used a regular expression. A rule already forbade those, and both files
say so in their own docstrings. The owner's ruling names why that rule was not
enough:

    "THE POINT WAS TO PREVENT ANYTHING THAT WAS NOT TRUE COMPREHENSION. I CANNOT
     JUST PLAY WHACK A MOLE AND BAN YOU FROM EACH AND EVERY CASE."

The defect is not the syntax of a regular expression. It is DECIDING WHAT A
STRING IS BY LOOKING AT ITS CHARACTERS. A web address and a file citation are
the same shape — letters, dots, slashes, a colon, digits — so any test written
in characters confuses them, whether it is spelled as a pattern or as a chain of
`startswith` and `in`. Banning the pattern language moved the same mistake into
longhand.

So the rule this module exists to enforce is stronger and simpler:

    ASK SOMETHING THAT KNOWS.

Every function here delegates to a real parser for the grammar in question —
`urllib.parse` for an address, markdown's own literal delimiters for a link,
`int()` for a number. A parser was written by someone who read the
specification. A character test was written by someone guessing.

CLAUDE.md rule 1 is the other half of the reason this is a module and not two
copies: the two guards asked the SAME question and each answered it privately,
so each got it wrong privately. One question, one answer, imported by both.
"""

from urllib.parse import urlparse

#: The literal delimiter between a markdown link's label and its target.
#: `[label](target)` is a defined grammar with a written specification; this is
#: its punctuation, not a shape somebody noticed.
LINK_DELIMITER = "]("


def is_web_address(token):
    """True when this token is a URL. Asked of the URL parser, not of its shape.

    `urlparse` fills `netloc` only when it saw a `//` after the scheme:

        urlparse("http://127.0.0.1:8010")  -> scheme "http",        netloc set
        urlparse("provider.py:248")        -> scheme "provider.py", netloc EMPTY

    Requiring BOTH is what separates them. The scheme alone would not: a scheme
    may legally contain dots, so `provider.py` is a well-formed scheme, and a
    guard checking only for one would go blind to every real citation.
    """
    try:
        parsed = urlparse(token)
    except ValueError:
        return False
    return bool(parsed.scheme) and bool(parsed.netloc)


def split_markdown_links(text):
    """`[label](target)` separated into two tokens — the label, then the target.

    A reader that splits on whitespace sees `[Dashboard](http://127.0.0.1:8010)`
    as ONE word, and no parser can make sense of a label and an address fused
    together. Putting a space at markdown's own delimiter hands the reader two
    words it can each ask a parser about. The surrounding brackets are ordinary
    punctuation and come off in the caller's own trimming.

    This is a parse, not a guess: `](` is the inline link's written punctuation.

    Use this where BOTH halves matter — a citation guard needs to see
    `.claude/hooks/citation-guard.py:41` inside a link as readily as beside one.
    Use `drop_link_targets` instead where the address is furniture.
    """
    return text.replace(LINK_DELIMITER, "] (")


def drop_link_targets(text):
    """`[label](target)` with the target removed. The address is shown, not said.

    Use this where the address is furniture the reader clicks rather than
    language the reader has to understand — a gate judging whether prose is
    plain has no business measuring a URL.
    """
    out = []
    index, length = 0, len(text)
    while index < length:
        if text.startswith(LINK_DELIMITER, index):
            close = text.find(")", index + len(LINK_DELIMITER))
            if close != -1:
                out.append("]")
                index = close + 1
                continue
        out.append(text[index])
        index += 1
    return "".join(out)
