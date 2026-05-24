from fastembed import SparseTextEmbedding, TextEmbedding
from qdrant_client import QdrantClient, models

from src.retrieval.schemas import RetrievedChunk


class RetrievalService:
    def __init__(
        self,
        qdrant: QdrantClient,
        dense_encoder: TextEmbedding,
        sparse_encoder: SparseTextEmbedding,
        collection_name: str,
    ) -> None:
        self.qdrant = qdrant
        self.dense_encoder = dense_encoder
        self.sparse_encoder = sparse_encoder
        self.collection_name = collection_name

    def retrieve(self, query: str, limit: int = 5) -> list[RetrievedChunk]:
        dense_vec = list(self.dense_encoder.embed([query]))[0].tolist()
        sparse_vec = next(self.sparse_encoder.embed([query]))

        results = self.qdrant.query_points(
            collection_name=self.collection_name,
            prefetch=[
                models.Prefetch(
                    query=dense_vec,
                    using="dense_vector",
                    limit=limit,
                ),
                models.Prefetch(
                    query=models.SparseVector(
                        indices=sparse_vec.indices.tolist(),
                        values=sparse_vec.values.tolist(),
                    ),
                    using="bm25_sparse_vector",
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
                chunk_idx=point.payload["chunk_idx"],
            )
            for point in results.points
        ]
