from dataclasses import dataclass
from datetime import UTC, datetime
import re
from xml.etree import ElementTree

import requests

from src.ingestion.schemas import PaperMetadata

ARXIV_API_URL = "http://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
ARXIV_NS = {"arxiv": "http://arxiv.org/schemas/atom"}
ARXIV_ID_RE = re.compile(r"^\d{4}\.\d{4,5}(?:v\d+)?$")


@dataclass(frozen=True)
class ArxivId:
    arxiv_id: str
    version: str | None


def looks_like_arxiv_id(raw: str) -> bool:
    stem = raw.strip().removesuffix(".pdf")
    return bool(ARXIV_ID_RE.fullmatch(stem))


def parse_arxiv_id(raw: str) -> ArxivId:
    raw = raw.strip()
    if not raw:
        raise ValueError("Empty arXiv identifier")

    stem = raw.removesuffix(".pdf")
    if "v" in stem:
        base, suffix = stem.rsplit("v", 1)
        if suffix.isdigit() and base:
            return ArxivId(arxiv_id=base, version=f"v{suffix}")
    return ArxivId(arxiv_id=stem, version=None)


def fetch_paper_metadata(
    raw_arxiv_id: str,
    *,
    timeout: int = 30,
) -> PaperMetadata:
    if not looks_like_arxiv_id(raw_arxiv_id):
        raise ValueError(f"Not an arXiv-style filename: {raw_arxiv_id}")

    parsed = parse_arxiv_id(raw_arxiv_id)
    response = requests.get(
        ARXIV_API_URL,
        params={"id_list": parsed.arxiv_id},
        timeout=timeout,
    )
    response.raise_for_status()
    return parse_paper_metadata_xml(response.text, raw_arxiv_id)


def parse_paper_metadata_xml(xml_text: str, raw_arxiv_id: str) -> PaperMetadata:
    parsed = parse_arxiv_id(raw_arxiv_id)
    root = ElementTree.fromstring(xml_text)
    entry = root.find("atom:entry", ATOM_NS)
    if entry is None:
        raise ValueError(f"No arXiv metadata found for {parsed.arxiv_id}")

    entry_id = _require_text(entry, "atom:id", ATOM_NS)
    latest = parse_arxiv_id(entry_id.rsplit("/", 1)[-1])
    version = parsed.version or latest.version or "v1"

    title = " ".join(_require_text(entry, "atom:title", ATOM_NS).split())
    authors = [
        " ".join(name.text.split())
        for name in entry.findall("atom:author/atom:name", ATOM_NS)
        if name.text
    ]
    categories = [
        category.attrib["term"]
        for category in entry.findall("atom:category", ATOM_NS)
        if category.attrib.get("term")
    ]
    published = _parse_datetime(_require_text(entry, "atom:published", ATOM_NS))
    doi = _optional_text(entry, "arxiv:doi", ARXIV_NS)

    return PaperMetadata(
        arxiv_id=parsed.arxiv_id,
        version=version,
        title=title,
        authors=authors,
        primary_category=categories[0] if categories else None,
        categories=categories,
        submitted_at=published.isoformat(),
        submitted_year=published.year,
        doi=doi,
        is_latest_version=version == latest.version,
    )


def build_fallback_metadata(raw_arxiv_id: str, title: str) -> PaperMetadata:
    parsed = parse_arxiv_id(raw_arxiv_id)
    return PaperMetadata(
        arxiv_id=parsed.arxiv_id,
        version=parsed.version or "v1",
        title=title,
        authors=[],
        is_latest_version=parsed.version is None,
    )


def _require_text(
    entry: ElementTree.Element,
    path: str,
    namespace: dict[str, str],
) -> str:
    node = entry.find(path, namespace)
    if node is None or not node.text:
        raise ValueError(f"Missing required arXiv field: {path}")
    return node.text


def _optional_text(
    entry: ElementTree.Element,
    path: str,
    namespace: dict[str, str],
) -> str | None:
    node = entry.find(path, namespace)
    if node is None or not node.text:
        return None
    return " ".join(node.text.split())


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
