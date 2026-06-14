from fastapi import APIRouter

from src.retrieval.dependencies import RetrievalServiceDep
from src.retrieval.schemas import RetrievalRequest, RetrievalResponse

router = APIRouter(prefix="/retrieve", tags=["retrieval"])


@router.post("/")
def retrieve(
    request: RetrievalRequest, service: RetrievalServiceDep
) -> RetrievalResponse:
    chunks = service.retrieve(request.query, request.limit, request.mmr_lambda)
    return RetrievalResponse(query=request.query, chunks=chunks)
