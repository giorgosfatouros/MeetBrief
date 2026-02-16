"""Audio chunking module for splitting large audio files."""

import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple

from .ingest import OPENAI_LIMIT_MB, MAX_FILE_SIZE_MB


def get_audio_duration(audio_path: Path) -> float:
    """Get audio duration in seconds using ffprobe.

    Args:
        audio_path: Path to audio file

    Returns:
        Duration in seconds

    Raises:
        RuntimeError: If ffprobe fails
    """
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError) as e:
        raise RuntimeError(f"Failed to get audio duration: {e}") from e
    except FileNotFoundError:
        raise RuntimeError(
            "ffprobe not found. Please install ffmpeg (which includes ffprobe)."
        )


def chunk_audio(
    audio_path: Path, target_size_mb: float = MAX_FILE_SIZE_MB
) -> List[Tuple[Path, float]]:
    """Split audio file into chunks based on target file size.

    Args:
        audio_path: Path to audio file to chunk
        target_size_mb: Target size per chunk in MB (default: 20MB)

    Returns:
        List of tuples (chunk_path, start_time_in_seconds)

    Raises:
        FileNotFoundError: If audio file doesn't exist
        RuntimeError: If ffmpeg is not available or chunking fails
    """
    audio_path = Path(audio_path)

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    # Get audio duration
    total_duration = get_audio_duration(audio_path)
    file_size_mb = audio_path.stat().st_size / (1024 * 1024)

    # Calculate how many chunks we need
    num_chunks = int((file_size_mb / target_size_mb) + 1)
    chunk_duration = total_duration / num_chunks

    chunks = []
    temp_dir = audio_path.parent

    for i in range(num_chunks):
        start_time = i * chunk_duration
        # For the last chunk, extend to end of file to avoid missing audio
        if i == num_chunks - 1:
            duration = total_duration - start_time
        else:
            duration = chunk_duration

        # Create temporary chunk file
        chunk_file = tempfile.NamedTemporaryFile(
            suffix=f".{audio_path.suffix}", delete=False, dir=temp_dir
        )
        chunk_path = Path(chunk_file.name)
        chunk_file.close()

        # Use ffmpeg to extract chunk
        # -ss: start time
        # -t: duration
        # -i: input file
        # -c copy: copy codec (no re-encoding, faster and preserves quality)
        # -y: overwrite output file
        cmd = [
            "ffmpeg",
            "-ss",
            str(start_time),
            "-t",
            str(duration),
            "-i",
            str(audio_path),
            "-c",
            "copy",
            "-y",
            str(chunk_path),
        ]

        try:
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            # Clean up any chunks created so far
            for chunk_file_path, _ in chunks:
                try:
                    chunk_file_path.unlink()
                except Exception:
                    pass
            raise RuntimeError(
                f"ffmpeg chunking failed: {e.stderr}\n"
                "Make sure ffmpeg is installed and accessible in PATH."
            ) from e
        except FileNotFoundError:
            # Clean up any chunks created so far
            for chunk_file_path, _ in chunks:
                try:
                    chunk_file_path.unlink()
                except Exception:
                    pass
            raise RuntimeError(
                "ffmpeg not found. Please install ffmpeg and ensure it's in PATH."
            )

        if chunk_path.exists():
            chunks.append((chunk_path, start_time))

    return chunks
