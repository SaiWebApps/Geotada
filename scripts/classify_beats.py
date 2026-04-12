"""
Beat & POI Enrichment Classifier for Paris data.
Classifies all beats with 6 metadata fields and all POIs with poi_role.
"""
import json
import re
from datetime import datetime, timezone
from collections import defaultdict

# ── Valid enums ──────────────────────────────────────────────────
VALID_NF = {'hook','deepen','transition','climax','callback','scene_setter','establishing'}
VALID_BT = {'anecdote','architectural_detail','character_story','event','sensory_observation','factoid','establishing'}
VALID_ER = {'reverent','somber','playful','dramatic','wry','neutral'}
VALID_ROLES = {'stop','setting','walk_by_only'}

# ── Entity extraction ────────────────────────────────────────────
# Common words to exclude from entity detection
COMMON_EXCLUSIONS = {
    'Paris', 'France', 'French', 'Parisian', 'Parisians',
    'Seine', 'Left Bank', 'Right Bank', 'Rive Gauche', 'Rive Droite',
    'God', 'Virgin Mary', 'Christ', 'Jesus',
    'Revolution', 'Commune', 'Republic', 'Restoration', 'Empire',
    'King', 'Queen', 'Emperor', 'Pope', 'Cardinal', 'Bishop',
    'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
    'AD', 'BC', 'WWI', 'WWII',
    # Sentence starters and common words that get capitalized
    'The', 'This', 'That', 'These', 'Those', 'Here', 'There', 'Where', 'When',
    'After', 'Before', 'During', 'Between', 'Among', 'Around', 'Behind', 'Beneath',
    'Inside', 'Outside', 'Above', 'Below', 'Near', 'Nearby',
    'But', 'Yet', 'However', 'Although', 'Despite', 'Though', 'While',
    'Not', 'Most', 'Many', 'Some', 'All', 'Every', 'Each', 'Few',
    'In', 'On', 'At', 'By', 'For', 'With', 'From', 'To', 'Of',
    'And', 'Or', 'Nor', 'So', 'Then', 'Thus', 'Hence', 'Also',
    'Even', 'Still', 'Just', 'Only', 'Already', 'Soon', 'Later',
    'He', 'She', 'It', 'They', 'We', 'His', 'Her', 'Its', 'Their', 'Our',
    'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten',
    'Such', 'Like', 'Over', 'Under', 'Both', 'Neither', 'Either',
    'Another', 'Other', 'Next', 'Last', 'First', 'Second', 'Third',
    'English', 'Italian', 'German', 'Spanish', 'Dutch', 'Swedish', 'British',
    'American', 'Roman', 'Greek', 'Christian', 'Catholic', 'Protestant', 'Jewish',
    'Gothic', 'Renaissance', 'Baroque', 'Romanesque', 'Neoclassical',
    'National', 'Royal', 'Imperial', 'Universal', 'Grand', 'Great',
    'Crown', 'Rising', 'Perhaps',
}

# Geographic features to exclude
GEO_EXCLUSIONS = {
    'Ile de la Cite', 'Ile Saint-Louis', 'Montagne Sainte-Genevieve',
    'Montmartre', 'Latin Quarter', 'Marais', 'Faubourg Saint-Germain',
    'Faubourg Saint-Honore', 'Champs-Elysees',
}

