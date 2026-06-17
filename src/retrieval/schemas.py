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


class RoutedRetrievalResponse(BaseModel):
    query: str
    intent: QueryIntent
    category: QueryCategory | None = None
    message: str | None = None
    chunks: list[RetrievedChunk] = []
