import math
import re
from dataclasses import dataclass

from embeddings import embed_passages, similarity

# How much the exact-word score counts in the final score.
# 0 (meaning only) confused "dengue" with "malaria"; higher values let
# common words like "hospital" pull in wrong lines.
KEYWORD_WEIGHT = 0.15

# Extra score when a question word matches the label of a "LABEL: value" line,
# e.g. "What surgery was done?" -> "SURGERY: Laser piles under spinal anaesthesia".
# Tested 0.1 / 0.2 / 0.3 on a bill and a discharge summary: 0.3 was best (20/27).
LABEL_WEIGHT = 0.3

# Sentences shorter than this (headings like "BILLING." or "DR.") are joined
# with the next sentence, so they don't win on their own
MIN_ANSWER_WORDS = 4

# A "LABEL: value" line: up to 4 words, then a colon
LABEL_PATTERN = re.compile(r"^\s*([A-Za-z][A-Za-z ./()&-]{0,40}?)\s*:")

STOP_WORDS = set(
    "a an the is are was were be been of to in on for and or what which who whom "
    "how much many did does do at by with from this that these those it its as i "
    "me my we our you your he she they his her their any there about when where "
    "why should can could would will has have had tell give show "
    # "patient" is on almost every line of a medical document, so it tells us nothing
    "patient".split()
)

# Words that documents often write in short form (e.g. "Mob." for phone)
SYNONYMS = {
    "phone": {"mob", "mobile", "tel", "contact", "gsm"},
    "mobile": {"mob", "phone", "tel"},
    "number": {"no"},
    "doctor": {"dr"},
    "amount": {"amt"},
    "cost": {"amount", "price", "charge"},
    "price": {"amount", "cost", "charge"},
    "charge": {"amount", "cost", "price"},
    "age": {"yrs", "year"},
    "gender": {"sex"},
    "illness": {"diagnosis", "disease"},
    "disease": {"diagnosis", "illness"},
    "problem": {"diagnosis", "complaint"},
    "fee": {"fees", "charge", "amount"},
}

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Answer:
    text: str
    score: float
    chunk_id: int


def stem(word: str) -> str:
    # Very small stemmer: "tests" -> "test", "charges" -> "charg"
    for suffix in ("ing", "es", "ed", "s"):
        if len(word) > 4 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def keywords(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {stem(word) for word in words if word not in STOP_WORDS and len(word) > 1}


def join_headings(lines: list[str]) -> list[str]:
    # A heading line with no value ("DISCHARGE ADVICE:") says nothing on its own,
    # so join it to the line below: "DISCHARGE ADVICE: Tab Zinnat 250mg BD"
    joined = []
    heading = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.endswith(":") and len(line.split()) <= 4:
            heading = f"{heading} {line}".strip()
            continue
        joined.append(f"{heading} {line}".strip())
        heading = ""

    if heading:
        joined.append(heading)

    return joined


def label_of(unit: str) -> set[str]:
    match = LABEL_PATTERN.match(unit)
    return keywords(match.group(1)) if match else set()


def answer_units(chunk_text: str) -> list[str]:
    # One "answer" is a sentence inside one line, e.g. "4 Electrolytes 800.00"
    units = []

    for line in join_headings(chunk_text.split("\n")):
        merged = []
        pending = ""

        for sentence in SENTENCE_END.split(line):
            pending = f"{pending} {sentence.strip()}".strip()
            if len(pending.split()) >= MIN_ANSWER_WORDS:
                merged.append(pending)
                pending = ""

        if pending:
            if merged:
                merged[-1] += " " + pending
            else:
                merged.append(pending)

        units.extend(merged)

    return units


def rank_answers(
    query: str,
    query_vector: list[float],
    chunks: list[tuple[int, str]],
) -> list[Answer]:
    # Collect every answer unit from the candidate chunks (without duplicates
    # from chunk overlap), remembering which chunk each one came from
    unit_chunk: dict[str, int] = {}
    for chunk_id, chunk_text in chunks:
        for unit in answer_units(chunk_text):
            unit_chunk.setdefault(unit, chunk_id)

    units = list(unit_chunk)
    if not units:
        return []

    # 1. Meaning score (embeddings), same as before
    vectors = embed_passages(units)
    meaning_scores = [similarity(query_vector, vector) for vector in vectors]

    # 2. Keyword score: how many of the question's words appear in the unit.
    # Rare words count more (IDF): "dengue" matters more than "test".
    unit_keywords = [keywords(unit) for unit in units]
    document_frequency: dict[str, int] = {}
    for words in unit_keywords:
        for word in words:
            document_frequency[word] = document_frequency.get(word, 0) + 1

    def idf(word: str) -> float:
        return math.log(1 + len(units) / (1 + document_frequency.get(word, 0)))

    query_groups = [
        {word} | {stem(synonym) for synonym in SYNONYMS.get(word, ())}
        for word in keywords(query)
    ]
    total_weight = sum(max(idf(word) for word in group) for group in query_groups) or 1

    answers = []
    for unit, words, meaning in zip(units, unit_keywords, meaning_scores):
        matched = sum(
            max((idf(word) for word in group if word in words), default=0)
            for group in query_groups
        )
        keyword_score = matched / total_weight

        # Do question words match this line's label ("SURGERY:", "Insurance :")?
        # Weighted by IDF too, so a common word like "patient" in
        # "Patient Name :" gives almost no boost, but a rare one like "surgery" does
        label = label_of(unit)
        label_score = sum(
            max((idf(word) for word in group if word in label), default=0)
            for group in query_groups
        ) / total_weight

        # 3. Hybrid score: mostly meaning, plus boosts for exact words and labels
        score = (
            (1 - KEYWORD_WEIGHT) * meaning
            + KEYWORD_WEIGHT * keyword_score
            + LABEL_WEIGHT * label_score
        )
        answers.append(Answer(unit, score, unit_chunk[unit]))

    return sorted(answers, key=lambda answer: answer.score, reverse=True)
