from dataclasses import dataclass

from FlagEmbedding import BGEM3FlagModel


@dataclass(frozen=True)
class SparseEmbedding:
    """A Qdrant-agnostic sparse vector: parallel token-id / weight lists."""

    indices: list[int]
    values: list[float]


@dataclass(frozen=True)
class BGEM3Output:
    """Encoder output. A lane is `None` when it wasn't requested."""

    dense: list[list[float]] | None
    sparse: list[SparseEmbedding] | None


def _to_sparse_embedding(lexical_weights: dict) -> SparseEmbedding:
    """Convert BGE-M3 lexical weights ({token_id: weight}) to a sparse vector.

    FlagEmbedding emits string token ids and may include zero-weight entries;
    Qdrant rejects zero values in a sparse vector, so they're dropped here.
    """
    indices: list[int] = []
    values: list[float] = []
    for token_id, weight in lexical_weights.items():
        weight = float(weight)
        if weight == 0.0:
            continue
        indices.append(int(token_id))
        values.append(weight)
    return SparseEmbedding(indices=indices, values=values)


class BGEM3Embedder:
    """BGE-M3 dense + learned-sparse encoder behind one model instance.

    A single forward pass yields both the 1024-d dense vector and the sparse
    lexical-weight vector, so neither ingestion nor retrieval has to load a
    second model (or a separate BM25 encoder) to populate the sparse lane.
    """

    def __init__(self, model_name: str, *, use_fp16: bool = True) -> None:
        self._model = BGEM3FlagModel(model_name, use_fp16=use_fp16)

    def embed(
        self,
        texts: list[str],
        *,
        return_dense: bool = True,
        return_sparse: bool = True,
        batch_size: int = 12,
    ) -> BGEM3Output:
        if not texts:
            return BGEM3Output(
                dense=[] if return_dense else None,
                sparse=[] if return_sparse else None,
            )

        encoded = self._model.encode(
            texts,
            batch_size=batch_size,
            return_dense=return_dense,
            return_sparse=return_sparse,
            return_colbert_vecs=False,
        )

        dense = (
            [vector.tolist() for vector in encoded["dense_vecs"]]
            if return_dense
            else None
        )
        sparse = (
            [_to_sparse_embedding(weights) for weights in encoded["lexical_weights"]]
            if return_sparse
            else None
        )
        return BGEM3Output(dense=dense, sparse=sparse)
