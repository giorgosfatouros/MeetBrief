"""Transcript cleaning module."""

import re
import warnings
from typing import List, Optional

from .client import LLMClient, OpenAIClient
from .models import TranscriptSegment


def clean_transcript(
    segments: List[TranscriptSegment], client: Optional[LLMClient] = None
) -> List[TranscriptSegment]:
    """Clean transcript segments, fixing ASR artifacts while preserving timestamps.

    Uses LLM-based cleaning with batch processing for efficiency. Falls back to
    rule-based cleaning if LLM is unavailable or fails.

    Args:
        segments: List of raw transcript segments
        client: Optional LLM client (creates OpenAIClient if not provided)

    Returns:
        List of cleaned transcript segments with preserved timestamps
    """
    if not segments:
        return segments

    # If no client provided, try to create one, but fall back to rule-based if it fails
    use_llm = True
    if client is None:
        try:
            client = OpenAIClient()
        except (ValueError, Exception) as e:
            warnings.warn(
                f"Could not initialize LLM client: {e}. Using rule-based cleaning.",
                UserWarning,
            )
            use_llm = False

    # Use LLM-based cleaning if client is available
    if use_llm and client is not None:
        try:
            # Batch segments for efficient processing
            batches = _batch_segments(segments)

            cleaned_segments = []

            for batch in batches:
                # Clean batch with LLM
                cleaned_texts = _clean_batch_with_llm(batch, client)

                # Reconstruct segments with cleaned text, preserving timestamps and speakers
                for i, seg in enumerate(batch):
                    if i < len(cleaned_texts):
                        cleaned_text = cleaned_texts[i]
                    else:
                        # Fallback if LLM didn't return enough segments
                        cleaned_text = _clean_text(seg.text)

                    cleaned_segments.append(
                        TranscriptSegment(
                            start=seg.start,
                            end=seg.end,
                            speaker=seg.speaker,
                            text=cleaned_text,
                        )
                    )

            return cleaned_segments

        except Exception as e:
            warnings.warn(
                f"LLM-based cleaning failed: {e}. Falling back to rule-based cleaning.",
                UserWarning,
            )

    # Fallback to rule-based cleaning
    cleaned_segments = []
    for seg in segments:
        cleaned_text = _clean_text(seg.text)
        cleaned_segments.append(
            TranscriptSegment(
                start=seg.start,
                end=seg.end,
                speaker=seg.speaker,
                text=cleaned_text,
            )
        )

    return cleaned_segments


def _batch_segments(
    segments: List[TranscriptSegment], max_tokens: int = 2000
) -> List[List[TranscriptSegment]]:
    """Group transcript segments into batches by approximate token count.

    Args:
        segments: List of transcript segments
        max_tokens: Maximum tokens per batch (default: 2000)

    Returns:
        List of segment batches
    """
    if not segments:
        return []

    # Estimate tokens: ~4 characters per token
    chars_per_token = 4
    max_chars = max_tokens * chars_per_token

    batches = []
    current_batch = []
    current_chars = 0

    for seg in segments:
        # Estimate segment size (text length)
        seg_chars = len(seg.text)

        # If adding this segment would exceed limit and we have a batch, start new batch
        if current_chars + seg_chars > max_chars and current_batch:
            batches.append(current_batch)
            current_batch = [seg]
            current_chars = seg_chars
        else:
            current_batch.append(seg)
            current_chars += seg_chars

    # Add final batch if it has segments
    if current_batch:
        batches.append(current_batch)

    return batches


def _clean_batch_with_llm(
    batch: List[TranscriptSegment], client: LLMClient
) -> List[str]:
    """Clean a batch of transcript segments using LLM.

    Args:
        batch: List of transcript segments to clean
        client: LLM client for processing

    Returns:
        List of cleaned text strings (one per segment)
    """
    if not batch:
        return []

    # Format segments for LLM input
    # Use numbered format to preserve segment order
    segment_texts = []
    for i, seg in enumerate(batch, 1):
        if seg.speaker:
            segment_texts.append(f"{i}. [{seg.speaker}] {seg.text}")
        else:
            segment_texts.append(f"{i}. {seg.text}")

    input_text = "\n".join(segment_texts)

    prompt = f"""Clean the following transcript segments from an automatic speech recognition (ASR) system. Fix common ASR artifacts while preserving the original meaning and context.

Instructions:
- Fix punctuation and spacing errors
- Correct capitalization (sentence starts, proper nouns)
- Remove filler words and artifacts (um, uh, etc.) if they don't add meaning
- Preserve the original meaning and context
- Handle multilingual content appropriately
- Maintain natural flow and readability

Return the cleaned text in the same format: one segment per line, numbered 1, 2, 3, etc.
For segments with speaker labels, preserve the format: "N. [Speaker] text"
For segments without speaker labels, use format: "N. text"

Transcript segments to clean:
{input_text}

Cleaned transcript:"""

    try:
        response = client.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that cleans transcript text from ASR systems, fixing artifacts while preserving meaning.",
                },
                {"role": "user", "content": prompt},
            ]
        )

        # Parse response to extract cleaned segments
        cleaned_segments = _parse_llm_response(response, len(batch))

        # If parsing failed, returned wrong count, or segments are empty, fall back to rule-based
        if len(cleaned_segments) != len(batch) or not all(
            seg.strip() for seg in cleaned_segments
        ):
            warnings.warn(
                f"LLM returned {len(cleaned_segments)} segments (expected {len(batch)}), "
                "or segments are empty. Falling back to rule-based cleaning for this batch.",
                UserWarning,
            )
            return [_clean_text(seg.text) for seg in batch]

        return cleaned_segments

    except Exception as e:
        warnings.warn(
            f"LLM cleaning failed: {e}. Falling back to rule-based cleaning for this batch.",
            UserWarning,
        )
        return [_clean_text(seg.text) for seg in batch]


def _parse_llm_response(response: str, expected_count: int) -> List[str]:
    """Parse LLM response to extract cleaned segment texts.

    Args:
        response: LLM response text
        expected_count: Expected number of segments

    Returns:
        List of cleaned text strings
    """
    lines = response.strip().split("\n")
    cleaned_segments = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Match patterns like "1. text" or "1. [Speaker] text"
        # Remove leading number and optional speaker label
        match = re.match(r"^\d+\.\s*(?:\[[^\]]+\]\s*)?(.+)$", line)
        if match:
            cleaned_text = match.group(1).strip()
            if cleaned_text:
                cleaned_segments.append(cleaned_text)

    # If we got fewer segments than expected, pad with empty strings
    # (will trigger fallback in caller)
    while len(cleaned_segments) < expected_count:
        cleaned_segments.append("")

    # If we got more, truncate
    return cleaned_segments[:expected_count]


def _clean_text(text: str) -> str:
    """Apply rule-based text cleaning.

    Args:
        text: Raw text to clean

    Returns:
        Cleaned text
    """
    # Basic cleaning rules
    cleaned = text.strip()

    # Fix common ASR artifacts
    # Remove excessive spaces
    cleaned = re.sub(r"\s+", " ", cleaned)

    # Fix capitalization at sentence start
    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]

    # Ensure sentence ends with punctuation if it looks like a sentence
    if cleaned and cleaned[-1] not in ".!?":
        # Only add period if it's a complete sentence (has verb-like words)
        # Simple heuristic: if it's longer than 10 chars, likely a sentence
        if len(cleaned) > 10:
            cleaned += "."

    return cleaned
