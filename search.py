"""Fuzzy search scoring engine for agent-first entity resolution."""

from dataclasses import dataclass

from rapidfuzz import fuzz


# --- Soundex (phonetic matching, no extra dependency) ---


def soundex(word: str) -> str:
    """Simple Soundex implementation for phonetic matching."""
    if not word:
        return ""
    word = word.upper()
    codes = {
        "B": "1", "F": "1", "P": "1", "V": "1",
        "C": "2", "G": "2", "J": "2", "K": "2", "Q": "2", "S": "2",
        "X": "2", "Z": "2",
        "D": "3", "T": "3",
        "L": "4",
        "M": "5", "N": "5",
        "R": "6",
    }
    result = word[0]
    prev = codes.get(word[0], "0")
    for ch in word[1:]:
        code = codes.get(ch, "0")
        if code != "0" and code != prev:
            result += code
        prev = code if code != "0" else prev
    return (result + "000")[:4]


def phonetic_match(query: str, candidate: str) -> bool:
    """Check if first tokens match phonetically."""
    q_tokens = query.strip().split()
    c_tokens = candidate.strip().split()
    if not q_tokens or not c_tokens:
        return False
    return soundex(q_tokens[0]) == soundex(c_tokens[0])


# --- Scoring ---


@dataclass
class ScoredResult:
    id: str
    score: float  # 0.0 - 1.0
    match_type: str  # "exact", "fuzzy", "phonetic", "partial"
    data: dict  # the original record


MIN_SCORE = 0.40


def score_candidate(query: str, name: str) -> tuple[float, str]:
    """Score how well a query matches a candidate name.

    Returns (score 0.0-1.0, match_type).
    """
    q = query.lower().strip()
    c = name.lower().strip()

    # Exact match
    if q == c:
        return 1.0, "exact"

    # Token exact: query matches a full token in the name
    c_tokens = c.split()
    if q in c_tokens:
        return 0.95, "exact"

    # Fuzzy score (handles typos, partial matches, word reordering)
    wratio = fuzz.WRatio(q, c) / 100.0

    # Token sort ratio (handles "lai kevin" → "kevin lai")
    token_sort = fuzz.token_sort_ratio(q, c) / 100.0

    # Partial ratio (handles substring: "kev" in "kevin lai")
    partial = fuzz.partial_ratio(q, c) / 100.0

    # Take the best fuzzy signal
    best_fuzzy = max(wratio, token_sort, partial * 0.85)

    # Phonetic bonus
    phonetic_bonus = 0.05 if phonetic_match(q, c) else 0.0

    score = min(best_fuzzy + phonetic_bonus, 0.99)

    # Determine match type
    if phonetic_bonus > 0 and best_fuzzy < 0.6:
        match_type = "phonetic"
    elif partial > wratio and partial > token_sort:
        match_type = "partial"
    else:
        match_type = "fuzzy"

    return round(score, 3), match_type


def score_record(
    query: str,
    record_id: str,
    fields: list[str],
    data: dict,
) -> ScoredResult | None:
    """Score a record by checking the query against multiple fields.

    Returns the best match across all fields, or None if below threshold.
    """
    best_score = 0.0
    best_type = "fuzzy"

    for field in fields:
        value = data.get(field)
        if not value:
            continue
        s, t = score_candidate(query, str(value))
        if s > best_score:
            best_score = s
            best_type = t

    if best_score < MIN_SCORE:
        return None

    return ScoredResult(id=record_id, score=best_score, match_type=best_type, data=data)


def determine_confidence(results: list[ScoredResult]) -> tuple[bool, str | None]:
    """Determine if the top result is a confident match.

    Returns (is_confident, best_match_id or None).
    """
    if not results:
        return False, None

    top = results[0]

    # Single strong match
    if len(results) == 1 and top.score >= 0.60:
        return True, top.id

    # Clear winner: high score with meaningful gap to second
    if len(results) >= 2:
        gap = top.score - results[1].score
        if top.score >= 0.85 and gap >= 0.15:
            return True, top.id

    # Exact match confident only if no close second
    if top.match_type == "exact":
        if len(results) < 2 or top.score - results[1].score >= 0.05:
            return True, top.id

    return False, None
