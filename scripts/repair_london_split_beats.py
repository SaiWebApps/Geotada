#!/usr/bin/env python3
"""One-off surgical repair of 4 London beats mangled by an old sentence splitter.

Root cause (fixed since, in src/tour/generation.split_sentences): the splitter
that ran during the 2026-07-15 London onboarding broke sentences on personal-name
initials and the "St." abbreviation, orphaning fragments as whole beat bodies:

  - london_london_bridge_wikipedia_3  "S."   <- from "The Waste Land by T. S. Eliot"
  - london_tate_britain_wikipedia_1   "...works of J."  } two fragments of ONE
  - london_tate_britain_wikipedia_2   "W."               } chunk sentence (J. M. W. Turner)
  - london_shaftesbury_avenue_wikipedia_1  "Giles and Soho."  <- from "St. Giles and Soho"

The CURRENT splitter handles all three names correctly (regression-tested), so this
is a stale-DATA repair, not a code fix. Every replacement body is grounded VERBATIM
in the beat's own Wikipedia chunk (data/london/wikipedia/*.txt) — no fabrication.
Tate beat _2 is DELETED: its content is absorbed into the now-complete beat _1.

Idempotent: re-running after a successful repair is a no-op (asserts the target
state). Run: `python scripts/repair_london_split_beats.py`
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts.beat_builder import hash_body, word_count

BEATS = Path(__file__).resolve().parent.parent / "data" / "london" / "beats.json"

# beat_id -> new script_body (also used as source_passage). Each is the FULL sentence
# taken VERBATIM from the beat's own Wikipedia chunk (data/london/wikipedia/*.txt) —
# a truncated HEAD gets its tail restored, an orphaned TAIL gets its head restored.
# `scripts/validate_beats.validate` (_check_wikipedia_grounding) confirms each is in
# the chunk; that is the no-fabrication proof.
_BODIES: dict[str, str] = {
    # --- first batch (single-letter fragments) ---
    "london_london_bridge_wikipedia_3":
        "The modern bridge is owned and maintained by Bridge House Estates, an "
        "independent charity of medieval origin overseen by the City of London "
        "Corporation.",
    "london_tate_britain_wikipedia_1":
        "Founded by Sir Henry Tate, it houses a substantial collection of the art "
        "of the United Kingdom since Tudor times, and in particular has large "
        "holdings of the works of J. M. W. Turner, who bequeathed all his own "
        "collection to the nation.",
    "london_shaftesbury_avenue_wikipedia_1":
        "Shaftesbury Avenue was built between 1877 and 1886 by the architect "
        "George Vulliamy and the engineer Sir Joseph Bazalgette, to provide a "
        "north–south traffic artery through the crowded districts of St. Giles "  # noqa: RUF001
        "and Soho.",
    # --- second batch (longer truncations the judge surfaced; whole-sentence sweep) ---
    "london_london_waterloo_station_wikipedia_3":
        "The station was the London terminus for Eurostar international trains "
        "from 1994 until 2007, when they were transferred to St. Pancras.",
    "london_nelson_s_column_wikipedia_2":
        "They depict the Battle of Cape St. Vincent, the Battle of the Nile, the "
        "Battle of Copenhagen and the death of Nelson at Trafalgar.",
    "london_nelson_s_column_wikipedia_3":
        "The sculptors were Musgrave Watson, William F. Woodington, John Ternouth "
        "and John Edward Carew, respectively.",
    "london_harrods_wikipedia_1":
        "The building was designed by C. W. Stephens for Charles Digby Harrod, and "
        "opened in 1905; it replaced the first store on the grounds founded by his "
        "father Charles Henry Harrod in 1849, which burned down in 1881.",
    "london_kensington_gardens_wikipedia_2":
        "The open spaces of Kensington Gardens, Hyde Park, Green Park, and St. "
        "James's Park together form an almost continuous \"green lung\" in the "
        "heart of London.",
    "london_sir_john_soane_s_museum_wikipedia_1":
        "The museum was established during Soane's lifetime by a private act of "
        "Parliament, Sir John Soane's Museum Act 1833 (3 & 4 Will. 4. c. 4 Pr.), "
        "which took effect on his death in 1837.",
    "london_sir_john_soane_s_museum_wikipedia_3":
        "In 1997, the trustees purchased the main house at No. 14 with the help of "
        "the Heritage Lottery Fund.",
    "london_royal_festival_hall_wikipedia_1":
        "The London Philharmonic Orchestra, the Philharmonia Orchestra, the "
        "Orchestra of the Age of Enlightenment, the London Sinfonietta, Chineke! "
        "and Aurora are resident orchestras at Southbank Centre.",
    "london_shaftesbury_avenue_wikipedia_3":
        "Between 1899 and 1902, no. 67 Shaftesbury Avenue was the location of the "
        "Bartitsu School of Arms and Physical Culture, which is the first "
        "commercial Asian martial arts training school in the Western world.",
    "london_kensal_green_cemetery_wikipedia_3":
        "The cemetery was immortalised in the lines of G. K. Chesterton's poem "
        "\"The Rolling English Road\" from his book The Flying Inn:\n\nDespite its "
        "Grecian-style buildings, the cemetery is primarily Gothic in character, "
        "due to the high number of private Gothic monuments.",
}
REPAIRS: dict[str, tuple[str, str]] = {bid: (body, body) for bid, body in _BODIES.items()}
DELETE_IDS = {"london_tate_britain_wikipedia_2"}  # absorbed into _1


def main() -> int:
    beats = json.loads(BEATS.read_text())
    by_id = {b["beat_id"]: b for b in beats}

    # Idempotency / preconditions: either already repaired, or in the known-bad state.
    for bid, (body, _passage) in REPAIRS.items():
        b = by_id.get(bid)
        if b is None:
            print(f"ABORT: {bid} not found", file=sys.stderr)
            return 1
        if b["script_body"] == body:
            print(f"skip (already repaired): {bid}")

    # Apply body/passage/hash repairs.
    for bid, (body, passage) in REPAIRS.items():
        b = by_id[bid]
        b["script_body"] = body
        b["source_passage"] = passage
        b["script_body_hash"] = hash_body(body)

    # Delete absorbed fragments.
    new_beats = [b for b in beats if b["beat_id"] not in DELETE_IDS]

    # Post-conditions (fail loudly rather than write bad data):
    #  1. no beat body under 4 words (the fragment signature; real corpus min is 8+)
    #  2. no duplicate script_body_hash file-wide (validate_beats enforces this)
    frags = [(b["beat_id"], b["script_body"]) for b in new_beats
             if 0 < word_count(b["script_body"]) < 4]
    assert not frags, f"fragments remain: {frags}"
    hashes: dict[str, str] = {}
    for b in new_beats:
        h = b["script_body_hash"]
        assert h not in hashes, f"hash collision: {b['beat_id']} vs {hashes[h]}"
        hashes[h] = b["beat_id"]
        assert h == hash_body(b["script_body"]), f"stale hash: {b['beat_id']}"

    BEATS.write_text(json.dumps(new_beats, indent=2, ensure_ascii=False) + "\n")
    print(f"repaired {len(REPAIRS)} beats, deleted {len(DELETE_IDS)}; "
          f"{len(beats)} -> {len(new_beats)} total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
