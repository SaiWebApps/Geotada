# Ondoway

Ondoway builds GPS-triggered audio walking tours: a person asks for a day in a
city and hears stories told at the places where they stand. One context covers
the whole product — planner, authoring, playback, workbench.

## Language

**Subject**:
An area of interest a traveller picks to steer their day. The
traveller-facing word; in code and data the same concept is called a lens.
_Avoid_: category, topic, genre, interest tag

**Lens**:
The code and corpus name for a subject. One concept with four roles: it
steers which places are picked, constrains which beats may speak at a stop,
colours the diction of the narration, and names the served subject on screen.
A parent lens stands for all of its children. The vocabulary is fixed — a
closed set, not free text.
_Avoid_: filter (it also orders and labels), register (one of its roles, not
the concept)

**Beat**:
One unit of corpus story, tied to a place and tagged with exactly one leaf
lens. Beats are the only source of a stop's words.

**Stop**:
One place on a day's route where the walker stands and a piece of the story
plays.

**Leg**:
The walk between two consecutive stops. A leg's narration belongs to that
specific pair; when the pair changes, the old words no longer apply.

**Footprint**:
The area whose entry makes a stop's piece play. Large places have large
footprints; words that claim "right here" are true only near the thing
itself, never at the footprint's edge.

**Anchor**:
A reviewed spot inside a large place's footprint where one chapter of the
story plays — a grave, a wall, a doorway.

**Replan**:
A mid-walk re-cut of the day: the same places kept and re-ordered, no new
audio owed. Every kept line is re-checked where it now lands; a line that is
no longer true is dropped — silence over wrongness — its script rewritten at
once and its audio caught up in the background.
