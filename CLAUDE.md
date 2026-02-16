# MeetBrief

CLI that turns meeting audio/video into transcripts and structured summaries. Pipeline: **Ingest → Transcribe → Clean → Enrich → Export**. Supports system audio recording; outputs go to timestamped folders under `reports/`.

## Overview

- **Input:** Audio/video files (mp3, mp4, wav, m4a) or system audio via `record`
- **Pipeline:** Ingest (ffmpeg normalize/compress) → Transcribe (Whisper, with chunking for large files) → Clean (LLM or rules, timestamps preserved) → Enrich (LLM chunk-and-merge for report) → Export (Markdown + JSON)
- **Output:** `reports/<timestamp>/` with `raw_transcript.json`, `clean_transcript.md`, `report.md`, `report.json`; recordings in `recordings/` (git-ignored)
- **Compatibility:** Python 3.12+, ffmpeg, OpenAI API key. Optional for recording: Linux pulseaudio-utils or pipewire-pulse; macOS BlackHole for isolated system audio.

## Architecture and Data Flow

- **CLI** (`src/meetbrief/cli.py`): `run`, `transcribe`, `summarize`, `record`. Uses `utils.load_env()`, Rich progress; creates timestamped output subdir via `utils.get_timestamp_subfolder()`.
- **Pipeline:** `run` calls ingest → transcribe → clean → enrich → export in order. Temp normalized audio is removed after transcribe. Large files (>25 MB) are chunked in ingest/transcribe via `src/meetbrief/chunk.py`.
- **Providers:** `src/meetbrief/client.py` defines `TranscriptionClient`, `LLMClient`, and `OpenAIClient` (single implementation). Transcribe uses the transcription client; clean and enrich use the LLM client.
- **Recording:** `src/meetbrief/record.py` handles system audio (Pulse on Linux, AVFoundation on macOS). `record` command can auto-run the pipeline after recording.

## Project Structure

```
MeetBrief/
├── pyproject.toml
├── README.md
├── src/
│   └── meetbrief/
│       ├── __init__.py
│       ├── cli.py          # Typer CLI: run, transcribe, summarize, record
│       ├── client.py       # TranscriptionClient, LLMClient, OpenAIClient
│       ├── ingest.py       # normalize_audio, compress_audio, OPENAI_LIMIT_MB
│       ├── chunk.py        # get_audio_duration, chunk_audio (large files)
│       ├── transcribe.py   # transcribe() using client, chunking
│       ├── clean.py        # clean_transcript (LLM batches + rule fallback)
│       ├── enrich.py       # enrich_transcript (chunk + merge reports)
│       ├── export.py       # export_markdown, export_json, export_raw_transcript, export_clean_transcript
│       ├── models.py       # Pydantic schemas
│       ├── record.py       # System audio recording (Pulse/AVFoundation)
│       └── utils.py        # load_env, ensure_output_dir, get_timestamp_subfolder, format_duration
├── tests/
│   ├── test_client.py
│   ├── test_ingest.py
│   ├── test_transcribe.py
│   ├── test_clean.py
│   ├── test_enrich.py
│   ├── test_export.py
│   └── test_record.py
└── recordings/             # git-ignored
```

## Pipeline Details

**Ingest** (`src/meetbrief/ingest.py`): `normalize_audio()` validates extension, runs ffmpeg to 16 kHz mono WAV (temp file). For files over `OPENAI_LIMIT_MB`, `compress_audio()` can produce MP3. Caller cleans up temp files.

**Transcribe** (`src/meetbrief/transcribe.py`): `transcribe(audio_path, language)` uses `OpenAIClient`. Large files are chunked (see `src/meetbrief/chunk.py`); segments are merged with `_merge_chunk_segments`. Returns `List[TranscriptSegment]`.

**Clean** (`src/meetbrief/clean.py`): `clean_transcript(segments)` preserves timestamps and speaker; batches segments for LLM (gpt-4o-mini) with rule-based fallback. Returns cleaned `List[TranscriptSegment]`.

