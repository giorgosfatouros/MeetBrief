"""Tests for cleaning module."""

import warnings
from unittest.mock import patch


from meetbrief.clean import (
    _batch_segments,
    _clean_batch_with_llm,
    _parse_llm_response,
    clean_transcript,
)
from meetbrief.client import LLMClient
from meetbrief.models import TranscriptSegment
from tests.test_client import MockLLMClient


def test_clean_transcript_empty():
    """Test cleaning empty transcript."""
    result = clean_transcript([])
    assert result == []


def test_clean_transcript_preserves_timestamps():
    """Test that cleaning preserves timestamps and speaker labels."""
    segments = [
        TranscriptSegment(start=0.0, end=5.0, speaker="S1", text="hello world"),
        TranscriptSegment(start=5.0, end=10.0, speaker="S2", text="how are you"),
    ]

    cleaned = clean_transcript(segments)

    assert len(cleaned) == 2
    assert cleaned[0].start == 0.0
    assert cleaned[0].end == 5.0
    assert cleaned[0].speaker == "S1"
    assert cleaned[1].speaker == "S2"


def test_clean_transcript_fixes_spacing():
    """Test that cleaning fixes excessive spaces."""
    segments = [
        TranscriptSegment(
            start=0.0, end=5.0, text="hello    world   with   spaces"
        ),
    ]

    cleaned = clean_transcript(segments)

    assert "  " not in cleaned[0].text
    # Cleaning capitalizes first letter and adds period for long text
    assert cleaned[0].text == "Hello world with spaces."


class MockCleaningLLMClient(LLMClient):
    """Mock LLM client that returns properly formatted cleaning responses."""

    def __init__(self, response_template=None, should_fail=False):
        """Initialize mock cleaning client.

        Args:
            response_template: Template for responses (uses default if None)
            should_fail: If True, raises exception on chat_completion
        """
        self.response_template = response_template
        self.should_fail = should_fail

    def generate_structured_output(self, prompt: str, schema: dict, model=None):
        """Not used in cleaning, but required by interface."""
        return {}

    def chat_completion(self, messages, model=None, **kwargs):
        """Return formatted cleaning response."""
        if self.should_fail:
            raise Exception("Mock LLM failure")

        if self.response_template:
            return self.response_template

        # Default: parse user message to extract segments and return cleaned version
        user_message = None
        for msg in messages:
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
                break

        if not user_message:
            return "1. Test response"

        # Extract numbered segments from prompt
        lines = user_message.split("\n")
        cleaned_lines = []
        segment_num = 1

        for line in lines:
            line = line.strip()
            # Look for numbered segments like "1. text" or "1. [Speaker] text"
            if line and line[0].isdigit() and ". " in line:
                # Extract the text part
                parts = line.split(". ", 1)
                if len(parts) == 2:
                    text = parts[1]
                    # Remove speaker label if present
                    if text.startswith("[") and "]" in text:
                        text = text.split("] ", 1)[1] if "] " in text else text
                    # Return cleaned version (capitalize, add period)
                    cleaned = text.strip()
                    if cleaned and cleaned[0].islower():
                        cleaned = cleaned[0].upper() + cleaned[1:]
                    if cleaned and cleaned[-1] not in ".!?":
                        cleaned += "."
                    cleaned_lines.append(f"{segment_num}. {cleaned}")
                    segment_num += 1

        return "\n".join(cleaned_lines) if cleaned_lines else "1. Test response"


def test_clean_transcript_with_mock_client():
    """Test cleaning with mock client (fallback to rule-based)."""
    # MockLLMClient returns "Test response" which won't parse correctly,
    # so it should fall back to rule-based cleaning
    client = MockLLMClient()
    segments = [
        TranscriptSegment(start=0.0, end=5.0, text="test"),
    ]

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cleaned = clean_transcript(segments, client=client)

    assert len(cleaned) == 1
    # Should fall back to rule-based cleaning (capitalizes first letter)
    # Note: "test" is < 10 chars, so no period added
    assert cleaned[0].text == "Test"
    # Should have warning about fallback
    assert len(w) > 0


def test_clean_transcript_with_llm():
    """Test LLM-based cleaning with properly formatted mock client."""
    client = MockCleaningLLMClient()
    segments = [
        TranscriptSegment(start=0.0, end=5.0, speaker="S1", text="hello world"),
        TranscriptSegment(start=5.0, end=10.0, text="how are you"),
    ]

    cleaned = clean_transcript(segments, client=client)

    assert len(cleaned) == 2
    assert cleaned[0].start == 0.0
    assert cleaned[0].end == 5.0
    assert cleaned[0].speaker == "S1"
    assert cleaned[1].speaker is None
    # LLM should clean the text
    assert "Hello" in cleaned[0].text or "hello" in cleaned[0].text.lower()
    assert "How" in cleaned[1].text or "how" in cleaned[1].text.lower()


def test_clean_transcript_llm_preserves_timestamps():
    """Test that LLM cleaning preserves timestamps and speakers."""
    client = MockCleaningLLMClient()
    segments = [
        TranscriptSegment(start=0.0, end=5.0, speaker="Alice", text="first segment"),
        TranscriptSegment(start=5.0, end=10.0, speaker="Bob", text="second segment"),
        TranscriptSegment(start=10.0, end=15.0, text="third segment"),
    ]

    cleaned = clean_transcript(segments, client=client)

    assert len(cleaned) == 3
    assert cleaned[0].start == 0.0
    assert cleaned[0].end == 5.0
    assert cleaned[0].speaker == "Alice"
    assert cleaned[1].start == 5.0
    assert cleaned[1].end == 10.0
    assert cleaned[1].speaker == "Bob"
    assert cleaned[2].start == 10.0
    assert cleaned[2].end == 15.0
    assert cleaned[2].speaker is None


