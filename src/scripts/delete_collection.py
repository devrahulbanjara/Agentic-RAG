"""Delete a Qdrant collection.

Usage:
    uv run python -m src.scripts.delete_collection
    uv run python -m src.scripts.delete_collection my_collection
"""

import argparse

from qdrant_client import QdrantClient

QDRANT_URL = "http://localhost:6333"
DEFAULT_COLLECTION = "arxiv_papers"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Delete a Qdrant collection")
    parser.add_argument(
        "collection",
        nargs="?",
        default=DEFAULT_COLLECTION,
        help=f"Collection name (default: {DEFAULT_COLLECTION})",
    )
    args = parser.parse_args(argv)

    client = QdrantClient(url=QDRANT_URL)

    if not client.collection_exists(args.collection):
        print(f"Collection '{args.collection}' does not exist")
        return

    client.delete_collection(args.collection)
    print(f"Deleted collection '{args.collection}'")


if __name__ == "__main__":
    main()
