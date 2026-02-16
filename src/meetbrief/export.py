"""Export module for Markdown and JSON output."""

import json
from datetime import datetime
from pathlib import Path
from typing import List

from .models import MeetingReport, TranscriptSegment


def export_json(report: MeetingReport, output_path: Path) -> None:
    """Export meeting report as JSON.

    Args:
        report: Meeting report to export
        output_path: Path to output JSON file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(), f, indent=2, ensure_ascii=False)


def export_raw_transcript(segments: List[TranscriptSegment], output_path: Path) -> None:
    """Export raw transcript as JSON.

    Args:
        segments: List of transcript segments
        output_path: Path to output JSON file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "segments": [seg.model_dump() for seg in segments],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def export_clean_transcript(segments: List[TranscriptSegment], output_path: Path) -> None:
    """Export cleaned transcript as Markdown.

    Args:
        segments: List of transcript segments
        output_path: Path to output Markdown file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = ["# Meeting Transcript\n", ""]

    for seg in segments:
        timestamp = f"[{format_time(seg.start)} - {format_time(seg.end)}]"
        speaker = f"**{seg.speaker}:** " if seg.speaker else ""
        lines.append(f"{timestamp} {speaker}{seg.text}\n")

    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def export_markdown(
    report: MeetingReport, transcript: List[TranscriptSegment], output_path: Path
) -> None:
    """Export meeting report as Notion-ready Markdown.

    Args:
        report: Meeting report to export
        transcript: List of transcript segments (not included in final report)
        output_path: Path to output Markdown file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = []

    # Title and metadata
    title = report.title or "Meeting Report"
    lines.append(f"# {title}\n")
    lines.append("---\n")

    if report.duration:
        lines.append(f"**Duration:** {report.duration}\n")
    lines.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d')}\n")
    lines.append("\n")

    # TL;DR
    if report.summary:
        lines.append("## TL;DR\n")
        # Use first sentence or first 200 chars as TL;DR
        tldr = report.summary.split(".")[0] if "." in report.summary else report.summary[:200]
        lines.append(f"{tldr}\n")
        lines.append("\n")

    # Executive Summary
    lines.append("## Executive Summary\n")
    lines.append(f"{report.summary}\n")
    lines.append("\n")

    # Decisions
    if report.decisions:
        lines.append("## Decisions\n")
        for decision in report.decisions:
            lines.append(f"- {decision}\n")
        lines.append("\n")

    # Action Items
    if report.action_items:
        lines.append("## Action Items\n")
        for item in report.action_items:
            checkbox = "- [ ]"  # Notion checkbox format
            owner = f"**Owner:** {item.owner}" if item.owner else ""
            due = f"**Due:** {item.due_date}" if item.due_date else ""
            priority = f"**Priority:** {item.priority}" if item.priority else ""
            metadata = ", ".join(filter(None, [owner, due, priority]))
            if metadata:
                lines.append(f"{checkbox} {item.task} ({metadata})\n")
            else:
                lines.append(f"{checkbox} {item.task}\n")
        lines.append("\n")

    # Risks and Blockers
    if report.risks:
        lines.append("## Risks and Blockers\n")
        for risk in report.risks:
            lines.append(f"- {risk}\n")
        lines.append("\n")

    # Open Questions
    if report.open_questions:
        lines.append("## Open Questions\n")
        for question in report.open_questions:
            lines.append(f"- {question}\n")
        lines.append("\n")

    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def format_time(seconds: float) -> str:
    """Format seconds as MM:SS or HH:MM:SS.

    Args:
        seconds: Time in seconds

    Returns:
        Formatted time string
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
