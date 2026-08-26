# The two hand-composed tours have MOVED

`01-place-des-vosges.md` and `02-ile-de-la-cite-notre-dame.md` now live at
`fixtures/reference-tours/`, beside the golden fixtures they calibrate.

**Why.** They were never only documents. A shipped tool reads them
(`make human-reference-tours`, `scripts/human_reference_tours.py`) and the quality
rubric is calibrated against them — they are the check that it does not reject work a
human approved. Living in a documentation folder meant a routine `Docs/` rename
deleted them and took five tests with it, on 2026-08-06.

`findings.md` stays here: it is prose for people, not data for programs. That is the
line — anything a program opens by path belongs where programs look for data.
