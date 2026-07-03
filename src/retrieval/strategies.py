from dataclasses import dataclass
from typing import Literal

from src.llm.schemas import QueryCategory

ExpansionStrategy = Literal["none", "fusion", "decompose"]


@dataclass(frozen=True)
class RetrievalStrategy:
    """How to retrieve for one kind of query: whether to expand the query, how
    many candidates to rerank, how many to keep, and whether to diversify."""

    expansion: ExpansionStrategy
    rerank_pool: int
    final_limit: int
    mmr_lambda: float | None = None
    fusion_variations: int = 0


# Used when routing is off, the classifier is unsure, or the category is unknown.
DEFAULT_STRATEGY = RetrievalStrategy(expansion="none", rerank_pool=40, final_limit=8)

STRATEGY_BY_CATEGORY: dict[QueryCategory, RetrievalStrategy] = {
    QueryCategory.SPECIFIC_FACTUAL: RetrievalStrategy(
        expansion="none", rerank_pool=30, final_limit=8
    ),
    QueryCategory.CONCEPTUAL: RetrievalStrategy(
        expansion="fusion",
        rerank_pool=40,
        final_limit=8,
        mmr_lambda=0.6,
        fusion_variations=4,
    ),
    QueryCategory.EXPLORATORY: RetrievalStrategy(
        expansion="fusion",
        rerank_pool=50,
        final_limit=10,
        mmr_lambda=0.7,
        fusion_variations=4,
    ),
    QueryCategory.COMPARATIVE: RetrievalStrategy(
        expansion="decompose", rerank_pool=30, final_limit=8
    ),
}
