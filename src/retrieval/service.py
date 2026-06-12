from qdrant_client import QdrantClient, models

from src.core.embeddings import BGEM3Embedder
from src.retrieval.schemas import RetrievedChunk

PER_SEARCH_LIMIT = 50
RRF_K = 60
FUSED_LIMIT = 30


class RetrievalService:
    def __init__(
        self,
        qdrant: QdrantClient,
        embedder: BGEM3Embedder,
        collection_name: str,
    ) -> None:
        self.qdrant = qdrant
        self.embedder = embedder
        self.collection_name = collection_name

    def retrieve(self, query: str, limit: int = FUSED_LIMIT) -> list[RetrievedChunk]:
        encoded = self.embedder.embed([query])
        dense_vector = encoded.dense[0]
        sparse_vector = encoded.sparse[0]

        responses = self.qdrant.query_batch_points(
            collection_name=self.collection_name,
            requests=[
                models.QueryRequest(
                    query=models.SparseVector(
                        indices=sparse_vector.indices,
                        values=sparse_vector.values,
                    ),
                    using="keywords_sparse",
                    limit=PER_SEARCH_LIMIT,
                    with_payload=True,
                ),
                models.QueryRequest(
                    query=dense_vector,
                    using="content",
                    limit=PER_SEARCH_LIMIT,
                    with_payload=True,
                ),
                models.QueryRequest(
                    query=dense_vector,
                    using="question",
                    limit=PER_SEARCH_LIMIT,
                    with_payload=True,
                ),
            ],
        )

        return self._reciprocal_rank_fusion([r.points for r in responses], limit)

    def _reciprocal_rank_fusion(
        self, result_lists: list[list[models.ScoredPoint]], limit: int
    ) -> list[RetrievedChunk]:
        """Merge the search result lists with RRF, return the top ``limit`` chunks."""
        scores: dict[str, float] = {}
        payloads: dict[str, dict] = {}
        for points in result_lists:
            for rank, point in enumerate(points, start=1):
                scores[point.id] = scores.get(point.id, 0.0) + 1.0 / (RRF_K + rank)
                payloads.setdefault(point.id, point.payload)

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return [
            RetrievedChunk(
                text=payloads[point_id]["text"],
                score=score,
                arxiv_id=payloads[point_id]["arxiv_id"],
            )
            for point_id, score in ranked[:limit]
        ]
