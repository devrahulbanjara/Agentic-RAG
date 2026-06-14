import numpy as np
from sentence_transformers import CrossEncoder


class BGEReranker:
    def __init__(self, model_name: str) -> None:
        self._model = CrossEncoder(model_name)

    def rerank(self, query: str, passages: list[str]) -> list[float]:
        """Score each passage against the query; higher means more relevant."""
        if not passages:
            return []

        raw_scores = self._model.predict([[query, passage] for passage in passages])
        return self._sigmoid(raw_scores).tolist()

    def _sigmoid(self, scores: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-scores))
