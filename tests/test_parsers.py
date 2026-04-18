"""Tests for paper parsers."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers to create sample files
# ---------------------------------------------------------------------------

def make_pdf(tmp_path: Path) -> Path:
    """Create a minimal PDF with known text using PyMuPDF."""
    try:
        import fitz
    except ImportError:
        pytest.skip("PyMuPDF not installed")

    pdf_path = tmp_path / "test_paper.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Abstract", fontsize=14)
    page.insert_text((72, 100), "We use the MNIST dataset for evaluation.", fontsize=11)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def make_xml(tmp_path: Path) -> Path:
    xml_path = tmp_path / "test_paper.xml"
    xml_path.write_text(
        textwrap.dedent("""\
            <?xml version="1.0" encoding="UTF-8"?>
            <article>
              <front>
                <article-meta>
                  <title-group>
                    <article-title>Test Paper</article-title>
                  </title-group>
                </article-meta>
              </front>
              <body>
                <sec>
                  <title>Introduction</title>
                  <p>We use the UCI Adult dataset from https://archive.ics.uci.edu/dataset/2/adult</p>
                </sec>
                <sec>
                  <title>Experiments</title>
                  <p>The ImageNet dataset is used for pretraining.</p>
                </sec>
              </body>
            </article>
        """),
        encoding="utf-8",
    )
    return xml_path


def make_html(tmp_path: Path) -> Path:
    html_path = tmp_path / "test_paper.html"
    html_path.write_text(
        textwrap.dedent("""\
            <!DOCTYPE html>
            <html>
            <head><title>Test Paper on Datasets</title></head>
            <body>
              <h1>Introduction</h1>
              <p>We use the CIFAR-10 dataset.</p>
              <h2>Methods</h2>
              <p>The Penn Treebank corpus is available at https://catalog.ldc.upenn.edu/LDC99T42.</p>
            </body>
            </html>
        """),
        encoding="utf-8",
    )
    return html_path


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------

def test_parse_xml_sections(tmp_path):
    from dataset_extractor.parsers.paper_parser import parse_xml

    paper = parse_xml(make_xml(tmp_path))
    assert paper.format == "xml"
    assert len(paper.sections) >= 2
    titles = [s.title for s in paper.sections]
    assert "Introduction" in titles
    assert "Experiments" in titles


def test_parse_xml_title(tmp_path):
    from dataset_extractor.parsers.paper_parser import parse_xml

    paper = parse_xml(make_xml(tmp_path))
    assert paper.title == "Test Paper"


def test_parse_html_sections(tmp_path):
    from dataset_extractor.parsers.paper_parser import parse_html

    paper = parse_html(make_html(tmp_path))
    assert paper.format == "html"
    assert len(paper.sections) >= 2


def test_parse_html_title(tmp_path):
    from dataset_extractor.parsers.paper_parser import parse_html

    paper = parse_html(make_html(tmp_path))
    assert paper.title == "Test Paper on Datasets"


def test_parse_pdf(tmp_path):
    from dataset_extractor.parsers.paper_parser import parse_pdf

    paper = parse_pdf(make_pdf(tmp_path))
    assert paper.format == "pdf"
    assert paper.raw_text is not None


def test_parse_paper_dispatcher(tmp_path):
    from dataset_extractor.parsers.paper_parser import parse_paper

    xml_file = make_xml(tmp_path)
    paper = parse_paper(xml_file)
    assert paper.paper_id  # non-empty id
    assert paper.format == "xml"


def test_parse_paper_unsupported(tmp_path):
    from dataset_extractor.parsers.paper_parser import parse_paper

    bad = tmp_path / "paper.docx"
    bad.write_text("hello")
    with pytest.raises(ValueError, match="Unsupported"):
        parse_paper(bad)


def test_parse_paper_missing():
    from dataset_extractor.parsers.paper_parser import parse_paper

    with pytest.raises(FileNotFoundError):
        parse_paper("/nonexistent/path/paper.pdf")
