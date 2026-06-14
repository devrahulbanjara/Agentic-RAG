from qdrant_client import QdrantClient, models

from src.core.embeddings import BGEM3Embedder
from src.core.reranker import BGEReranker
from src.retrieval.mmr import mmr_select_diverse
from src.retrieval.schemas import RetrievedChunk

# How many results each of the three searches returns.
RESULTS_PER_SEARCH = 50

# RRF constant that keeps a single rank-1 hit from dominating the merge.
RRF_K = 60

# How many merged results we hand to the reranker.
RESULTS_TO_RERANK = 30

# How many chunks we return when the caller doesn't ask for a specific number.
DEFAULT_LIMIT = 8

# Drop the chunks finally that have the reranker score below this.
MIN_RELEVANCE_SCORE = 0.5


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

    def retrieve(
        self, query: str, limit: int = DEFAULT_LIMIT, mmr_lambda: float | None = None
    ) -> list[RetrievedChunk]:
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
        return self._rerank(query, merged, limit, mmr_lambda)

    def _merge_results(
        self, search_results: list[list[models.ScoredPoint]]
    ) -> list[dict]:
        """Merge the three searches with RRF, return the top chunk payloads."""
        scores: dict[str, float] = {}
        payloads: dict[str, dict] = {}
        for results in search_results:
            for rank, point in enumerate(results, start=1):
                scores[point.id] = scores.get(point.id, 0.0) + 1.0 / (RRF_K + rank)
                payloads.setdefault(point.id, point.payload)

        ranked_ids = sorted(scores, key=scores.get, reverse=True)
        return [payloads[point_id] for point_id in ranked_ids[:RESULTS_TO_RERANK]]

    def _rerank(
        self, query: str, chunks: list[dict], limit: int, mmr_lambda: float | None
    ) -> list[RetrievedChunk]:
        """Rescore the merged chunks with the cross-encoder, keep the top ``limit``."""
        texts = [self._chunk_text(chunk) for chunk in chunks]
        scores = self.reranker.rerank(query, texts)

        if mmr_lambda is None:
            order = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
        else:
            vectors = self.embedder.embed(texts, return_sparse=False).dense
            order = mmr_select_diverse(scores, vectors, limit, mmr_lambda)

        order = [i for i in order if scores[i] >= MIN_RELEVANCE_SCORE]

        return [
            RetrievedChunk(
                text=chunks[i]["text"],
                reranker_score=scores[i],
                arxiv_id=chunks[i]["arxiv_id"],
            )
            for i in order[:limit]
        ]

    def _chunk_text(self, chunk: dict) -> str:
        """Text the cross-encoder reads: chunk text plus its LLM description."""
        description = chunk.get("description")
        if description:
            return f"{chunk['text']}\n\nDescription: {description}"
        return chunk["text"]
