# 06 — Julien, who lives here

**Who.** 37, lives in the 11th, has lived in Paris eleven years. Walks constantly. Has taken
visiting relatives to Notre-Dame perhaps forty times and would be happy never to see it again.

**The request.** Start Père-Lachaise gate, open walk, two hours, interest: hidden history.
Sunday, 09:30.

**What makes him different from a tourist.** He is not trying to see Paris. He is trying to be
told something he does not already know about a street he walks down every week. **Novelty is the
entire product.** A tour that is 80% excellent and 20% familiar is a tour he switches off, because
the familiar parts tell him the rest is probably wrong too.

## The two hours

1. 09:30–09:38 — Walks from the gate. **Skips the famous graves entirely.** Any route built around
   Morrison, Wilde and Piaf has already lost him.
2. 09:38–09:58 — Twenty minutes in the north-east corner of the cemetery, at the Mur des Fédérés
   and the deportation memorials. He knows the wall. He does not know the detail he is told about
   the last week of the Commune, and that detail is why he keeps listening.
3. 09:58–10:10 — Out and down Rue de la Réunion. **A street with nothing on it that any guidebook
   names.** He passes it twice a week.
4. 10:10–10:18 — Eight minutes at the site of the old Charonne village church. A tier-2 place at
   best. **This is the highlight of his tour.**
5. 10:18–10:32 — Walks through the Rue Saint-Blaise stretch, listening the whole way.
6. 10:32–10:40 — Stops at a wall with a faded painted advertisement on it. Eight minutes. **This
   is not in the corpus and probably never will be at tier 3 or above.**
7. 10:40–10:55 — Fifteen minutes around the Père-Lachaise crematorium's columbarium — a part
   even he has never walked.
8. 10:55–11:10 — Long walk back west, continuous narration, no stops.
9. 11:10–11:22 — Twelve minutes at a courtyard off Rue de Bagnolet he has walked past for a
   decade without going into.
10. 11:22–11:30 — Ends where he can get a coffee. **He does not need to end anywhere in
    particular** — the loop constraint matters far less to him than to a visitor with a hotel.

## What this persona breaks

- **Importance is not worth.** The planner scores by importance tier and beat count. For Julien
  those scores are close to inverted: the tier-5 anchors are exactly the things he wants excluded.
  A high score should not automatically mean a stop.
- **A tour made entirely of tier-2 places must be able to be excellent.** Any floor requiring an
  anchor, or any rule that a landmark can never be silenced, produces a worse tour for him.
- **The system needs to know what he has already been told.** Novelty is only computable against
  history. Nothing today remembers what a person has heard.
- **One familiar stop poisons the tour**, disproportionately to its share of the time. The cost
  function is not linear in the number of good stops.
- **Long unbroken walking with continuous narration is a legitimate segment** (steps 5 and 8) —
  the same shape Marcus wanted for a completely different reason.
- **The best stops may not be in the corpus at all.** A painted wall advertisement is real
  content and no POI pipeline built around monuments will find it.
