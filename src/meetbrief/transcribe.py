"""Transcription module using client abstraction."""

from pathlib import Path
from typing import List, Optional

from .chunk import chunk_audio
from .client import TranscriptionClient, OpenAIClient
from .ingest import OPENAI_LIMIT_MB
from .models import TranscriptSegment


def _merge_chunk_segments(segments: List[TranscriptSegment]) -> List[TranscriptSegment]:
    """Merge transcript segments from multiple chunks, ensuring chronological order.

    Args:
        segments: List of transcript segments from all chunks

    Returns:
        Merged and sorted list of segments
    """
    # Sort by start time
    sorted_segments = sorted(segments, key=lambda s: s.start)
    
    # Remove any overlapping or duplicate segments
    merged = []
    for seg in sorted_segments:
        if not merged:
            merged.append(seg)
        else:
            last_seg = merged[-1]
            # If segments overlap or are very close, merge them
            if seg.start <= last_seg.end + 0.1:  # 0.1 second tolerance
                # Merge overlapping segments
                merged_text = last_seg.text
                if seg.text and not merged_text.endswith(seg.text):
                    merged_text += " " + seg.text
                merged[-1] = TranscriptSegment(
                    start=last_seg.start,
                    end=max(last_seg.end, seg.end),
                    speaker=last_seg.speaker or seg.speaker,
                    text=merged_text.strip(),
                )
            else:
                merged.append(seg)
    
    return merged


def transcribe(
    audio_path: Path,
    language: Optional[str] = None,
    client: Optional[TranscriptionClient] = None,
) -> List[TranscriptSegment]:
    """Transcribe audio file to text segments.

    Args:
        audio_path: Path to normalized audio file
        language: Optional language code (e.g., 'en', 'es')
        client: Optional transcription client (creates OpenAIClient if not provided)

    Returns:
        List of transcript segments with timestamps

    Raises:
        FileNotFoundError: If audio file doesn't exist
        ValueError: If client doesn't support the language
    """
    audio_path = Path(audio_path)

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    # Create client if not provided
    if client is None:
        client = OpenAIClient()

    # Check language support if specified
    if language and not client.supports_language(language):
        raise ValueError(f"Language not supported: {language}")

    # Check file size (OpenAI limit is 25MB)
    file_size_mb = audio_path.stat().st_size / (1024 * 1024)
    
    if file_size_mb > OPENAI_LIMIT_MB:
        # File is too large, need to chunk it
        chunks = chunk_audio(audio_path)
        
        if not chunks:
            raise RuntimeError("Failed to create audio chunks")
        
        # Transcribe each chunk and collect segments
        all_segments = []
        chunk_files_to_cleanup = []
        
        try:
            for i, (chunk_path, start_time) in enumerate(chunks):
                chunk_files_to_cleanup.append(chunk_path)
                
                # Transcribe this chunk
                chunk_segments = client.transcribe_audio(chunk_path, language=language)
                
                # Adjust timestamps by adding chunk start time offset
                adjusted_segments = [
                    TranscriptSegment(
                        start=seg.start + start_time,
                        end=seg.end + start_time,
                        speaker=seg.speaker,
                        text=seg.text,
                    )
                    for seg in chunk_segments
                ]
                
                all_segments.extend(adjusted_segments)
            
            # Merge and sort segments by start time
            merged_segments = _merge_chunk_segments(all_segments)
            return merged_segments
            
        finally:
            # Clean up chunk files
            for chunk_file in chunk_files_to_cleanup:
                try:
                    if chunk_file.exists():
                        chunk_file.unlink()
                except Exception:
                    pass  # Ignore cleanup errors

    # File is small enough, transcribe directly
    segments = client.transcribe_audio(audio_path, language=language)

    return segments
