from typing import Annotated

from pydantic import BaseModel, Field
from src.llm.schemas import QueryCategory, QueryIntent

QueryStr = Annotated[str, Field(min_length=1, max_length=500)]


class RetrievalRequest(BaseModel):
    query: QueryStr


class RetrievedChunk(BaseModel):
    text: str
    reranker_score: float
    arxiv_id: str
    chunk_type: str
    section_path: list[str] = []


class ReasoningTrace(BaseModel):
    intent: QueryIntent
    category: QueryCategory | None = None
    confidence: float | None = None
    expansion: str | None = None
    search_queries: list[str] = []
    rerank_pool: int | None = None
    mmr_lambda: float | None = None
    chunks_kept: int | None = None


class RoutedRetrievalResponse(BaseModel):
    query: str
    intent: QueryIntent
    category: QueryCategory | None = None
    message: str | None = None
    answer: str | None = None
    chunks: list[RetrievedChunk] = []
    trace: ReasoningTrace | None = None
