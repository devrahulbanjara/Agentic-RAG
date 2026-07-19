from pathlib import Path
from xml.etree import ElementTree as ET

import httpx
from loguru import logger
from src.ingestion.schemas import Reference

TEI_NS = "{http://www.tei-c.org/ns/1.0}"
XML_NS = "{http://www.w3.org/XML/1998/namespace}"


def parse_tei_references(xml_text: str) -> list[Reference]:
    """Parse GROBID TEI XML and extract structured references.

    Pure function — no HTTP, no side effects. Testable with fixture XML.
    """
    root = ET.fromstring(xml_text)
    references: list[Reference] = []

    for entry in root.findall(f".//{TEI_NS}listBibl/{TEI_NS}biblStruct"):
        references.append(_parse_reference(entry))

    return references


def _parse_reference(entry: ET.Element) -> Reference:
    """Parse one <biblStruct> element into a Reference."""
    # Authors
    authors: list[str] = []
    for person in entry.findall(f".//{TEI_NS}author/{TEI_NS}persName"):
        first = person.findtext(f"{TEI_NS}forename", default="")
        last = person.findtext(f"{TEI_NS}surname", default="")
        name = f"{first} {last}".strip()
        if name:
            authors.append(name)

    # Title:
    title = ""
    for parent_tag in [f"{TEI_NS}analytic", f"{TEI_NS}monogr"]:
        title_el = entry.find(f"{parent_tag}/{TEI_NS}title")
        if title_el is not None and title_el.text:
            title = title_el.text.strip()
            break
    if not title:
        note = entry.find(f"{TEI_NS}note[@type='report_type']")
        if note is not None and note.text:
            title = (
                note.text.strip()
                .removesuffix(". arXiv preprint")
                .removesuffix("arXiv preprint")
            )

    # Venue
    venue = ""
    monogr_title = entry.find(f"{TEI_NS}monogr/{TEI_NS}title")
    if (
        monogr_title is not None
        and monogr_title.text
        and monogr_title.text.strip() != title
    ):
        venue = monogr_title.text.strip()

    # Year
    year: int | None = None
    date_el = entry.find(f".//{TEI_NS}date[@when]")
    if date_el is not None:
        try:
            year = int(date_el.get("when", "")[:4])
        except ValueError, TypeError:
            pass

    # DOI
    doi: str | None = None
    doi_el = entry.find(f"{TEI_NS}idno[@type='DOI']")
    if doi_el is not None and doi_el.text:
        doi = doi_el.text.strip()

    ref_id = entry.get(f"{XML_NS}id", "")

    return Reference(
        ref_id=ref_id,
        authors=authors,
        title=title,
        venue=venue,
        year=year,
        doi=doi,
    )


def extract_references(base_url: str, timeout: int, pdf_path: Path) -> list[Reference]:
    """Send PDF to GROBID, parse TEI XML, return references."""
    url = f"{base_url.rstrip('/')}/api/processFulltextDocument"
    try:
        with open(pdf_path, "rb") as pdf_file:
            response = httpx.post(
                url,
                files={"input": (pdf_path.name, pdf_file, "application/pdf")},
                data={"generateIDs": "1", "consolidateHeader": "1"},
                timeout=timeout,
            )

        if response.status_code != 200:
            logger.warning(
                "GROBID returned {} for {}", response.status_code, pdf_path.name
            )
            return []

        return parse_tei_references(response.text)
    except httpx.HTTPError:
        logger.exception("GROBID request failed for {}", pdf_path.name)
        return []
