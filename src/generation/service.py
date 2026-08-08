from loguru import logger
from src.generation.context import assemble_context
from src.llm.base import LLMProvider
from src.retrieval.schemas import RetrievedChunk


class AnswerGenerator:
    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    def generate(self, query: str, chunks: list[RetrievedChunk]) -> str:
        context = assemble_context(chunks)
        logger.info(
            "generating answer | chunks={} context_chars={}", len(chunks), len(context)
        )
        answer = self._llm.generate_answer(query, context)
        logger.info("answer generated | chars={}", len(answer))
        return answer
