from typing import Annotated
from pydantic import BaseModel, Field

QueryStr = Annotated[str, Field(min_length=1, max_length=500)]
LimitInt = Annotated[int, Field(default=8, ge=1, le=20)]


class RetrievalRequest(BaseModel):
    query: QueryStr
    limit: LimitInt = 8


class RetrievedChunk(BaseModel):
    text: str
    reranker_score: float
    arxiv_id: str


class RetrievalResponse(BaseModel):
    query: str
    chunks: list[RetrievedChunk]
