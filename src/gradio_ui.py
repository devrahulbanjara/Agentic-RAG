import gradio as gr
from fastapi import FastAPI


def create_demo(app: FastAPI) -> gr.Blocks:
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

    return gr.ChatInterface(
        fn=_retrieve,
        title="Research Paper Retrieval",
        save_history=True,
        examples=[
            "How does multi-head attention work?",
            "What is the Transformer architecture?",
            "Explain positional encoding",
        ],
        chatbot=gr.Chatbot(height=700, placeholder="Ask anything about indexed papers"),
        textbox=gr.Textbox(
            placeholder="Ask a question about research papers...", scale=7
        ),
    )
