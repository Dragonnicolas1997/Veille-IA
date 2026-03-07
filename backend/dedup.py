"""Déduplication d'articles par similarité de titre."""
import re

STOP_WORDS = {
    "le", "la", "les", "de", "du", "des", "un", "une", "en", "et", "à", "au", "aux",
    "the", "a", "an", "of", "in", "to", "for", "and", "or", "is", "are", "was", "were",
    "on", "with", "by", "from", "at", "as", "it", "its", "that", "this", "be", "has", "have",
    "par", "pour", "sur", "dans", "qui", "que", "est", "sont", "avec", "son", "sa", "ses",
    "ce", "cette", "ces", "se", "ne", "pas", "plus", "mais", "how", "what", "why", "when",
    "comment", "quoi", "pourquoi", "quand", "peut", "peut-on", "faut", "tout", "nous", "vous",
    "new", "now", "just", "get", "got", "dit", "fait", "entre", "aussi", "encore",
    "says", "said", "could", "will", "would", "should", "about", "than", "into", "been",
    "here", "there", "leur", "leurs", "notre", "votre", "selon", "vers", "chez",
}


def _normalize(title: str) -> set[str]:
    """Extract significant words from a title."""
    t = title.lower()
    t = re.sub(r"[^\w\s]", " ", t)
    return {w for w in t.split() if w not in STOP_WORDS and len(w) > 2}


def _extract_entities(title: str) -> tuple[set[str], set[str]]:
    """Extract named entities and numbers separately — strongest dedup signal.
    Returns (names, numbers)."""
    names = set()
    numbers = set()
    # Company/product names (capitalized words or known AI acronyms)
    for w in re.findall(r'\b[A-Z][a-zA-Z]{2,}\b', title):
        names.add(w.lower())
    # Also catch all-caps acronyms like GPT, AMD, BMW
    for w in re.findall(r'\b[A-Z]{2,}\b', title):
        names.add(w.lower())
    # Numbers (versions, amounts, etc.)
    for n in re.findall(r'\b\d+(?:\.\d+)?\b', title):
        numbers.add(n)
    return names, numbers


def _similarity(a_words: set, b_words: set,
                a_names: set, a_numbers: set,
                b_names: set, b_numbers: set) -> float:
    """Combined similarity: Jaccard on words + entity overlap bonus."""
    if not a_words or not b_words:
        return 0.0

    jaccard = len(a_words & b_words) / len(a_words | b_words)

    # Entity overlap bonus
    entity_bonus = 0.0
    common_names = a_names & b_names
    common_numbers = a_numbers & b_numbers

    # Strongest signal: same company/product name + same version number
    # e.g. "OpenAI" + "5.4" → almost certainly same story
    if common_names and common_numbers:
        entity_bonus = 0.35
    elif len(common_names) >= 2:
        entity_bonus = 0.25
    elif len(common_names) >= 1:
        entity_bonus = 0.1

    return jaccard + entity_bonus


def deduplicate(articles: list[dict], title_key="title",
                score_key=None, date_key=None, threshold=0.35) -> list[dict]:
    """
    Group articles by title similarity (combined score > threshold).
    Uses both word overlap and named entity matching.
    Keep the best per group (highest score, then most recent date).
    Returns deduplicated list preserving original order for the kept articles.
    """
    if not articles:
        return []

    # Use title_fr if available for better French comparison
    def get_title(a):
        return a.get("title_fr") or a.get(title_key, "")

    normalized = [_normalize(get_title(a)) for a in articles]
    # Extract entities from both original and French titles for better coverage
    entities = []
    for a in articles:
        orig = a.get(title_key, "")
        fr = a.get("title_fr", "") or ""
        names1, nums1 = _extract_entities(orig)
        names2, nums2 = _extract_entities(fr)
        entities.append((names1 | names2, nums1 | nums2))

    # Assign each article to a group
    groups: list[list[int]] = []

    for i, words in enumerate(normalized):
        placed = False
        for group in groups:
            rep_idx = group[0]
            score = _similarity(
                words, normalized[rep_idx],
                entities[i][0], entities[i][1],
                entities[rep_idx][0], entities[rep_idx][1],
            )
            if score > threshold:
                group.append(i)
                placed = True
                break
        if not placed:
            groups.append([i])

    # Pick the best from each group
    kept_indices = set()
    for group in groups:
        if len(group) == 1:
            kept_indices.add(group[0])
        else:
            def sort_key(idx):
                a = articles[idx]
                s = a.get(score_key, 0) if score_key else 0
                d = a.get(date_key, "") if date_key else ""
                return (s or 0, d or "")
            best = max(group, key=sort_key)
            kept_indices.add(best)

    return [a for i, a in enumerate(articles) if i in kept_indices]