**Enrich** (`src/meetbrief/enrich.py`): `enrich_transcript(segments, title)` chunks transcript by time/token limits, calls LLM for structured extraction per chunk, merges with `_merge_reports` (dedupe, normalize). Returns `MeetingReport`.

**Export** (`src/meetbrief/export.py`): Writes `report.json`, `raw_transcript.json`, `clean_transcript.md`, `report.md` (Notion-style: metadata, TL;DR, summary, decisions, action items, risks, open questions, full transcript with `[HH:MM:SS]` timestamps). Output directory is the timestamped subfolder under `--output-dir`.

## CLI Commands

| Command | Purpose |
|--------|--------|
| `meetbrief run <file>` | Full pipeline. Options: `--title`, `--language`, `--output-dir`, `--timestamps` / `--no-timestamps` |
| `meetbrief transcribe <file>` | Transcribe only. Options: `--language`, `--output-dir` |
| `meetbrief summarize <file>` | Enrich + export from existing transcript JSON. Options: `--title`, `--output-dir` |
| `meetbrief record` | Record system audio; optional auto-process. Options: `-o`, `-d`, `-t`, `-l`, `--auto-process`, `-s`, `--output-dir`. `--list-sources` |

## Models

Location: `src/meetbrief/models.py`. Pydantic v2.

- **TranscriptSegment:** `start`, `end` (float), `speaker` (Optional[str]), `text` (str)
- **ActionItem:** `task` (str), `owner` (str, required), `due_date`, `priority` (Optional)
- **MeetingReport:** `title`, `duration` (Optional), `summary`, `decisions`, `action_items`, `risks`, `open_questions`
- **RawTranscript:** `segments: List[TranscriptSegment]`

## Clients

Location: `src/meetbrief/client.py`.

- **TranscriptionClient:** `transcribe_audio(audio_path, language)`, `supports_language(language)`
- **LLMClient:** `generate_structured_output(prompt, schema, model)`, `chat_completion(messages, model, **kwargs)`
- **OpenAIClient:** Implements both; uses Whisper for transcription and gpt-4o-mini (or configured model) for LLM. Used by transcribe, clean, and enrich.

## Conventions

- **Paths:** `pathlib.Path`; output dirs created as needed; timestamp subfolders via `utils.get_timestamp_subfolder()`.
- **Env:** `OPENAI_API_KEY` via `utils.load_env()` (python-dotenv).
- **UI:** Rich for progress and console output.
- **Tests:** pytest; see `tests/test_*.py`. Mock external APIs in tests.
- **Privacy:** No persistent storage of audio on servers; temp files removed after use. Data sent to OpenAI per user configuration.

## Refinement Guidance

- **New export format:** Add function in `src/meetbrief/export.py`, call from `src/meetbrief/cli.py` in `run` and `summarize` (and record's auto-process path). Add tests in `tests/test_export.py`.
- **Pipeline change:** Follow ingest → transcribe → clean → enrich → export; preserve timestamp handling in clean and segment list shape through enrich.
- **Recording:** Platform-specific logic in `src/meetbrief/record.py` (`_list_pulse_sources`, `_record_pulse`, `_list_avfoundation_sources`, `_record_avfoundation`). CLI in `src/meetbrief/cli.py` `record` command.
- **Tests:** One test file per main module; mock `OpenAIClient` / API calls to avoid network and cost.

## Pitfalls to Avoid

1. Preserve `start`/`end` (and speaker) through cleaning; do not drop or reorder segments.
2. Respect OpenAI file size limit; use existing chunking in ingest/transcribe for large files.
3. Use `pathlib.Path` and CLI options for paths; avoid hardcoded paths.
4. Validate input file and API key early; give clear, actionable errors.
5. Remove temp files after use (e.g. normalized audio after transcribe).
