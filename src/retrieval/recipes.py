from dataclasses import dataclass
from typing import Literal

from src.llm.schemas import QueryCategory

ExpansionStrategy = Literal["none", "fusion", "decompose"]


@dataclass(frozen=True)
class RetrievalRecipe:
    expansion: ExpansionStrategy
    rerank_pool: int
    final_limit: int
    mmr_lambda: float | None = None
    fusion_variations: int = 0


GENERAL_RECIPE = RetrievalRecipe(expansion="none", rerank_pool=40, final_limit=8)

RECIPES: dict[QueryCategory, RetrievalRecipe] = {
    QueryCategory.SPECIFIC_FACTUAL: RetrievalRecipe(
        expansion="none", rerank_pool=30, final_limit=8
    ),
    QueryCategory.CONCEPTUAL: RetrievalRecipe(
        expansion="fusion",
        rerank_pool=40,
        final_limit=8,
        mmr_lambda=0.6,
        fusion_variations=4,
    ),
    QueryCategory.EXPLORATORY: RetrievalRecipe(
        expansion="fusion",
        rerank_pool=50,
        final_limit=10,
        mmr_lambda=0.7,
        fusion_variations=4,
    ),
    QueryCategory.COMPARATIVE: RetrievalRecipe(
        expansion="decompose", rerank_pool=30, final_limit=8
    ),
}
