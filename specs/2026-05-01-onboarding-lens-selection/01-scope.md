# 01 — Scope: Onboarding Lens Selection + Bottom Navbar

**Date:** 2026-05-01
**Status:** Draft — awaiting user review

---

## Problem

After signing in via magic link, the user lands on a blank "Welcome" page with a logout button. There's no onboarding, no personalization, and no navigation structure. The app feels dead.

The backend already supports lens preferences (`Profile -[:PREFERS_LENS]-> Lens`) and uses them in trip generation. But the Flutter app has no way to create a profile, select lenses, or navigate between screens.

---

## What we're building

Three things in one scope:

1. **Welcome animation** — 1-2 second branded moment after first sign-in, then auto-advance
2. **Lens selection screen** — grid of 18 taggable lenses organized under 8 parent categories, minimum 3 required
3. **Bottom navigation bar** — 3 tabs: Explore, Lenses, Profile

---

## User flows

### First-time sign-in
```
Magic link verified → Welcome animation (1.5s)
  → "What stories interest you?" lens selection screen
    → User picks 3+ lenses → Save
      → Explore tab (empty state for now — tour building comes later)
```

### Return sign-in
```
Magic link verified → Explore tab directly (skip welcome + lens selection)
```

### Edit lenses (anytime)
```
Bottom nav → Lenses tab → same grid, pre-checked with current selections → Save
```

---

## Data model (already exists in Neo4j)

```
User -[:HAS_PROFILE]-> Profile -[:PREFERS_LENS {weight: 1.0}]-> Lens
```

- On first sign-in: backend creates User node (via /magic-link/verify)
- This scope adds: create a default Profile + PREFERS_LENS edges
- 18 selectable child lenses, 8 non-selectable parent lenses (category headers)
- `is_parent` property on Lens nodes distinguishes them

---

## Lens inventory (18 taggable)

| Parent Category | Child Lenses |
|----------------|-------------|
| History | Hidden History, War & Conflict, Dark History, Social Change |
| Architecture & Design | Historic Architecture, Modern & Contemporary Design |
| Arts & Culture | Music Heritage, Visual Art, Street Art, Film & TV Locations |
| Food & Drink | Historic Cuisine, Markets & Street Food |
| Stories & Characters | Local Legends & Folklore, Literary Heritage, Famous Residents |
| Faith & Spirituality | Historic Houses of Worship, Sacred Traditions |
| Nature & Landscape | Parks & Gardens, Waterways & Views |
| Commerce & Innovation | Historic Markets & Shopping, Science & Technology |

---

## API calls needed

All endpoints already exist in the backend:

| Action | Method | Endpoint | Notes |
|--------|--------|----------|-------|
| Fetch all lenses | GET | `/api/v1/nodes?label=Lens` | Returns all 26, filter client-side by `is_parent` |
| Create profile | POST | `/api/v1/nodes` | `{"label": "Profile", "properties": {"display_name": "..."}}` |
| Link profile to user | POST | `/api/v1/edges` | `HAS_PROFILE` edge from User → Profile |
| Save lens preference | POST | `/api/v1/edges` | `PREFERS_LENS` edge from Profile → Lens |
| Remove lens preference | DELETE | `/api/v1/edges/{edge_id}` | When user deselects a lens |
| Get user's profiles | GET | `/api/v1/edges?type=HAS_PROFILE&source_id={user_id}` | Check if profile exists |
| Get current preferences | GET | `/api/v1/edges?type=PREFERS_LENS&source_id={profile_id}` | Pre-check on edit screen |

---

## Scope boundaries

### In scope
- Welcome animation (first sign-in only)
- Lens selection grid (onboarding + edit mode)
- Bottom navbar with 3 tabs (Explore, Lenses, Profile)
- Default profile creation (auto-named, no name prompt for MVP)
- Save/update PREFERS_LENS edges
- Minimum 3 lens requirement with validation
- First-time vs return detection (has profile with lenses = return user)

### Out of scope
- Multiple profiles per user (MVP = 1 default profile)
- Profile name editing
- Lens icons or illustrations (text + category color for MVP)
- Explore tab content (empty state placeholder)
- Profile tab content beyond logout button
- Tour generation UI
- Lens weight/priority customization

---

## Flutter files to create/modify

### New files
| File | Purpose |
|------|---------|
| `lib/models/lens.dart` | Lens data model (id, name, slug, isParent, parentId) |
| `lib/services/profile_service.dart` | Profile + lens preference CRUD |
| `lib/pages/welcome_page.dart` | Animated welcome screen |
| `lib/pages/lens_selection_page.dart` | Lens grid (onboarding + edit mode) |
| `lib/widgets/bottom_nav.dart` | Bottom navigation scaffold |
| `lib/pages/explore_page.dart` | Placeholder explore tab |
| `lib/pages/profile_page.dart` | Profile tab (logout + future settings) |

### Modified files
| File | Change |
|------|--------|
| `lib/router.dart` | Add routes for welcome, lens selection, main shell with bottom nav |
| `lib/main.dart` | Register ProfileService provider |
| `lib/services/auth_service.dart` | Expose user ID (needed for profile creation) |

---

## Open questions for you

1. **Profile auto-naming:** For MVP, should the default profile be named after the user's email prefix (e.g., "sairam" from sairam@ondoway.com), or just "My Profile"?

2. **Welcome animation style:** Simple fade-in of the Ondoway logo + "Welcome" text, or something more dynamic (e.g., a map pin dropping, lens icons floating in)?

3. **Lens grid layout:** 2-column grid with category headers above each group, or a single scrollable list with sections? The 18 lenses fit in about 2 screens of scrolling either way.

4. **Save behavior on edit:** Auto-save as user taps lenses (instant feedback), or require an explicit "Save" button?

5. **Color palette:** Does Ondoway have brand colors defined anywhere, or should I pick something for the category headers?
