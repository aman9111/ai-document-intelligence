import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).resolve().parent / ".env")

# Any OpenAI-compatible provider works (Groq, OpenRouter, ...):
# switching provider only means changing these values in .env
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL")
LLM_MODEL = os.getenv("LLM_MODEL")

SYSTEM_PROMPT = """You answer questions about a user's document (medical reports, bills, forms).

Rules:
- Use ONLY the numbered document excerpts given below the question. Do not use outside facts about this patient or document.
- You may use general knowledge to explain terms (e.g. "Augmentin is an antibiotic", "TDS means three times a day").
- The text comes from OCR, so it can have errors: "S" for "5", "O" for "0", missing spaces. Read it sensibly.
- Copy numbers, amounts and dates exactly as written. Do not add currency symbols or units that are not in the text.
- If the excerpts do not contain the answer, say: "I couldn't find this in the document."
- After each fact, cite the excerpt number(s) it came from, like [1] or [2][3].
- Be short and clear: 1-3 sentences, or a short list if there are several items.
- Earlier messages of the conversation are given for context. Use them to understand
  follow-up questions like "and for how long?", but take facts only from the excerpts."""


@dataclass
class Source:
    number: int
    page_number: int
    text: str


@dataclass
class LLMUsage:
    # Tokens used by the last answer (question + excerpts + answer)
    tokens_used: int | None
    # Free-tier limits the provider reports in its response headers
    requests_limit: int | None
    requests_remaining: int | None
    requests_reset: str | None
    tokens_limit: int | None
    tokens_remaining: int | None
    tokens_reset: str | None


class LLMNotConfiguredError(Exception):
    pass


# Latest limits seen from the provider. The API key is shared by the whole
# app, so these numbers are the same for every user.
last_usage: LLMUsage | None = None


def _header_int(headers, name: str) -> int | None:
    value = headers.get(name)
    return int(value) if value and value.isdigit() else None


def save_usage(headers, tokens_used: int | None) -> LLMUsage:
    global last_usage

    last_usage = LLMUsage(
        tokens_used=tokens_used,
        requests_limit=_header_int(headers, "x-ratelimit-limit-requests"),
        requests_remaining=_header_int(headers, "x-ratelimit-remaining-requests"),
        requests_reset=headers.get("x-ratelimit-reset-requests"),
        tokens_limit=_header_int(headers, "x-ratelimit-limit-tokens"),
        tokens_remaining=_header_int(headers, "x-ratelimit-remaining-tokens"),
        tokens_reset=headers.get("x-ratelimit-reset-tokens"),
    )
    return last_usage


_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client

    if not LLM_API_KEY or not LLM_BASE_URL or not LLM_MODEL:
        raise LLMNotConfiguredError("Set LLM_API_KEY, LLM_BASE_URL and LLM_MODEL in backend/.env")

    if _client is None:
        _client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

    return _client


def build_user_message(question: str, sources: list[Source]) -> str:
    excerpts = "\n\n".join(
        f"[{source.number}] (page {source.page_number})\n{source.text}" for source in sources
    )
    return f"Question: {question}\n\nDocument excerpts:\n\n{excerpts}"


# Settings shared by normal and streaming answers
ANSWER_SETTINGS = {
    # Low temperature = less "creative", sticks closer to the excerpts
    "temperature": 0.2,
    # gpt-oss thinks before answering; "medium" understood OCR typos like "Sdays"
    "reasoning_effort": "medium",
    "max_completion_tokens": 1000,
}


def build_messages(question: str, sources: list[Source], history: list[dict] | None = None) -> list[dict]:
    # history = earlier {"role", "content"} messages of the conversation (without
    # their excerpts, to save tokens). Only the new question gets excerpts.
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        *(history or []),
        {"role": "user", "content": build_user_message(question, sources)},
    ]


def answer_question(question: str, sources: list[Source]) -> tuple[str, LLMUsage]:
    # with_raw_response gives us the HTTP headers too, which is where the
    # provider says how much of the free limit is left
    raw = get_client().chat.completions.with_raw_response.create(
        model=LLM_MODEL,
        messages=build_messages(question, sources),
        **ANSWER_SETTINGS,
    )

    response = raw.parse()
    usage = save_usage(raw.headers, response.usage.total_tokens if response.usage else None)

    return (response.choices[0].message.content or "").strip(), usage


def stream_answer(
    question: str,
    sources: list[Source],
    history: list[dict],
) -> Iterator[tuple[str, str | LLMUsage]]:
    # Yields ("token", "some text") for every small piece of the answer as the
    # LLM writes it, and finally ("usage", LLMUsage) once it has finished
    raw = get_client().chat.completions.with_raw_response.create(
        model=LLM_MODEL,
        messages=build_messages(question, sources, history),
        stream=True,
        # Ask the provider to send the token count in the last piece
        stream_options={"include_usage": True},
        **ANSWER_SETTINGS,
    )

    tokens_used = None

    for chunk in raw.parse():
        if chunk.choices and chunk.choices[0].delta.content:
            yield "token", chunk.choices[0].delta.content
        if chunk.usage:
            tokens_used = chunk.usage.total_tokens

    yield "usage", save_usage(raw.headers, tokens_used)
