from time import perf_counter

from loguru import logger

from src.core.config import ReasoningSettings
from src.generation.service import AnswerGenerator
from src.llm.base import LLMError, LLMProvider
from src.llm.schemas import QueryCategory, QueryClassification, QueryIntent
from src.retrieval.schemas import RetrievedChunk, RoutedRetrievalResponse
from src.retrieval.service import RetrievalService
from src.retrieval.strategies import (
    DEFAULT_STRATEGY,
    STRATEGY_BY_CATEGORY,
    RetrievalStrategy,
)

CONVERSATIONAL_REPLY = (
    "I'm a research assistant for the indexed arXiv papers. Ask me about their "
    "methods, results, or how they compare."
)
REFUSAL_REPLY = (
    "I can only answer questions grounded in the indexed arXiv papers, and I "
    "don't have that here."
)
NO_EVIDENCE_REPLY = "I don't have that information in the retrieved papers."
GENERATION_FAILED_REPLY = (
    "I couldn't write an answer just now. The most relevant passages I found are "
    "listed below."
)


class ReasoningEngine:
    def __init__(
        self,
        classifier: LLMProvider,
        retrieval: RetrievalService,
        generator: AnswerGenerator,
        settings: ReasoningSettings,
    ) -> None:
        self._classifier = classifier
        self._retrieval = retrieval
        self._generator = generator
        self._settings = settings

    def answer(self, query: str) -> RoutedRetrievalResponse:
        logger.info("query received | query={!r}", query)

        # if routing is disabled, skip classifications, and fancy things
        if not self._settings.routing_enabled:
            logger.info("routing disabled | using default strategy")
            return self._run_retrieval(query, None, DEFAULT_STRATEGY)

        classification = self._classify(query)

        if classification.intent is QueryIntent.CONVERSATIONAL:
            return self._reply(query, classification.intent, CONVERSATIONAL_REPLY)
        if classification.intent is QueryIntent.OUT_OF_SCOPE:
            return self._reply(query, classification.intent, REFUSAL_REPLY)

        strategy, category = self._resolve_strategy(classification)
        return self._run_retrieval(query, category, strategy)

    def _classify(self, query: str) -> QueryClassification:
        try:
            classification = self._classifier.classify_query(query)
        except LLMError:
            logger.exception("classification failed | falling back to retrieval")
            return QueryClassification(intent=QueryIntent.RETRIEVAL, confidence=0.0)
        logger.info(
            "classified | intent={} category={} confidence={:.2f}",
            classification.intent,
            classification.category,
            classification.confidence,
        )
        return classification

    def _resolve_strategy(
        self, classification: QueryClassification
    ) -> tuple[RetrievalStrategy, QueryCategory | None]:
        category = classification.category
        if (
            category is None
            or classification.confidence < self._settings.classifier_confidence_floor
        ):
            return DEFAULT_STRATEGY, category
        return STRATEGY_BY_CATEGORY.get(category, DEFAULT_STRATEGY), category

    def _run_retrieval(
        self,
        query: str,
        category: QueryCategory | None,
        strategy: RetrievalStrategy,
    ) -> RoutedRetrievalResponse:
        started = perf_counter()
        search_queries = self._build_search_queries(query, strategy)
        logger.debug(
            "search queries | expansion={} count={} {}",
            strategy.expansion,
            len(search_queries),
            search_queries,
        )
        chunks = self._retrieval.retrieve(
            query,
            search_queries,
            rerank_pool=strategy.rerank_pool,
            limit=strategy.final_limit,
            mmr_lambda=strategy.mmr_lambda,
        )
        answer = self._write_answer(query, chunks)
        logger.info(
            "routed query | category={} expansion={} searches={} chunks={} latency_ms={:.0f}",
            category,
            strategy.expansion,
            len(search_queries),
            len(chunks),
            (perf_counter() - started) * 1000,
        )
        return RoutedRetrievalResponse(
            query=query,
            intent=QueryIntent.RETRIEVAL,
            category=category,
            answer=answer,
            chunks=chunks,
        )

    def _write_answer(self, query: str, chunks: list[RetrievedChunk]) -> str:
        if not chunks:
            logger.info("no evidence above floor | refusing, generation skipped")
            return NO_EVIDENCE_REPLY
        try:
            return self._generator.generate(query, chunks)
        except LLMError:
            logger.exception("Answer generation failed; returning chunks only")
            return GENERATION_FAILED_REPLY

    def _build_search_queries(
        self, query: str, strategy: RetrievalStrategy
    ) -> list[str]:
        if strategy.expansion == "fusion":
            return [query, *self._expand(query, strategy.fusion_variations)]
        if strategy.expansion == "decompose":
            return self._decompose(query)
        return [query]

    def _expand(self, query: str, count: int) -> list[str]:
        try:
            return self._classifier.expand_query(query, count)
        except LLMError:
            logger.exception("Query expansion failed; using original query only")
            return []

    def _decompose(self, query: str) -> list[str]:
        try:
            sub_questions = self._classifier.decompose_query(query)
        except LLMError:
            logger.exception("Query decomposition failed; using original query only")
            return [query]
        return sub_questions or [query]

    def _reply(
        self, query: str, intent: QueryIntent, message: str
    ) -> RoutedRetrievalResponse:
        logger.info("routed query | intent={} (no retrieval)", intent)
        return RoutedRetrievalResponse(query=query, intent=intent, message=message)