def extract_entities(text, poi_name):
    """Extract named entities from beat text."""
    entities = set()

    # ── Person patterns ──
    # Look for names like "Philippe-Auguste", "Louis XIV", "Victor Hugo"
    # Titles + names
    title_name = re.findall(
        r'(?:King|Queen|Emperor|Empress|Cardinal|Bishop|Saint|Madame|Monsieur|'
        r'Prince|Princess|Princesse|Duke|Duc|Duchess|Duchesse|'
        r'Marquis|Marquise|Comte|Comtesse|Marshal|Marechal|Baron|'
        r'General|Captain|President|Minister|Abbe|Abbot)\s+'
        r'(?:de\s+(?:la\s+)?|du\s+|des\s+)?'
        r'([A-Z][a-zéèêëàâäîïôöùûü\-]+(?:\s+(?:de\s+(?:la\s+)?|du\s+|des\s+)?[A-Z][a-zéèêëàâäîïôöùûü\-]+)*)',
        text
    )

    # Full names with Roman numerals
    roman_names = re.findall(
        r'([A-Z][a-zéèêëàâäîïôöùûü\-]+(?:\s+(?:de\s+(?:la\s+)?|du\s+|des\s+)?[A-Z][a-zéèêëàâäîïôöùûü\-]+)*\s+(?:I{1,3}V?|IV|VI{0,3}|IX|X{0,3}I{0,3}V?))\b',
        text
    )

    # Simple proper names (two+ capitalized words)
    proper_names = re.findall(
        r'\b([A-Z][a-zéèêëàâäîïôöùûü\-]+(?:\s+(?:de\s+(?:la\s+)?|du\s+|des\s+)?[A-Z][a-zéèêëàâäîïôöùûü\-]+)+)\b',
        text
    )

    # Specific historical people that appear frequently
    known_people = [
        'Philippe-Auguste', 'Charles V', 'Louis XIV', 'Louis XIII', 'Louis XV', 'Louis XVI',
        'Henri IV', 'Henri II', 'Henri III', 'Francois I', 'Napoleon', 'Napoleon III',
        'Marie de Medici', 'Marie-Antoinette', 'Anne of Austria', 'Catherine de Medici',
        'Richelieu', 'Mazarin', 'Colbert', 'Haussmann', 'Louvois', 'Talleyrand',
        'Victor Hugo', 'Voltaire', 'Moliere', 'Balzac', 'Zola', 'Baudelaire',
        'Hemingway', 'Sartre', 'Simone de Beauvoir', 'Delacroix', 'Rodin',
        'Viollet-le-Duc', 'Le Vau', 'Mansart', 'Le Brun', 'Chalgrin',
        'Danton', 'Marat', 'Robespierre', 'Charlotte Corday',
        'Abelard', 'Heloise', 'Rabelais', 'Racine', 'Corneille',
        'Mozart', 'Berlioz', 'Chopin', 'Liszt', 'Couperin',
        'Gustave Eiffel', 'Jules-Hardouin Mansart',
    ]

    for name in known_people:
        if name in text:
            entities.add(name)

    for name in title_name + roman_names + proper_names:
        name = name.strip()
        if len(name) > 2 and name not in COMMON_EXCLUSIONS:
            # Don't include the POI's own name
            if name.lower() != poi_name.lower() and name not in poi_name:
                entities.add(name)

    # Clean up
    cleaned = set()
    poi_lower = poi_name.lower()
    poi_parts = set(w.lower() for w in poi_name.split() if len(w) > 3)

    for e in entities:
        e = e.strip(' .,;:!?')
        if len(e) <= 2:
            continue
        if e in COMMON_EXCLUSIONS or e in GEO_EXCLUSIONS:
            continue
        # Skip if starts with lowercase
        if e[0].islower():
            continue
        # Skip if it's (part of) the POI name
        e_lower = e.lower()
        if e_lower == poi_lower or e_lower in poi_lower or poi_lower in e_lower:
            continue
        # Skip partial POI name matches (e.g., "The Louvre" for Louvre Museum)
        e_parts = set(w.lower() for w in e.split() if len(w) > 3)
        if e_parts and e_parts.issubset(poi_parts):
            continue
        # Skip common sentence-starting patterns
        if re.match(r'^(The|A|An|In|On|At|By|For|With|From|To|Of|It|As)\s', e):
            continue
        # Skip single common words
        if ' ' not in e and e in COMMON_EXCLUSIONS:
            continue
        # Skip if it's just a number or date
        if re.match(r'^\d+$', e):
            continue
        # Skip generic titles alone
        if e in ('Duc', 'Comte', 'Prince', 'Marshal', 'General', 'Bishop',
                 'Marquise', 'Duchesse', 'Princesse', 'Madame', 'Monsieur'):
            continue
        # Skip fragments (ending with hyphen or very short fragments)
        if e.endswith('-') or e.endswith(' ') or len(e) < 4:
            continue
        # Skip if it looks like a fragment of a POI name
        if re.match(r'^(Beneath|Above|Inside|Behind|Near)\s', e):
            continue
        # Skip common adjective-like words that got capitalized
        if e in ('Place', 'Hotel', 'Rue', 'Pont', 'Tour', 'Porte', 'Quai',
                 'Passage', 'Square', 'Boulevard', 'Avenue', 'Eglise',
                 'Saint', 'Sainte', 'Notre', 'Dame',
                 'Thorns', 'Auguste', 'Revolutionary', 'Communards'):
            continue
        # Remove duplicates where one is a subset of another (handle later)

        cleaned.add(e)

    # Remove subset entities (e.g., keep "Madame de Sevigne" but remove "Sevigne")
    final = set()
    for e in cleaned:
        # Check if this entity is a suffix/part of a longer entity
        is_subset = False
        for other in cleaned:
            if e != other and e in other and len(e) < len(other):
                is_subset = True
                break
        if not is_subset:
            final.add(e)

    cleaned = final

    return sorted(cleaned)


