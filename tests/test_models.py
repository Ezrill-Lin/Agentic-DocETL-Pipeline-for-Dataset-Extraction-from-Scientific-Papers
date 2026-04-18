"""Tests for data models."""

from __future__ import annotations

from dataset_extractor.models import (
    DatasetReference,
    ExtractionState,
    PaperContent,
    PaperSection,
    ReferenceStatus,
)


def _make_paper() -> PaperContent:
    return PaperContent(
        paper_id="abc123",
        title="A Test Paper",
        source_path="/tmp/test.pdf",
        format="pdf",
        sections=[
            PaperSection(title="Abstract", content="We use MNIST.", index=0),
            PaperSection(title="Methods", content="Trained on ImageNet.", index=1),
        ],
    )


def test_dataset_reference_defaults():
    ref = DatasetReference(
        dataset_identifier="MNIST",
        paper_source="abc123",
    )
    assert ref.status == ReferenceStatus.INCOMPLETE
    assert ref.repair_attempts == 0
    assert ref.url is None


def test_extraction_state_add_reference():
    state = ExtractionState(paper=_make_paper())
    ref = DatasetReference(dataset_identifier="MNIST", paper_source="abc123")
    state.add_reference(ref)
    assert len(state.references) == 1
    assert state.new_refs_this_cycle == 1


def test_extraction_state_deduplication():
    state = ExtractionState(paper=_make_paper())
    ref1 = DatasetReference(dataset_identifier="MNIST", paper_source="abc123")
    ref2 = DatasetReference(dataset_identifier="mnist", paper_source="abc123")  # same, different case
    state.add_reference(ref1)
    state.add_reference(ref2)
    assert len(state.references) == 1


def test_extraction_state_incomplete_refs():
    state = ExtractionState(paper=_make_paper())
    ref_incomplete = DatasetReference(dataset_identifier="MNIST", paper_source="abc123")
    ref_complete = DatasetReference(
        dataset_identifier="ImageNet",
        paper_source="abc123",
        url="https://image-net.org",
        status=ReferenceStatus.COMPLETE,
    )
    state.add_reference(ref_incomplete)
    state.add_reference(ref_complete)
    assert len(state.incomplete_refs()) == 1
    assert state.incomplete_refs()[0].dataset_identifier == "MNIST"


def test_paper_content_serialization():
    paper = _make_paper()
    json_str = paper.model_dump_json()
    restored = PaperContent.model_validate_json(json_str)
    assert restored.paper_id == paper.paper_id
    assert len(restored.sections) == 2


def test_extraction_state_serialization():
    state = ExtractionState(paper=_make_paper())
    ref = DatasetReference(dataset_identifier="CIFAR-10", paper_source="abc123")
    state.add_reference(ref)
    json_str = state.model_dump_json()
    restored = ExtractionState.model_validate_json(json_str)
    assert len(restored.references) == 1
    assert restored.references[0].dataset_identifier == "CIFAR-10"
