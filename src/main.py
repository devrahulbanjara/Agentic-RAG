from contextlib import asynccontextmanager

import gradio as gr
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    qdrant = QdrantClient(url=settings.qdrant.url, api_key=settings.qdrant.api_key or None)
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


def _respond(message: str, history: list[dict]) -> str:
    if not message.strip():
        return "Enter a query."
    result = app.state.reasoning_engine.answer(message)
    if result.message:
        return result.message

    reply = [result.answer or ""]
    if result.chunks:
        reply.append(f"---\n\n_Sources · category: {result.category}_")
        for number, chunk in enumerate(result.chunks, 1):
            reply.append(
                f"**{number}. arxiv:{chunk.arxiv_id}** (score {chunk.reranker_score:.3f})\n\n"
                f"{chunk.text}"
            )
    return "\n\n".join(reply)


demo = gr.ChatInterface(
    fn=_respond,
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
