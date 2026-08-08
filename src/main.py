from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from qdrant_client import QdrantClient
from src.core.config import settings
from src.core.embeddings import BGEM3Embedder
from src.core.reranker import BGEReranker
from src.generation.service import AnswerGenerator
from src.llm.factory import get_llm_provider
from src.retrieval.reasoning import ReasoningEngine
from src.retrieval.router import router as retrieval_router
from src.retrieval.service import RetrievalService

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    qdrant = QdrantClient(
        url=settings.qdrant.url, api_key=settings.qdrant.api_key or None
    )
    retrieval = RetrievalService(
        qdrant=qdrant,
        embedder=BGEM3Embedder(settings.qdrant.embedding_model),
        reranker=BGEReranker(settings.reranker.model),
        collection_name=settings.qdrant.collection,
    )
    llm = get_llm_provider(settings.reasoning.classifier_model)
    app.state.reasoning_engine = ReasoningEngine(
        classifier=llm,
        retrieval=retrieval,
        generator=AnswerGenerator(llm),
        settings=settings.reasoning,
    )
    yield
    qdrant.close()


app = FastAPI(title="Research Assistant", lifespan=lifespan)
app.include_router(retrieval_router)
app.frontend("/", directory=FRONTEND_DIR)
