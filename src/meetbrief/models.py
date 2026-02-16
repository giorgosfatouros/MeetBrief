"""Data models for MeetBrief using Pydantic."""

from typing import List, Optional
from pydantic import BaseModel, Field


class TranscriptSegment(BaseModel):
    """A single segment of transcribed audio with timestamp."""

    start: float = Field(..., description="Start time in seconds")
    end: float = Field(..., description="End time in seconds")
    speaker: Optional[str] = Field(None, description="Speaker identifier (optional)")
    text: str = Field(..., description="Transcribed text")


class ActionItem(BaseModel):
    """An action item extracted from the meeting."""

    task: str = Field(..., description="Description of the task")
    owner: str = Field(..., description="Person responsible for the task")
    due_date: Optional[str] = Field(None, description="Due date (if mentioned)")
    priority: Optional[str] = Field(None, description="Priority level (if mentioned)")


class MeetingReport(BaseModel):
    """Structured meeting report with extracted insights."""

    title: Optional[str] = Field(None, description="Meeting title")
    duration: Optional[str] = Field(None, description="Meeting duration")
    summary: str = Field(..., description="Executive summary of the meeting")
    decisions: List[str] = Field(default_factory=list, description="Decisions made")
    action_items: List[ActionItem] = Field(
        default_factory=list, description="Action items with owners"
    )
    risks: List[str] = Field(default_factory=list, description="Risks and blockers")
    open_questions: List[str] = Field(
        default_factory=list, description="Open questions"
    )


class RawTranscript(BaseModel):
    """Container for raw transcript segments."""

    segments: List[TranscriptSegment] = Field(
        default_factory=list, description="List of transcript segments"
    )
