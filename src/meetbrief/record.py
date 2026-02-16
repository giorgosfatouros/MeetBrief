"""Audio recording module for capturing system audio on Linux and macOS."""

import platform
import signal
import subprocess
import time
from pathlib import Path
from typing import List, Optional, Tuple


class RecordingError(Exception):
    """Exception raised for recording-related errors."""

    pass


def detect_platform() -> str:
    """Detect the current platform.

    Returns:
        Platform identifier: 'linux' or 'darwin' (macOS)

    Raises:
        RecordingError: If platform is not supported
    """
    system = platform.system().lower()
    if system == "linux":
        return "linux"
    elif system == "darwin":
        return "darwin"
    else:
        raise RecordingError(
            f"Unsupported platform: {system}. Only Linux and macOS are supported."
        )


def detect_audio_system() -> str:
    """Detect the available audio system on the current platform.

    Returns:
        Audio system identifier: 'pulse', 'pipewire', or 'avfoundation'

    Raises:
        RecordingError: If no supported audio system is found
    """
    plat = detect_platform()

    if plat == "linux":
        # Check for PipeWire (which provides PulseAudio compatibility)
        try:
            result = subprocess.run(
                ["pactl", "info"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                # Check if it's PipeWire or PulseAudio
                if "PipeWire" in result.stdout:
                    return "pipewire"
                else:
                    return "pulse"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        raise RecordingError(
            "No supported audio system found. Please install:\n"
            "  - pulseaudio-utils (for PulseAudio)\n"
            "  - pipewire-pulse (for PipeWire)\n"
            "  On Ubuntu/Debian: sudo apt install pulseaudio-utils\n"
            "  On Fedora: sudo dnf install pipewire-pulse"
        )

    elif plat == "darwin":
        # Check if ffmpeg supports AVFoundation
        try:
            result = subprocess.run(
                ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                capture_output=True,
                text=True,
                timeout=5,
            )
            # Even if it errors, if it lists devices, AVFoundation is available
            if "AVFoundation" in result.stderr or "audio devices" in result.stderr.lower():
                return "avfoundation"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        raise RecordingError(
            "AVFoundation not available. Please ensure ffmpeg is installed:\n"
            "  brew install ffmpeg"
        )

    raise RecordingError(f"Unsupported platform: {plat}")


def list_audio_sources() -> List[Tuple[str, str]]:
    """List available audio sources for recording.

    Returns:
        List of tuples (source_id, description) for available audio sources

    Raises:
        RecordingError: If sources cannot be listed
    """
    audio_system = detect_audio_system()

    if audio_system in ("pulse", "pipewire"):
        return _list_pulse_sources()
    elif audio_system == "avfoundation":
        return _list_avfoundation_sources()

    raise RecordingError(f"Unsupported audio system: {audio_system}")


def _list_pulse_sources() -> List[Tuple[str, str]]:
    """List PulseAudio/PipeWire sources.

    Returns:
        List of tuples (source_id, description)
    """
    try:
        result = subprocess.run(
            ["pactl", "list", "sources", "short"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        raise RecordingError(
            f"Failed to list audio sources: {e}\n"
            "Make sure pulseaudio-utils or pipewire-pulse is installed."
        ) from e

    sources = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            source_id = parts[0].strip()
            description = parts[1].strip() if len(parts) > 1 else source_id
            # Only include monitor sources (for system audio)
            if ".monitor" in source_id or "monitor" in description.lower():
                sources.append((source_id, description))

    if not sources:
        raise RecordingError(
            "No monitor sources found. You may need to create a loopback:\n"
            "  pactl load-module module-loopback"
        )

    return sources


def _list_avfoundation_sources() -> List[Tuple[str, str]]:
    """List AVFoundation audio devices.

    Returns:
        List of tuples (device_index, description)
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        raise RecordingError(
            "Failed to list audio devices. Make sure ffmpeg is installed:\n"
            "  brew install ffmpeg"
        ) from e

    sources = []
    in_audio_section = False
    for line in result.stderr.split("\n"):
        line = line.strip()
        if "audio devices" in line.lower():
            in_audio_section = True
            continue
        if in_audio_section and "]" in line:
            # Parse device line: [index] "Device Name"
            if "[" in line and "]" in line:
                try:
                    start_idx = line.index("[") + 1
                    end_idx = line.index("]")
                    device_index = line[start_idx:end_idx].strip()
                    # Extract device name (between quotes)
                    if '"' in line:
                        name_start = line.index('"') + 1
                        name_end = line.rindex('"')
                        device_name = line[name_start:name_end]
                        sources.append((device_index, device_name))
                except (ValueError, IndexError):
                    continue

    if not sources:
        raise RecordingError(
            "No audio devices found. You may need to install BlackHole:\n"
            "  https://github.com/ExistentialAudio/BlackHole"
        )

    return sources


def find_monitor_source() -> str:
    """Find the default monitor source for system audio recording.

    Returns:
        Source identifier for the default monitor source

    Raises:
        RecordingError: If no monitor source is found
    """
    audio_system = detect_audio_system()

    if audio_system in ("pulse", "pipewire"):
        sources = _list_pulse_sources()
        if not sources:
            raise RecordingError("No monitor sources found")
        # Prefer default monitor or first available
        for source_id, description in sources:
            if "default" in source_id.lower() or "default" in description.lower():
                return source_id
        return sources[0][0]

    elif audio_system == "avfoundation":
        # For macOS, we'll use the first available audio device
        # User can specify a different one if needed
        sources = _list_avfoundation_sources()
        if not sources:
            raise RecordingError("No audio devices found")
        # Prefer BlackHole if available (common for system audio capture)
        for device_index, device_name in sources:
            if "blackhole" in device_name.lower():
                return device_index
        return sources[0][0]

    raise RecordingError(f"Unsupported audio system: {audio_system}")


def record_system_audio(
    output_path: Path,
    source: Optional[str] = None,
    duration: Optional[int] = None,
    sample_rate: int = 16000,
    channels: int = 1,
) -> Path:
    """Record system audio to a file.

    Args:
        output_path: Path where the recording will be saved
        source: Optional audio source identifier (auto-detected if not provided)
        duration: Optional duration in seconds (None = record until stopped)
        sample_rate: Audio sample rate (default: 16kHz for Whisper)
        channels: Number of audio channels (default: 1 = mono)

    Returns:
        Path to the recorded audio file

    Raises:
        RecordingError: If recording fails
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    audio_system = detect_audio_system()

    if audio_system in ("pulse", "pipewire"):
        return _record_pulse(output_path, source, duration, sample_rate, channels)
    elif audio_system == "avfoundation":
        return _record_avfoundation(output_path, source, duration, sample_rate, channels)

    raise RecordingError(f"Unsupported audio system: {audio_system}")


def _record_pulse(
    output_path: Path,
    source: Optional[str],
    duration: Optional[int],
    sample_rate: int,
    channels: int,
) -> Path:
    """Record using PulseAudio/PipeWire.

    Args:
        output_path: Output file path
        source: Audio source (auto-detected if None)
        duration: Optional duration in seconds
        sample_rate: Sample rate
        channels: Number of channels

    Returns:
        Path to recorded file
    """
    if source is None:
        source = find_monitor_source()

    cmd = [
        "ffmpeg",
        "-f",
        "pulse",
        "-i",
        source,
        "-ar",
        str(sample_rate),
        "-ac",
        str(channels),
        "-y",  # overwrite
        str(output_path),
    ]

    if duration:
        cmd.extend(["-t", str(duration)])

    return _run_recording(cmd, output_path, duration is None)


def _record_avfoundation(
    output_path: Path,
    source: Optional[str],
    duration: Optional[int],
    sample_rate: int,
    channels: int,
) -> Path:
    """Record using AVFoundation (macOS).

    Args:
        output_path: Output file path
        source: Audio device index (auto-detected if None)
        duration: Optional duration in seconds
        sample_rate: Sample rate
        channels: Number of channels

    Returns:
        Path to recorded file
    """
    if source is None:
        source = find_monitor_source()

    # AVFoundation format: ":audio_device_index"
    # The colon prefix indicates we're only recording audio (no video)
    cmd = [
        "ffmpeg",
        "-f",
        "avfoundation",
        "-i",
        f":{source}",
        "-ar",
        str(sample_rate),
        "-ac",
        str(channels),
        "-y",  # overwrite
        str(output_path),
    ]

    if duration:
        cmd.extend(["-t", str(duration)])

    return _run_recording(cmd, output_path, duration is None)


def _run_recording(
    cmd: List[str], output_path: Path, wait_for_interrupt: bool
) -> Path:
    """Run the recording command and handle interruption.

    Args:
        cmd: ffmpeg command to execute
        output_path: Output file path
        wait_for_interrupt: If True, wait for Ctrl+C; otherwise run for duration

    Returns:
        Path to recorded file

    Raises:
        RecordingError: If recording fails
    """
    try:
        if wait_for_interrupt:
            # Polling loop + SIGINT handler so Ctrl+C is handled even when run
            # from pipx or a different terminal (avoids blocking in wait() which
            # may not be interrupted in some environments).
            stderr = None
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            sigint_received = False

            def _handle_sigint(signum: int, frame: object) -> None:
                nonlocal sigint_received
                sigint_received = True

            old_sigint = signal.signal(signal.SIGINT, _handle_sigint)
            try:
                while process.poll() is None and not sigint_received:
                    time.sleep(0.25)
            finally:
                signal.signal(signal.SIGINT, old_sigint)

            if sigint_received:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                if output_path.exists() and output_path.stat().st_size > 0:
                    return output_path
                raise KeyboardInterrupt()
        else:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = process.communicate()

        if process.returncode != 0 and process.returncode != -signal.SIGINT:
            err_bytes = stderr if not wait_for_interrupt else None
            error_msg = (
                err_bytes.decode("utf-8", errors="ignore") if err_bytes else "Unknown error"
            )
            raise RecordingError(
                f"Recording failed with exit code {process.returncode}:\n{error_msg}"
            )

    except FileNotFoundError:
        raise RecordingError(
            "ffmpeg not found. Please install ffmpeg:\n"
            "  Linux: sudo apt install ffmpeg\n"
            "  macOS: brew install ffmpeg"
        )
    except Exception as e:
        raise RecordingError(f"Recording failed: {e}") from e

    if not output_path.exists():
        raise RecordingError(f"Recording file was not created: {output_path}")

    return output_path
