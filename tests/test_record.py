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
    """Test recording with PulseAudio (system only, no mic)."""
    mock_detect.return_value = "pulse"
    mock_find.return_value = "default.monitor"
    mock_run.return_value = Path("output.wav")

    output = record.record_system_audio(Path("output.wav"), include_mic=False)
    assert output == Path("output.wav")
    mock_run.assert_called_once()


@patch("meetbrief.record.detect_audio_system")
@patch("meetbrief.record.find_monitor_source")
@patch("meetbrief.record._run_recording")
def test_record_system_audio_avfoundation(mock_run, mock_find, mock_detect):
    """Test recording with AVFoundation (system only, no mic)."""
    mock_detect.return_value = "avfoundation"
    mock_find.return_value = "1"
    mock_run.return_value = Path("output.wav")

    output = record.record_system_audio(Path("output.wav"), include_mic=False)
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
    """Test listing audio sources for PulseAudio (monitors + mics with labels)."""
    mock_detect.return_value = "pulse"

    with patch("meetbrief.record._list_pulse_sources_with_kind") as mock_list:
        mock_list.return_value = [("0", "default.monitor (system)")]
        sources = record.list_audio_sources()
        assert len(sources) == 1
        assert sources[0][1] == "default.monitor (system)"


@patch("meetbrief.record.detect_audio_system")
def test_list_audio_sources_avfoundation(mock_detect):
    """Test listing audio sources for AVFoundation."""
    mock_detect.return_value = "avfoundation"

    with patch("meetbrief.record._list_avfoundation_sources") as mock_list:
        mock_list.return_value = [("0", "Built-in Microphone")]
        sources = record.list_audio_sources()
        assert len(sources) == 1


@patch("meetbrief.record.detect_audio_system")
@patch("subprocess.run")
def test_find_default_microphone_source_pulse(mock_run, mock_detect):
    """Test finding default microphone on Pulse (first input when default is monitor)."""
    mock_detect.return_value = "pulse"
    mock_run.return_value = MagicMock(returncode=0, stdout="alsa_output.default.monitor\n")

    with patch("meetbrief.record._list_pulse_input_sources") as mock_inputs:
        mock_inputs.return_value = [("2", "alsa_input.usb-Mic.analog-mono")]
        source = record.find_default_microphone_source()
        assert source == "2"


@patch("meetbrief.record.detect_audio_system")
@patch("subprocess.run")
def test_find_default_microphone_source_pulse_uses_default_if_input(mock_run, mock_detect):
    """Test finding default microphone when pactl default is already an input."""
    mock_detect.return_value = "pulse"
    mock_run.return_value = MagicMock(returncode=0, stdout="alsa_input.usb-Mic.analog-mono\n")

    with patch("meetbrief.record._list_pulse_input_sources") as mock_inputs:
        mock_inputs.return_value = [
            ("1", "other"),
            ("2", "alsa_input.usb-Mic.analog-mono"),
        ]
        source = record.find_default_microphone_source()
        # pactl get-default-source returns the source name; we match by name
        assert source == "2"


@patch("meetbrief.record.detect_audio_system")
@patch("meetbrief.record.find_monitor_source")
@patch("meetbrief.record.find_default_microphone_source")
@patch("meetbrief.record._run_recording")
def test_record_system_audio_pulse_include_mic(mock_run, mock_find_mic, mock_find_monitor, mock_detect):
    """Test that include_mic=True builds ffmpeg command with two pulse inputs and amix."""
    mock_detect.return_value = "pulse"
    mock_find_monitor.return_value = "monitor.source"
    mock_find_mic.return_value = "mic.source"
    mock_run.return_value = Path("output.wav")

    record.record_system_audio(Path("output.wav"), include_mic=True)

    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "ffmpeg"
    # Two pulse inputs: -f pulse -i <source> appears twice
    assert cmd.count("-i") == 2
    assert "amix=inputs=2:duration=longest" in " ".join(cmd)
    assert "-filter_complex" in cmd
    assert "[aout]" in cmd


@patch("meetbrief.record.detect_audio_system")
@patch("meetbrief.record.find_monitor_source")
@patch("meetbrief.record._run_recording")
def test_record_system_audio_pulse_no_include_mic(mock_run, mock_find, mock_detect):
    """Test that include_mic=False uses single source (unchanged behaviour)."""
    mock_detect.return_value = "pulse"
    mock_find.return_value = "default.monitor"
    mock_run.return_value = Path("output.wav")

    record.record_system_audio(Path("output.wav"), include_mic=False)

    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert "-f" in cmd and "pulse" in cmd and "-i" in cmd
    assert "amix" not in " ".join(cmd)
