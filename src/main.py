from contextlib import asynccontextmanager

import gradio as gr
from fastembed import SparseTextEmbedding, TextEmbedding
from fastapi import FastAPI
from qdrant_client import QdrantClient

from src.core.config import settings
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


def _retrieve(message: str, history: list[dict]) -> str:
    if not message.strip():
        return "Enter a query."
    service = app.state.retrieval_service
    chunks = service.retrieve(message)
    if not chunks:
        return "No chunks found."
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(
            f"**Chunk {i}** (score: {chunk.score:.4f}, arxiv: {chunk.arxiv_id})\n\n"
            f"{chunk.text}"
        )
    return "\n\n---\n\n".join(parts)


demo = gr.ChatInterface(
    fn=_retrieve,
    title="Research Paper Retrieval",
    save_history=True,
    examples=[
        "How does multi-head attention work?",
        "What is the Transformer architecture?",
        "Explain positional encoding",
    ],
    chatbot=gr.Chatbot(height=700, placeholder="Ask anything about indexed papers"),
    textbox=gr.Textbox(placeholder="Ask a question about research papers...", scale=7),
)
app = gr.mount_gradio_app(app, demo, path="/ui")
