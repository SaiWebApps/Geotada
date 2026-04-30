# Neo4j Database Dump — Ondoway

**Exported:** 2026-03-16
**Database:** bolt://localhost:7687
**Totals:** 68 nodes, 65 relationships

---

## Table of Contents

1. [User](#user)
2. [Profiles](#profiles)
3. [Trip](#trip)
4. [Itinerary Items](#itinerary-items)
5. [Lenses](#lenses)
6. [POIs](#pois)
7. [Narrative Beats](#narrative-beats)
8. [Relationships](#relationships)

---

## User

| Field | Value |
|---|---|
| id | `178f3e21-ca09-4139-9135-2480051b4656` |
| email | testuser@ondoway.app |
| created_at | 2026-03-13T01:11:34.446Z |
| last_logon | 2026-03-13T01:11:34.446Z |

---

## Profiles

### Profile: "Mom"

| Field | Value |
|---|---|
| id | `9e4d4fd2-07a7-4f04-a44d-b485a7416ed5` |
| display_name | Mom |
| role | Captain (IS_CAPTAIN_OF trip) |
| preferred_lenses | Hidden History, Food & Culinary Culture, Literary & Film Locations |

### Profile: "Kid"

| Field | Value |
|---|---|
| id | `a5f4bf41-56e9-4009-8c03-8d1d5a69e998` |
| display_name | Kid |
| role | Crew (IS_CREW_OF trip) |
| preferred_lenses | Art & Street Culture, Nature & Green Spaces, Local Legends & Folklore |

---

## Trip

| Field | Value |
|---|---|
| id | `0d738f52-1c9b-48d5-83db-0dfe0492de67` |
| name | Paris Spring 2026 |
| status | planning |
| start_date | 2026-04-10 |
| end_date | 2026-04-14 |
| cover_image_url | https://images.ondoway.app/trips/paris-spring.jpg |

---

## Itinerary Items

All items are on **2026-04-10**, assigned to **Profile: Mom**.

### Item 1 — Eiffel Tower

| Field | Value |
|---|---|
| id | `7a9fc64b-00ae-468a-93cb-f8ed8c4aa08e` |
| sort_order | 1 |
| start_time | 09:00Z |
| duration_min | 90 |
| status | NOT_STARTED |
| at_poi | Eiffel Tower (`ed6c1388-5e46-4a94-ab6f-1b7680841855`) |
| plays_beat | `388bd856-edda-42d1-b5eb-6d5d23226dcf` (Eiffel Tower beat) |

### Item 2 — Cafe de Flore

| Field | Value |
|---|---|
| id | `6ccc8374-c6ba-4205-8f36-d5f7507da6cf` |
| sort_order | 2 |
| start_time | 11:00Z |
| duration_min | 30 |
| status | NOT_STARTED |
| at_poi | Cafe de Flore (`e50d1c97-8e8e-4202-90ba-796fa4cfd298`) |
| plays_beat | `b25cf9d1-08df-4856-9dbd-f3c5011baed7` (Sartre/de Beauvoir beat) |

### Item 3 — Shakespeare and Company

| Field | Value |
|---|---|
| id | `2d199a30-c293-4ab5-aed9-ed80aae3d484` |
| sort_order | 3 |
| start_time | 12:00Z |
| duration_min | 45 |
| status | NOT_STARTED |
| at_poi | Shakespeare and Company (`b793b3f0-439e-4f72-a573-846380b6dd4a`) |
| plays_beat | `16fbf18f-0528-467f-897c-ad851a1e8529` (Sylvia Beach beat) |

---

## Lenses

| id | name | display_label | parent |
|---|---|---|---|
| `8911a2d2-8bff-4d42-b3af-b521199cf9dd` | arch_design | Architecture & Design | — |
| `0fc803b6-52d8-4208-8607-133aafb11869` | arch_gothic_01 | Gothic Architecture | arch_design |
| `ad1ed2ee-27dc-4125-ab70-cd052c46c4c5` | art_street | Art & Street Culture | — |
| `bf036b47-17ae-4a09-9a63-16f6077dfe34` | dark_history | Dark History | — |
| `751adc48-1db7-43b7-a7f7-3f30e4812949` | food_culinary | Food & Culinary Culture | — |
| `65c3097a-81b1-4fb5-9b67-cf6fc639ef58` | hidden_history | Hidden History | — |
| `49e6f02b-a5ec-49d2-9051-51bbe754d269` | literary_film | Literary & Film Locations | — |
| `b24b5921-df4a-4eeb-988b-e44a30b5e167` | local_legends | Local Legends & Folklore | — |
| `48ea9c3b-9add-42b8-8c95-0f8ce4875940` | music_nightlife | Music & Nightlife History | — |
| `a4f8884a-2547-4804-b61b-4b52879c89c5` | nature_green | Nature & Green Spaces | — |
| `aec10cf7-719e-4c1e-bca5-e41391d8cadc` | religious_spiritual | Religious & Spiritual Sites | — |
| `ac237219-d315-4142-b3e6-605f1e9b9c39` | revolutionary | Revolutionary Moments | — |
| `01edd264-4814-4466-bcd1-009248aa423d` | shopping_markets | Shopping & Markets | — |

---

## POIs

### Paris POIs

#### Eiffel Tower

| Field | Value |
|---|---|
| id | `ed6c1388-5e46-4a94-ab6f-1b7680841855` |
| name | Eiffel Tower |
| short_description | Iron lattice tower on the Champ de Mars, symbol of Paris. |
| location | lat 48.8584, lon 2.2945 |
| importance_tier | 5 |
| typical_duration_min | 90 |
| trigger_radius | 10 |
| kid_friendly | yes |

#### Cafe de Flore

| Field | Value |
|---|---|
| id | `e50d1c97-8e8e-4202-90ba-796fa4cfd298` |
| name | Cafe de Flore |
| short_description | Legendary Left Bank cafe, haunt of Sartre and de Beauvoir. |
| location | lat 48.854, lon 2.3325 |
| importance_tier | 3 |
| typical_duration_min | 30 |
| trigger_radius | 10 |
| kid_friendly | yes |

#### Shakespeare and Company

| Field | Value |
|---|---|
| id | `b793b3f0-439e-4f72-a573-846380b6dd4a` |
| name | Shakespeare and Company |
| short_description | Iconic English-language bookshop across from Notre-Dame. |
| location | lat 48.8526, lon 2.3471 |
| importance_tier | 2 |
| typical_duration_min | 45 |
| trigger_radius | 10 |
| kid_friendly | yes |

### Boston POIs

#### 44 Hull Street

| Field | Value |
|---|---|
| id | `2e8220a8-2aec-44c6-bb52-d0cd25331919` |
| name | 44 Hull Street |
| short_description | Boston's narrowest wood-framed house. |
| location | lat 42.3664, lon -71.056 |
| importance_tier | 1 |
| typical_duration_min | 30 |
| trigger_radius | 10 |
| kid_friendly | yes |
| created_at | 2026-03-13T01:17:20.888Z |

#### Berkeley Building

| Field | Value |
|---|---|
| id | `f62dca6a-45ce-4e4d-bf9b-b2824f8736ac` |
| name | Berkeley Building |
| name_variations | The Wedding Cake Building, Old John Hancock Building, 200 Berkeley Street, The Berkeley Building on Boylston |
| short_description | An ornate Art Nouveau commercial building known as the wedding cake. |
| location | lat 42.3501, lon -71.0718 |
| importance_tier | 1 |
| typical_duration_min | 30 |
| trigger_radius | 10 |
| kid_friendly | yes |
| created_at | 2026-03-16T02:15:36.216Z |

#### Boston City Hall

| Field | Value |
|---|---|
| id | `5cc752c1-26d9-42d0-8480-4ef7a1cecf8e` |
| name | Boston City Hall |
| short_description | The controversial Brutalist headquarters of Boston's municipal government. |
| location | lat 42.3603, lon -71.058 |
| importance_tier | 1 |
| typical_duration_min | 30 |
| trigger_radius | 10 |
| kid_friendly | yes |
| created_at | 2026-03-13T01:31:55.315Z |

#### Boston Custom House

| Field | Value |
|---|---|
| id | `60169102-b5b0-4656-850b-0ac514cc39c7` |
| name | Boston Custom House |
| name_variations | Marriott's Custom House, Custom House Tower, The Boston Clock Tower, Marriott Vacation Club Pulse at Custom House, Boston |
| short_description | Now operating as Marriott Vacation Club Pulse at Custom House, Boston. |
| location | lat 42.359069, lon -71.053369 |
| importance_tier | 1 |
| typical_duration_min | 30 |
| trigger_radius | 10 |
| kid_friendly | yes |
| created_at | 2026-03-16T01:58:29.320Z |

#### Copp's Hill Burying Ground

| Field | Value |
|---|---|
| id | `f9dce704-e6fb-4652-87c1-e7186fa7f102` |
| name | Copp's Hill Burying Ground |
| short_description | Boston's second-oldest burying ground, dating back to 1660. |
| location | lat 42.367, lon -71.056 |
| importance_tier | 1 |
| typical_duration_min | 30 |
| trigger_radius | 10 |
| kid_friendly | yes |
| created_at | 2026-03-13T01:15:12.085Z |

#### Liberty Hotel

| Field | Value |
|---|---|
| id | `a19137f8-319c-43bc-9445-d71c3a89614b` |
| name | Liberty Hotel |
| short_description | Now operating as a luxury hotel in the former Suffolk County Jail. |
| location | lat 42.3617604, lon -71.0704893 |
| importance_tier | 1 |
| typical_duration_min | 30 |
| trigger_radius | 10 |
| kid_friendly | yes |
| created_at | 2026-03-13T01:28:51.881Z |

#### Massachusetts General Hospital Bulfinch Building

| Field | Value |
|---|---|
| id | `94ac84c3-42c2-41ac-9b8d-9a1d279c0767` |
| name | Massachusetts General Hospital Bulfinch Building |
| short_description | The original granite hospital building designed by Charles Bulfinch. |
| location | lat 42.3626, lon -71.0688 |
| importance_tier | 1 |
| typical_duration_min | 30 |
| trigger_radius | 10 |
| kid_friendly | yes |
| created_at | 2026-03-13T01:29:54.804Z |

#### Massachusetts State House

| Field | Value |
|---|---|
| id | `207e9f1a-474f-446e-8c26-b7032c8eb9cd` |
| name | Massachusetts State House |
| short_description | The historic seat of the Massachusetts state government on Beacon Hill. |
| location | lat 42.3588, lon -71.0638 |
| importance_tier | 1 |
| typical_duration_min | 30 |
| trigger_radius | 10 |
| kid_friendly | yes |
| created_at | 2026-03-13T01:09:51.494Z |

#### New England Holocaust Memorial

| Field | Value |
|---|---|
| id | `8e125430-abbc-4a0b-a39f-f7b7db4e6ad6` |
| name | New England Holocaust Memorial |
| name_variations | Holocaust Memorial, Saitowitz Memorial |
| short_description | A striking glass memorial dedicated to the victims of the Holocaust. |
| location | lat 42.3612969, lon -71.0572599 |
| importance_tier | 1 |
| typical_duration_min | 30 |
| trigger_radius | 10 |
| kid_friendly | yes |
| created_at | 2026-03-16T01:50:06.997Z |

#### Old North Church

| Field | Value |
|---|---|
| id | `33e359f7-804f-4329-b61d-eac5cda803c3` |
| name | Old North Church |
| short_description | The site of the famous 'two if by sea' lantern signal of the American Revolution. |
| location | lat 42.3663, lon -71.0544 |
| importance_tier | 1 |
| typical_duration_min | 30 |
| trigger_radius | 10 |
| kid_friendly | yes |
| created_at | 2026-03-13T01:18:14.707Z |

#### Old State House

| Field | Value |
|---|---|
| id | `227a1dfd-ff15-4742-901a-1b533571b7f3` |
| name | Old State House |
| name_variations | The Old State House Museum, Second Town House, Province House, Old Provincial State House, Boston City Hall (former) |
| short_description | The oldest surviving public building in Boston. |
| location | lat 42.358769, lon -71.057806 |
| importance_tier | 1 |
| typical_duration_min | 30 |
| trigger_radius | 10 |
| kid_friendly | yes |
| created_at | 2026-03-16T02:14:16.688Z |

#### Paul Revere House

| Field | Value |
|---|---|
| id | `951ced47-f657-408f-a1c5-0aef19fcc5bb` |
| name | Paul Revere House |
| short_description | The 17th-century home of the famous silversmith and patriot. |
| location | lat 42.3637, lon -71.0537 |
| importance_tier | 1 |
| typical_duration_min | 30 |
| trigger_radius | 10 |
| kid_friendly | yes |
| created_at | 2026-03-13T01:20:31.562Z |

#### Sears' Crescent

| Field | Value |
|---|---|
| id | `14e9228c-9358-44e5-ae12-c5c8cfa37bf9` |
| name | Sears' Crescent |
| short_description | A historic curved redbrick building near City Hall Plaza. |
| location | lat 42.3606, lon -71.0588 |
| importance_tier | 1 |
| typical_duration_min | 30 |
| trigger_radius | 10 |
| kid_friendly | yes |
| created_at | 2026-03-13T01:33:07.602Z |

#### St. Stephen's Church

| Field | Value |
|---|---|
| id | `c4fe46c4-f7db-4c24-b0e7-f272cadfa9e6` |
| name | St. Stephen's Church |
| short_description | A Neoclassical church designed by Charles Bulfinch. |
| location | lat 42.3653, lon -71.0537 |
| importance_tier | 1 |
| typical_duration_min | 30 |
| trigger_radius | 10 |
| kid_friendly | yes |
| created_at | 2026-03-13T01:19:29.780Z |

#### The Boston Stone

| Field | Value |
|---|---|
| id | `132b9af6-29ee-44f0-995f-658e0666855e` |
| name | The Boston Stone |
| name_variations | Ground Zero Stone, Boston Stone, Oldest Paint-Mill in the US |
| short_description | A historic millstone used as a geographical reference point. |
| location | lat 42.361944, lon -71.056944 |
| importance_tier | 1 |
| typical_duration_min | 30 |
| trigger_radius | 10 |
| kid_friendly | yes |
| created_at | 2026-03-16T01:46:08.398Z |

#### The Steaming Kettle

| Field | Value |
|---|---|
| id | `d1404e2d-d5df-4b14-a0e6-d567c90545db` |
| name | The Steaming Kettle |
| name_variations | Oriental Tea Company Sign, Boston Tea Kettle, Giant Tea Kettle, World's Largest Tea Kettle |
| short_description | A massive, functional trade sign from the 19th century. |
| location | lat 42.359296, lon -71.059236 |
| importance_tier | 1 |
| typical_duration_min | 30 |
| trigger_radius | 10 |
| kid_friendly | yes |
| created_at | 2026-03-16T01:40:47.864Z |

#### Trinity Church

| Field | Value |
|---|---|
| id | `9b0d9aae-d825-4889-8430-f51fd00aa95b` |
| name | Trinity Church |
| name_variations | Trinity Church in the City of Boston, H.H. Richardson's Trinity Church |
| short_description | A masterpiece of American Romanesque architecture. |
| location | lat 42.35002, lon -71.07548 |
| importance_tier | 1 |
| typical_duration_min | 30 |
| trigger_radius | 10 |
| kid_friendly | yes |
| created_at | 2026-03-16T02:11:23.588Z |

#### Union Oyster House

| Field | Value |
|---|---|
| id | `8d9d2250-0ae5-4a39-a210-6910b716e9f4` |
| name | Union Oyster House |
| name_variations | Atwood & Bacon Oyster House, Oldest Restaurant in America, Atwood & Bacon, Atwood |
| short_description | The oldest continuously operating restaurant in the United States. |
| location | lat 42.361389, lon -71.056944 |
| importance_tier | 1 |
| typical_duration_min | 30 |
| trigger_radius | 10 |
| kid_friendly | yes |
| created_at | 2026-03-16T01:43:09.250Z |

---

## Narrative Beats

### Beats linked to POIs (via HAS_BEAT)

#### Beat: Eiffel Tower

| Field | Value |
|---|---|
| id | `388bd856-edda-42d1-b5eb-6d5d23226dcf` |
| poi | Eiffel Tower |
| tagged_with | arch_design, hidden_history |
| duration_sec | 300 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| audio_url | s3://ondoway-audio/placeholder/eiffel_tower.mp3 |

> Look up. Every rivet you see was placed by hand — 2.5 million of them. Gustave Eiffel didn't build this for beauty; he built it to prove iron could touch the sky. Parisians called it an eyesore. Now it's the most visited paid monument on Earth.

---

#### Beat 1: Cafe de Flore — Existentialist Cafe

| Field | Value |
|---|---|
| id | `b25cf9d1-08df-4856-9dbd-f3c5011baed7` |
| poi | Cafe de Flore |
| tagged_with | literary_film |
| duration_sec | 180 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| audio_url | s3://ondoway-audio/placeholder/cafe_de_flore.mp3 |

> This corner table — yes, this exact one — is where Sartre scribbled Being and Nothingness while chain-smoking Gauloises. De Beauvoir sat across from him, writing her own masterpiece. The hot chocolate recipe hasn't changed since 1887.

---

#### Beat 2: Cafe de Flore — WWII Resistance

| Field | Value |
|---|---|
| id | `4a535603-828b-4545-af66-966912f67c1d` |
| poi | Cafe de Flore |
| tagged_with | dark_history |
| duration_sec | 180 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| audio_url | s3://ondoway-audio/placeholder/cafe_de_flore.mp3 |

> During the Occupation, Cafe de Flore became an unlikely resistance hub. The Nazis preferred the Deux Magots next door — which made Flore the place where intellectuals quietly planned acts of cultural defiance.

---

#### Beat: Shakespeare and Company

| Field | Value |
|---|---|
| id | `16fbf18f-0528-467f-897c-ad851a1e8529` |
| poi | Shakespeare and Company |
| tagged_with | literary_film, local_legends |
| duration_sec | 120 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| audio_url | s3://ondoway-audio/placeholder/shakespeare_and_company.mp3 |

> Sylvia Beach opened the original shop in 1919 and published Ulysses when no one else would. This reincarnation, opened by George Whitman in 1951, still lets writers sleep among the shelves — they call them Tumbleweeds.

---

#### Beat: Massachusetts State House

| Field | Value |
|---|---|
| id | `da661420-2652-4e7d-ab8c-c2d3620e7adb` |
| poi | Massachusetts State House |
| tagged_with | local_legends |
| duration_sec | 300 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| created_at | 2026-03-13T01:13:49.659Z |

> In the mid-19th century, the legendary Oliver Wendell Holmes looked up at this very structure and coined a phrase that would stick forever: the 'Hub of the Universe.' While he was likely poking a bit of fun at the high and lofty ideals of his fellow Bostonians, the nickname was embraced with zero irony. Face the golden dome and imagine it as the literal center of a spinning cosmos. Completed in 1798 by architect Charles Bulfinch, the building was designed to command the skyline. The scale of the Neoclassical columns and the sheer brilliance of the dome were meant to signal that Boston was not just a city, but a democratic beacon for the nation. It represents a era when Boston was frequently called the 'Athens of America.' As you look at the dome, consider how this single point on the hill became the psychological anchor for a city that still views itself as a center of global influence.

---

#### Beat: Copp's Hill Burying Ground

| Field | Value |
|---|---|
| id | `e30da115-43d3-4d9f-aff0-c452335a89b0` |
| poi | Copp's Hill Burying Ground |
| tagged_with | hidden_history |
| duration_sec | 240 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| created_at | 2026-03-13T01:15:12.094Z |

> Notice the slate headstones and you'll see a gallery of early American macabre art. Look closely at the carvings to find skulls and crossbones, winged hourglasses symbolizing the flight of time, and weeping willows. These aren't just decorations; they are the 17th- and 18th-century way of telling the story of the person resting below. This ground was laid out in 1660 and named for William Copp, a local who once operated a windmill on this very hill. While many prominent Bostonians are interred here, the site also served as the final resting place for a final resting place for over 10,000 people, including a large community of African Americans who lived on the hill's north slope. The air here often carries a salty breeze from the harbor. As you walk the paths, think of the thousands of anonymous lives that contributed to the fabric of the city, now resting under the shade of trees planted by the city back in the mid-19th century.

---

#### Beat: 44 Hull Street

| Field | Value |
|---|---|
| id | `6d38f582-942f-49db-92d6-8224470953cf` |
| poi | 44 Hull Street |
| tagged_with | arch_design |
| duration_sec | 60 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| created_at | 2026-03-13T01:17:20.902Z |

> Stretch your arms out and you might feel like you can almost touch both sides of the house at 44 Hull Street. This is officially the narrowest house in Boston, measuring a mere 10.5 feet wide. Notice the wood-framed construction, a rare sight in the North End where brick dominates the landscape. It was built in the civil war era by a housewright named Joseph Eustis. For over two centuries, this tiny sliver of a building has sheltered families, surviving the massive topographical and architectural changes that leveled other wooden homes in the neighborhood. Its presence is a testament to the extreme density of the old North End. The scale is so intimate it feels like a dollhouse brought to life. Imagine the challenge of moving furniture up those narrow stairs or the sound of the city streets vibrating through such thin walls. It remains one of the city's most charming architectural oddities.

---

#### Beat: Old North Church

| Field | Value |
|---|---|
| id | `7cb37978-d9dc-47c1-b671-216c3c987a6f` |
| poi | Old North Church |
| tagged_with | dark_history |
| duration_sec | 240 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| created_at | 2026-03-13T01:18:14.717Z |

> While most visitors focus on the steeple, there is a much darker history resting directly beneath your feet. Face the main entrance and imagine descending into the tombs below the church floor. These crypts are said to hold the remains of over 1,000 North Enders. In the 18th and 19th centuries, this was a space of perpetual twilight and the heavy scent of damp earth and old stone. The tombs represent a loyal congregation that never truly left, creating a silent community that exists in parallel to the parishioners who still gather for divine worship every Sunday. While Paul Revere's ride gave the church its international fame, it is the sheer volume of history packed into the basement that grounds the building in the everyday life—and death—of the colonial city. It is a quiet, somber contrast to the bustling, tourist-heavy streets just outside the church doors.

---

#### Beat: St. Stephen's Church

| Field | Value |
|---|---|
| id | `9c999501-8398-40f4-ba18-ac3722cb4282` |
| poi | St. Stephen's Church |
| tagged_with | religious_spiritual |
| duration_sec | 180 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| created_at | 2026-03-13T01:19:29.793Z |

> Notice the clean, Neoclassical lines of the brickwork, but look deeper into the stories of the people who gathered here. Originally built as the New North Church, the building was sold in 1862 to the Roman Catholic Diocese to accommodate the massive wave of Irish immigrants. Among the most famous parishioners was Rose Fitzgerald Kennedy. She was baptized in this very church in 1890 and, over a century later, her funeral mass was held here in 1995. The church has acted as a spiritual anchor for the neighborhood through its evolution from a Puritan stronghold to a bustling center of Irish and later Italian life. If you stand near the entrance, you can almost hear the echoes of the countless baptisms and funerals that have marked the immigrant experience in Boston. The building was restored in 1965 to its original Bulfinch design, stripping away later additions to reveal its elegant, 19th-century bones.

---

#### Beat: Paul Revere House

| Field | Value |
|---|---|
| id | `6cc38c9d-014a-4fb7-8700-b5512f75a15a` |
| poi | Paul Revere House |
| tagged_with | hidden_history |
| duration_sec | 240 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| created_at | 2026-03-13T01:20:31.578Z |

> Before it was a museum, this house had a much grittier, commercial life. By the late 19th century, the home of the silversmith Paul Revere had been transformed into a hub for the neighborhood's growing Italian population. Face the ground floor windows and imagine them filled with boxes of cigars and the busy chatter of a neighborhood bank. At that time, it housed the Banca Italiana and the F.A. Goduti Company, businesses that catered to the financial and social needs of new immigrants. It wasn't until 1907 that the Paul Revere Memorial Association purchased the building to restore it to its colonial appearance. Architect Joseph Everett Chandler actually removed an entire third story that had been added over the years to bring it back to its 17th-century silhouette. This spot is a perfect example of how Boston layers its history—one century's revolutionary home is the next century's immigrant cigar shop.

---

#### Beat: Liberty Hotel

| Field | Value |
|---|---|
| id | `3150bed3-f51c-4bba-96f8-9063e0f34342` |
| poi | Liberty Hotel |
| tagged_with | arch_design |
| duration_sec | 120 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| created_at | 2026-03-13T01:28:51.904Z |

> Run your hand along the rough, hammered granite and consider that for over a century, the people inside these walls were here against their will. Designed by architect Gridley J. Fox Bryant, the jail featured four long wings extending from an octagonal rotunda with a 90-foot-tall atrium. This design was intended to provide light and ventilation, but the atmosphere was undeniably grim. Today, that same rotunda is a luxury lobby, and the old cells have been transformed into high-end rooms. One of the hotel's restaurants is even named 'The Clink' as a nod to its incarcerated past. It is a striking example of adaptive reuse, where a place once defined by bars and sentences is now a destination for cocktails and luxury stays. The scale of the granite blocks reminds you of the building's original purpose: to be a formidable and inescapable presence at the edge of the West End.

---

#### Beat: Massachusetts General Hospital Bulfinch Building

| Field | Value |
|---|---|
| id | `95396f16-3a28-4bb1-a9a6-f0a04c3304de` |
| poi | Massachusetts General Hospital Bulfinch Building |
| tagged_with | hidden_history |
| duration_sec | 180 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| created_at | 2026-03-13T01:29:54.813Z |

> Within these granite walls, the world of medicine changed forever. Look up at the high windows and imagine a day in the 19th century when Dr. John Collins Warren performed the first successful operation using anesthesia. Before that moment, surgery was a terrifying and agonizing experience; the introduction of ether here was a global breakthrough. The building itself, designed by Charles Bulfinch, was intended to provide a dignified space for medical care, funded by local benefactors who sought to help Boston's most impoverished residents. Today, while MGH is an international leader in medical technology, this specific building remains the anchor of its history. The smell of antiseptic today replaced the heavier odors of 19th-century medicine, but the sense of quiet, academic excellence still hangs in the air around the Ionic-colonnaded entrance. It is a place where scientific progress was literally carved out of New England granite.

---

#### Beat: Boston City Hall

| Field | Value |
|---|---|
| id | `eb7da590-2a72-4a89-9552-21cc2cd6a22f` |
| poi | Boston City Hall |
| tagged_with | arch_design |
| duration_sec | 300 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| created_at | 2026-03-13T01:31:55.323Z |

> Look up at the building and try to trace the shape of an inverted pyramid. Notice the heavy brick base and the massive cast concrete piers that seem to hang over the plaza. Designed by the firm Kallmann McKinnell & Knowles, this structure was meant to be a monumental, freestanding symbol of government transparency and modernism. However, it has been a lightning rod for debate since the day it opened. Some admire its bold, raw honesty, while others see it as an 'outre' concrete fortress. The plaza itself was created by clearing away a significant portion of the old West End, making the building a symbol of the radical urban renewal that transformed Boston in the 1960s. Whether you love the texture of the rough concrete or find it cold, there is no denying its presence. It stands as a stark, angular contrast to the winding colonial streets that once defined this area.

---

#### Beat: Sears' Crescent

| Field | Value |
|---|---|
| id | `eece4232-e58a-4116-b72b-ea2b54999336` |
| poi | Sears' Crescent |
| tagged_with | arch_design |
| duration_sec | 120 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| created_at | 2026-03-13T01:33:07.615Z |

> Notice how the building gently curves to follow the line of the street. This isn't a modern architectural flourish; it's a ghost of the past. The Sears' Crescent was built in 1816 along Cornhill Street, a curving road that used to run parallel to Court Street. In the early 1960s, almost everything around this building was demolished to make way for the vast, open expanse of City Hall Plaza. Remarkably, the Crescent was spared. If you look at the redbrick facade, you're seeing a survivor of the 'urban renewal' that leveled the old West End. It was remodeled just before the Civil War and restored again in 1969. Today, it stands as a warm, brick reminder of the human-scaled, winding streets that used to define this part of the city before they were replaced by the monumental concrete of the government center.

---

#### Beat: The Steaming Kettle

| Field | Value |
|---|---|
| id | `7b7bbdab-daa2-485f-a0b6-1085c53b78a5` |
| poi | The Steaming Kettle |
| tagged_with | local_legends |
| duration_sec | 120 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| created_at | 2026-03-16T01:40:47.917Z |

> Notice the steam rising steadily from the spout of this giant copper teapot. This is the Steaming Kettle, the original trade sign for the old Oriental Tea Company. Manufactured by the Hicks & Badger Company in 1873, it is far more than a simple decoration. In 1875, the kettle became the center of a massive city-wide spectacle. After the Boston Sealer of Weights and Measures officially measured the vessel, a contest was held to guess its true capacity. The answer is surprisingly precise: 227 gallons, two quarts, one pint, and three gills. Imagine the scene in the late 1800s as thousands of curious Bostonians gathered on this street corner, tilting their heads back to guess how much tea could fit inside this looming copper landmark. Run your hand along the wall of the Sears' Block below the sign to feel the history of this busy intersection.

---

#### Beat: Union Oyster House

| Field | Value |
|---|---|
| id | `2f03ce59-0ee1-4f34-a946-df4f1e22e2ae` |
| poi | Union Oyster House |
| tagged_with | food_culinary |
| duration_sec | 300 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| created_at | 2026-03-16T01:43:09.259Z |

> Take a moment to admire the weathered red bricks of this Georgian structure, which dates back to roughly 1716. This is the Union Oyster House, officially recognized as the oldest restaurant in continuous service in the United States. It first opened its doors to hungry Bostonians in 1826, originally known as the Atwood & Bacon Oyster House. However, the building's history goes back even further than its culinary fame. In 1771, more than half a century before the first oyster was shucked here, a printer named Isaiah Thomas occupied the second floor. From that space, he published the 'Massachusetts Spy,' a newspaper that would become a vital voice during the lead-up to the American Revolution. Notice the charming Colonial aspect of the facade, which has remained largely unchanged for centuries, even as the city grew up around it.

---

#### Beat: The Boston Stone

| Field | Value |
|---|---|
| id | `964ef9bb-9867-47c8-981c-a3d4dfa400ca` |
| poi | The Boston Stone |
| tagged_with | hidden_history |
| duration_sec | 120 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| created_at | 2026-03-16T01:46:08.414Z |

> Look down at the circular millstone embedded in the brick wall. This artifact, imported from England in 1700, originally served a very practical purpose: it was used to grind the raw substances that became pigments for paint. By 1737, the date inscribed on its base, it had taken on a new, more prestigious role. For many years, this very spot was considered 'ground zero' for the city of Boston. Surveyors used this stone as the official starting point for signaling any distance from the city. Though the paint mill building it once belonged to was eventually demolished, the stone was carefully saved and reinstalled into this structure. Run your hand over the rough surface of the millstone and imagine the 18th-century surveyors standing in this narrow alley, setting their instruments to measure the expanding Massachusetts colony.

---

#### Beat: New England Holocaust Memorial

| Field | Value |
|---|---|
| id | `67798f48-1ed8-4f47-ac97-3dbadc4da3f4` |
| poi | New England Holocaust Memorial |
| tagged_with | arch_design |
| duration_sec | 240 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| created_at | 2026-03-16T01:50:07.013Z |

> Step onto the black granite path and look up at the six glass towers rising above you. Designed by Stanley Saitowitz and completed in 1995, this memorial uses architecture to evoke a profound sense of loss and memory. Each of the towers represents one of the six principal Nazi death camps. As you walk between them, notice the steam emanating from the bottom of each chamber. If you look closely at the glass panels, you will see six million numbers etched into the surface, a staggering visual representation of the victims that replicates the tattooed numbers used by the Nazis. At night, the towers are illuminated internally, creating a somber glow. The design is intended to recall both a menorah of memorial candles and the chimneys of the camps, grounding the listener in the cold, hard reality of the 20th century's greatest tragedy.

---

#### Beat: Boston Custom House

| Field | Value |
|---|---|
| id | `87798165-eae7-4a73-8c6f-68ac729691c8` |
| poi | Boston Custom House |
| tagged_with | arch_design |
| duration_sec | 240 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| created_at | 2026-03-16T01:58:29.347Z |

> Look up at the towering granite spire that defines this building. When the Boston Custom House was first completed in 1849, it was a much shorter structure designed like a Greek Cross by Ammi Burnham Young. It sat right at the edge of the harbor, serving as the federal office for cargo ships docking in Boston. However, as the city grew and land was filled in to the east, the shoreline moved away. In 1915, the architectural firm Peabody & Stearns added the high-rise office tower, transforming it into Boston's first true skyscraper. For five decades, this was the tallest point in the city's skyline. Today, the building has transitioned from federal business to leisure, operating as a vacation club. Face east and imagine the 19th-century masts of cargo ships once bobbing right where the surrounding streets and buildings now stand.

---

#### Beat: Trinity Church

| Field | Value |
|---|---|
| id | `ff247377-6338-4a8d-af87-24e87f453514` |
| poi | Trinity Church |
| tagged_with | arch_design |
| duration_sec | 300 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| created_at | 2026-03-16T02:11:23.610Z |

> Notice the massive square lantern tower and the polychromatic decoration of the stone walls. This is Trinity Church, the building that established Henry Hobson Richardson's reputation and gave birth to the Richardsonian Romanesque style. Built between 1872 and 1877, its design was so influential that in 1885, American architects voted it the most important building in the United States. It remains the only structure from that original 19th-century list still ranked in the American Institute of Architects' top ten today. Look closely at the rough-hewn Dedham granite and brownstone, which give the church its compact, powerful feel. Unlike the soaring spires of typical Gothic churches, Trinity's heavy arches and sturdy tower ground it firmly in Copley Square. Face the main entrance and imagine the sound of horse-drawn carriages clattering across the square as congregants arrived for service a century ago.

---

#### Beat: Old State House

| Field | Value |
|---|---|
| id | `3e01042f-2e11-4675-9b17-ffa3a3b6ed7b` |
| poi | Old State House |
| tagged_with | hidden_history |
| duration_sec | 300 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| created_at | 2026-03-16T02:14:16.703Z |

> Look up at the white steeple and the brick facade of the Old State House. Built in 1713, this is the oldest surviving public building in Boston. For nearly a century, it served as the seat of government for the Massachusetts Legislature, witnessing the heated debates and pivotal moments that led to American independence. In 1798, the government moved to the new state house on Beacon Hill, but this building remained as a sentinel of the city's past. Today, it is a key stop on the Freedom Trail. Notice the contrast between its small, historic scale and the glass-and-steel skyscrapers that loom over it. This building has survived fires, the threat of demolition, and the total transformation of the city around it. Run your hand along the brickwork at the corner to feel the texture of one of the few pieces of 18th-century Boston still standing in its original location.

---

#### Beat: Berkeley Building

| Field | Value |
|---|---|
| id | `955bf0a8-5383-4a40-aa75-05ca3be1771a` |
| poi | Berkeley Building |
| tagged_with | arch_design |
| duration_sec | 180 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| created_at | 2026-03-16T02:15:36.227Z |

> Gaze up at the intricate white terra-cotta that covers this building from sidewalk to roof. Constructed in 1909 and designed by Codman and Despradelle, the Berkeley Building is often referred to as a 'wedding cake' because of its fanciful, layered appearance. It is a rare and striking example of Art Nouveau design in Boston, where the architects used stone and clay to create flowing, organic shapes that feel more like lace than a commercial structure. Originally, this building served as the Design Center for Boston, a fitting use for such an aesthetically adventurous landmark. In 1988, it was remodeled for modern offices, but the exterior was carefully preserved to maintain its whimsical charm. Notice the way the white terra-cotta catches the light, making the building seem to glow even on a gray Boston afternoon.

---

### Standalone Beats (not linked to a POI via HAS_BEAT)

#### Beat: Old North Church — Lantern Signal

| Field | Value |
|---|---|
| id | `d4e928fd-4cf0-4b27-83bf-35539c55104b` |
| tagged_with | hidden_history |
| duration_sec | 60 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| created_at | 2026-03-13T00:36:07.772Z |

> The Old North Church steeple held two lanterns on that fateful April night in 1775. Robert Newman climbed the dark narrow stairs while Paul Revere waited across the harbor. The signal one if by land two if by sea changed the course of American history. Those lanterns became the most famous signal lights in the revolution sparking the midnight ride that warned every Middlesex village and farm.

---

#### Beat: Paul Revere's Midnight Ride

| Field | Value |
|---|---|
| id | `85a85068-5c02-45e1-92ae-5e108a7c9be2` |
| tagged_with | (none) |
| duration_sec | 60 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| created_at | 2026-03-13T00:36:07.809Z |

> Paul Revere galloped through the Massachusetts countryside warning colonial militia that British regulars were marching toward Lexington and Concord. His midnight ride covered roughly twelve miles of dark roads and sleeping villages. At every farmhouse he pounded on doors shouting the regulars are coming. Samuel Prescott and William Dawes joined the ride but only Prescott made it all the way to Concord.

---

#### Beat: British Occupation of Boston

| Field | Value |
|---|---|
| id | `556f039d-62c2-4ed0-9963-a1cd4f4ea190` |
| tagged_with | dark_history |
| duration_sec | 60 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| created_at | 2026-03-13T00:36:07.833Z |

> British soldiers occupied Boston for years before the Revolution turning churches into stables and homes into barracks. The redcoats patrolled cobblestone streets enforcing harsh laws on colonial citizens. Tensions boiled over at the Boston Massacre when soldiers fired into a crowd killing five men.

---

#### Beat: Boston Harbor Lighthouse

| Field | Value |
|---|---|
| id | `944fae66-11ac-4d76-8033-41368d593d82` |
| tagged_with | hidden_history |
| duration_sec | 180 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| created_at | 2026-03-13T00:37:12.688Z |

> Boston Harbor Lighthouse has guided mariners since 1716, making it the first lighthouse established in what would become the United States. The original tower was destroyed during the Revolutionary War and rebuilt in 1783. Standing at the edge of the harbor, you can still see its beam sweeping across the water on foggy nights.

---

#### Beat: Keeper Worthylake Ghost

| Field | Value |
|---|---|
| id | `c6472253-fda4-406c-9a82-87ae495f70a0` |
| tagged_with | local_legends |
| duration_sec | 240 |
| version | 1 |
| active_status | active |
| kid_friendly | yes |
| created_at | 2026-03-13T00:37:12.745Z |

> Local fishermen swear they see the ghost of keeper Worthylake walking the rocks at low tide. He drowned in 1718 along with his wife and daughter when their boat capsized returning to the lighthouse. A young Benjamin Franklin wrote a ballad about the tragedy — his first published work.

---

## Relationships — Complete List

### HAS_PROFILE (User → Profile)
| From | To |
|---|---|
| testuser@ondoway.app | Mom |
| testuser@ondoway.app | Kid |

### IS_CAPTAIN_OF / IS_CREW_OF (Profile → Trip)
| Profile | Role | Trip |
|---|---|---|
| Mom | Captain | Paris Spring 2026 |
| Kid | Crew | Paris Spring 2026 |

### PREFERS_LENS (Profile → Lens)
| Profile | Lens |
|---|---|
| Mom | hidden_history |
| Mom | food_culinary |
| Mom | literary_film |
| Kid | art_street |
| Kid | nature_green |
| Kid | local_legends |

### HAS_STOP (Trip → ItineraryItem)
| Trip | Item |
|---|---|
| Paris Spring 2026 | Item 1 (Eiffel Tower, 09:00) |
| Paris Spring 2026 | Item 2 (Cafe de Flore, 11:00) |
| Paris Spring 2026 | Item 3 (Shakespeare and Co., 12:00) |

### ASSIGNED_TO (ItineraryItem → Profile)
All 3 items assigned to **Mom**.

### AT_POI (ItineraryItem → POI)
| Item | POI |
|---|---|
| Item 1 | Eiffel Tower |
| Item 2 | Cafe de Flore |
| Item 3 | Shakespeare and Company |

### PLAYS_BEAT (ItineraryItem → NarrativeBeat)
| Item | Beat |
|---|---|
| Item 1 | Eiffel Tower beat (`388bd856`) |
| Item 2 | Cafe de Flore — Existentialist beat (`b25cf9d1`) |
| Item 3 | Shakespeare and Company beat (`16fbf18f`) |

### IS_PARENT_OF (Lens → Lens)
| Parent | Child |
|---|---|
| arch_design | arch_gothic_01 |

### HAS_BEAT (POI → NarrativeBeat) — 24 relationships
| POI | Beat ID |
|---|---|
| 44 Hull Street | `6d38f582` |
| Berkeley Building | `955bf0a8` |
| Boston City Hall | `eb7da590` |
| Boston Custom House | `87798165` |
| Cafe de Flore | `b25cf9d1` (existentialist) |
| Cafe de Flore | `4a535603` (WWII resistance) |
| Copp's Hill Burying Ground | `e30da115` |
| Eiffel Tower | `388bd856` |
| Liberty Hotel | `3150bed3` |
| MGH Bulfinch Building | `95396f16` |
| Massachusetts State House | `da661420` |
| New England Holocaust Memorial | `67798f48` |
| Old North Church | `7cb37978` |
| Old State House | `3e01042f` |
| Paul Revere House | `6cc38c9d` |
| Sears' Crescent | `eece4232` |
| Shakespeare and Company | `16fbf18f` |
| St. Stephen's Church | `9c999501` |
| The Boston Stone | `964ef9bb` |
| The Steaming Kettle | `7b7bbdab` |
| Trinity Church | `ff247377` |
| Union Oyster House | `2f03ce59` |

### TAGGED_WITH (NarrativeBeat → Lens) — 27 relationships
| Beat (POI context) | Lens |
|---|---|
| Eiffel Tower | arch_design |
| Eiffel Tower | hidden_history |
| Cafe de Flore (existentialist) | literary_film |
| Cafe de Flore (WWII) | dark_history |
| Shakespeare and Company | literary_film |
| Shakespeare and Company | local_legends |
| Massachusetts State House | local_legends |
| Copp's Hill Burying Ground | hidden_history |
| 44 Hull Street | arch_design |
| Old North Church | dark_history |
| St. Stephen's Church | religious_spiritual |
| Paul Revere House | hidden_history |
| Liberty Hotel | arch_design |
| MGH Bulfinch Building | hidden_history |
| Boston City Hall | arch_design |
| Sears' Crescent | arch_design |
| The Steaming Kettle | local_legends |
| Union Oyster House | food_culinary |
| The Boston Stone | hidden_history |
| New England Holocaust Memorial | arch_design |
| Boston Custom House | arch_design |
| Trinity Church | arch_design |
| Old State House | hidden_history |
| Berkeley Building | arch_design |
| Old North Church Lantern (standalone) | hidden_history |
| British Occupation (standalone) | dark_history |
| Boston Harbor Lighthouse (standalone) | hidden_history |
| Keeper Worthylake (standalone) | local_legends |
