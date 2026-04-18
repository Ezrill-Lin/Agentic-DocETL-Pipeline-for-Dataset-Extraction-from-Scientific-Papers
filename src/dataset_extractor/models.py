"""Pydantic data models for the dataset extraction pipeline."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


# ---------------------------------------------------------------------------
# Dataset reference
# ---------------------------------------------------------------------------

class ReferenceStatus(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    UNRESOLVED = "unresolved"
    VALIDATED = "validated"
    INVALID_URL = "invalid_url"


class DatasetReference(BaseModel):
    """A single dataset reference extracted from a paper."""

    dataset_identifier: str = Field(
        ..., description="Name or canonical identifier of the dataset"
    )
    repository: Optional[str] = Field(
        None,
        description="Hosting platform (e.g. Zenodo, GitHub, UCI ML Repository)",
    )
    url: Optional[str] = Field(
        None, description="Direct URL to the dataset"
    )
    description: Optional[str] = Field(
        None, description="Brief description of the dataset"
    )
    paper_source: str = Field(
        ..., description="Identifier of the paper this reference was extracted from"
    )
    status: ReferenceStatus = Field(default=ReferenceStatus.INCOMPLETE)
    extraction_context: Optional[str] = Field(
        None,
        description="Text snippet where the reference was found",
    )
    repair_attempts: int = Field(default=0)


# ---------------------------------------------------------------------------
# Paper content
# ---------------------------------------------------------------------------

class PaperSection(BaseModel):
    """One logical section of a parsed paper."""

    title: str
    content: str
    index: int = Field(description="Section order in the paper")


class PaperContent(BaseModel):
    """Full parsed representation of a scientific paper."""

    paper_id: str = Field(..., description="Unique identifier for the paper")
    title: Optional[str] = None
    source_path: str = Field(..., description="Original file path")
    format: str = Field(..., description="File format: pdf, xml, or html")
    sections: list[PaperSection] = Field(default_factory=list)
    raw_text: Optional[str] = Field(
        None, description="Full paper text when sections cannot be determined"
    )


# ---------------------------------------------------------------------------
# Extraction state (tracks one full RTR→FDR cycle)
# ---------------------------------------------------------------------------

class ExtractionState(BaseModel):
    """Mutable state passed through the RTR→FDR pipeline."""

    paper: PaperContent
    references: list[DatasetReference] = Field(default_factory=list)
    cycle: int = Field(default=0, description="Current RTR→FDR cycle number")
    sections_read: int = Field(default=0)
    new_refs_this_cycle: int = Field(default=0)
    is_complete: bool = Field(default=False)

    def incomplete_refs(self) -> list[DatasetReference]:
        return [r for r in self.references if r.status == ReferenceStatus.INCOMPLETE]

    def add_reference(self, ref: DatasetReference) -> None:
        # Deduplicate by dataset_identifier
        existing_ids = {r.dataset_identifier.lower() for r in self.references}
        if ref.dataset_identifier.lower() not in existing_ids:
            self.references.append(ref)
            self.new_refs_this_cycle += 1


# ---------------------------------------------------------------------------
# Pipeline I/O (for DocETL integration)
# ---------------------------------------------------------------------------

class PipelineInput(BaseModel):
    """Input document for the DocETL pipeline."""

    paper_path: str
    paper_id: Optional[str] = None


class PipelineOutput(BaseModel):
    """Final output of the pipeline for one paper."""

    paper_id: str
    paper_title: Optional[str] = None
    references: list[DatasetReference]
    cycles_run: int
    total_sections: int
