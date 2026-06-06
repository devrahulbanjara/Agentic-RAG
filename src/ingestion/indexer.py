from uuid import NAMESPACE_URL, uuid5

from fastembed import SparseTextEmbedding
from loguru import logger
from qdrant_client import QdrantClient, models
from qdrant_client.models import PointStruct
from sentence_transformers import SentenceTransformer

from src.core.config import QdrantSettings
from src.ingestion.schemas import Chunk


class QdrantIndexer:
    def __init__(self, cfg: QdrantSettings) -> None:
        self._client = QdrantClient(url=cfg.url)
        self._collection = cfg.collection
        self._embedding_dim = cfg.embedding_dim
        self._dense_encoder = SentenceTransformer(cfg.dense_model)
        self._sparse_encoder = SparseTextEmbedding(model_name=cfg.sparse_model)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        if self._client.collection_exists(self._collection):
            logger.debug("Collection '{}' exists", self._collection)
            return
        self._client.create_collection(
            collection_name=self._collection,
            vectors_config={
                "dense_vector": models.VectorParams(
                    size=self._embedding_dim, distance=models.Distance.COSINE
                )
            },
            sparse_vectors_config={
                "bm25_sparse_vector": models.SparseVectorParams(
                    modifier=models.Modifier.IDF
                )
            },
        )
        logger.info("Created collection '{}'", self._collection)

    def index(self, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0

        dense_texts = [self._embed_text(c) for c in chunks]
        sparse_texts = [self._bm25_text(c) for c in chunks]

        logger.info("  Indexer: encoding {} chunks (dense)", len(chunks))
        dense_embeddings = self._dense_encoder.encode(
            dense_texts, show_progress_bar=True
        )
        logger.info(
            "  Indexer: encoding {} chunks (sparse BM25 over keywords)", len(chunks)
        )
        sparse_embeddings = list(self._sparse_encoder.embed(sparse_texts))
        logger.debug("  Indexer: building point payloads")

        points = []
        for chunk, dense_vec, sparse_vec in zip(
            chunks, dense_embeddings, sparse_embeddings
        ):
            point_id = str(uuid5(NAMESPACE_URL, f"{chunk.arxiv_id}:{chunk.text[:200]}"))
            point = PointStruct(
                id=point_id,
                payload={
                    "text": chunk.text,
                    "arxiv_id": chunk.arxiv_id,
                    "chunk_type": chunk.chunk_type,
                    "section_path": chunk.section_path,
                    "description": chunk.description,
                    "image_path": chunk.image_path,
                    "hypothetical_questions": chunk.hypothetical_questions,
                    "keywords": chunk.keywords,
                },
                vector={
                    "dense_vector": dense_vec.tolist(),
                    "bm25_sparse_vector": models.SparseVector(
                        indices=sparse_vec.indices.tolist(),
                        values=sparse_vec.values.tolist(),
                    ),
                },
            )
            points.append(point)

        logger.info("  Indexer: uploading {} points to Qdrant", len(points))
        self._client.upload_points(
            collection_name=self._collection, points=points, batch_size=64
        )
        logger.info("  Indexer: upload complete ({} points)", len(points))
        return len(points)

    def _embed_text(self, chunk: Chunk) -> str:
        """Text fed to the dense encoder.

        For non-paragraph chunks, appends the LLM description so natural
        language rather than raw markdown/LaTeX drives the dense vector.
        """
        if chunk.description:
            return f"{chunk.text}\n\nDescription: {chunk.description}"
        return chunk.text

    def _bm25_text(self, chunk: Chunk) -> str:
        """Text fed to the sparse BM25 encoder.

        Uses the curated keyword list when available — cleaner signal than
        encoding the full chunk text which contains structural noise.
        Falls back to the dense text if no keywords were generated.
        """
        if chunk.keywords:
            return " ".join(chunk.keywords)
        return self._embed_text(chunk)
