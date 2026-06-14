import numpy as np


def mmr_select_diverse(
    relevance: list[float], vectors: list[list[float]], k: int, lam: float
) -> list[int]:
    """Pick k items that are relevant to the query yet dissimilar to the ones already picked, returned as indices."""
    normalized = np.asarray(vectors)
    normalized = normalized / np.linalg.norm(normalized, axis=1, keepdims=True)
    similarity = normalized @ normalized.T

    selected: list[int] = []
    candidates = list(range(len(relevance)))
    while candidates and len(selected) < k:
        if not selected:
            best = max(candidates, key=lambda i: relevance[i])
        else:
            best = max(
                candidates,
                key=lambda i: (
                    lam * relevance[i]
                    - (1 - lam) * max(similarity[i][j] for j in selected)
                ),
            )
        selected.append(best)
        candidates.remove(best)
    return selected