def classify_sensory_anchor(text, poi_name):
    """Determine if beat references something currently visible at the POI.
    Must be conservative: only True if there's a strong signal of current visibility."""
    text_lower = text.lower()

    # Strong positive indicators — direct references to current visibility
    strong_positive = [
        r'\byou(?:\'ll| will| can) see\b', r'\blook (?:at|up|down|for|carefully) (?:at |the |and )',
        r'\bstill stands\b', r'\bstill visible\b', r'\bstill bears\b',
        r'\bcan be seen\b', r'\bvisible today\b',
        r'\byou are standing\b', r'\bstep inside\b',
        r'\bnotice the\b', r'\byou(?:\'ll| will) (?:find|spot|notice)\b',
        r'\bplaque (?:on |at |marks)\b', r'\binscription reads\b',
        r'\bwalk up close\b', r'\bon the wall\b.*\breads\b',
        r'\blook down at the\b', r'\blook up at the\b', r'\blook up\b.*\byou\b',
        r'\bnow displayed\b', r'\bnow housed\b',
        r'\bstill (?:on display|preserved|intact|standing)\b',
    ]

    # Weak positive indicators — might reference something visible but could be historical
    weak_positive = [
        r'\bsurviv(?:es|ing)\b(?!.*\bson\b)(?!.*\bchild)',  # "survives/surviving" but NOT "surviving son/child"
        r'\bremains today\b',
        r'\bstands? (?:on|at|in|here|today)\b',
    ]
    # Filter out "surviving" false positives about people
    if re.search(r'\bsurviving\b.*\b(?:son|daughter|child|heir|member)\b', text_lower):
        weak_positive = [p for p in weak_positive if 'surviv' not in p]

    # Negative indicators — demolished, destroyed, historical only
    negative_patterns = [
        r'\bdemolished\b', r'\bdestroyed\b', r'\bno longer (?:exists|stands|survives)\b',
        r'\bonce stood\b', r'\blong gone\b',
        r'\bburned down\b', r'\bburnt down\b', r'\brazed\b',
        r'\bdisappeared\b', r'\bwas (?:torn|pulled|knocked) down\b',
        r'\bwas replaced\b', r'\bno trace\b', r'\blost forever\b',
        r'\bwas (?:executed|killed|murdered|stabbed|shot|guillotined|beheaded)\b',
        r'\bwas (?:imprisoned|arrested|deported|exiled)\b',
    ]

    # Contextual negative — the beat is about people/events, not physical things
    event_focus = [
        r'\b(?:during|in) (?:the )?(?:revolution|war|commune|terror|occupation|siege)\b',
        r'\b(?:on|in) \d{1,2} (?:january|february|march|april|may|june|july|august|september|october|november|december) \d{4}\b',
        r'\b(?:married|baptized|baptised|buried|born|died|lived|stayed)\b.*\b(?:here|at)\b',
    ]

    strong_pos = sum(1 for p in strong_positive if re.search(p, text_lower))
    weak_pos = sum(1 for p in weak_positive if re.search(p, text_lower))
    neg_score = sum(1 for p in negative_patterns if re.search(p, text_lower))
    event_score = sum(1 for p in event_focus if re.search(p, text_lower))

    # Strong positive always wins unless negated
    if strong_pos > 0 and neg_score == 0:
        return True

    # Weak positive only counts if no negatives and no event-focus
    if weak_pos > 0 and neg_score == 0 and event_score == 0:
        return True

    # Default false — conservative
    return False


