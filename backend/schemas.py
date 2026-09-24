from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    created_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    content_type: str
    size_bytes: int
    status: str
    created_at: datetime


class DocumentPageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    page_number: int
    text: str
    method: str


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)


class SearchResult(BaseModel):
    chunk_index: int
    page_number: int
    text: str
    best_line: str
    score: float


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class AskSource(BaseModel):
    number: int
    page_number: int
    text: str


class AIUsage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tokens_used: int | None
    requests_limit: int | None
    requests_remaining: int | None
    requests_reset: str | None
    tokens_limit: int | None
    tokens_remaining: int | None
    tokens_reset: str | None


class AskResponse(BaseModel):
    answer: str
    sources: list[AskSource]
    usage: AIUsage
