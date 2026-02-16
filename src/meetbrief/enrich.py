"""LLM enrichment module for extracting structured insights."""

from typing import List, Optional, Dict, Any

from .client import LLMClient, OpenAIClient
from .models import MeetingReport, TranscriptSegment, ActionItem


def enrich_transcript(
    segments: List[TranscriptSegment],
    title: Optional[str] = None,
    client: Optional[LLMClient] = None,
) -> MeetingReport:
    """Extract structured insights from transcript using LLM.

    Args:
        segments: List of transcript segments
        title: Optional meeting title
        client: Optional LLM client (creates OpenAIClient if not provided)

    Returns:
        Meeting report with extracted insights
    """
    if not segments:
        return MeetingReport(
            title=title,
            summary="No transcript content available.",
            decisions=[],
            action_items=[],
            risks=[],
            open_questions=[],
        )

    # Create client if not provided
    if client is None:
        client = OpenAIClient()

    # Calculate duration
    duration = _calculate_duration(segments)

    # Chunk transcript for processing
    chunks = _chunk_transcript(segments)

    # Process each chunk
    chunk_reports = []
    for chunk in chunks:
        chunk_text = _segments_to_text(chunk)
        report = _extract_insights(chunk_text, client)
        chunk_reports.append(report)

    # Merge chunk results
    merged_report = _merge_reports(chunk_reports, title=title, duration=duration)

    return merged_report


def _calculate_duration(segments: List[TranscriptSegment]) -> str:
    """Calculate meeting duration from segments.

    Args:
        segments: List of transcript segments

    Returns:
        Formatted duration string
    """
    if not segments:
        return "0:00"

    max_end = max(seg.end for seg in segments)
    hours = int(max_end // 3600)
    minutes = int((max_end % 3600) // 60)

    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _chunk_transcript(
    segments: List[TranscriptSegment], max_chunk_duration: float = 1200.0
) -> List[List[TranscriptSegment]]:
    """Split transcript into chunks by time duration.

    Args:
        segments: List of transcript segments
        max_chunk_duration: Maximum duration per chunk in seconds (default 20 minutes)

    Returns:
        List of chunk lists
    """
    if not segments:
        return []

    chunks = []
    current_chunk = []
    current_duration = 0.0

    for seg in segments:
        seg_duration = seg.end - seg.start
        if current_duration + seg_duration > max_chunk_duration and current_chunk:
            chunks.append(current_chunk)
            current_chunk = [seg]
            current_duration = seg_duration
        else:
            current_chunk.append(seg)
            current_duration = seg.end - (current_chunk[0].start if current_chunk else 0)

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def _segments_to_text(segments: List[TranscriptSegment]) -> str:
    """Convert segments to plain text.

    Args:
        segments: List of transcript segments

    Returns:
        Plain text representation
    """
    lines = []
    for seg in segments:
        if seg.speaker:
            lines.append(f"{seg.speaker}: {seg.text}")
        else:
            lines.append(seg.text)
    return "\n".join(lines)


def _extract_insights(text: str, client: LLMClient) -> MeetingReport:
    """Extract structured insights from text using LLM.

    Args:
        text: Transcript text
        client: LLM client

    Returns:
        Meeting report with extracted insights
    """
    # Define JSON schema for structured output
    schema = {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "Executive summary of the meeting",
            },
            "decisions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of decisions made",
            },
            "action_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string"},
                        "owner": {"type": "string"},
                        "due_date": {"type": ["string", "null"]},
                        "priority": {"type": ["string", "null"]},
                    },
                    "required": ["task", "owner", "due_date", "priority"],
                    "additionalProperties": False,
                },
                "description": "List of action items",
            },
            "risks": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of risks and blockers",
            },
            "open_questions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of open questions",
            },
        },
        "required": ["summary", "decisions", "action_items", "risks", "open_questions"],
        "additionalProperties": False,
    }

    prompt = f"""Extract structured information from this meeting transcript:

{text}

Extract:
1. A concise executive summary (2-3 sentences)
2. All decisions made during the meeting
3. Action items with owners, due dates (if mentioned), and priorities (if mentioned)
4. Risks and blockers mentioned
5. Open questions that need to be resolved

Be thorough and accurate. Only extract information that is explicitly stated in the transcript."""

    try:
        result = client.generate_structured_output(prompt, schema)
    except Exception as e:
        # Fallback to basic report if LLM call fails
        return MeetingReport(
            summary=f"Error extracting insights: {str(e)}",
            decisions=[],
            action_items=[],
            risks=[],
            open_questions=[],
        )

    # Convert to MeetingReport
    action_items = [
        ActionItem(
            task=item.get("task", ""),
            owner=item.get("owner", ""),
            due_date=item.get("due_date"),
            priority=item.get("priority"),
        )
        for item in result.get("action_items", [])
    ]

    return MeetingReport(
        summary=result.get("summary", ""),
        decisions=result.get("decisions", []),
        action_items=action_items,
        risks=result.get("risks", []),
        open_questions=result.get("open_questions", []),
    )


def _merge_reports(
    reports: List[MeetingReport], title: Optional[str] = None, duration: Optional[str] = None
) -> MeetingReport:
    """Merge multiple chunk reports into a single report.

    Args:
        reports: List of chunk reports
        title: Optional meeting title
        duration: Optional meeting duration

    Returns:
        Merged meeting report
    """
    if not reports:
        return MeetingReport(
            title=title,
            duration=duration,
            summary="No content extracted.",
            decisions=[],
            action_items=[],
            risks=[],
            open_questions=[],
        )

    # Combine summaries
    summaries = [r.summary for r in reports if r.summary]
    combined_summary = " ".join(summaries) if summaries else "No summary available."

    # Deduplicate decisions
    decisions = []
    seen_decisions = set()
    for report in reports:
        for decision in report.decisions:
            decision_lower = decision.lower().strip()
            if decision_lower and decision_lower not in seen_decisions:
                decisions.append(decision)
                seen_decisions.add(decision_lower)

    # Deduplicate action items
    action_items = []
    seen_tasks = set()
    for report in reports:
        for item in report.action_items:
            task_lower = item.task.lower().strip()
            if task_lower and task_lower not in seen_tasks:
                action_items.append(item)
                seen_tasks.add(task_lower)

    # Deduplicate risks
    risks = []
    seen_risks = set()
    for report in reports:
        for risk in report.risks:
            risk_lower = risk.lower().strip()
            if risk_lower and risk_lower not in seen_risks:
                risks.append(risk)
                seen_risks.add(risk_lower)

    # Deduplicate open questions
    open_questions = []
    seen_questions = set()
    for report in reports:
        for question in report.open_questions:
            question_lower = question.lower().strip()
            if question_lower and question_lower not in seen_questions:
                open_questions.append(question)
                seen_questions.add(question_lower)

    return MeetingReport(
        title=title,
        duration=duration,
        summary=combined_summary,
        decisions=decisions,
        action_items=action_items,
        risks=risks,
        open_questions=open_questions,
    )
