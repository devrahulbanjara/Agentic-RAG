from qdrant_client import QdrantClient, models

from src.core.embeddings import BGEM3Embedder
from src.core.reranker import BGEReranker
from src.retrieval.schemas import RetrievedChunk

RESULTS_PER_SEARCH = 50
RRF_K = 60
# How many merged results we rerank. Wider than the final answer so a chunk
# only one search ranked well still gets read by the cross-encoder.
RESULTS_TO_RERANK = 30
DEFAULT_LIMIT = 8


class RetrievalService:
    def __init__(
        self,
        qdrant: QdrantClient,
        embedder: BGEM3Embedder,
        reranker: BGEReranker,
        collection_name: str,
    ) -> None:
        self.qdrant = qdrant
        self.embedder = embedder
        self.reranker = reranker
        self.collection_name = collection_name

    def retrieve(self, query: str, limit: int = DEFAULT_LIMIT) -> list[RetrievedChunk]:
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
                    limit=RESULTS_PER_SEARCH,
                    with_payload=True,
                ),
                models.QueryRequest(
                    query=dense_vector,
                    using="content",
                    limit=RESULTS_PER_SEARCH,
                    with_payload=True,
                ),
                models.QueryRequest(
                    query=dense_vector,
                    using="question",
                    limit=RESULTS_PER_SEARCH,
                    with_payload=True,
                ),
            ],
        )

        merged = self._merge_results([r.points for r in responses])
        return self._rerank(query, merged, limit)

    def _merge_results(
        self, search_results: list[list[models.ScoredPoint]]
    ) -> list[dict]:
        """Merge the three searches with RRF, return the top chunk payloads.

        A chunk found by several searches accumulates score; ``RRF_K`` keeps a
        single rank-1 hit from dominating chunks that placed well everywhere.
        """
        scores: dict[str, float] = {}
        payloads: dict[str, dict] = {}
        for results in search_results:
            for rank, point in enumerate(results, start=1):
                scores[point.id] = scores.get(point.id, 0.0) + 1.0 / (RRF_K + rank)
                payloads.setdefault(point.id, point.payload)

        ranked_ids = sorted(scores, key=scores.get, reverse=True)
        return [payloads[point_id] for point_id in ranked_ids[:RESULTS_TO_RERANK]]

    def _rerank(
        self, query: str, chunks: list[dict], limit: int
    ) -> list[RetrievedChunk]:
        """Rescore the merged chunks with the cross-encoder, keep the top ``limit``."""
        scores = self.reranker.rerank(
            query, [self._chunk_text(chunk) for chunk in chunks]
        )
        ranked = sorted(zip(scores, chunks), key=lambda pair: pair[0], reverse=True)
        return [
            RetrievedChunk(
                text=chunk["text"],
                reranker_score=score,
                arxiv_id=chunk["arxiv_id"],
            )
            for score, chunk in ranked[:limit]
        ]

    def _chunk_text(self, chunk: dict) -> str:
        """Text the cross-encoder reads — mirrors the indexer's content lane.

        Non-paragraph chunks store raw markdown/LaTeX in ``text`` and the LLM
        description separately; the reranker, like the content embedder, scores
        better on the natural-language description appended. Kept in sync with
        ``QdrantIndexer._content_text``.
        """
        description = chunk.get("description")
        if description:
            return f"{chunk['text']}\n\nDescription: {description}"
        return chunk["text"]