def classify_narrative_function(text, lens, poi_name, beat_idx, total_beats):
    """Classify narrative function."""
    text_lower = text.lower()

    # Hook signals: surprising opening, origin stories, provocative facts
    hook_signals = [
        r'\bbegan not as\b', r'\bfew (?:who|people|visitors)\b.*\bknow\b',
        r'\bironi(?:c|cally)\b', r'\bsurpris(?:e|ing|ingly)\b',
        r'\bnickname\b', r'\bcalled it\b', r'\bdubbed\b',
        r'\bnever had\b', r'\bnot .* as .* imagine\b',
        r'\bfar from\b.*\bpopular imagination\b',
    ]

    # Establishing signals: basic identity, what it IS (must be specifically about the POI's identity)
    establishing_signals = [
        r'\borigins?\b.*\b(?:date|trace|reach|stretch)\b',
        r'\bthe (?:first|oldest)\b.*\bin paris\b',
        r'\bwas (?:the|a) \w+ (?:in|of) paris\b',
    ]
    # Only count "founded/built/designed" if it's the POI itself, not something else
    if re.search(r'^(?:the |this |it )', text_lower) and re.search(r'\b(?:founded in|built (?:in|by|for|between)|designed by|inaugurated)\b', text_lower):
        establishing_signals.append(r'\b(?:founded|built|designed|inaugurated)\b')

    # Climax signals: high drama, death, destruction
    climax_signals = [
        r'\bkilled\b', r'\bexecut(?:ed|ion)\b', r'\bmurder(?:ed)?\b',
        r'\bassassinat(?:ed|ion)\b', r'\bguillotine\b', r'\bstabbed\b',
        r'\bburned?\b.*\bdown\b', r'\bexplosion\b', r'\bmassacre\b',
        r'\bdeath\b', r'\bdied\b.*\b(?:tragic|poverty|misery)\b',
    ]

    # Scene setter: atmospheric, mood
    scene_signals = [
        r'\batmospher(?:e|ic)\b', r'\bbuskers?\b', r'\bacrobats?\b',
        r'\bstreet life\b', r'\bvillage\b.*\bwithin\b',
        r'\bpicturesque\b', r'\bcharming\b', r'\bbewitching\b',
    ]

    # Deepener: adds context to already-known subject
    deepen_signals = [
        r'\bbut\b.*\bstory\b', r'\balso\b', r'\bmoreover\b',
        r'\bin addition\b', r'\bnearby\b', r'\baround the corner\b',
    ]

    hook_score = sum(1 for p in hook_signals if re.search(p, text_lower))
    est_score = sum(1 for p in establishing_signals if re.search(p, text_lower))
    cli_score = sum(1 for p in climax_signals if re.search(p, text_lower))
    scene_score = sum(1 for p in scene_signals if re.search(p, text_lower))

    # Callbacks reference other locations/beats
    callback_patterns = [
        r'\bsame\b.*\bwho\b', r'\bjust as\b.*\b(?:at|in|on)\b',
        r'\brecall(?:ing|s)?\b', r'\becho(?:es|ing)?\b',
    ]
    callback_score = sum(1 for p in callback_patterns if re.search(p, text_lower))

    # Transitions bridge between topics
    transition_patterns = [
        r'\bafter\b.*\b(?:century|years|decades)\b.*\b(?:became|transformed|turned)\b',
        r'\bwith the\b.*\b(?:transfer|move|departure)\b',
        r'\bmeanwhile\b', r'\bacross the street\b',
    ]
    transition_score = sum(1 for p in transition_patterns if re.search(p, text_lower))

    scores = {
        'hook': hook_score * 2,
        'establishing': est_score,
        'climax': cli_score * 1.5,
        'scene_setter': scene_score * 1.5,
        'callback': callback_score * 2,
        'transition': transition_score * 1.5,
        'deepen': deepen_score if (deepen_score := sum(1 for p in deepen_signals if re.search(p, text_lower))) else 0,
    }

    # Boost establishing for first beats of a POI
    if beat_idx == 0:
        scores['establishing'] += 2
        scores['hook'] += 1

    # Boost hook for surprising/ironic facts
    if lens in ('hidden_history', 'local_legends'):
        scores['hook'] += 0.5

    # Boost climax for dark history
    if lens in ('dark_history', 'war_conflict'):
        scores['climax'] += 0.5

    # Boost scene_setter for sensory and street lenses
    if lens in ('street_art', 'markets_street_food', 'parks_gardens'):
        scores['scene_setter'] += 1

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        # Default based on lens
        lens_defaults = {
            'historic_arch': 'establishing',
            'hidden_history': 'deepen',
            'dark_history': 'deepen',
            'war_conflict': 'deepen',
            'literary_heritage': 'deepen',
            'famous_residents': 'deepen',
            'music_heritage': 'deepen',
            'social_change': 'deepen',
            'visual_art': 'deepen',
            'historic_worship': 'establishing',
            'historic_cuisine': 'deepen',
            'local_legends': 'hook',
            'street_art': 'scene_setter',
            'modern_design': 'establishing',
            'sacred_traditions': 'deepen',
            'science_tech': 'deepen',
            'historic_markets': 'deepen',
            'commerce_innovation': 'establishing',
            'parks_gardens': 'scene_setter',
        }
        return lens_defaults.get(lens, 'deepen')

    return best


