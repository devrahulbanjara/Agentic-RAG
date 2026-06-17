from time import perf_counter

from loguru import logger

from src.core.config import ReasoningSettings
from src.llm.base import LLMError, LLMProvider
from src.llm.schemas import QueryCategory, QueryClassification, QueryIntent
from src.retrieval.recipes import GENERAL_RECIPE, RECIPES, RetrievalRecipe
from src.retrieval.schemas import RoutedRetrievalResponse
from src.retrieval.service import RetrievalService

CONVERSATIONAL_REPLY = (
    "I'm a research assistant for the indexed arXiv papers. Ask me about their "
    "methods, results, or how they compare."
)
REFUSAL_REPLY = (
    "I can only answer questions grounded in the indexed arXiv papers, and I "
    "don't have that here."
)


class ReasoningEngine:
    def __init__(
        self,
        classifier: LLMProvider,
        retrieval: RetrievalService,
        settings: ReasoningSettings,
    ) -> None:
        self._classifier = classifier
        self._retrieval = retrieval
        self._settings = settings

    def answer(self, query: str) -> RoutedRetrievalResponse:
        if not self._settings.routing_enabled:
            return self._run_retrieval(query, None, GENERAL_RECIPE)

        classification = self._classify(query)

        if classification.intent is QueryIntent.CONVERSATIONAL:
            return self._reply(query, classification.intent, CONVERSATIONAL_REPLY)
        if classification.intent is QueryIntent.OUT_OF_SCOPE:
            return self._reply(query, classification.intent, REFUSAL_REPLY)

        recipe, category = self._resolve_recipe(classification)
        return self._run_retrieval(query, category, recipe)

    def _classify(self, query: str) -> QueryClassification:
        try:
            return self._classifier.classify_query(query)
        except LLMError:
            logger.exception("Query classification failed; falling back to retrieval")
            return QueryClassification(intent=QueryIntent.RETRIEVAL, confidence=0.0)

    def _resolve_recipe(
        self, classification: QueryClassification
    ) -> tuple[RetrievalRecipe, QueryCategory | None]:
        category = classification.category
        if (
            category is None
            or classification.confidence < self._settings.classifier_confidence_floor
        ):
            return GENERAL_RECIPE, category
        return RECIPES.get(category, GENERAL_RECIPE), category

    def _run_retrieval(
        self,
        query: str,
        category: QueryCategory | None,
        recipe: RetrievalRecipe,
    ) -> RoutedRetrievalResponse:
        started = perf_counter()
        search_queries = self._build_search_queries(query, recipe)
        chunks = self._retrieval.retrieve(
            query,
            search_queries,
            rerank_pool=recipe.rerank_pool,
            limit=recipe.final_limit,
            mmr_lambda=recipe.mmr_lambda,
        )
        logger.info(
            "routed query | category={} expansion={} searches={} chunks={} latency_ms={:.0f}",
            category,
            recipe.expansion,
            len(search_queries),
            len(chunks),
            (perf_counter() - started) * 1000,
        )
        return RoutedRetrievalResponse(
            query=query,
            intent=QueryIntent.RETRIEVAL,
            category=category,
            chunks=chunks,
        )

    def _build_search_queries(self, query: str, recipe: RetrievalRecipe) -> list[str]:
        if recipe.expansion == "fusion":
            return [query, *self._expand(query, recipe.fusion_variations)]
        if recipe.expansion == "decompose":
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
