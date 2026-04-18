"""FDR (Follow Data References) agent — validates and completes incomplete references."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from openai import OpenAI

from dataset_extractor.config import OPENAI_API_KEY, OPENAI_MODEL, MAX_REPAIR_ATTEMPTS
from dataset_extractor.logging_utils import get_logger, log_event
from dataset_extractor.models import (
    DatasetReference,
    ExtractionState,
    ReferenceStatus,
)
from dataset_extractor.url_validator import URLStatus, check_url
from dataset_extractor.agents.prompts import FDR_SYSTEM_PROMPT, FDR_USER_TEMPLATE

logger = get_logger(__name__, log_file="fdr_agent.jsonl")


def _build_client() -> OpenAI:
    return OpenAI(api_key=OPENAI_API_KEY)


def _parse_llm_json_obj(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
    if raw.endswith("```"):
        raw = raw[: raw.rfind("```")]
    raw = raw.strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1:
            parsed = json.loads(raw[start : end + 1])
        else:
            return {}
    return parsed if isinstance(parsed, dict) else {}


def repair_reference(client: OpenAI, ref: DatasetReference, paper_title: str) -> DatasetReference:
    """Attempt to complete an incomplete reference using the LLM."""
    user_msg = FDR_USER_TEMPLATE.format(
        paper_title=paper_title,
        dataset_identifier=ref.dataset_identifier,
        repository=ref.repository or "unknown",
        url=ref.url or "unknown",
        description=ref.description or "unknown",
        extraction_context=ref.extraction_context or "N/A",
    )

    log_event(
        logger,
        "fdr_repair_start",
        dataset=ref.dataset_identifier,
        attempt=ref.repair_attempts + 1,
    )

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": FDR_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content or "{}"
    data = _parse_llm_json_obj(raw)

    ref.repair_attempts += 1

    if data.get("url"):
        ref.url = data["url"]
    if data.get("repository"):
        ref.repository = data["repository"]
    if data.get("description") and not ref.description:
        ref.description = data["description"]
    if data.get("dataset_identifier") and ref.dataset_identifier == "Unknown":
        ref.dataset_identifier = data["dataset_identifier"]

    # Determine new status based on completeness
    if ref.url:
        ref.status = ReferenceStatus.COMPLETE
    elif ref.repair_attempts >= MAX_REPAIR_ATTEMPTS:
        ref.status = ReferenceStatus.UNRESOLVED
    # else stays INCOMPLETE for further attempts

    confidence = data.get("confidence", "low")
    log_event(
        logger,
        "fdr_repair_done",
        dataset=ref.dataset_identifier,
        status=ref.status.value,
        confidence=confidence,
    )
    return ref


async def validate_reference_url(ref: DatasetReference) -> DatasetReference:
    """Check that a reference's URL is actually reachable."""
    if not ref.url:
        return ref

    result = await check_url(ref.url)
    if result.status == URLStatus.VALID:
        ref.status = ReferenceStatus.VALIDATED
    elif result.status in (URLStatus.NOT_FOUND, URLStatus.INVALID):
        ref.status = ReferenceStatus.INVALID_URL
        log_event(
            logger,
            "fdr_url_invalid",
            dataset=ref.dataset_identifier,
            url=ref.url,
            http_code=result.http_code,
        )
    return ref


def run_fdr(state: ExtractionState) -> ExtractionState:
    """Run the full FDR phase: repair incomplete refs, then validate URLs."""
    client = _build_client()
    paper_title = state.paper.title or "Unknown"
    state.new_refs_this_cycle = 0

    log_event(
        logger,
        "fdr_start",
        paper_id=state.paper.paper_id,
        incomplete_count=len(state.incomplete_refs()),
    )

    # Phase 1: Repair incomplete references
    for ref in state.references:
        if ref.status == ReferenceStatus.INCOMPLETE and ref.repair_attempts < MAX_REPAIR_ATTEMPTS:
            repair_reference(client, ref, paper_title)

    # Phase 2: Validate URLs on all COMPLETE references
    refs_to_validate = [r for r in state.references if r.status == ReferenceStatus.COMPLETE and r.url]
    if refs_to_validate:
        loop = asyncio.new_event_loop()
        try:
            tasks = [validate_reference_url(r) for r in refs_to_validate]
            loop.run_until_complete(asyncio.gather(*tasks))
        finally:
            loop.close()

    # Phase 3: Re-attempt repair on INVALID_URL refs (URL might be wrong)
    for ref in state.references:
        if ref.status == ReferenceStatus.INVALID_URL and ref.repair_attempts < MAX_REPAIR_ATTEMPTS:
            ref.url = None  # Clear bad URL
            ref.status = ReferenceStatus.INCOMPLETE
            repair_reference(client, ref, paper_title)

    log_event(
        logger,
        "fdr_complete",
        paper_id=state.paper.paper_id,
        validated=sum(1 for r in state.references if r.status == ReferenceStatus.VALIDATED),
        unresolved=sum(1 for r in state.references if r.status == ReferenceStatus.UNRESOLVED),
    )
    return state