def classify_beat_type(text, lens):
    """Classify what kind of content the beat is."""
    text_lower = text.lower()

    # Anecdote: specific story with characters and action
    if re.search(r'\b(?:one day|on \d|in \d{4}.*(?:he|she|they|who))\b', text_lower):
        if re.search(r'\b(?:story|tale|episode|account|legend)\b', text_lower) or \
           re.search(r'\b(?:he|she|they)\s+(?:was|were|had|did|went|came|took|made|found|saw)\b', text_lower):
            return 'anecdote'

    # Character story: biographical focus
    if re.search(r'\b(?:born|lived|died|arrived|moved|settled|married)\b.*\b(?:in|at|on|here)\b', text_lower):
        if lens in ('famous_residents', 'literary_heritage'):
            return 'character_story'

    # Architectural detail
    if lens == 'historic_arch' and re.search(
        r'\b(?:facade|dome|tower|designed|built|architect|style|columns|portal|'
        r'Romanesque|Gothic|Renaissance|Baroque|neoclassical|Art Nouveau)\b', text_lower):
        return 'architectural_detail'

    # Event: something that happened at a specific time
    if re.search(r'\b(?:on|in) (?:\d{1,2} )?(?:January|February|March|April|May|June|July|August|September|October|November|December)?\s*\d{4}\b', text_lower):
        if re.search(r'\b(?:storm|massacre|fire|explosion|duel|assassination|execution|war|battle|siege)\b', text_lower):
            return 'event'

    # Sensory observation
    if lens in ('street_art', 'markets_street_food', 'parks_gardens', 'historic_cuisine'):
        if re.search(r'\b(?:atmosphere|smell|taste|sound|sight|colour|color|light|shade)\b', text_lower):
            return 'sensory_observation'

    # Factoid: discrete surprising fact
    if len(text.split()) < 60 and re.search(r'\b(?:only|first|oldest|last|most|record)\b', text_lower):
        return 'factoid'

    # Establishing: basic identity
    if re.search(r'\b(?:founded|built|designed|inaugurated|origins?|traces? its)\b', text_lower):
        if lens in ('historic_arch', 'historic_worship', 'modern_design'):
            return 'establishing'

    # Default mappings based on lens
    lens_to_type = {
        'historic_arch': 'architectural_detail',
        'hidden_history': 'anecdote',
        'dark_history': 'event',
        'war_conflict': 'event',
        'literary_heritage': 'character_story',
        'famous_residents': 'character_story',
        'music_heritage': 'character_story',
        'social_change': 'event',
        'visual_art': 'architectural_detail',
        'historic_worship': 'establishing',
        'historic_cuisine': 'sensory_observation',
        'local_legends': 'anecdote',
        'street_art': 'sensory_observation',
        'modern_design': 'architectural_detail',
        'sacred_traditions': 'anecdote',
        'science_tech': 'factoid',
        'historic_markets': 'establishing',
        'commerce_innovation': 'establishing',
        'parks_gardens': 'sensory_observation',
        'markets_street_food': 'sensory_observation',
        'history': 'event',
    }
    return lens_to_type.get(lens, 'anecdote')


