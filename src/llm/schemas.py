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