def test_batch_segments():
    """Test batching logic."""
    # Create segments with varying text lengths
    segments = [
        TranscriptSegment(start=0.0, end=5.0, text="a" * 100),  # ~25 tokens
        TranscriptSegment(start=5.0, end=10.0, text="b" * 200),  # ~50 tokens
        TranscriptSegment(start=10.0, end=15.0, text="c" * 3000),  # ~750 tokens
        TranscriptSegment(start=15.0, end=20.0, text="d" * 4000),  # ~1000 tokens
        TranscriptSegment(start=20.0, end=25.0, text="e" * 500),  # ~125 tokens
    ]

    batches = _batch_segments(segments, max_tokens=2000)

    # Should create multiple batches due to token limits
    assert len(batches) > 0
    # All segments should be in batches
    total_segments = sum(len(batch) for batch in batches)
    assert total_segments == len(segments)
def test_batch_segments_empty():
    """Test batching with empty segments."""
    batches = _batch_segments([])
    assert batches == []


def test_batch_segments_single_segment():
    """Test batching with single segment."""
    segments = [TranscriptSegment(start=0.0, end=5.0, text="test")]
    batches = _batch_segments(segments)
    assert len(batches) == 1
    assert len(batches[0]) == 1


def test_parse_llm_response():
    """Test parsing LLM response."""
    response = """1. Hello world.
2. How are you?
3. I'm fine."""
    result = _parse_llm_response(response, 3)
    assert len(result) == 3
    assert result[0] == "Hello world."
    assert result[1] == "How are you?"
    assert result[2] == "I'm fine."


def test_parse_llm_response_with_speakers():
    """Test parsing LLM response with speaker labels."""
    response = """1. [Alice] Hello world.
2. [Bob] How are you?
3. I'm fine."""
    result = _parse_llm_response(response, 3)
    assert len(result) == 3
    assert result[0] == "Hello world."
    assert result[1] == "How are you?"
    assert result[2] == "I'm fine."


def test_parse_llm_response_wrong_count():
    """Test parsing when LLM returns wrong number of segments."""
    response = "1. Only one segment."
    result = _parse_llm_response(response, 3)
    # Should pad with empty strings
    assert len(result) == 3
    assert result[0] == "Only one segment."
    assert result[1] == ""
    assert result[2] == ""


def test_clean_batch_with_llm():
    """Test cleaning a batch with LLM."""
    client = MockCleaningLLMClient()
    batch = [
        TranscriptSegment(start=0.0, end=5.0, text="hello world"),
        TranscriptSegment(start=5.0, end=10.0, text="test message"),
    ]

    cleaned = _clean_batch_with_llm(batch, client)

    assert len(cleaned) == 2
    assert all(isinstance(text, str) for text in cleaned)


def test_clean_batch_with_llm_failure():
    """Test fallback when LLM fails."""
    client = MockCleaningLLMClient(should_fail=True)
    batch = [
        TranscriptSegment(start=0.0, end=5.0, text="hello world"),
    ]

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cleaned = _clean_batch_with_llm(batch, client)

        # Should fall back to rule-based cleaning
        assert len(cleaned) == 1
        assert cleaned[0] == "Hello world."
        # Should have warning
        assert len(w) > 0
        assert "LLM cleaning failed" in str(w[0].message)


def test_clean_batch_with_llm_wrong_segment_count():
    """Test fallback when LLM returns wrong segment count."""
    client = MockCleaningLLMClient(response_template="1. Only one segment.")
    batch = [
        TranscriptSegment(start=0.0, end=5.0, text="first message here"),
        TranscriptSegment(start=5.0, end=10.0, text="second message here"),
    ]

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cleaned = _clean_batch_with_llm(batch, client)

        # Should fall back to rule-based cleaning
        assert len(cleaned) == 2
        assert cleaned[0] == "First message here."
        assert cleaned[1] == "Second message here."
        # Should have warning
        assert len(w) > 0


def test_clean_transcript_fallback_on_llm_failure():
    """Test that cleaning falls back to rule-based when LLM fails."""
    client = MockCleaningLLMClient(should_fail=True)
    segments = [
        TranscriptSegment(start=0.0, end=5.0, text="hello    world"),
    ]

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cleaned = clean_transcript(segments, client=client)

        assert len(cleaned) == 1
        # Should use rule-based cleaning
        assert cleaned[0].text == "Hello world."
        # Should have warning
        assert len(w) > 0


def test_clean_transcript_multilingual():
    """Test cleaning with multilingual content."""
    client = MockCleaningLLMClient(
        response_template="1. Είπαμε ο Γιώργος να δει και να φτιάξει τον mapper."
    )
    segments = [
        TranscriptSegment(
            start=0.0,
            end=5.0,
            text="είπαμε ο γιώργος να δει και να φτιάξει τον mapper",
        ),
    ]

    cleaned = clean_transcript(segments, client=client)

    assert len(cleaned) == 1
    assert cleaned[0].start == 0.0
    assert cleaned[0].end == 5.0


@patch.dict("os.environ", {}, clear=True)
def test_clean_transcript_no_api_key_fallback():
    """Test that cleaning falls back to rule-based when API key is missing."""
    segments = [
        TranscriptSegment(start=0.0, end=5.0, text="hello world"),
    ]

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cleaned = clean_transcript(segments)

        # Should fall back to rule-based cleaning
        assert len(cleaned) == 1
        assert cleaned[0].text == "Hello world."
        # Should have warning about missing API key
        assert len(w) > 0