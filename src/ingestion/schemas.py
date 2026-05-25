from typing import Literal

from pydantic import BaseModel


class Reference(BaseModel):
    ref_id: str
    authors: list[str]
    title: str
    venue: str
    year: int | None = None
    doi: str | None = None


class DocumentElement(BaseModel):
    element_type: Literal["paragraph", "equation", "table", "figure"]
    text: str | None = None
    latex: str | None = None
    caption: str | None = None
    rows: list[list[str]] | None = None
    has_image: bool = False


class Section(BaseModel):
    heading: str
    level: int
    content: list[DocumentElement]
    children: list[Section]


class ParsedDocument(BaseModel):
    arxiv_id: str
    title: str
    sections: list[Section]
    references: list[Reference]


class Chunk(BaseModel):
    text: str
    arxiv_id: str
    chunk_type: Literal["paragraph"]
    section_path: list[str]
