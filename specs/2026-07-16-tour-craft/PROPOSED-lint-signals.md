# LINT — proposed new signals

# LINT — proposed new signals (spec, ready to implement)

Target file: `/Users/sairambkrishnan/git/ondoway/src/tour/narration_quality.py`. All line refs below are against the current file.

## 0. Global design decisions (apply to every signal)

These resolve the tension between "give me each signal's composite fold-in" and lint-gap #11 ("DO NOT fold any new signal into the two composites"):

- **Two classes of new signal.** (a) *New independent signals* → surfaced only as their own `hits` / `per_100w` entry or their own dataclass rate field; they do **not** enter `stilted_score`/`engagement_score` (gap #11). (b) *Extensions of an existing lexicon* (`_MORALIZING`, `_PUFFERY`, `_EMPTY_TRANSITION`, `_LOOK_INITIAL`) → the new matches flow through the *existing* composite term for that lexicon (1.6 / 1.4 / 1.0 / 0.7 weights already at lines 180–192). That is intended: it is the *same* phenomenon, not a new axis, so no new weight is added. Gap #11's "no new signal in the composite" is honored — no *new term* is introduced anywhere.
- **`hits` stays the trustworthy output** (module docstring lines 3–5). Every penalty-type signal goes into the `tells` dict (lines 158–164) so it produces both a quoted `hits[...]` list and a `per_100w[...]` rate for free. Every positive/engagement signal becomes a new `float` field on `NarrationQuality` (like `second_person_rate`, line 129), reported but not folded.
- **Freeze the composite formula** except the one deletion in §11 (drop the `year_density` term). Do not add terms.
- **Test obligation (not edited here):** each new penalty tell needs a unit test with (i) a positive example that fires and (ii) a false-positive guard that must *not* fire; each positive rate needs a hit + a near-zero case. Any existing test that asserts the exact key-set of `per_100w` or the field-set of `NarrationQuality` must be updated for the additions in §12.

---

## S1 — `_PARTICIPLE_TAIL` (significance-participle clause)  [NEW · stilted-penalty]

- **Regex:**
```python
_PARTICIPLE_TAIL = re.compile(
    r",\s+(highlighting|underscoring|emphasi[sz]ing|reflecting|symboli[sz]ing|"
    r"showcasing|cementing|solidifying|marking|shaping|ensuring|reinforcing|"
    r"contributing|fostering|embodying|serving|paving)\b",
    re.IGNORECASE,
)
```
- **Matches:** a comma followed by a significance/"-ing" participle that opens a trailing editorial clause (", underscoring its importance", ", cementing its legacy"). Lexicon-anchored on purpose so ordinary progressives (", waving", ", running") do **not** fire.
- **Source:** Wikipedia *Signs of AI Writing* — trailing present-participle "significance" clauses (Superficial-analysis / Present-Participle tell); rubric WHAT-TO-AVOID ("significance-participle tails").
- **Penalty / engagement:** stilted-penalty.
- **Composite:** report-only. New key `"participle_tail"` in the `tells` dict → auto `hits` + `per_100w`; **not** added to `penalties`.
- **Overlap guard:** does not double-count with `_AI_VOCAB` (that matches `underscore[sd]?`, not `underscoring`). Minor benign overlap possible with `_MORALIZING`'s `mark(s|ing|ed)? a pivotal` on ", marking a pivotal…" — different metrics (one report-only, one composite), acceptable. See S5 for the `showcasing` de-dup rule.

## S2 — extend `_MORALIZING` (significance/legacy closers)  [EXTENSION · stilted-penalty]

- **Regex additions** (append alternations inside `_MORALIZING`, lines 42–51; fold the new `mark…` branch into the existing `mark(s|ing|ed)? a pivotal` to avoid a partial duplicate):
```python
    r"|\bmark(s|ed|ing)?\s+a\s+(pivotal|turning\s+point|watershed|new\s+era|new\s+chapter)\b"
    r"|\bset(s|ting)?\s+the\s+stage\s+for\b"
    r"|\brepresent(s|ed|ing)?\s+a\s+(shift|departure|turning\s+point)\b"
    r"|\bcement(s|ed|ing)?\s+(its|their)\s+(place|legacy|status)\b"
    r"|\bleft\s+an\s+(indelible|lasting)\s+(mark|legacy)\b"
    r"|\b(cultural|historical|ever-evolving)\s+landscape\b"
```
(Replace the existing `\bmark(s|ing|ed)?\s+a\s+pivotal\b` line with the merged first branch above.)
- **Matches:** the flat-ending "this mattered" closers the tour complaint names — "marked a turning point", "set the stage for", "cemented its legacy", "left an indelible mark", "cultural landscape".
- **Source:** Wikipedia *Signs of AI Writing* (Undue Emphasis on Significance/Legacy) + Charlie Fink *Seven Tells* (inspirational pivot); rubric WHAT-TO-AVOID.
- **Penalty / engagement:** stilted-penalty.
- **Composite:** flows through the **existing** `moralizing_closer` term (`1.6 * per_100["moralizing_closer"]`, line 180). No new term. This is the highest-value gap — same axis, already weighted.

## S3 — `_CONTRACTION` rate  [NEW · engagement-signal, report-only]

- **Metric / regex** (curated base-word list so possessive noun `'s`, e.g. "Napoleon's", does **not** inflate it):
```python
_CONTRACTION = re.compile(
    r"\b(?:i|you|we|they|he|she|it|that|there|who|what|where|here|let|"
    r"is|are|was|were|do|does|did|have|has|had|can|could|would|should|will|"
    r"won|ain|don|doesn|didn|isn|aren|wasn|weren|hasn|haven|hadn|"
    r"couldn|wouldn|shouldn|mustn)['’](?:s|re|ll|ve|d|t|m)\b",
    re.IGNORECASE,
)
# contraction_rate = _rate_per_100(len(_CONTRACTION.findall(text)), n_words)
```
- **Matches:** genuine spoken contractions ("you're", "it's", "don't", "I'm", "there's"). Curated bases exclude proper-noun possessives.
- **Source:** NPR Training *Would You Say It That Way?* / Ira Glass; rubric VOICE (conversational register). A near-zero rate is the cleanest tell of stiff written-for-the-eye prose.
- **Penalty / engagement:** engagement-signal (positive).
- **Composite:** **report-only** — new field `contraction_rate`. Gap #3 is explicit: "Surface as report-only rate, NOT folded into the composite." Use `['’]` to catch both apostrophe glyphs.

## S4 — `_VIVID_VERB` rate (human-stakes verbs)  [NEW · engagement-signal, report-only]

- **Regex** (verbatim from gap #4, kept tight to limit FPs):
```python
_VIVID_VERB = re.compile(
    r"\b(fled|hid|plotted|betrayed|starved|rioted|burned|stormed|crowned|"
    r"executed|beheaded|buried|smuggled|defied|drowned|murdered|besieged|"
    r"assassinated|imprisoned|exiled|revolted|conspired)\b",
    re.IGNORECASE,
)
# vivid_verb_rate = _rate_per_100(len(_VIVID_VERB.findall(text)), n_words)
```
- **Matches:** concrete narrative-of-people verbs signalling stakes/conflict. Near-zero = a place described with no story ("reading Wikipedia aloud").
- **Source:** VoiceMap "tell one person's story, not the statistics'"; Freeman Tilden (human stakes over aggregate); rubric FACT-INTO-MOMENT.
- **Penalty / engagement:** engagement-signal (positive).
- **Composite:** report-only — new field `vivid_verb_rate`. Not folded (gap #11).

## S5 — extend `_PUFFERY`  [EXTENSION · stilted-penalty]

- **Regex additions** (append inside `_PUFFERY`, lines 54–60):
```python
    r"|in\s+the\s+heart\s+of|home\s+to|renowned|world-class|unparalleled|"
    r"sprawling|diverse\s+array|steeped\s+in\s+history"
```
- **De-dup decision:** gap #5 lists `showcasing`, but S1 already catches the characteristic ", showcasing …". **Do not add `showcasing` to `_PUFFERY`** — leave it to `_PARTICIPLE_TAIL` so one phrase never inflates two metrics.
- **Matches:** promotional/advertisement clichés — "in the heart of", "home to", "renowned", "world-class", "steeped in history".
- **Source:** Wikipedia *Signs of AI Writing* (Promotional / Advertisement Language); rubric WHAT-TO-AVOID.
- **Penalty / engagement:** stilted-penalty.
- **Composite:** flows through the **existing** `puffery` term (`1.4 * per_100["puffery"]`, line 181). No new term.
- **Known mild FP:** "home to 2 million people" is descriptive; accepted because `hits` quotes it for human eyeball.

## S6 — question/imagination openers  [NEW rates + EXTENSION · engagement-signal]

Three pieces:
- **S6a `_QUESTION_OPENER`** (sentence-initial provocation), reported as a sentence-fraction like `look_rate` (lines 173–175):
```python
_QUESTION_OPENER = re.compile(
    r"^(ever\b|notice\b|imagine\b|picture\b|what\s+if\b|have\s+you\b|"
    r"did\s+you\s+know\b|why\s+(do|is|was|does|did)\b)",
    re.IGNORECASE,
)
# question_opener_rate = round(sum(1 for s in sents if _QUESTION_OPENER.match(s)) / n_sents, 3) if n_sents else 0.0
```
- **S6b `question_rate`** = fraction of sentences ending in `?`:
```python
# question_rate = round(sum(1 for s in sents if s.rstrip().endswith("?")) / n_sents, 3) if n_sents else 0.0
```
- **S6c** rename `_LOOK_INITIAL` → `_PROMPT_INITIAL` and add imagination verbs (extends the *existing* `look_prompt_rate`, keep that field name for back-compat):
```python
_PROMPT_INITIAL = re.compile(
    r"^(look|notice|spot|glance|watch|listen|turn|cross|walk|stop|pause|head|"
    r"carry\s+on|step|face|find|imagine|picture|close\s+your\s+eyes|"
    r"think\s+(of|back|about)|feel)\b",
    re.IGNORECASE,
)
```
- **Matches:** engaging openers that provoke rather than instruct — "Ever wonder…", "Imagine…", "What if…", questions, and imaginative direct-address cues.
- **Source:** Freeman Tilden ("provocation, not instruction"); Rick Steves / VoiceMap direct address + Theatre of the Mind; rubric STRUCTURE/HOOK. (Consistent with the paired craft-gap that relaxes the `imagine/picture` ban.)
- **Penalty / engagement:** engagement-signal (positive).
- **Composite:** `question_opener_rate` and `question_rate` are **new report-only fields** (not folded). The `_PROMPT_INITIAL` extension flows through the **existing** `engagement_score` term (`0.7 * look_rate`, line 192) — no new term.

## S7 — `_SUPERLATIVE_HEDGE`  [NEW · stilted-penalty]

- **Regex** (verbatim from gap #7; targets the *hedged* frame, not bare factual superlatives):
```python
_SUPERLATIVE_HEDGE = re.compile(
    r"\b(one|among)\s+(of\s+)?the\s+most\s+\w+"
    r"|\b(widely|generally)\s+(regarded|considered|recogni[sz]ed|known)\s+as\b"
    r"|\barguably\s+(the|one)\b",
    re.IGNORECASE,
)
```
- **Matches:** "one of the most beautiful", "widely regarded as", "arguably the finest" — weasel-worded significance inflation.
- **Source:** Wikipedia *Signs of AI Writing* (weasel words) **and** project Pipeline Guardrail #4 (superlatives are never auto-resolved); rubric WHAT-TO-AVOID.
- **Penalty / engagement:** stilted-penalty.
- **Composite:** report-only. New key `"superlative_hedge"` in `tells` → auto `hits` + `per_100w`; not added to `penalties` (gap #11).

## S8 — extend `_EMPTY_TRANSITION` (throat-clearing)  [EXTENSION · stilted-penalty]

- **Regex** — replace the two existing "worth noting" branches (lines 74–75) with a consolidated set, keeping the sentence-start anchor:
```python
_EMPTY_TRANSITION = re.compile(
    r"(^|[.!?]\s+)(Furthermore|Moreover|Additionally|In addition(?!\s+to)|Indeed|"
    r"Notably|Importantly|Ultimately|In conclusion|"
    r"It'?s\s+(important|worth)\s+(to\s+)?(note|noting|remember|remembering|mention|mentioning)|"
    r"It\s+is\s+worth\s+noting|It\s+should\s+be\s+noted|"
    r"Keep\s+in\s+mind|Needless\s+to\s+say)\b",
    re.IGNORECASE,
)
```
- **Matches:** sentence-initial filler — "It's important to note", "It should be noted", "Keep in mind", "Needless to say".
- **Source:** Wikipedia *Signs of AI Writing* (throat-clearing / editorializing); rubric WHAT-TO-AVOID.
- **Penalty / engagement:** stilted-penalty.
- **Composite:** flows through the **existing** `empty_transition` term (`1.0 * per_100["empty_transition"]`, line 183). No new term.

## S9 — ear-difficulty rates  [NEW · report-only, not folded]

Three report-only metrics for "hard to hear" prose:
```python
_NOMINALIZATION = re.compile(r"\b\w{4,}(?:tion|ment|ance|ence|ity|ism)s?\b", re.IGNORECASE)
_PASSIVE = re.compile(
    r"\b(is|are|was|were|be|been|being)\s+"
    r"(\w+ed|built|born|known|made|held|found|written|given|shown|set|kept|told|sold)\b",
    re.IGNORECASE,
)
# nominalization_rate = _rate_per_100(len(_NOMINALIZATION.findall(text)), n_words)
# passive_rate        = _rate_per_100(len(_PASSIVE.findall(text)), n_words)
# clauses = [c for c in re.split(r"[,;:—.!?]", text) if c.strip()]
# mean_clause_words = round(sum(len(_words(c)) for c in clauses) / len(clauses), 2) if clauses else 0.0
```
- **Matches:** zombie nouns (`-tion/-ment/-ance/-ence/-ity/-ism`), be-verb + past-participle passives, and mean words per clause (clause-density).
- **Source:** plain-language / write-for-the-ear canon — look2innovate, MediaHelpingMedia *Radio News Script*, VoiceMap *Writing for Voice*; rubric RHYTHM-FOR-THE-EAR. These are the "hard to hear" tells independent of sentence length.
- **Penalty / engagement:** diagnostic (ear-difficulty); treated as report-only.
- **Composite:** **not folded** (gap #9 + gap #11 explicit). New fields `nominalization_rate`, `passive_rate`, `mean_clause_words`.
- **Known FPs (accept, or optionally tighten):** `_NOMINALIZATION` fires on "moment", "city", "France", "science"; `_PASSIVE`'s `\w+ed` catches predicate adjectives ("was tired"). Acceptable as a coarse proxy since it is report-only and never gates. Optional tightening: raise the nominalization min-length to `{6,}` and add a tiny stoplist.

## S10 — `_TRICOLON` (rule-of-three)  [NEW · stilted-penalty]

- **Regex:**
```python
_TRICOLON = re.compile(r"\b([A-Za-z]{3,}),\s+([A-Za-z]{3,}),?\s+and\s+([A-Za-z]{3,})\b")
```
- **Matches:** "X, Y, and Z" / "X, Y and Z" three-item parallel lists that read robotic aloud. `hits["rule_of_three"]` quotes each triplet so a human can judge adjective-tricolons vs. legitimate noun lists.
- **Source:** Charlie Fink *Seven Tells* (Triplet Framing) + Wikipedia *Signs of AI Writing* (rule-of-three); rubric WHAT-TO-AVOID.
- **Penalty / engagement:** stilted-penalty.
- **Composite:** report-only. New key `"rule_of_three"` in `tells` → auto `hits` + `per_100w`; not folded.
- **FP note:** noun lists ("bread, cheese, and wine") also match. Because it is report-only and the module's contract is "eyeball the `hits`", keep it permissive. Optional tightening if noise is high: require ≥1 of the three tokens to end in an adjective suffix `(ic|al|ive|ous|ful|ent|ant|ing|y)`. (The gap's separate suggestion to extend the rapidfuzz same-beat dedup to flag parallel lists is out of scope for this module — note it for `compose.py`/`_dedup_composed`, do not implement here.)

## S11 — composite + `_YEAR` cleanup  [MODIFY]

- **Drop the year term** from `penalties` (line 185): delete `+ 0.15 * per_100["year_density"]`. Recompute nothing else; the `/ 6.0` normalizer (line 190) is unchanged (it is just a squash, not a mean).
- **Keep `year_density` report-only** — leave line 167 (`per_100["year_density"] = ...`) in place.
- **Simplify `_YEAR`** (delete the brittle enumerated unit blocklist, lines 89–95):
```python
_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})s?\b")
```
- **Source:** the module's own docstring (composites are COARSE, lines 15–18) + rubric FACT-INTO-MOMENT (concrete > abstract — a history tour should not be penalized for dated facts).
- **Penalty / engagement:** removes a weak penalty.
- **Composite:** this is the only change to the formula. After it, no new signal enters either composite; `stilted_score`/`engagement_score` are effectively frozen at their current definition minus the year term.
- **Tradeoff to note:** without the blocklist, `year_density` will now count "2000 workers" as a year. Accepted because it is purely report-only and the blocklist was leaky/brittle (gap #11).

---

## 12. Summary of code touches (nothing else changes)

**New `tells` dict keys (lines 158–164) → auto `hits` + `per_100w`, NOT in `penalties`:**
- `"participle_tail"` (S1), `"superlative_hedge"` (S7), `"rule_of_three"` (S10)

**Extended existing lexicons (matches flow through their existing composite term):**
- `_MORALIZING` (S2), `_PUFFERY` (S5), `_EMPTY_TRANSITION` (S8), `_LOOK_INITIAL`→`_PROMPT_INITIAL` (S6c)

**New `NarrationQuality` fields (lines 122–133), all report-only floats defaulting to `0.0`:**
- `contraction_rate` (S3), `vivid_verb_rate` (S4), `question_opener_rate` (S6a), `question_rate` (S6b), `nominalization_rate` (S9), `passive_rate` (S9), `mean_clause_words` (S9)

**Composite (lines 179–193):** remove the `year_density` term only; add nothing.
**`_YEAR` (lines 89–95):** collapse to the bare 4-digit pattern.

**Net effect on the two composites:** `stilted_score` loses the year term; `engagement_score` gains breadth only through the `_PROMPT_INITIAL` extension (existing term). Every genuinely new axis is report-only, honoring lint-gap #11.

**Housekeeping (optional):** update the module docstring (lines 6–9) to name the added surface features; update `__all__` unchanged (no new public symbols).
