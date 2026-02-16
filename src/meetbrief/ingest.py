"""Audio ingestion and normalization module."""

import subprocess
import tempfile
from pathlib import Path
from typing import Optional


SUPPORTED_FORMATS = {".mp3", ".mp4", ".wav", ".m4a"}

# File size limit in MB (OpenAI limit is 25MB, use 20MB as safety margin)
MAX_FILE_SIZE_MB = 20
OPENAI_LIMIT_MB = 25


def compress_audio(input_path: Path, output_path: Optional[Path] = None) -> Path:
    """Compress audio file to MP3 format to reduce file size.

    Args:
        input_path: Path to input audio file (typically WAV)
        output_path: Optional output path (creates temp file if not provided)

    Returns:
        Path to compressed MP3 file

    Raises:
        FileNotFoundError: If input file doesn't exist
        RuntimeError: If ffmpeg is not available or conversion fails
    """
    input_path = Path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    # Create temporary file if output path not provided
    if output_path is None:
        temp_file = tempfile.NamedTemporaryFile(
            suffix=".mp3", delete=False, dir=input_path.parent
        )
        output_path = Path(temp_file.name)
        temp_file.close()

    output_path = Path(output_path)

    # ffmpeg command to compress audio to MP3
    # -i: input file
    # -acodec libmp3lame: use MP3 codec
    # -ab 128k: bitrate 128kbps (good quality for speech)
    # -ar 16000: sample rate 16kHz (maintains compatibility)
    # -ac 1: mono channel (maintains compatibility)
    # -y: overwrite output file
    cmd = [
        "ffmpeg",
        "-i",
        str(input_path),
        "-acodec",
        "libmp3lame",
        "-ab",
        "128k",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-y",
        str(output_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"ffmpeg compression failed: {e.stderr}\n"
            "Make sure ffmpeg is installed and accessible in PATH."
        ) from e
    except FileNotFoundError:
        import platform
        system = platform.system().lower()
        
        install_instructions = {
            "linux": "sudo apt update && sudo apt install -y ffmpeg  # Ubuntu/Debian\n"
                     "  or: sudo yum install -y ffmpeg  # RHEL/CentOS\n"
                     "  or: sudo dnf install -y ffmpeg  # Fedora",
            "darwin": "brew install ffmpeg  # macOS with Homebrew",
            "windows": "Download from https://ffmpeg.org/download.html or use: choco install ffmpeg",
        }
        
        instruction = install_instructions.get(system, 
            "See https://ffmpeg.org/download.html for installation instructions")
        
        raise RuntimeError(
            f"ffmpeg not found. Please install ffmpeg:\n"
            f"  {instruction}\n"
            f"  Or visit: https://ffmpeg.org/download.html"
        )

    if not output_path.exists():
        raise RuntimeError(f"Output file was not created: {output_path}")

    return output_path


def normalize_audio(input_path: Path, output_path: Optional[Path] = None) -> Path:
    """Normalize audio file to 16kHz mono WAV format.

    Args:
        input_path: Path to input audio/video file
        output_path: Optional output path (creates temp file if not provided)

    Returns:
        Path to normalized WAV file (or MP3 if compressed)

    Raises:
        ValueError: If file format is not supported
        FileNotFoundError: If input file doesn't exist
        RuntimeError: If ffmpeg is not available or conversion fails
    """
    input_path = Path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    suffix = input_path.suffix.lower()
    if suffix not in SUPPORTED_FORMATS:
        raise ValueError(
            f"Unsupported file format: {suffix}. Supported: {SUPPORTED_FORMATS}"
        )

    # Create temporary file if output path not provided
    if output_path is None:
        temp_file = tempfile.NamedTemporaryFile(
            suffix=".wav", delete=False, dir=input_path.parent
        )
        output_path = Path(temp_file.name)
        temp_file.close()

    output_path = Path(output_path)

    # ffmpeg command to normalize audio
    # -i: input file
    # -ar 16000: sample rate 16kHz
    # -ac 1: mono channel
    # -y: overwrite output file
    cmd = [
        "ffmpeg",
        "-i",
        str(input_path),
        "-ar",
        "16000",
        "-ac",
        "1",
        "-y",
        str(output_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"ffmpeg conversion failed: {e.stderr}\n"
            "Make sure ffmpeg is installed and accessible in PATH."
        ) from e
    except FileNotFoundError:
        import platform
        system = platform.system().lower()
        
        install_instructions = {
            "linux": "sudo apt update && sudo apt install -y ffmpeg  # Ubuntu/Debian\n"
                     "  or: sudo yum install -y ffmpeg  # RHEL/CentOS\n"
                     "  or: sudo dnf install -y ffmpeg  # Fedora",
            "darwin": "brew install ffmpeg  # macOS with Homebrew",
            "windows": "Download from https://ffmpeg.org/download.html or use: choco install ffmpeg",
        }
        
        instruction = install_instructions.get(system, 
            "See https://ffmpeg.org/download.html for installation instructions")
        
        raise RuntimeError(
            f"ffmpeg not found. Please install ffmpeg:\n"
            f"  {instruction}\n"
            f"  Or visit: https://ffmpeg.org/download.html"
        )

    if not output_path.exists():
        raise RuntimeError(f"Output file was not created: {output_path}")

    # Check file size after normalization
    # If it's a large WAV file (>20MB), try compressing to MP3
    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    if file_size_mb > MAX_FILE_SIZE_MB and output_path.suffix.lower() == ".wav":
        try:
            # Compress to MP3
            compressed_path = compress_audio(output_path)
            compressed_size_mb = compressed_path.stat().st_size / (1024 * 1024)
            
            # If compression helped, use the compressed file
            if compressed_size_mb < file_size_mb:
                # Clean up the original WAV file if it was temporary
                if output_path != input_path:
                    try:
                        output_path.unlink()
                    except Exception:
                        pass  # Ignore cleanup errors
                return compressed_path
            else:
                # Compression didn't help, keep original
                try:
                    compressed_path.unlink()
                except Exception:
                    pass  # Ignore cleanup errors
        except Exception:
            # If compression fails, continue with original file
            # The chunking logic in transcribe.py will handle it
            pass

    return output_path
