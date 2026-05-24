from typing import Annotated

from fastapi import Depends, Request

from src.retrieval.service import RetrievalService


def get_retrieval_service(request: Request) -> RetrievalService:
    return request.app.state.retrieval_service


RetrievalServiceDep = Annotated[RetrievalService, Depends(get_retrieval_service)]
