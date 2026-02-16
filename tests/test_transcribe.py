"""Tests for transcription module."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from meetbrief.transcribe import transcribe
from meetbrief.models import TranscriptSegment
from tests.test_client import MockTranscriptionClient


def test_transcribe_file_not_found():
    """Test error when audio file doesn't exist."""
    with pytest.raises(FileNotFoundError):
        transcribe(Path("nonexistent.wav"))


def test_transcribe_with_mock_client():
    """Test transcription with mock client."""
    client = MockTranscriptionClient()

    with patch("pathlib.Path.exists", return_value=True):
        with patch("pathlib.Path.stat") as mock_stat:
            mock_stat.return_value = Mock(st_size=1024 * 1024)  # 1MB

            segments = transcribe(Path("test.wav"), client=client)

            assert len(segments) == 2
            assert segments[0].text == "Hello world"
            assert segments[1].text == "How are you?"


def test_transcribe_file_too_large():
    """Test error when file exceeds size limit."""
    client = MockTranscriptionClient()

    with patch("pathlib.Path.exists", return_value=True):
        with patch("pathlib.Path.stat") as mock_stat:
            # 30MB file (exceeds 25MB limit)
            mock_stat.return_value = Mock(st_size=30 * 1024 * 1024)

            with pytest.raises(ValueError, match="exceeds 25MB"):
                transcribe(Path("large.wav"), client=client)
