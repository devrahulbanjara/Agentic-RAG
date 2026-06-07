from qdrant_client import QdrantClient, models

from src.core.embeddings import BGEM3Embedder
from src.retrieval.schemas import RetrievedChunk


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

    def retrieve(self, query: str, limit: int = 5) -> list[RetrievedChunk]:
        encoded = self.embedder.embed([query])
        dense_vector = encoded.dense[0]
        sparse_vector = encoded.sparse[0]

        results = self.qdrant.query_points(
            collection_name=self.collection_name,
            prefetch=[
                models.Prefetch(
                    query=dense_vector,
                    using="content",
                    limit=limit,
                ),
                models.Prefetch(
                    query=models.SparseVector(
                        indices=sparse_vector.indices,
                        values=sparse_vector.values,
                    ),
                    using="keywords_bm25",
                    limit=limit,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
        )

        return [
            RetrievedChunk(
                text=point.payload["text"],
                score=point.score,
                arxiv_id=point.payload["arxiv_id"],
            )
            for point in results.points
        ]
