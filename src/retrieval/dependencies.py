from typing import Annotated

from fastapi import Depends, Request

from src.retrieval.reasoning import ReasoningEngine


def get_reasoning_engine(request: Request) -> ReasoningEngine:
    return request.app.state.reasoning_engine


ReasoningEngineDep = Annotated[ReasoningEngine, Depends(get_reasoning_engine)]
