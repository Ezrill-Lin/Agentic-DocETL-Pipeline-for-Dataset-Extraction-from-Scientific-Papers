"""Custom DocETL operations wrapping the RTR and FDR agents."""

from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any

from dataset_extractor.agents.fdr_agent import run_fdr
from dataset_extractor.agents.rtr_agent import run_rtr
from dataset_extractor.config import DATA_OUTPUT_DIR, MAX_RTR_FDR_CYCLES
from dataset_extractor.logging_utils import get_logger, log_event
from dataset_extractor.models import ExtractionState, PipelineInput, PipelineOutput
from dataset_extractor.parsers.paper_parser import parse_paper

logger = get_logger(__name__, log_file="pipeline.jsonl")


# ---------------------------------------------------------------------------
# DocETL expects operations to be plain callables: dict -> dict
# ---------------------------------------------------------------------------

def parse_paper_op(doc: dict[str, Any]) -> dict[str, Any]:
    """
    DocETL map operation: parse a paper file into sections.

    Input doc keys:
      - paper_path (str): path to the paper file
      - paper_id (str, optional): override paper ID

    Output adds:
      - paper_id, paper_title, sections (list[dict]), format
    """
    inp = PipelineInput(**doc)
    try:
        paper = parse_paper(inp.paper_path)
        if inp.paper_id:
            paper.paper_id = inp.paper_id
        log_event(logger, "parse_done", paper_id=paper.paper_id, sections=len(paper.sections))
        return {
            **doc,
            "paper_id": paper.paper_id,
            "paper_title": paper.title,
            "format": paper.format,
            "sections": [s.model_dump() for s in paper.sections],
            "_paper_json": paper.model_dump_json(),
            "_error": None,
        }
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "parse_error", paper_path=inp.paper_path, error=str(exc), level="error")
        return {**doc, "_error": f"parse: {exc}", "_paper_json": None}


def rtr_op(doc: dict[str, Any]) -> dict[str, Any]:
    """
    DocETL map operation: run RTR agent on a parsed paper.

    Input doc must contain `_paper_json` from `parse_paper_op`.
    Output adds `_state_json` with the ExtractionState after RTR.
    """
    if doc.get("_error") or not doc.get("_paper_json"):
        return {**doc, "_error": doc.get("_error", "missing _paper_json")}

    from dataset_extractor.models import PaperContent

    paper = PaperContent.model_validate_json(doc["_paper_json"])
    state = ExtractionState(paper=paper)

    try:
        state = run_rtr(state)
        log_event(logger, "rtr_op_done", paper_id=paper.paper_id, refs=len(state.references))
        return {
            **doc,
            "_state_json": state.model_dump_json(),
            "references_count": len(state.references),
            "_error": None,
        }
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "rtr_op_error", paper_id=paper.paper_id, error=str(exc), level="error")
        return {**doc, "_state_json": None, "_error": f"rtr: {exc}"}


def fdr_op(doc: dict[str, Any]) -> dict[str, Any]:
    """
    DocETL map operation: run FDR agent to validate and repair references.

    Loops RTR→FDR up to MAX_RTR_FDR_CYCLES until no new references appear.
    """
    if doc.get("_error") or not doc.get("_state_json"):
        return {**doc, "_error": doc.get("_error", "missing _state_json")}

    state = ExtractionState.model_validate_json(doc["_state_json"])

    try:
        for cycle in range(MAX_RTR_FDR_CYCLES):
            state.cycle = cycle + 1
            state.new_refs_this_cycle = 0
            state = run_fdr(state)
            log_event(
                logger,
                "fdr_cycle_done",
                paper_id=state.paper.paper_id,
                cycle=cycle + 1,
                new_refs=state.new_refs_this_cycle,
            )
            if state.new_refs_this_cycle == 0:
                break
            # Re-run RTR for another pass if FDR found new leads
            state = run_rtr(state)

        state.is_complete = True
        return {**doc, "_state_json": state.model_dump_json(), "_error": None}
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "fdr_op_error", paper_id=state.paper.paper_id, error=str(exc), level="error")
        return {**doc, "_state_json": state.model_dump_json(), "_error": f"fdr: {exc}"}


def output_op(doc: dict[str, Any]) -> dict[str, Any]:
    """
    DocETL map operation: serialize final results to a JSON file.

    Writes `data/output/<paper_id>.json`.
    """
    if not doc.get("_state_json"):
        return {**doc, "output_path": None}

    state = ExtractionState.model_validate_json(doc["_state_json"])
    paper = state.paper

    output = PipelineOutput(
        paper_id=paper.paper_id,
        paper_title=paper.title,
        references=state.references,
        cycles_run=state.cycle,
        total_sections=len(paper.sections),
    )

    DATA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_OUTPUT_DIR / f"{paper.paper_id}.json"
    out_path.write_text(output.model_dump_json(indent=2), encoding="utf-8")

    log_event(logger, "output_written", paper_id=paper.paper_id, path=str(out_path))
    return {**doc, "output_path": str(out_path), "references_count": len(state.references)}


# ---------------------------------------------------------------------------
# Operation registry (used by DocETL YAML via `custom_operations`)
# ---------------------------------------------------------------------------

OPERATION_REGISTRY: dict[str, Any] = {
    "parse_paper": parse_paper_op,
    "rtr": rtr_op,
    "fdr": fdr_op,
    "output": output_op,
}