def classify_emotional_register(text, lens):
    """Classify dominant tone."""
    text_lower = text.lower()

    # Somber signals
    somber_patterns = [
        r'\b(?:killed|murdered|executed|died|death|dead|massacre|deported|prison)\b',
        r'\b(?:tragic|grief|mourning|bereaved|sorrow|suffering|perished)\b',
        r'\b(?:tomb|grave|burial|crypt|memorial|martyrs?)\b',
    ]

    # Dramatic signals
    dramatic_patterns = [
        r'\b(?:storm(?:ing|ed)?|explosion|fire|rebellion|revolt|riot)\b',
        r'\b(?:stabbed|shot|assassinated|seized|arrested|imprisoned)\b',
        r'\b(?:dramatic|extraordinary|spectacular|sensation|scandal)\b',
        r'\b(?:blood|flames|fury|rage|terror)\b',
    ]

    # Playful signals
    playful_patterns = [
        r'\b(?:joke|prank|jest|laugh|funny|witty|amusing|amusement)\b',
        r'\b(?:nickname|dubbed|ironi(?:c|cally)|eccentric)\b',
        r'\b(?:urinated|drowned|drowning.*for a laugh)\b',
    ]

    # Wry signals
    wry_patterns = [
        r'\b(?:ironi(?:c|cally)|paradox|contrary|opposite|despite|yet)\b',
        r'\b(?:how ironic|the irony)\b',
        r'\b(?:pretended|claimed|supposedly)\b',
    ]

    # Reverent signals
    reverent_patterns = [
        r'\b(?:masterpiece|magnificent|splendid|sublime|extraordinary|genius)\b',
        r'\b(?:masterwork|greatest|finest|most (?:beautiful|outstanding|famous))\b',
        r'\b(?:sacred|holy|miraculous|divine|saint)\b',
    ]

    somber = sum(1 for p in somber_patterns if re.search(p, text_lower))
    dramatic = sum(1 for p in dramatic_patterns if re.search(p, text_lower))
    playful = sum(1 for p in playful_patterns if re.search(p, text_lower))
    wry = sum(1 for p in wry_patterns if re.search(p, text_lower))
    reverent = sum(1 for p in reverent_patterns if re.search(p, text_lower))

    scores = {
        'somber': somber,
        'dramatic': dramatic,
        'playful': playful,
        'wry': wry,
        'reverent': reverent,
        'neutral': 0.5,  # baseline
    }

    # Lens-based boosting
    if lens in ('dark_history',):
        scores['somber'] += 0.5
        scores['dramatic'] += 0.5
    elif lens in ('war_conflict',):
        scores['dramatic'] += 1
    elif lens in ('local_legends',):
        scores['playful'] += 0.5
        scores['wry'] += 0.5
    elif lens in ('historic_arch', 'visual_art', 'music_heritage'):
        scores['reverent'] += 0.3
    elif lens in ('hidden_history',):
        scores['wry'] += 0.3

    best = max(scores, key=scores.get)
    return best


