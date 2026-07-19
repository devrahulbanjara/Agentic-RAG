from uuid import NAMESPACE_URL, uuid5

from loguru import logger
from qdrant_client import QdrantClient, models
from qdrant_client.models import PointStruct

from src.core.config import QdrantSettings
from src.core.embeddings import BGEM3Embedder
from src.ingestion.schemas import Chunk


class QdrantIndexer:
    def __init__(self, config: QdrantSettings) -> None:
        self._client = QdrantClient(url=config.url, api_key=config.api_key or None)
        self._collection = config.collection
        self._embedding_dim = config.embedding_dim
        self._embedder = BGEM3Embedder(config.embedding_model)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        if self._client.collection_exists(self._collection):
            logger.debug("Collection '{}' exists", self._collection)
            return
        self._client.create_collection(
            collection_name=self._collection,
            vectors_config={
                "content": models.VectorParams(
                    size=self._embedding_dim, distance=models.Distance.COSINE
                ),
                "question": models.VectorParams(
                    size=self._embedding_dim, distance=models.Distance.COSINE
                ),
            },
            sparse_vectors_config={"keywords_sparse": models.SparseVectorParams()},
            hnsw_config=models.HnswConfigDiff(m=32, ef_construct=256),
        )
        self._client.create_payload_index(
            self._collection, "arxiv_id", models.PayloadSchemaType.KEYWORD
        )
        self._client.create_payload_index(
            self._collection, "chunk_type", models.PayloadSchemaType.KEYWORD
        )
        self._client.create_payload_index(
            self._collection, "primary_category", models.PayloadSchemaType.KEYWORD
        )
        self._client.create_payload_index(
            self._collection, "version", models.PayloadSchemaType.KEYWORD
        )
        self._client.create_payload_index(
            self._collection, "is_latest_version", models.PayloadSchemaType.BOOL
        )
        self._client.create_payload_index(
            self._collection, "submitted_year", models.PayloadSchemaType.INTEGER
        )
        self._client.create_payload_index(
            self._collection, "authors", models.PayloadSchemaType.KEYWORD
        )
        logger.info("Created collection '{}'", self._collection)

    def index(self, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0

        content_texts = [self._content_text(c) for c in chunks]
        question_texts = [self._question_text(c) for c in chunks]
        keyword_texts = [self._keywords_text(c) for c in chunks]

        logger.info("  Indexer: encoding {} chunks (content dense)", len(chunks))
        content_vectors = self._embedder.embed(content_texts, return_sparse=False).dense
        logger.info("  Indexer: encoding {} chunks (question dense)", len(chunks))
        question_vectors = self._embedder.embed(
            question_texts, return_sparse=False
        ).dense
        logger.info(
            "  Indexer: encoding {} chunks (BGE-M3 sparse over keywords)", len(chunks)
        )
        keyword_vectors = self._embedder.embed(keyword_texts, return_dense=False).sparse
        logger.debug("  Indexer: building point payloads")

        points = []
        for chunk, content_vector, question_vector, keyword_vector in zip(
            chunks, content_vectors, question_vectors, keyword_vectors
        ):
            point_id = str(
                uuid5(
                    NAMESPACE_URL,
                    f"{chunk.arxiv_id}:{chunk.version}:{chunk.text[:200]}",
                )
            )
            point = PointStruct(
                id=point_id,
                payload={
                    "text": chunk.text,
                    "arxiv_id": chunk.arxiv_id,
                    "chunk_type": chunk.chunk_type,
                    "section_path": chunk.section_path,
                    "title": chunk.title,
                    "authors": chunk.authors,
                    "primary_category": chunk.primary_category,
                    "categories": chunk.categories,
                    "version": chunk.version,
                    "submitted_at": chunk.submitted_at,
                    "submitted_year": chunk.submitted_year,
                    "doi": chunk.doi,
                    "is_latest_version": chunk.is_latest_version,
                    "description": chunk.description,
                    "image_path": chunk.image_path,
                    "hypothetical_questions": chunk.hypothetical_questions,
                    "keywords": chunk.keywords,
                },
                vector={
                    "content": content_vector,
                    "question": question_vector,
                    "keywords_sparse": models.SparseVector(
                        indices=keyword_vector.indices,
                        values=keyword_vector.values,
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

    def _content_text(self, chunk: Chunk) -> str:
        """Text fed to the `content` dense encoder.

        For non-paragraph chunks, appends the LLM description so natural
        language rather than raw markdown/LaTeX drives the dense vector.
        """
        if chunk.description:
            return f"{chunk.text}\n\nDescription: {chunk.description}"
        return chunk.text

    def _question_text(self, chunk: Chunk) -> str:
        """Text fed to the `question` dense encoder.

        The hypothetical questions (step 7) concatenated into one string. This
        is the lane that fires when a user query is near a question we predicted
        at ingest time. Falls back to the content text when none were generated.
        """
        if chunk.hypothetical_questions:
            return " ".join(chunk.hypothetical_questions)
        return self._content_text(chunk)

    def _keywords_text(self, chunk: Chunk) -> str:
        """Text fed to the sparse BM25 encoder.

        Uses the curated keyword list when available — cleaner signal than
        encoding the full chunk text which contains structural noise.
        Falls back to the content text if no keywords were generated.
        """
        if chunk.keywords:
            return " ".join(chunk.keywords)
        return self._content_text(chunk)
