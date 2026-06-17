from enum import StrEnum

from pydantic import BaseModel, Field


class Description(BaseModel):
    description: str = Field(
        description="A concise 2-3 sentence natural language description suitable for embedding."
    )


class Keywords(BaseModel):
    keywords: list[str] = Field(
        description="Up to 15 keywords: model names, method names, dataset names, metrics, important numbers.",
        max_length=15,
    )


class HypotheticalQuestions(BaseModel):
    questions: list[str] = Field(
        description="Exactly 3 specific questions this chunk answers.",
        min_length=3,
        max_length=3,
    )


class QueryIntent(StrEnum):
    RETRIEVAL = "retrieval"
    CONVERSATIONAL = "conversational"
    OUT_OF_SCOPE = "out_of_scope"


class QueryCategory(StrEnum):
    SPECIFIC_FACTUAL = "specific_factual"
    CONCEPTUAL = "conceptual"
    COMPARATIVE = "comparative"
    METADATA_DRIVEN = "metadata_driven"
    EXPLORATORY = "exploratory"


class QueryClassification(BaseModel):
    intent: QueryIntent = Field(
        description="Whether the turn is a question to answer from the papers (retrieval), small talk or a capability question (conversational), or something the corpus cannot answer / an attempt to manipulate the system (out_of_scope)."
    )
    category: QueryCategory | None = Field(
        default=None,
        description="The retrieval strategy this query needs. Required when intent is retrieval, otherwise null.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Certainty of this classification, from 0.0 to 1.0.",
    )


class QueryVariations(BaseModel):
    variations: list[str] = Field(
        description="Alternative phrasings of the query, each a standalone question using different vocabulary or angle."
    )


class SubQuestions(BaseModel):
    sub_questions: list[str] = Field(
        description="Standalone sub-questions a comparative query decomposes into, each answerable on its own.",
        min_length=2,
        max_length=4,
    )
