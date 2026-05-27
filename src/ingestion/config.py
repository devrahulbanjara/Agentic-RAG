from pydantic_settings import BaseSettings


class IngestionSettings(BaseSettings):
    # GROBID
    grobid_url: str = "http://localhost:8070"
    grobid_enabled: bool = True
    grobid_timeout: int = 120

    # Docling
    do_ocr: bool = False
    do_formula_enrichment: bool = True
    generate_picture_images: bool = True
    images_scale: float = 2.0
    num_threads: int = 4

    # Chunking
    min_chunk_chars: int = 20
    merge_max_chars: int = 800
    skip_sections: list[str] = [
        "Table of Contents",
        "List of Figures",
        "List of Tables",
    ]

    # Output
    figure_output_dir: str = "data/figures"

    # Qdrant + Embedding
    qdrant_url: str = "http://localhost:6333"
    collection_name: str = "arxiv_papers"
    dense_model: str = "BAAI/bge-small-en"
    sparse_model: str = "qdrant/bm25"
    embedding_dim: int = 384
