"""Client abstraction layer for LLM and transcription providers."""

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Dict, Any

from openai import OpenAI

from .models import TranscriptSegment


class TranscriptionClient(ABC):
    """Abstract interface for transcription providers."""

    @abstractmethod
    def transcribe_audio(
        self, audio_path: Path, language: Optional[str] = None
    ) -> List[TranscriptSegment]:
        """Transcribe audio file to text segments with timestamps.

        Args:
            audio_path: Path to audio file
            language: Optional language code (e.g., 'en', 'es')

        Returns:
            List of transcript segments with timestamps
        """
        pass

    @abstractmethod
    def supports_language(self, language: str) -> bool:
        """Check if the client supports a given language.

        Args:
            language: Language code to check

        Returns:
            True if language is supported
        """
        pass


class LLMClient(ABC):
    """Abstract interface for LLM providers."""

    @abstractmethod
    def generate_structured_output(
        self, prompt: str, schema: Dict[str, Any], model: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate structured output matching a JSON schema.

        Args:
            prompt: Input prompt/text
            schema: JSON schema definition
            model: Optional model name override

        Returns:
            Dictionary matching the schema
        """
        pass

    @abstractmethod
    def chat_completion(
        self, messages: List[Dict[str, str]], model: Optional[str] = None, **kwargs
    ) -> str:
        """Generate chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Optional model name override
            **kwargs: Additional model parameters

        Returns:
            Generated text response
        """
        pass


class OpenAIClient(TranscriptionClient, LLMClient):
    """OpenAI implementation of both transcription and LLM clients."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        transcription_model: str = "whisper-1",
        llm_model: str = "gpt-4o-mini",
    ):
        """Initialize OpenAI client.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            transcription_model: Model for transcription (whisper-1 or gpt-4o-transcribe)
            llm_model: Model for LLM tasks (gpt-4o-mini or gpt-4o)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key required. Set OPENAI_API_KEY environment variable."
            )

        self.client = OpenAI(api_key=self.api_key)
        self.transcription_model = transcription_model
        self.llm_model = llm_model

    def transcribe_audio(
        self, audio_path: Path, language: Optional[str] = None
    ) -> List[TranscriptSegment]:
        """Transcribe audio using OpenAI Audio API.

        Args:
            audio_path: Path to audio file
            language: Optional language code

        Returns:
            List of transcript segments with timestamps
        """
        with open(audio_path, "rb") as audio_file:
            transcript = self.client.audio.transcriptions.create(
                model=self.transcription_model,
                file=audio_file,
                response_format="verbose_json",
                language=language,
            )

        segments = []
        # OpenAI SDK v2.0 returns objects, not dicts
        # Check if we have segments (for whisper-1 with verbose_json)
        transcript_segments = getattr(transcript, "segments", None)
        if transcript_segments:
            # verbose_json format with segments
            for seg in transcript_segments:
                # Access attributes directly since seg is an object
                start = float(getattr(seg, "start", 0.0))
                end = float(getattr(seg, "end", 0.0))
                speaker = getattr(seg, "speaker", None)
                text = getattr(seg, "text", "")
                
                segments.append(
                    TranscriptSegment(
                        start=start,
                        end=end,
                        speaker=speaker,
                        text=text,
                    )
                )
        else:
            # Fallback: single segment with full text
            text = getattr(transcript, "text", str(transcript))
            duration = float(getattr(transcript, "duration", 0.0))
            segments.append(
                TranscriptSegment(
                    start=0.0,
                    end=duration,
                    text=text,
                )
            )

        return segments

    def supports_language(self, language: str) -> bool:
        """OpenAI Whisper supports many languages."""
        # Whisper supports 99+ languages
        return True

    def generate_structured_output(
        self, prompt: str, schema: Dict[str, Any], model: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate structured output using OpenAI with JSON Schema.

        Args:
            prompt: Input prompt/text
            schema: JSON schema definition
            model: Optional model name override

        Returns:
            Dictionary matching the schema
        """
        model_name = model or self.llm_model

        response = self.client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that extracts structured information from meeting transcripts. Always respond with valid JSON matching the provided schema.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "meeting_report",
                    "strict": True,
                    "schema": schema,
                },
            },
        )

        import json

        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response from LLM")
        
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response from LLM: {e}") from e

    def chat_completion(
        self, messages: List[Dict[str, str]], model: Optional[str] = None, **kwargs
    ) -> str:
        """Generate chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Optional model name override
            **kwargs: Additional model parameters

        Returns:
            Generated text response
        """
        model_name = model or self.llm_model

        response = self.client.chat.completions.create(
            model=model_name, messages=messages, **kwargs
        )

        return response.choices[0].message.content
