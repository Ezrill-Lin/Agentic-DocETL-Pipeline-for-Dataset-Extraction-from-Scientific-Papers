"""RTR (Read & Extract) agent — reads paper sections and extracts dataset references."""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from dataset_extractor.config import OPENAI_API_KEY, OPENAI_MODEL
from dataset_extractor.logging_utils import get_logger, log_event
from dataset_extractor.models import (
    DatasetReference,
    ExtractionState,
    PaperContent,
    ReferenceStatus,
)
from dataset_extractor.agents.prompts import RTR_SYSTEM_PROMPT, RTR_USER_TEMPLATE

logger = get_logger(__name__, log_file="rtr_agent.jsonl")


def _build_client() -> OpenAI:
    return OpenAI(api_key=OPENAI_API_KEY)


def _parse_llm_json(raw: str) -> list[dict[str, Any]]:
    """Robustly parse a JSON array (or wrapped object) from LLM output."""
    raw = raw.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
    if raw.endswith("```"):
        raw = raw[: raw.rfind("```")]
    raw = raw.strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("[")
        end = raw.rfind("]")
        if start != -1 and end != -1:
            parsed = json.loads(raw[start : end + 1])
        else:
            logger.warning("Failed to parse LLM JSON output: %s", raw[:200])
            return []

    # Unwrap {"datasets": [...]} envelope (required by json_object response_format)
    if isinstance(parsed, dict):
        for key in ("datasets", "data", "results", "references"):
            if key in parsed and isinstance(parsed[key], list):
                parsed = parsed[key]
                break
        else:
            # Single-item flat object — wrap it
            parsed = [parsed]

    return parsed if isinstance(parsed, list) else []


def extract_from_section(
    client: OpenAI,
    paper: PaperContent,
    section_index: int,
) -> list[DatasetReference]:
    """Call the LLM to extract dataset references from one section."""
    section = paper.sections[section_index]
    user_msg = RTR_USER_TEMPLATE.format(
        paper_title=paper.title or "Unknown",
        section_index=section_index + 1,
        total_sections=len(paper.sections),
        section_title=section.title,
        section_content=section.content[:8000],  # token budget guard
    )

    log_event(
        logger,
        "rtr_section_start",
        paper_id=paper.paper_id,
        section=section.title,
        index=section_index,
    )

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": RTR_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    raw_text = response.choices[0].message.content or "[]"
    items = _parse_llm_json(raw_text)

    refs: list[DatasetReference] = []
    for item in items:
        identifier = item.get("dataset_identifier") or "Unknown"
        # Skip placeholder items with no meaningful content
        if identifier == "Unknown" and not item.get("url") and not item.get("description"):
            continue
        status = ReferenceStatus.COMPLETE if item.get("url") else ReferenceStatus.INCOMPLETE
        ref = DatasetReference(
            dataset_identifier=identifier,
            repository=item.get("repository") or None,
            url=item.get("url") or None,
            description=item.get("description") or None,
            paper_source=paper.paper_id,
            status=status,
            extraction_context=item.get("extraction_context") or None,
        )
        refs.append(ref)

    log_event(
        logger,
        "rtr_section_done",
        paper_id=paper.paper_id,
        section=section.title,
        refs_found=len(refs),
    )
    return refs


def run_rtr(state: ExtractionState) -> ExtractionState:
    """Run the full RTR phase: read every section and extract references."""
    client = _build_client()
    paper = state.paper
    state.new_refs_this_cycle = 0

    log_event(logger, "rtr_start", paper_id=paper.paper_id, total_sections=len(paper.sections))

    for idx in range(len(paper.sections)):
        refs = extract_from_section(client, paper, idx)
        for ref in refs:
            state.add_reference(ref)
        state.sections_read = idx + 1

    log_event(
        logger,
        "rtr_complete",
        paper_id=paper.paper_id,
        total_refs=len(state.references),
        new_refs=state.new_refs_this_cycle,
    )
    return state
