from qdrant_client import models
from src.llm.schemas import MetadataQuery


def build_qdrant_filter(metadata: MetadataQuery) -> models.Filter | None:
    must: list[models.Condition] = []

    if metadata.primary_category:
        must.append(
            models.FieldCondition(
                key="primary_category",
                match=models.MatchValue(value=metadata.primary_category),
            )
        )

    for author_name in metadata.author_names:
        must.append(
            models.FieldCondition(
                key="authors",
                match=models.MatchValue(value=author_name),
            )
        )

    if metadata.year_from is not None or metadata.year_to is not None:
        must.append(
            models.FieldCondition(
                key="submitted_year",
                range=models.Range(
                    gte=metadata.year_from,
                    lte=metadata.year_to,
                ),
            )
        )

    if metadata.latest_only:
        must.append(
            models.FieldCondition(
                key="is_latest_version",
                match=models.MatchValue(value=True),
            )
        )

    if not must:
        return None
    return models.Filter(must=must)
