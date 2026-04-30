# Paris Tourability Map — Summary

**Generated:** 2026-04-30T00:43:32.960673+00:00
**City:** paris
**Grid resolution:** 100m
**Cells:** 11205

**Bounding box:** lat [48.82366, 48.89755], lng [2.26060, 2.44417]

---

## Status mix per duration bucket

| Bucket | GREEN | YELLOW | RED |
|---|---|---|---|
| 60min round-trip | 48 (0.4%) | 288 (2.6%) | 10869 (97.0%) |
| 60min one-way | 550 (4.9%) | 474 (4.2%) | 10181 (90.9%) |
| 90min round-trip | 130 (1.2%) | 400 (3.6%) | 10675 (95.3%) |
| 90min one-way | 915 (8.2%) | 689 (6.1%) | 9601 (85.7%) |
| 120min round-trip | 238 (2.1%) | 500 (4.5%) | 10467 (93.4%) |
| 120min one-way | 1309 (11.7%) | 901 (8.0%) | 8995 (80.3%) |
| 180min round-trip | 386 (3.4%) | 653 (5.8%) | 10166 (90.7%) |
| 180min one-way | 2226 (19.9%) | 1192 (10.6%) | 7787 (69.5%) |

---

## Top 10 highest-density GREEN starts (60min round-trip)

| Rank | Lat,Lng | Nearest POI | Fill | Anchors | Compactness |
|---|---|---|---|---|---|
| 1 | 48.85339, 2.36467 | Hotel de Mayenne | 2.06 | 8 | 0.76 |
| 2 | 48.85429, 2.36604 | Musee Victor Hugo | 2.06 | 8 | 0.76 |
| 3 | 48.85429, 2.36467 | Hotel de Sully | 2.05 | 8 | 0.76 |
| 4 | 48.85519, 2.36604 | Musee Victor Hugo | 2.02 | 8 | 0.76 |
| 5 | 48.85609, 2.34961 | Hotel de Ville | 2.00 | 10 | 0.86 |
| 6 | 48.85249, 2.36467 | Village Saint-Paul | 1.99 | 8 | 0.76 |
| 7 | 48.85519, 2.36330 | Place du Marché Sainte-Catherine | 1.98 | 9 | 0.87 |
| 8 | 48.85339, 2.36604 | Rue Saint-Antoine | 1.96 | 7 | 0.74 |
| 9 | 48.85429, 2.36193 | Passage Saint-Paul | 1.96 | 9 | 0.87 |
| 10 | 48.85519, 2.34824 | Ile de la Cite | 1.94 | 10 | 0.86 |

---

## 10 most-likely-asked thin tier-5 starts

Tier-5 POIs whose own cell falls YELLOW or RED at 60min round-trip — expected user starting points where the gate will refuse or warn.

| POI | 60min RT | 60min one-way | 90min RT | 90min one-way | Recommendation |
|---|---|---|---|---|---|
| Bois de Vincennes | RED | RED | RED | RED | All buckets thin — sparse start |
| Moulin Rouge | RED | RED | RED | RED | All buckets thin — sparse start |
| Rue Lepic | RED | RED | RED | RED | All buckets thin — sparse start |
| Grand Palais | RED | YELLOW | RED | YELLOW | Try 180min one-way |
| Bibliotheque Nationale de France - Richelieu | RED | RED | RED | GREEN | Try 90min one-way |
| Champs-Elysees | RED | RED | RED | RED | All buckets thin — sparse start |
| Musee d'Orsay | RED | RED | RED | GREEN | Try 90min one-way |
| Arc de Triomphe | RED | RED | RED | RED | All buckets thin — sparse start |
| Sacre-Coeur Basilica | RED | RED | RED | RED | All buckets thin — sparse start |
| Eiffel Tower | RED | YELLOW | RED | YELLOW | All buckets thin — sparse start |

---

## Neighborhood-level rollup (60min round-trip)

Cells assigned to the nearest POI's (most-specific) Area; % GREEN within each Area. Useful but not the canonical gate.

| Area | Cells | % GREEN | % YELLOW | % RED |
|---|---|---|---|---|
| Île de la Cité | 37 | 24% | 27% | 49% |
| Le Marais | 187 | 15% | 27% | 58% |
| Latin Quarter | 59 | 5% | 31% | 64% |
| 4th Arrondissement | 41 | 2% | 10% | 88% |
| Bastille | 263 | 2% | 2% | 97% |
| 5th Arrondissement | 263 | 1% | 3% | 96% |
| 15th Arrondissement | 1375 | 0% | 0% | 100% |
| 14th Arrondissement | 293 | 0% | 0% | 100% |
| 13th Arrondissement | 463 | 0% | 0% | 100% |
| 12th Arrondissement | 1177 | 0% | 0% | 100% |
| 6th Arrondissement | 179 | 0% | 24% | 76% |
| 7th Arrondissement | 519 | 0% | 8% | 92% |
| Île Saint-Louis | 21 | 0% | 38% | 62% |
| Saint-Germain-des-Prés | 41 | 0% | 71% | 29% |
| 20th Arrondissement | 1424 | 0% | 0% | 100% |
| Trocadéro-Passy | 472 | 0% | 0% | 100% |
| 1st Arrondissement | 123 | 0% | 37% | 63% |
| Les Halles | 26 | 0% | 81% | 19% |
| 11th Arrondissement | 125 | 0% | 0% | 100% |
| Champs-Élysées | 236 | 0% | 0% | 100% |
| 2nd Arrondissement | 214 | 0% | 2% | 98% |
| Madeleine-Concorde | 74 | 0% | 0% | 100% |
| 16th Arrondissement | 373 | 0% | 0% | 100% |
| 3rd Arrondissement | 73 | 0% | 0% | 100% |
| Opéra-Garnier | 110 | 0% | 0% | 100% |
| Plaine Monceau | 333 | 0% | 0% | 100% |
| 19th Arrondissement | 955 | 0% | 0% | 100% |
| 10th Arrondissement | 289 | 0% | 0% | 100% |
| 9th Arrondissement | 79 | 0% | 0% | 100% |
| 17th Arrondissement | 391 | 0% | 0% | 100% |
| Montmartre | 560 | 0% | 0% | 100% |
