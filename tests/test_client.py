"""Tests for client abstraction layer."""

from pathlib import Path
from unittest.mock import patch

import pytest

from meetbrief.client import OpenAIClient, TranscriptionClient, LLMClient
from meetbrief.models import TranscriptSegment


class MockTranscriptionClient(TranscriptionClient):
    """Mock transcription client for testing."""

    def transcribe_audio(self, audio_path: Path, language=None):
        return [
            TranscriptSegment(start=0.0, end=5.0, text="Hello world"),
            TranscriptSegment(start=5.0, end=10.0, text="How are you?"),
        ]

    def supports_language(self, language: str) -> bool:
        return True


class MockLLMClient(LLMClient):
    """Mock LLM client for testing."""

    def generate_structured_output(self, prompt: str, schema: dict, model=None):
        return {
            "summary": "Test summary",
            "decisions": ["Decision 1"],
            "action_items": [{"task": "Task 1", "owner": "Alice"}],
            "risks": [],
            "open_questions": [],
        }

    def chat_completion(self, messages, model=None, **kwargs):
        return "Test response"


def test_mock_transcription_client():
    """Test mock transcription client."""
    client = MockTranscriptionClient()
    segments = client.transcribe_audio(Path("test.mp3"))
    assert len(segments) == 2
    assert segments[0].text == "Hello world"


def test_mock_llm_client():
    """Test mock LLM client."""
    client = MockLLMClient()
    schema = {"type": "object"}
    result = client.generate_structured_output("test prompt", schema)
    assert "summary" in result
    assert result["summary"] == "Test summary"


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
def test_openai_client_initialization():
    """Test OpenAI client initialization."""
    client = OpenAIClient(api_key="test-key")
    assert client.api_key == "test-key"
    assert client.transcription_model == "whisper-1"
    assert client.llm_model == "gpt-4o-mini"


def test_openai_client_missing_key():
    """Test OpenAI client raises error without API key."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="OpenAI API key required"):
            OpenAIClient()
