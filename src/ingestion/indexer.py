from uuid import NAMESPACE_URL, uuid5

from fastembed import SparseTextEmbedding
from loguru import logger
from qdrant_client import QdrantClient, models
from qdrant_client.models import PointStruct
from sentence_transformers import SentenceTransformer

from src.ingestion.config import IngestionSettings
from src.ingestion.schemas import Chunk


class QdrantIndexer:
    def __init__(self, settings: IngestionSettings) -> None:
        self._client = QdrantClient(url=settings.qdrant_url)
        self._collection = settings.collection_name
        self._embedding_dim = settings.embedding_dim
        self._dense_encoder = SentenceTransformer(settings.dense_model)
        self._sparse_encoder = SparseTextEmbedding(model_name=settings.sparse_model)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        if self._client.collection_exists(self._collection):
            logger.info("Collection '{}' exists", self._collection)
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

        texts = [c.text for c in chunks]

        logger.info("Encoding {} chunks (dense + sparse)", len(texts))
        dense_embeddings = self._dense_encoder.encode(texts, show_progress_bar=True)
        sparse_embeddings = list(self._sparse_encoder.embed(texts))

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

        self._client.upload_points(
            collection_name=self._collection, points=points, batch_size=64
        )
        logger.info("Indexed {} chunks to '{}'", len(points), self._collection)
        return len(points)
