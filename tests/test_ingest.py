"""Tests for ingest module."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from meetbrief.ingest import normalize_audio, SUPPORTED_FORMATS


def test_supported_formats():
    """Test supported file formats."""
    assert ".mp3" in SUPPORTED_FORMATS
    assert ".mp4" in SUPPORTED_FORMATS
    assert ".wav" in SUPPORTED_FORMATS
    assert ".m4a" in SUPPORTED_FORMATS


def test_normalize_audio_file_not_found():
    """Test error when file doesn't exist."""
    with pytest.raises(FileNotFoundError):
        normalize_audio(Path("nonexistent.mp3"))


def test_normalize_audio_unsupported_format():
    """Test error for unsupported format."""
    with patch("pathlib.Path.exists", return_value=True):
        with pytest.raises(ValueError, match="Unsupported file format"):
            normalize_audio(Path("test.xyz"))


@patch("subprocess.run")
@patch("pathlib.Path.exists")
@patch("pathlib.Path.stat")
def test_normalize_audio_success(mock_stat, mock_exists, mock_run):
    """Test successful audio normalization."""
    mock_exists.return_value = True
    mock_stat.return_value = MagicMock(st_size=1000)
    mock_run.return_value = MagicMock(returncode=0)

    input_path = Path("test.mp3")
    output_path = Path("output.wav")

    result = normalize_audio(input_path, output_path)

    assert result == output_path
    mock_run.assert_called_once()
    assert "ffmpeg" in str(mock_run.call_args[0][0])


@patch("subprocess.run")
@patch("pathlib.Path.exists")
def test_normalize_audio_ffmpeg_not_found(mock_exists, mock_run):
    """Test error when ffmpeg is not found."""
    mock_exists.return_value = True
    mock_run.side_effect = FileNotFoundError()

    with pytest.raises(RuntimeError, match="ffmpeg not found"):
        normalize_audio(Path("test.mp3"))
