import json
from collections.abc import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from src.retrieval.dependencies import ReasoningEngineDep
from src.retrieval.schemas import (
    ReasoningTrace,
    RetrievalRequest,
    RoutedRetrievalResponse,
)

router = APIRouter(prefix="/retrieve", tags=["retrieval"])


@router.post("/")
def retrieve(
    request: RetrievalRequest, engine: ReasoningEngineDep
) -> RoutedRetrievalResponse:
    return engine.answer(request.query)


@router.post("/stream")
def retrieve_stream(
    request: RetrievalRequest, engine: ReasoningEngineDep
) -> StreamingResponse:

    def events() -> Iterator[str]:
        for step in engine.stream_answer(request.query):
            if isinstance(step, ReasoningTrace):
                payload = {"type": "trace", "trace": step.model_dump(mode="json")}
            else:
                payload = {"type": "final", "response": step.model_dump(mode="json")}
            yield json.dumps(payload) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")
