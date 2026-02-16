"""Tests for export module."""

import json
import tempfile
from pathlib import Path

from meetbrief.export import (
    export_json,
    export_markdown,
    export_raw_transcript,
    export_clean_transcript,
    format_time,
)
from meetbrief.models import MeetingReport, TranscriptSegment, ActionItem


def test_format_time():
    """Test time formatting."""
    assert format_time(0) == "00:00"
    assert format_time(65) == "01:05"
    assert format_time(3665) == "01:01:05"


def test_export_json():
    """Test JSON export."""
    report = MeetingReport(
        summary="Test summary",
        decisions=["Decision 1"],
        action_items=[ActionItem(task="Task 1", owner="Alice")],
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "report.json"
        export_json(report, output_path)

        assert output_path.exists()
        with open(output_path, "r") as f:
            data = json.load(f)
            assert data["summary"] == "Test summary"
            assert len(data["decisions"]) == 1


def test_export_raw_transcript():
    """Test raw transcript export."""
    segments = [
        TranscriptSegment(start=0.0, end=5.0, text="Hello"),
        TranscriptSegment(start=5.0, end=10.0, text="World"),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "transcript.json"
        export_raw_transcript(segments, output_path)

        assert output_path.exists()
        with open(output_path, "r") as f:
            data = json.load(f)
            assert len(data["segments"]) == 2


def test_export_clean_transcript():
    """Test clean transcript export."""
    segments = [
        TranscriptSegment(start=0.0, end=5.0, speaker="S1", text="Hello"),
        TranscriptSegment(start=5.0, end=10.0, speaker="S2", text="World"),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "transcript.md"
        export_clean_transcript(segments, output_path)

        assert output_path.exists()
        content = output_path.read_text()
        assert "Hello" in content
        assert "World" in content
        assert "S1" in content


def test_export_markdown():
    """Test Markdown report export."""
    report = MeetingReport(
        title="Test Meeting",
        duration="30m",
        summary="This is a test meeting summary.",
        decisions=["Decision 1", "Decision 2"],
        action_items=[
            ActionItem(task="Complete task", owner="Alice", due_date="2024-01-01")
        ],
        risks=["Risk 1"],
        open_questions=["Question 1"],
    )

    segments = [
        TranscriptSegment(start=0.0, end=60.0, text="Meeting content"),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "report.md"
        export_markdown(report, segments, output_path)

        assert output_path.exists()
        content = output_path.read_text()
        assert "Test Meeting" in content
        assert "Executive Summary" in content
        assert "Decisions" in content
        assert "Action Items" in content
        assert "Complete task" in content
        assert "Alice" in content
