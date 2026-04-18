"""Parsers for extracting text content from PDF, XML, and HTML papers."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Optional

from dataset_extractor.models import PaperContent, PaperSection


# ---------------------------------------------------------------------------
# PDF parser (PyMuPDF / fitz)
# ---------------------------------------------------------------------------

def parse_pdf(path: Path) -> PaperContent:
    """Extract sections from a PDF file using PyMuPDF."""
    import fitz  # PyMuPDF

    doc = fitz.open(str(path))
    sections: list[PaperSection] = []
    current_title = "Untitled Section"
    current_text_parts: list[str] = []
    idx = 0
    paper_title: Optional[str] = None

    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                text = "".join(span["text"] for span in line["spans"]).strip()
                if not text:
                    continue

                # Heuristic: larger / bold fonts → section heading
                max_size = max(span["size"] for span in line["spans"])
                is_bold = any("bold" in span["font"].lower() for span in line["spans"])

                if max_size >= 12 and is_bold and len(text.split()) < 15:
                    # Save previous section
                    if current_text_parts:
                        sections.append(
                            PaperSection(
                                title=current_title,
                                content="\n".join(current_text_parts),
                                index=idx,
                            )
                        )
                        idx += 1
                        current_text_parts = []

                    if paper_title is None:
                        paper_title = text
                    current_title = text
                else:
                    current_text_parts.append(text)

    # Final section
    if current_text_parts:
        sections.append(
            PaperSection(
                title=current_title,
                content="\n".join(current_text_parts),
                index=idx,
            )
        )

    doc.close()

    return PaperContent(
        paper_id=_make_paper_id(path),
        title=paper_title,
        source_path=str(path),
        format="pdf",
        sections=sections,
        raw_text="\n\n".join(s.content for s in sections) if sections else None,
    )


# ---------------------------------------------------------------------------
# XML parser (e.g., JATS / TEI formats common in academic publishing)
# ---------------------------------------------------------------------------

def parse_xml(path: Path) -> PaperContent:
    """Extract sections from an XML file (JATS / TEI / generic)."""
    from lxml import etree

    tree = etree.parse(str(path))  # noqa: S320
    root = tree.getroot()

    # Strip namespaces for easier XPath
    for elem in root.iter():
        if elem.tag and isinstance(elem.tag, str) and "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]

    paper_title = _xpath_text(root, ".//article-title") or _xpath_text(root, ".//title")

    sections: list[PaperSection] = []
    # Try JATS <sec> elements first
    sec_elems = root.findall(".//sec")
    if not sec_elems:
        # Fallback: try TEI <div> elements
        sec_elems = root.findall(".//div")

    for idx, sec in enumerate(sec_elems):
        title_el = sec.find("title")
        if title_el is None:
            title_el = sec.find("head")
        title = (title_el.text or "").strip() if title_el is not None else f"Section {idx + 1}"
        content = " ".join(sec.itertext()).strip()
        if content:
            sections.append(PaperSection(title=title, content=content, index=idx))

    # Fallback: entire body as one section
    if not sections:
        body = root.find(".//body")
        raw = " ".join(body.itertext()).strip() if body is not None else ""
        if raw:
            sections.append(PaperSection(title="Full Text", content=raw, index=0))

    return PaperContent(
        paper_id=_make_paper_id(path),
        title=paper_title,
        source_path=str(path),
        format="xml",
        sections=sections,
        raw_text="\n\n".join(s.content for s in sections) if sections else None,
    )


# ---------------------------------------------------------------------------
# HTML parser
# ---------------------------------------------------------------------------

def parse_html(path: Path) -> PaperContent:
    """Extract sections from an HTML file."""
    from bs4 import BeautifulSoup

    html_text = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html_text, "html.parser")

    paper_title = soup.title.string.strip() if soup.title and soup.title.string else None

    sections: list[PaperSection] = []
    idx = 0

    # Strategy: split on heading tags
    headings = soup.find_all(re.compile(r"^h[1-6]$"))
    if headings:
        for i, heading in enumerate(headings):
            title = heading.get_text(strip=True)
            # Gather content until next heading
            content_parts: list[str] = []
            for sibling in heading.find_next_siblings():
                if sibling.name and re.match(r"^h[1-6]$", sibling.name):
                    break
                text = sibling.get_text(strip=True)
                if text:
                    content_parts.append(text)
            if content_parts:
                sections.append(
                    PaperSection(title=title, content="\n".join(content_parts), index=idx)
                )
                idx += 1

    # Fallback: full body
    if not sections:
        body = soup.find("body")
        raw = body.get_text(separator="\n", strip=True) if body else soup.get_text(separator="\n", strip=True)
        if raw:
            sections.append(PaperSection(title="Full Text", content=raw, index=0))

    return PaperContent(
        paper_id=_make_paper_id(path),
        title=paper_title,
        source_path=str(path),
        format="html",
        sections=sections,
        raw_text="\n\n".join(s.content for s in sections) if sections else None,
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

PARSERS = {
    ".pdf": parse_pdf,
    ".xml": parse_xml,
    ".html": parse_html,
    ".htm": parse_html,
}


def parse_paper(path: str | Path) -> PaperContent:
    """Auto-detect format and parse a paper file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Paper not found: {p}")
    suffix = p.suffix.lower()
    parser = PARSERS.get(suffix)
    if parser is None:
        raise ValueError(f"Unsupported paper format: {suffix}. Supported: {list(PARSERS)}")
    return parser(p)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_paper_id(path: Path) -> str:
    return hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:12]


def _xpath_text(root, xpath: str) -> Optional[str]:
    el = root.find(xpath)
    if el is not None and el.text:
        return el.text.strip()
    return None
