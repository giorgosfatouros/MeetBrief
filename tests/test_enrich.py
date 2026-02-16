"""Tests for enrichment module."""

from meetbrief.enrich import (
    enrich_transcript,
    _chunk_transcript,
    _merge_reports,
    _calculate_duration,
)
from meetbrief.models import TranscriptSegment, MeetingReport, ActionItem
from tests.test_client import MockLLMClient


def test_calculate_duration():
    """Test duration calculation."""
    segments = [
        TranscriptSegment(start=0.0, end=60.0, text="test"),
        TranscriptSegment(start=60.0, end=120.0, text="test"),
    ]

    duration = _calculate_duration(segments)
    assert duration == "2m"


def test_calculate_duration_with_hours():
    """Test duration calculation with hours."""
    segments = [
        TranscriptSegment(start=0.0, end=3660.0, text="test"),  # 1h 1m
    ]

    duration = _calculate_duration(segments)
    assert "1h" in duration


def test_chunk_transcript():
    """Test transcript chunking."""
    segments = [
        TranscriptSegment(start=i * 100, end=(i + 1) * 100, text=f"segment {i}")
        for i in range(30)  # 30 segments, 100s each = 3000s total
    ]

    chunks = _chunk_transcript(segments, max_chunk_duration=1200.0)

    assert len(chunks) > 1  # Should be split into multiple chunks
    assert all(len(chunk) > 0 for chunk in chunks)


def test_merge_reports():
    """Test merging multiple reports."""
    reports = [
        MeetingReport(
            summary="Summary 1",
            decisions=["Decision 1"],
            action_items=[ActionItem(task="Task 1", owner="Alice")],
            risks=["Risk 1"],
            open_questions=["Question 1"],
        ),
        MeetingReport(
            summary="Summary 2",
            decisions=["Decision 2", "Decision 1"],  # Duplicate
            action_items=[ActionItem(task="Task 2", owner="Bob")],
            risks=[],
            open_questions=[],
        ),
    ]

    merged = _merge_reports(reports, title="Test Meeting", duration="10m")

    assert merged.title == "Test Meeting"
    assert merged.duration == "10m"
    assert "Summary 1" in merged.summary
    assert "Summary 2" in merged.summary
    assert len(merged.decisions) == 2  # Duplicate removed
    assert len(merged.action_items) == 2
    assert len(merged.risks) == 1


def test_enrich_transcript_with_mock_client():
    """Test enrichment with mock client."""
    client = MockLLMClient()
    segments = [
        TranscriptSegment(start=0.0, end=60.0, text="Meeting transcript here"),
    ]

    report = enrich_transcript(segments, title="Test Meeting", client=client)

    assert report.title == "Test Meeting"
    assert report.summary == "Test summary"
    assert len(report.decisions) == 1
    assert len(report.action_items) == 1


def test_enrich_empty_transcript():
    """Test enrichment with empty transcript."""
    report = enrich_transcript([])

    assert report.summary == "No transcript content available."
    assert len(report.decisions) == 0
    assert len(report.action_items) == 0
