# Replanned days drop stale lines instead of refusing or charging

A mid-walk replan keeps the day's places and audio but changes their order,
so a kept line can become false where it now plays. The day is never refused
over this, and fixing it is never sold separately: every kept line is
re-checked against its new position; a line that fails is dropped from
playback immediately, its script is regenerated in the replan response (the
deterministic nav template is always available and always correct for the new
pair), and its audio is synthesized in the background with the walker's
arrival at that leg as the deadline — the corrected text shows on screen if
the audio misses it. Regenerated lines pass the same floors as first
authoring.

## Considered Options

- **Refuse the replan** — punishes the traveller mid-walk for staleness that
  is ours, and breaks the personas with hard deadlines worst.
- **A paid dynamic-replan tier** — the pricing model promises unlimited
  changes inside the Day Pass and rejects metering the living session; a
  surcharge here contradicts it.
- **Re-author everything synchronously** — audio latency mid-walk for lines
  the walker may never reach.
