#!/usr/bin/env python3
"""
run_pipeline.py — Entry point for the dataset extraction pipeline.

Usage:
    python run_pipeline.py --input data/input/
    python run_pipeline.py --input data/input/ --output data/output/
    python run_pipeline.py --file path/to/paper.pdf
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add src/ to path so the package is importable without installing
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dataset_extractor.config import DATA_INPUT_DIR, DATA_OUTPUT_DIR
from dataset_extractor.docetl_ops.operations import fdr_op, output_op, parse_paper_op, rtr_op
from dataset_extractor.logging_utils import get_logger, log_event

logger = get_logger("run_pipeline", log_file="pipeline.jsonl")

SUPPORTED_EXTENSIONS = {".pdf", ".xml", ".html", ".htm"}


def process_paper(paper_path: Path, output_dir: Path) -> dict:
    """Run the full pipeline on a single paper file."""
    log_event(logger, "pipeline_start", paper=str(paper_path))

    doc: dict = {"paper_path": str(paper_path)}

    doc = parse_paper_op(doc)
    if doc.get("_error"):
        print(f"  [PARSE ERROR] {paper_path.name}: {doc['_error']}")
        return doc

    doc = rtr_op(doc)
    if doc.get("_error"):
        print(f"  [RTR ERROR] {paper_path.name}: {doc['_error']}")
        return doc

    doc = fdr_op(doc)

    # Override output dir if requested
    from dataset_extractor import config as cfg

    cfg.DATA_OUTPUT_DIR = output_dir
    doc = output_op(doc)

    refs = doc.get("references_count", 0)
    out = doc.get("output_path", "?")
    print(f"  ✓ {paper_path.name}  →  {refs} dataset(s) extracted  →  {out}")
    log_event(logger, "pipeline_done", paper=str(paper_path), refs=refs, output=out)
    return doc


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract dataset references from scientific papers")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", "-i", type=Path, help="Directory of paper files")
    group.add_argument("--file", "-f", type=Path, help="Single paper file")
    parser.add_argument(
        "--output", "-o", type=Path, default=DATA_OUTPUT_DIR, help="Output directory"
    )
    args = parser.parse_args()

    output_dir: Path = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.file:
        papers = [args.file]
    else:
        input_dir: Path = args.input
        if not input_dir.exists():
            print(f"Input directory not found: {input_dir}")
            sys.exit(1)
        papers = [
            p for p in input_dir.rglob("*") if p.suffix.lower() in SUPPORTED_EXTENSIONS
        ]

    if not papers:
        print("No supported paper files found (.pdf, .xml, .html).")
        sys.exit(0)

    print(f"\nProcessing {len(papers)} paper(s)...\n")
    results = []
    for paper in papers:
        result = process_paper(paper, output_dir)
        results.append({
            "paper": str(paper),
            "output": result.get("output_path"),
            "refs": result.get("references_count", 0),
            "error": result.get("_error"),
        })

    # Summary
    print(f"\n{'─' * 50}")
    total_refs = sum(r["refs"] for r in results if not r["error"])
    errors = [r for r in results if r["error"]]
    print(f"Summary: {len(papers)} paper(s), {total_refs} datasets found, {len(errors)} error(s)")

    # Write manifest
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Manifest written to: {manifest_path}\n")


if __name__ == "__main__":
    main()
