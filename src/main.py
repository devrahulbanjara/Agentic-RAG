from contextlib import asynccontextmanager

import gradio as gr
from fastembed import SparseTextEmbedding, TextEmbedding
from fastapi import FastAPI
from qdrant_client import QdrantClient

from src.core.config import settings
from src.gradio_ui import create_demo
from src.retrieval.router import router as retrieval_router
from src.retrieval.service import RetrievalService


@asynccontextmanager
async def lifespan(app: FastAPI):
    qdrant = QdrantClient(url=settings.qdrant_url)
    app.state.retrieval_service = RetrievalService(
        qdrant=qdrant,
        dense_encoder=TextEmbedding(model_name=settings.dense_model),
        sparse_encoder=SparseTextEmbedding(model_name=settings.sparse_model),
        collection_name=settings.qdrant_collection,
    )
    yield
    qdrant.close()


app = FastAPI(title="Research Assistant", lifespan=lifespan)
app.include_router(retrieval_router)
app = gr.mount_gradio_app(app, create_demo(app), path="/ui")