def classify_poi_role(poi, beat_counts, beats_for_poi):
    """Classify POI role based on tier, trigger_radius, and description."""
    tier = poi.get('importance_tier', 3)
    trigger_radius = poi.get('trigger_radius', 30)
    desc = poi.get('short_description', '').lower()
    name = poi.get('name', '').lower()

    # Tier 1-2 default to walk_by_only
    if tier <= 2:
        return 'walk_by_only', f'Tier {tier} — minor landmark, default walk_by_only'

    # Large footprint candidates for setting
    setting_keywords = ['island', 'boulevard', 'garden', 'quarter', 'park', 'square',
                        'street', 'rue', 'passage', 'quai', 'avenue', 'champ']

    if tier >= 3 and (trigger_radius >= 50 or any(k in desc for k in setting_keywords) or any(k in name for k in setting_keywords)):
        # But only if it's truly an area, not a specific building/venue
        building_keywords = [
            'church', 'cathedral', 'chapel', 'museum', 'musee', 'hotel', 'palais',
            'palace', 'tower', 'tour ', 'theatre', 'theater', 'temple', 'mosque',
            'synagogue', 'basilica', 'abbey', 'priory', 'school', 'lycee',
            'college', 'bibliotheque', 'library', 'institut', 'academy',
            'fontaine', 'fountain', 'statue', 'memorial', 'cafe', 'brasserie',
            'restaurant', 'rotonde', 'closerie', 'procope', 'bon march',
            'olympia', 'pantheon', 'sorbonne', 'val-de-grace', 'invalides',
            'atelier', 'fondation', 'conciergerie', 'arsenal',
        ]
        name_lower = name.lower()

        is_building = any(k in name_lower for k in building_keywords) or any(k in desc for k in building_keywords)

        # Specific addresses (e.g. "27 Rue de Fleurus") are not settings
        is_address = bool(re.match(r'^\d+\s', name))

        # Named houses on specific streets (e.g. "Half-Timbered Houses") are stops
        is_specific_structure = bool(re.search(r'house|maison|half-timbered', name_lower))

        if not is_building and not is_address and not is_specific_structure:
            # For "Rue X" names, only classify as setting if trigger_radius >= 50 or it's a notable street
            if name_lower.startswith('rue ') and trigger_radius < 50:
                # Narrow named streets with specific historical events → stop
                return 'stop', f'Tier {tier} named street but narrow (radius={trigger_radius}m), classified as stop'

            return 'setting', f'Tier {tier}, large footprint area (trigger_radius={trigger_radius}m or area keywords in name/description)'

    # Default for tier 3-5 discrete buildings/monuments
    return 'stop', f'Tier {tier} discrete building/monument, default stop'


