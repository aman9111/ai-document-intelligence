from fastembed import TextEmbedding

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMENSIONS = 384

_model: TextEmbedding | None = None


def get_model() -> TextEmbedding:
    # Loading the model takes a few seconds, so it's done once
    # (on first use) and then reused for every request
    global _model

    if _model is None:
        _model = TextEmbedding(EMBEDDING_MODEL)

    return _model


def embed_passages(texts: list[str]) -> list[list[float]]:
    return [vector.tolist() for vector in get_model().passage_embed(texts)]


def embed_query(text: str) -> list[float]:
    return next(iter(get_model().query_embed(text))).tolist()


def similarity(a: list[float], b: list[float]) -> float:
    # The model's vectors have length 1, so cosine similarity is just the dot product
    return sum(x * y for x, y in zip(a, b))
