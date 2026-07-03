from fastapi import APIRouter

from src.retrieval.dependencies import ReasoningEngineDep
from src.retrieval.schemas import RetrievalRequest, RoutedRetrievalResponse

router = APIRouter(prefix="/retrieve", tags=["retrieval"])


@router.post("/")
def retrieve(
    request: RetrievalRequest, engine: ReasoningEngineDep
) -> RoutedRetrievalResponse:
    return engine.answer(request.query)