def main():
    # Load data
    beats = json.load(open('data/paris/beats.json'))
    pois = json.load(open('data/paris/poi-raw.json'))

    # Group beats by POI
    by_poi = defaultdict(list)
    for i, b in enumerate(beats):
        by_poi[b['poi_name']].append((i, b))

    # Beat counts per POI
    beat_counts = {poi: len(blist) for poi, blist in by_poi.items()}

    enrichment_meta = {
        'model': 'claude-opus-4-6',
        'enriched_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'version': 'v1'
    }

    # ── Phase 1: Classify beats ──
    print("Phase 1: Classifying beats...")
    for poi_name, beat_list in by_poi.items():
        total = len(beat_list)
        for beat_idx, (global_idx, beat) in enumerate(beat_list):
            text = beat['script_body']
            lens = beat['lens']

            # Extract entities
            entities = extract_entities(text, poi_name)

            # Classify sensory anchor
            sensory_anchor = classify_sensory_anchor(text, poi_name)

            # Classify narrative function
            narrative_function = classify_narrative_function(text, lens, poi_name, beat_idx, total)

            # Classify beat type
            beat_type = classify_beat_type(text, lens)

            # Classify emotional register
            emotional_register = classify_emotional_register(text, lens)

            # Compute est_spoken_seconds
            word_count = len(text.split())
            est_spoken_seconds = round(word_count / 2.5)

            # Apply to beat
            beat['entities'] = entities
            beat['sensory_anchor'] = sensory_anchor
            beat['est_spoken_seconds'] = est_spoken_seconds
            beat['narrative_function'] = narrative_function
            beat['beat_type'] = beat_type
            beat['emotional_register'] = emotional_register
            beat['_enrichment'] = enrichment_meta.copy()

    # Save beats
    json.dump(beats, open('data/paris/beats.json', 'w'), indent=2, ensure_ascii=False)
    print(f"  Enriched {len(beats)} beats")

    # ── Phase 2: Classify POIs ──
    print("\nPhase 2: Classifying POIs...")
    for poi in pois:
        name = poi['name']
        beats_for_poi = [b for _, b in by_poi.get(name, [])]
        role, reasoning = classify_poi_role(poi, beat_counts, beats_for_poi)
        poi['poi_role'] = role
        poi['_poi_role_reasoning'] = reasoning

    # Save POIs
    json.dump(pois, open('data/paris/poi-raw.json', 'w'), indent=2, ensure_ascii=False)
    print(f"  Classified {len(pois)} POIs")

    # ── Phase 3: Validation ──
    print("\n--- Validation ---")

    # Validate beats
    errors = 0
    for b in beats:
        bid = b.get('beat_id', 'unknown')
        if not isinstance(b.get('entities'), list):
            print(f"  ERROR {bid}: entities not a list")
            errors += 1
        if not isinstance(b.get('sensory_anchor'), bool):
            print(f"  ERROR {bid}: sensory_anchor not bool")
            errors += 1
        if not isinstance(b.get('est_spoken_seconds'), int):
            print(f"  ERROR {bid}: est_spoken_seconds not int")
            errors += 1
        if b.get('narrative_function') not in VALID_NF:
            print(f"  ERROR {bid}: bad narrative_function '{b.get('narrative_function')}'")
            errors += 1
        if b.get('beat_type') not in VALID_BT:
            print(f"  ERROR {bid}: bad beat_type '{b.get('beat_type')}'")
            errors += 1
        if b.get('emotional_register') not in VALID_ER:
            print(f"  ERROR {bid}: bad emotional_register '{b.get('emotional_register')}'")
            errors += 1
        expected = round(len(b['script_body'].split()) / 2.5)
        if b['est_spoken_seconds'] != expected:
            print(f"  ERROR {bid}: est_spoken_seconds {b['est_spoken_seconds']} != {expected}")
            errors += 1

    if errors == 0:
        print(f"  All {len(beats)} beats validated.")
    else:
        print(f"  {errors} errors found!")

    # Validate POIs
    poi_errors = 0
    for p in pois:
        if p.get('poi_role') not in VALID_ROLES:
            print(f"  ERROR {p['name']}: bad poi_role '{p.get('poi_role')}'")
            poi_errors += 1

    if poi_errors == 0:
        print(f"  All {len(pois)} POIs validated.")
    else:
        print(f"  {poi_errors} POI errors found!")

    # Distribution check
    print("\n--- Distribution ---")
    from collections import Counter
    for f in ['narrative_function', 'beat_type', 'emotional_register']:
        dist = Counter(b[f] for b in beats)
        total = len(beats)
        print(f"\n  {f}:")
        for val, count in dist.most_common():
            pct = count/total*100
            flag = ' ⚠️ WARNING >70%' if pct > 70 else ''
            print(f"    {val:20s} = {count:4d} ({pct:5.1f}%){flag}")


if __name__ == '__main__':
    main()
