# Editorial Workbench UI Bug Report — 2026-03-11

## Summary

- Tests run: 56
- Issues found: 10 (2 critical, 8 major, 0 minor)
- Screenshots captured: 10

## Issues

### [Major] Lens dropdown has 1 options instead of 12+

- **Flow:** Beat Rendering
- **Steps:**
  1. Check lens select option count
- **Expected:** 12+ options in lens dropdown
- **Actual:** 1 options found
- **Screenshot:** [screenshots/ac9-lens-count-220620.png](screenshots/ac9-lens-count-220620.png)

### [Critical] POI upload did not complete — no uploaded badge or success toast

- **Flow:** Upload Flow
- **Steps:**
  1. Navigate to valid POI (Harbor Lighthouse)
  2. Click Mark as Complete
  3. Wait 3s for upload
  4. Check for .badge-uploaded or #successToast
- **Expected:** POI shows uploaded badge or success toast appears
- **Actual:** Uploaded badge: False, Toast: False
- **Screenshot:** [screenshots/ac8-upload-failed-220646.png](screenshots/ac8-upload-failed-220646.png)

### [Critical] No hard conflict badge found after triggering Mark as Complete

- **Flow:** Conflict Detection — Hard Match
- **Steps:**
  1. Click Mark as Complete on conflict-target POI
  2. Beat A shares lens 'hidden_history' with seeded beat
  3. Check for .beat-conflict-badge-hard
- **Expected:** Red hard conflict badge visible on beat A
- **Actual:** Hard badges found: 0
- **Screenshot:** [screenshots/ac13-no-hard-badge-220655.png](screenshots/ac13-no-hard-badge-220655.png)

### [Major] No side-by-side comparison panel for hard conflict

- **Flow:** Conflict Detection — Hard Match
- **Steps:**
  1. Check for .conflict-side panel
- **Expected:** Side-by-side panel visible
- **Actual:** Found 0 panels
- **Screenshot:** [screenshots/ac13-no-side-by-side-220657.png](screenshots/ac13-no-side-by-side-220657.png)

### [Major] Soft conflict beat C missing amber conflict badge

- **Flow:** Conflict Detection — Soft ≥70%
- **Steps:**
  1. Check beat C (food_culinary, 84% Jaccard vs seed 2)
  2. Look for amber badge with similarity percentage
- **Expected:** Amber badge with 'Conflict (XX% similar)'
- **Actual:** Badge found: False, text: ''
- **Screenshot:** [screenshots/ac15-no-soft-badge-220702.png](screenshots/ac15-no-soft-badge-220702.png)

### [Major] No side-by-side panel for soft conflict beat C

- **Flow:** Conflict Detection — Soft ≥70%
- **Steps:**
  1. Check for .conflict-side in beat C card
- **Expected:** Side-by-side panel visible
- **Actual:** Found 0 panels
- **Screenshot:** [screenshots/ac15-no-side-by-side-220703.png](screenshots/ac15-no-side-by-side-220703.png)

### [Major] Review-band beat D missing review badge

- **Flow:** Conflict Detection — Review 30-69%
- **Steps:**
  1. Check beat D (art_street, 56% Jaccard vs seed 3)
  2. Look for .beat-conflict-badge-review
- **Expected:** Yellow review badge with 'Review (XX% similar)'
- **Actual:** Review badges found: 0
- **Screenshot:** [screenshots/ac16-no-review-badge-220706.png](screenshots/ac16-no-review-badge-220706.png)

### [Major] Could not find 'replace' resolution action on beat #1

- **Flow:** Conflict Resolution — Replace
- **Steps:**
  1. Look for 'replace' button/option on beat card
- **Expected:** 'Replace' action available
- **Actual:** Action not found
- **Screenshot:** [screenshots/ac18-replace-not-found-220711.png](screenshots/ac18-replace-not-found-220711.png)

### [Major] Could not find 'skip' resolution action on beat #3

- **Flow:** Conflict Resolution — Skip
- **Steps:**
  1. Look for 'skip' button/option on beat card
- **Expected:** 'Skip' action available
- **Actual:** Action not found
- **Screenshot:** [screenshots/ac18-skip-not-found-220714.png](screenshots/ac18-skip-not-found-220714.png)

### [Major] Could not find 'Merge' action on beat #4

- **Flow:** Conflict Resolution — Merge
- **Steps:**
  1. Look for 'Merge' button on review-band beat
- **Expected:** 'Merge' action available
- **Actual:** Not found
- **Screenshot:** [screenshots/ac18-merge-not-found-220717.png](screenshots/ac18-merge-not-found-220717.png)
