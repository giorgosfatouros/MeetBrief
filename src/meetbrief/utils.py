"""Utility functions for MeetBrief."""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def load_env(env_path: Optional[Path] = None) -> None:
    """Load environment variables from .env file.

    Args:
        env_path: Optional path to .env file (defaults to .env in current directory)
    """
    if env_path is None:
        env_path = Path(".env")

    if env_path.exists():
        # override=True ensures .env file takes precedence over existing env vars
        load_dotenv(env_path, override=True)


def ensure_output_dir(output_dir: Path) -> Path:
    """Ensure output directory exists.

    Args:
        output_dir: Path to output directory

    Returns:
        Path object (created if needed)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def get_timestamp_subfolder() -> str:
    """Generate timestamp-based subfolder name.

    Returns:
        Timestamp string in format YYYY-MM-DD-HH-MM-SS
    """
    return datetime.now().strftime("%Y-%m-%d-%H-%M-%S")


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted duration string (e.g., "1h 23m" or "45m")
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)

    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"
