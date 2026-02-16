"""Tests for record module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from meetbrief import record


@patch("platform.system")
def test_detect_platform_linux(mock_system):
    """Test platform detection for Linux."""
    mock_system.return_value = "Linux"
    assert record.detect_platform() == "linux"


@patch("platform.system")
def test_detect_platform_darwin(mock_system):
    """Test platform detection for macOS."""
    mock_system.return_value = "Darwin"
    assert record.detect_platform() == "darwin"


@patch("platform.system")
def test_detect_platform_unsupported(mock_system):
    """Test error for unsupported platform."""
    mock_system.return_value = "Windows"
    with pytest.raises(record.RecordingError, match="Unsupported platform"):
        record.detect_platform()


@patch("meetbrief.record.detect_platform")
@patch("subprocess.run")
def test_detect_audio_system_pulse(mock_run, mock_platform):
    """Test detection of PulseAudio."""
    mock_platform.return_value = "linux"
    mock_run.return_value = MagicMock(returncode=0, stdout="Server Name: PulseAudio")
    
    assert record.detect_audio_system() == "pulse"


@patch("meetbrief.record.detect_platform")
@patch("subprocess.run")
def test_detect_audio_system_pipewire(mock_run, mock_platform):
    """Test detection of PipeWire."""
    mock_platform.return_value = "linux"
    mock_run.return_value = MagicMock(returncode=0, stdout="Server Name: PipeWire")
    
    assert record.detect_audio_system() == "pipewire"


@patch("meetbrief.record.detect_platform")
@patch("subprocess.run")
def test_detect_audio_system_avfoundation(mock_run, mock_platform):
    """Test detection of AVFoundation on macOS."""
    mock_platform.return_value = "darwin"
    mock_run.return_value = MagicMock(
        returncode=1,  # ffmpeg returns non-zero for list_devices
        stderr="[AVFoundation audio devices]"
    )
    
    assert record.detect_audio_system() == "avfoundation"


@patch("meetbrief.record.detect_platform")
@patch("subprocess.run")
def test_detect_audio_system_not_found(mock_run, mock_platform):
    """Test error when no audio system is found."""
    mock_platform.return_value = "linux"
    mock_run.side_effect = FileNotFoundError()
    
    with pytest.raises(record.RecordingError, match="No supported audio system"):
        record.detect_audio_system()


@patch("meetbrief.record.detect_audio_system")
@patch("subprocess.run")
def test_list_pulse_sources(mock_run, mock_detect):
    """Test listing PulseAudio sources."""
    mock_detect.return_value = "pulse"
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="0\talsa_output.pci-0000_00_1f.3.analog-stereo.monitor\tMonitor of Built-in Audio Analog Stereo\n"
    )
    
    sources = record._list_pulse_sources()
    assert len(sources) == 1
    assert sources[0][0] == "0"
    assert "monitor" in sources[0][1].lower()


@patch("meetbrief.record.detect_audio_system")
@patch("subprocess.run")
def test_list_avfoundation_sources(mock_run, mock_detect):
    """Test listing AVFoundation sources."""
    mock_detect.return_value = "avfoundation"
    mock_result = MagicMock()
    mock_result.stderr = "[AVFoundation audio devices]\n[0] \"Built-in Microphone\"\n[1] \"BlackHole 2ch\""
    mock_run.return_value = mock_result
    
    sources = record._list_avfoundation_sources()
    assert len(sources) >= 1
    assert any("blackhole" in name.lower() for _, name in sources)


@patch("meetbrief.record.detect_audio_system")
@patch("meetbrief.record._list_pulse_sources")
def test_find_monitor_source_pulse(mock_list, mock_detect):
    """Test finding monitor source on PulseAudio."""
    mock_detect.return_value = "pulse"
    mock_list.return_value = [
        ("0", "default.monitor"),
        ("1", "other.monitor")
    ]
    
    source = record.find_monitor_source()
    assert source == "0"  # Should prefer default


@patch("meetbrief.record.detect_audio_system")
@patch("meetbrief.record._list_avfoundation_sources")
def test_find_monitor_source_avfoundation(mock_list, mock_detect):
    """Test finding monitor source on AVFoundation."""
    mock_detect.return_value = "avfoundation"
    mock_list.return_value = [
        ("0", "Built-in Microphone"),
        ("1", "BlackHole 2ch")
    ]
    
    source = record.find_monitor_source()
    assert source == "1"  # Should prefer BlackHole


@patch("meetbrief.record.detect_audio_system")
@patch("meetbrief.record.find_monitor_source")
@patch("meetbrief.record._run_recording")
def test_record_system_audio_pulse(mock_run, mock_find, mock_detect):
    """Test recording with PulseAudio."""
    mock_detect.return_value = "pulse"
    mock_find.return_value = "default.monitor"
    mock_run.return_value = Path("output.wav")
    
    output = record.record_system_audio(Path("output.wav"))
    assert output == Path("output.wav")
    mock_run.assert_called_once()


@patch("meetbrief.record.detect_audio_system")
@patch("meetbrief.record.find_monitor_source")
@patch("meetbrief.record._run_recording")
def test_record_system_audio_avfoundation(mock_run, mock_find, mock_detect):
    """Test recording with AVFoundation."""
    mock_detect.return_value = "avfoundation"
    mock_find.return_value = "1"
    mock_run.return_value = Path("output.wav")
    
    output = record.record_system_audio(Path("output.wav"))
    assert output == Path("output.wav")
    mock_run.assert_called_once()


@patch("subprocess.Popen")
@patch("pathlib.Path.exists")
def test_run_recording_success(mock_exists, mock_popen):
    """Test successful recording execution."""
    mock_exists.return_value = True
    mock_process = MagicMock()
    mock_process.communicate.return_value = (b"", b"")
    mock_process.returncode = 0
    mock_popen.return_value = mock_process
    
    cmd = ["ffmpeg", "-f", "pulse", "-i", "default", "output.wav"]
    result = record._run_recording(cmd, Path("output.wav"), wait_for_interrupt=False)
    
    assert result == Path("output.wav")
    mock_popen.assert_called_once()


@patch("subprocess.Popen")
def test_run_recording_ffmpeg_not_found(mock_popen):
    """Test error when ffmpeg is not found."""
    mock_popen.side_effect = FileNotFoundError()
    
    cmd = ["ffmpeg", "-f", "pulse", "-i", "default", "output.wav"]
    with pytest.raises(record.RecordingError, match="ffmpeg not found"):
        record._run_recording(cmd, Path("output.wav"), wait_for_interrupt=False)


@patch("subprocess.Popen")
@patch("pathlib.Path.exists")
def test_run_recording_failure(mock_exists, mock_popen):
    """Test recording failure."""
    mock_exists.return_value = False
    mock_process = MagicMock()
    mock_process.communicate.return_value = (b"", b"Error message")
    mock_process.returncode = 1
    mock_popen.return_value = mock_process
    
    cmd = ["ffmpeg", "-f", "pulse", "-i", "default", "output.wav"]
    with pytest.raises(record.RecordingError, match="Recording failed"):
        record._run_recording(cmd, Path("output.wav"), wait_for_interrupt=False)


@patch("meetbrief.record.detect_audio_system")
def test_list_audio_sources_pulse(mock_detect):
    """Test listing audio sources for PulseAudio."""
    mock_detect.return_value = "pulse"
    
    with patch("meetbrief.record._list_pulse_sources") as mock_list:
        mock_list.return_value = [("0", "default.monitor")]
        sources = record.list_audio_sources()
        assert len(sources) == 1


@patch("meetbrief.record.detect_audio_system")
def test_list_audio_sources_avfoundation(mock_detect):
    """Test listing audio sources for AVFoundation."""
    mock_detect.return_value = "avfoundation"
    
    with patch("meetbrief.record._list_avfoundation_sources") as mock_list:
        mock_list.return_value = [("0", "Built-in Microphone")]
        sources = record.list_audio_sources()
        assert len(sources) == 1
