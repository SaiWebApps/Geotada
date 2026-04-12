# Editorial Workbench UI Bug Report — 2026-04-11

## Summary

- Tests run: 58
- Issues found: 6 (1 critical, 5 major, 0 minor)
- Screenshots captured: 6

## Issues

### [Critical] Worklist shows 13 POIs instead of 12

- **Flow:** Worklist Rendering
- **Steps:**
  1. Load 12-entry fixture
  2. Resolve duplicate names
  3. Check worklist row count
- **Expected:** 12 .worklist-row elements visible
- **Actual:** Found 13 rows
- **Screenshot:** [screenshots/ac1-worklist-count-133541.png](screenshots/ac1-worklist-count-133541.png)

### [Major] Soft conflict beat C missing amber conflict badge

- **Flow:** Conflict Detection — Soft ≥70%
- **Steps:**
  1. Check beat C (food_culinary, 84% Jaccard vs seed 2)
  2. Look for amber badge with similarity percentage
- **Expected:** Amber badge with 'Conflict (XX% similar)'
- **Actual:** Badge found: False, text: ''
- **Screenshot:** [screenshots/ac15-no-soft-badge-133651.png](screenshots/ac15-no-soft-badge-133651.png)

### [Major] No side-by-side panel for soft conflict beat C

- **Flow:** Conflict Detection — Soft ≥70%
- **Steps:**
  1. Check for .conflict-side in beat C card
- **Expected:** Side-by-side panel visible
- **Actual:** Found 0 panels
- **Screenshot:** [screenshots/ac15-no-side-by-side-133651.png](screenshots/ac15-no-side-by-side-133651.png)

### [Major] Review-band beat D missing review badge

- **Flow:** Conflict Detection — Review 30-69%
- **Steps:**
  1. Check beat D (art_street, 56% Jaccard vs seed 3)
  2. Look for .beat-conflict-badge-review
- **Expected:** Yellow review badge with 'Review (XX% similar)'
- **Actual:** Review badges found: 0
- **Screenshot:** [screenshots/ac16-no-review-badge-133652.png](screenshots/ac16-no-review-badge-133652.png)

### [Major] Could not find 'skip' resolution action on beat #3

- **Flow:** Conflict Resolution — Skip
- **Steps:**
  1. Look for 'skip' button/option on beat card
- **Expected:** 'Skip' action available
- **Actual:** Action not found
- **Screenshot:** [screenshots/ac18-skip-not-found-133654.png](screenshots/ac18-skip-not-found-133654.png)

### [Major] Could not find 'Merge' action on beat #1

- **Flow:** Conflict Resolution — Merge
- **Steps:**
  1. Look for 'Merge' button on review-band beat
- **Expected:** 'Merge' action available
- **Actual:** Not found
- **Screenshot:** [screenshots/ac18-merge-not-found-133655.png](screenshots/ac18-merge-not-found-133655.png)
