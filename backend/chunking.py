import re
from dataclasses import dataclass

CHUNK_SIZE = 100  # max words in one chunk (tested: 200 was too broad, 60 split facts apart)
CHUNK_OVERLAP = 20  # words repeated from the end of the previous chunk

# A sentence ends at . ! or ? followed by a space
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Chunk:
    page_number: int
    text: str


def split_sentences(text: str) -> list[str]:
    sentences = []

    # Split line by line first, so rows of a table (like a bill) stay separate.
    # The last sentence of each line keeps a "\n" so the line break survives.
    for line in text.splitlines():
        parts = [part.strip() for part in SENTENCE_END.split(line) if part.strip()]
        if parts:
            parts[-1] += "\n"
            sentences.extend(parts)

    return sentences


def join_sentences(sentences: list[str]) -> str:
    return " ".join(sentences).replace("\n ", "\n").strip()


def split_long_sentence(sentence: str, chunk_size: int) -> list[str]:
    # A "sentence" longer than a whole chunk (e.g. OCR text with no full stops)
    # is cut into word groups, like the simple chunker from try_chunk.py
    words = sentence.split()
    return [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]


def chunk_page(
    text: str,
    page_number: int,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[Chunk]:
    if overlap >= chunk_size:
        # Otherwise the loop never moves forward (Experiment 3 from Lesson 3.1)
        raise ValueError("overlap must be smaller than chunk_size")

    sentences = []
    for sentence in split_sentences(text):
        if len(sentence.split()) > chunk_size:
            sentences.extend(split_long_sentence(sentence, chunk_size))
        else:
            sentences.append(sentence)

    chunks = []
    current = []  # sentences in the chunk being built
    current_words = 0

    for sentence in sentences:
        sentence_words = len(sentence.split())

        # Adding this sentence would make the chunk too big: close it
        # and start the next one with the last few sentences as overlap
        if current and current_words + sentence_words > chunk_size:
            chunks.append(Chunk(page_number, join_sentences(current)))

            overlap_sentences = []
            overlap_words = 0
            for previous in reversed(current):
                previous_words = len(previous.split())
                if overlap_words + previous_words > overlap:
                    break
                overlap_sentences.insert(0, previous)
                overlap_words += previous_words

            current = overlap_sentences
            current_words = overlap_words

        current.append(sentence)
        current_words += sentence_words

    if current:
        chunks.append(Chunk(page_number, join_sentences(current)))

    return chunks
