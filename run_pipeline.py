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
import time
from pathlib import Path

# Add src/ to path so the package is importable without installing
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dataset_extractor.config import DATA_INPUT_DIR, DATA_OUTPUT_DIR
from dataset_extractor.docetl_ops.operations import fdr_op, output_op, parse_paper_op, rtr_op
from dataset_extractor.logging_utils import get_logger, log_event

logger = get_logger("run_pipeline", log_file="pipeline.jsonl")

SUPPORTED_EXTENSIONS = {".pdf", ".xml", ".html", ".htm"}

# ANSI colors (disabled on non-TTY)
_IS_TTY = sys.stdout.isatty()
GREEN  = "\033[32m" if _IS_TTY else ""
YELLOW = "\033[33m" if _IS_TTY else ""
CYAN   = "\033[36m" if _IS_TTY else ""
RED    = "\033[31m" if _IS_TTY else ""
BOLD   = "\033[1m"  if _IS_TTY else ""
DIM    = "\033[2m"  if _IS_TTY else ""
RESET  = "\033[0m"  if _IS_TTY else ""


def _bar(current: int, total: int, width: int = 25) -> str:
    filled = int(width * current / total) if total else 0
    return f"[{'█' * filled}{'░' * (width - filled)}]"


def process_paper(paper_path: Path, output_dir: Path, index: int, total: int) -> dict:
    """Run the full pipeline on a single paper file."""
    log_event(logger, "pipeline_start", paper=str(paper_path))

    header = f"{BOLD}[{index}/{total}]{RESET} {CYAN}{paper_path.name}{RESET}"
    print(f"\n{header}")

    t0 = time.perf_counter()
    doc: dict = {"paper_path": str(paper_path)}

    # --- Parse ---
    print(f"  {DIM}Parsing...{RESET}", end="", flush=True)
    doc = parse_paper_op(doc)
    if doc.get("_error"):
        print(f"\r  {RED}✗ PARSE ERROR:{RESET} {doc['_error']}")
        return doc
    n_sections = doc.get("state", {}).get("paper", {}).get("sections") or "?"
    # n_sections may not be directly accessible; get it from log context
    print(f"\r  {GREEN}✓ Parsed{RESET}                        ", flush=True)

    # --- RTR ---
    print(f"  {DIM}RTR: reading sections...{RESET}", end="", flush=True)
    doc = rtr_op(doc)
    if doc.get("_error"):
        print(f"\r  {RED}✗ RTR ERROR:{RESET} {doc['_error']}")
        return doc
    rtr_refs = doc.get("references_count", 0)
    print(f"\r  {GREEN}✓ RTR complete{RESET} — {BOLD}{rtr_refs}{RESET} candidate(s) found", flush=True)

    # --- FDR ---
    print(f"  {DIM}FDR: resolving & validating...{RESET}", end="", flush=True)
    doc = fdr_op(doc)
    if doc.get("_error"):
        print(f"\r  {YELLOW}⚠ FDR warning:{RESET} {doc['_error']}")
    fdr_refs = doc.get("references_count", rtr_refs)
    print(f"\r  {GREEN}✓ FDR complete{RESET} — {BOLD}{fdr_refs}{RESET} dataset(s) resolved", flush=True)

    # --- Output ---
    from dataset_extractor import config as cfg
    cfg.DATA_OUTPUT_DIR = output_dir
    doc = output_op(doc)

    elapsed = time.perf_counter() - t0
    refs = doc.get("references_count", 0)
    out = doc.get("output_path", "?")
    print(f"  {GREEN}{'─' * 48}{RESET}")
    print(f"  {BOLD}Result:{RESET} {refs} dataset(s)  {DIM}({elapsed:.1f}s){RESET}")
    print(f"  {DIM}→ {out}{RESET}")

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
        papers = sorted(
            p for p in input_dir.rglob("*") if p.suffix.lower() in SUPPORTED_EXTENSIONS
        )

    if not papers:
        print("No supported paper files found (.pdf, .xml, .html).")
        sys.exit(0)

    print(f"\n{BOLD}Dataset Extraction Pipeline{RESET}")
    print(f"{DIM}{'─' * 50}{RESET}")
    print(f"  Papers  : {BOLD}{len(papers)}{RESET}")
    print(f"  Output  : {output_dir}")
    print(f"{DIM}{'─' * 50}{RESET}")

    wall_start = time.perf_counter()
    results = []
    for i, paper in enumerate(papers, 1):
        result = process_paper(paper, output_dir, i, len(papers))
        results.append({
            "paper": str(paper),
            "output": result.get("output_path"),
            "refs": result.get("references_count", 0),
            "error": result.get("_error"),
        })
        done = i
        remaining = len(papers) - done
        bar = _bar(done, len(papers))
        print(f"\n  {bar} {done}/{len(papers)} papers  |  {remaining} remaining", flush=True)

    # Final summary
    wall_elapsed = time.perf_counter() - wall_start
    total_refs = sum(r["refs"] for r in results if not r["error"])
    errors = [r for r in results if r["error"]]

    print(f"\n{BOLD}{'═' * 50}{RESET}")
    print(f"{BOLD}  Done in {wall_elapsed:.1f}s{RESET}")
    print(f"  Papers processed : {len(papers)}")
    print(f"  Total datasets   : {BOLD}{GREEN}{total_refs}{RESET}")
    if errors:
        print(f"  Errors           : {RED}{len(errors)}{RESET}")
        for e in errors:
            print(f"    {DIM}• {Path(e['paper']).name}: {e['error']}{RESET}")
    print(f"{BOLD}{'═' * 50}{RESET}\n")

    # Write manifest
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Manifest: {manifest_path}\n")


if __name__ == "__main__":
    main()

