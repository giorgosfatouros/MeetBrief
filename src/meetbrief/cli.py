"""CLI interface for MeetBrief using Typer."""

from pathlib import Path
import subprocess
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from . import ingest, clean, enrich, export, utils
from . import transcribe as transcribe_module
from . import record as recording
from .models import TranscriptSegment

app = typer.Typer(help="MeetBrief - Turn meeting recordings into structured summaries")
console = Console()


@app.command()
def run(
    file: Path = typer.Argument(..., help="Path to audio/video file"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Meeting title"),
    language: Optional[str] = typer.Option(
        None, "--language", "-l", help="Language code (e.g., 'en', 'es')"
    ),
    output_dir: Path = typer.Option(
        Path("reports"), "--output-dir", "-o", help="Output directory"
    ),
    timestamps: bool = typer.Option(True, "--timestamps/--no-timestamps", help="Include timestamps"),
):
    """Run the full pipeline: ingest, transcribe, clean, enrich, and export."""
    utils.load_env()

    output_dir = utils.ensure_output_dir(output_dir)
    
    # Create timestamp-based subfolder
    timestamp_folder = utils.get_timestamp_subfolder()
    output_subdir = output_dir / timestamp_folder
    output_subdir.mkdir(parents=True, exist_ok=True)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # Step 1: Ingest
        task1 = progress.add_task("[cyan]Normalizing audio...", total=None)
        try:
            normalized_audio = ingest.normalize_audio(file)
            # Check if file was compressed
            file_size_mb = normalized_audio.stat().st_size / (1024 * 1024)
            if normalized_audio.suffix.lower() == ".mp3" and file.suffix.lower() != ".mp3":
                console.print(f"[yellow]File compressed to MP3 ({file_size_mb:.1f}MB)[/yellow]")
            progress.update(task1, completed=True)
        except Exception as e:
            console.print(f"[red]Error normalizing audio: {e}[/red]")
            raise typer.Exit(1)

        # Step 2: Transcribe
        file_size_mb = normalized_audio.stat().st_size / (1024 * 1024)
        if file_size_mb > ingest.OPENAI_LIMIT_MB:
            task2 = progress.add_task(
                "[cyan]Transcribing audio (chunking large file)...", total=None
            )
        else:
            task2 = progress.add_task("[cyan]Transcribing audio...", total=None)
        try:
            raw_segments = transcribe_module.transcribe(normalized_audio, language=language)
            progress.update(task2, completed=True)
        except Exception as e:
            console.print(f"[red]Error transcribing audio: {e}[/red]")
            raise typer.Exit(1)
        finally:
            # Cleanup temp file
            if normalized_audio != file and normalized_audio.exists():
                normalized_audio.unlink()

        # Step 3: Clean
        task3 = progress.add_task("[cyan]Cleaning transcript...", total=None)
        try:
            clean_segments = clean.clean_transcript(raw_segments)
            progress.update(task3, completed=True)
        except Exception as e:
            console.print(f"[yellow]Warning: Error cleaning transcript: {e}[/yellow]")
            clean_segments = raw_segments  # Fallback to raw

        # Step 4: Enrich
        task4 = progress.add_task("[cyan]Extracting insights...", total=None)
        try:
            report = enrich.enrich_transcript(clean_segments, title=title)
            progress.update(task4, completed=True)
        except Exception as e:
            console.print(f"[red]Error extracting insights: {e}[/red]")
            raise typer.Exit(1)

        # Step 5: Export
        task5 = progress.add_task("[cyan]Exporting reports...", total=None)
        try:
            export.export_json(report, output_subdir / "report.json")
            export.export_markdown(report, clean_segments, output_subdir / "report.md")
            export.export_raw_transcript(raw_segments, output_subdir / "raw_transcript.json")
            export.export_clean_transcript(clean_segments, output_subdir / "clean_transcript.md")
            progress.update(task5, completed=True)
        except Exception as e:
            console.print(f"[red]Error exporting reports: {e}[/red]")
            raise typer.Exit(1)

    console.print(f"[green]✓[/green] Reports exported to: {output_subdir}")


@app.command()
def transcribe(
    file: Path = typer.Argument(..., help="Path to audio/video file"),
    language: Optional[str] = typer.Option(
        None, "--language", "-l", help="Language code (e.g., 'en', 'es')"
    ),
    output_dir: Path = typer.Option(
        Path("reports"), "--output-dir", "-o", help="Output directory"
    ),
):
    """Transcribe audio file only (no enrichment)."""
    utils.load_env()

    output_dir = utils.ensure_output_dir(output_dir)
    
    # Create timestamp-based subfolder
    timestamp_folder = utils.get_timestamp_subfolder()
    output_subdir = output_dir / timestamp_folder
    output_subdir.mkdir(parents=True, exist_ok=True)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # Normalize
        task1 = progress.add_task("[cyan]Normalizing audio...", total=None)
        try:
            normalized_audio = ingest.normalize_audio(file)
            # Check if file was compressed
            file_size_mb = normalized_audio.stat().st_size / (1024 * 1024)
            if normalized_audio.suffix.lower() == ".mp3" and file.suffix.lower() != ".mp3":
                console.print(f"[yellow]File compressed to MP3 ({file_size_mb:.1f}MB)[/yellow]")
            progress.update(task1, completed=True)
        except Exception as e:
            console.print(f"[red]Error normalizing audio: {e}[/red]")
            raise typer.Exit(1)

        # Transcribe
        file_size_mb = normalized_audio.stat().st_size / (1024 * 1024)
        if file_size_mb > ingest.OPENAI_LIMIT_MB:
            task2 = progress.add_task(
                "[cyan]Transcribing audio (chunking large file)...", total=None
            )
        else:
            task2 = progress.add_task("[cyan]Transcribing audio...", total=None)
        try:
            segments = transcribe_module.transcribe(normalized_audio, language=language)
            progress.update(task2, completed=True)
        except Exception as e:
            console.print(f"[red]Error transcribing audio: {e}[/red]")
            raise typer.Exit(1)
        finally:
            if normalized_audio != file and normalized_audio.exists():
                normalized_audio.unlink()

        # Export
        task3 = progress.add_task("[cyan]Exporting transcript...", total=None)
        try:
            export.export_raw_transcript(segments, output_subdir / "raw_transcript.json")
            export.export_clean_transcript(segments, output_subdir / "clean_transcript.md")
            progress.update(task3, completed=True)
        except Exception as e:
            console.print(f"[red]Error exporting transcript: {e}[/red]")
            raise typer.Exit(1)

    console.print(f"[green]✓[/green] Transcript exported to: {output_subdir}")


@app.command()
def summarize(
    file: Path = typer.Argument(..., help="Path to transcript JSON file"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Meeting title"),
    output_dir: Path = typer.Option(
        Path("reports"), "--output-dir", "-o", help="Output directory"
    ),
):
    """Summarize existing transcript file."""
    utils.load_env()

    import json

    output_dir = utils.ensure_output_dir(output_dir)
    
    # Create timestamp-based subfolder
    timestamp_folder = utils.get_timestamp_subfolder()
    output_subdir = output_dir / timestamp_folder
    output_subdir.mkdir(parents=True, exist_ok=True)

    # Load transcript
    try:
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)
        segments_data = data.get("segments", [])
        segments = [TranscriptSegment(**seg) for seg in segments_data]
    except Exception as e:
        console.print(f"[red]Error loading transcript: {e}[/red]")
        raise typer.Exit(1)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # Enrich
        task1 = progress.add_task("[cyan]Extracting insights...", total=None)
        try:
            report = enrich.enrich_transcript(segments, title=title)
            progress.update(task1, completed=True)
        except Exception as e:
            console.print(f"[red]Error extracting insights: {e}[/red]")
            raise typer.Exit(1)

        # Export
        task2 = progress.add_task("[cyan]Exporting reports...", total=None)
        try:
            export.export_json(report, output_subdir / "report.json")
            export.export_markdown(report, segments, output_subdir / "report.md")
            progress.update(task2, completed=True)
        except Exception as e:
            console.print(f"[red]Error exporting reports: {e}[/red]")
            raise typer.Exit(1)

    console.print(f"[green]✓[/green] Reports exported to: {output_subdir}")


@app.command()
def record(
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file path (default: auto-generated with timestamp)"
    ),
    duration: Optional[int] = typer.Option(
        None, "--duration", "-d", help="Recording duration in seconds (Ctrl+C to stop if not set)"
    ),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Meeting title"),
    language: Optional[str] = typer.Option(
        None, "--language", "-l", help="Language code (e.g., 'en', 'es')"
    ),
    output_dir: Path = typer.Option(
        Path("reports"), "--output-dir", help="Output directory for processed reports"
    ),
    auto_process: bool = typer.Option(
        True, "--auto-process/--no-auto-process", help="Automatically process after recording"
    ),
    source: Optional[str] = typer.Option(
        None, "--source", "-s", help="Audio source identifier (auto-detected if not set)"
    ),
    include_mic: bool = typer.Option(
        True, "--include-mic/--no-include-mic", "-m",
        help="Record from default microphone and mix with system audio (default: on). Use --no-include-mic for system audio only."
    ),
    list_sources: bool = typer.Option(
        False, "--list-sources", help="List available audio sources and exit"
    ),
    quick: bool = typer.Option(
        False,
        "--quick",
        help=(
            "Quick-start recording with automatic fallback retries if the default setup fails "
            "(tries without mic and Pulse default source when available)."
        ),
    ),
):
    """Record system audio from meeting apps (Zoom, Google Meet, Teams, etc.).

    Records system audio output and optionally processes it through the full pipeline.
    Press Ctrl+C to stop recording if --duration is not set.

    Examples:
      meetbrief record --quick
      meetbrief record --quick --no-auto-process
    """
    utils.load_env()

    try:
        # Detect platform and audio system
        platform_name = recording.detect_platform()
        audio_system = recording.detect_audio_system()
        console.print(f"[cyan]Platform: {platform_name}, Audio system: {audio_system}[/cyan]")

        # List sources if requested
        if list_sources:
            console.print("[cyan]Available audio sources:[/cyan]")
            try:
                sources = recording.list_audio_sources()
                for source_id, description in sources:
                    console.print(f"  [green]{source_id}[/green]: {description}")
            except recording.RecordingError as e:
                console.print(f"[red]Error listing sources: {e}[/red]")
                raise typer.Exit(1)
            return

        # Determine output path
        if output is None:
            timestamp = utils.get_timestamp_subfolder()
            output = Path("recordings") / f"recording_{timestamp}.wav"
        else:
            output = Path(output)

        # Start recording
        console.print("[cyan]Starting system audio recording...[/cyan]")
        if duration:
            console.print(f"[yellow]Recording for {duration} seconds...[/yellow]")
        else:
            console.print("[yellow]Press Ctrl+C to stop recording[/yellow]")

        try:
            if not quick:
                recorded_file = recording.record_system_audio(
                    output_path=output,
                    source=source,
                    duration=duration,
                    include_mic=include_mic,
                )
            else:
                attempts = [
                    {
                        "source": source,
                        "include_mic": include_mic,
                        "label": "default recording settings",
                    }
                ]
                if include_mic:
                    attempts.append(
                        {
                            "source": source,
                            "include_mic": False,
                            "label": "fallback: disabled microphone mixing",
                        }
                    )

                pulse_default_source = None
                try:
                    result = subprocess.run(
                        ["pactl", "get-default-source"],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        pulse_default_source = result.stdout.strip()
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    pulse_default_source = None

                if pulse_default_source:
                    attempts.append(
                        {
                            "source": pulse_default_source,
                            "include_mic": False,
                            "label": (
                                f"fallback: explicit Pulse default source '{pulse_default_source}' "
                                "without microphone"
                            ),
                        }
                    )

                last_error = None
                recorded_file = None
                for index, attempt in enumerate(attempts):
                    try:
                        recorded_file = recording.record_system_audio(
                            output_path=output,
                            source=attempt["source"],
                            duration=duration,
                            include_mic=attempt["include_mic"],
                        )
                        if index > 0:
                            console.print(
                                "[yellow]Fallback used:[/yellow] "
                                f"{attempt['label']}. "
                                "If quality is low, run [bold]meetbrief record --list-sources[/bold] "
                                "and retry with [bold]--source[/bold] or use [bold]--no-include-mic[/bold]."
                            )
                        break
                    except recording.RecordingError as exc:
                        last_error = exc
                        if index < len(attempts) - 1:
                            console.print(
                                "[yellow]Quick mode:[/yellow] "
                                f"{attempt['label']} failed, retrying with a simpler fallback..."
                            )

                if recorded_file is None:
                    assert last_error is not None
                    raise last_error

            console.print(f"[green]✓[/green] Recording saved to: {recorded_file}")

            # Auto-process if requested
            if auto_process:
                console.print("[cyan]Processing recording through pipeline...[/cyan]")
                output_dir = utils.ensure_output_dir(output_dir)
                timestamp_folder = utils.get_timestamp_subfolder()
                output_subdir = output_dir / timestamp_folder
                output_subdir.mkdir(parents=True, exist_ok=True)

                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    # Step 1: Normalize (may be no-op since we record in correct format)
                    task1 = progress.add_task("[cyan]Normalizing audio...", total=None)
                    try:
                        normalized_audio = ingest.normalize_audio(recorded_file)
                        # Check if file was compressed
                        file_size_mb = normalized_audio.stat().st_size / (1024 * 1024)
                        if normalized_audio.suffix.lower() == ".mp3" and recorded_file.suffix.lower() != ".mp3":
                            console.print(f"[yellow]File compressed to MP3 ({file_size_mb:.1f}MB)[/yellow]")
                        progress.update(task1, completed=True)
                    except Exception as e:
                        console.print(f"[yellow]Warning: Error normalizing audio: {e}[/yellow]")
                        normalized_audio = recorded_file

                    # Step 2: Transcribe
                    file_size_mb = normalized_audio.stat().st_size / (1024 * 1024)
                    if file_size_mb > ingest.OPENAI_LIMIT_MB:
                        task2 = progress.add_task(
                            "[cyan]Transcribing audio (chunking large file)...", total=None
                        )
                    else:
                        task2 = progress.add_task("[cyan]Transcribing audio...", total=None)
                    try:
                        raw_segments = transcribe_module.transcribe(normalized_audio, language=language)
                        progress.update(task2, completed=True)
                    except Exception as e:
                        console.print(f"[red]Error transcribing audio: {e}[/red]")
                        raise typer.Exit(1)
                    finally:
                        if normalized_audio != recorded_file and normalized_audio.exists():
                            normalized_audio.unlink()

                    # Step 3: Clean
                    task3 = progress.add_task("[cyan]Cleaning transcript...", total=None)
                    try:
                        clean_segments = clean.clean_transcript(raw_segments)
                        progress.update(task3, completed=True)
                    except Exception as e:
                        console.print(f"[yellow]Warning: Error cleaning transcript: {e}[/yellow]")
                        clean_segments = raw_segments

                    # Step 4: Enrich
                    task4 = progress.add_task("[cyan]Extracting insights...", total=None)
                    try:
                        report = enrich.enrich_transcript(clean_segments, title=title)
                        progress.update(task4, completed=True)
                    except Exception as e:
                        console.print(f"[red]Error extracting insights: {e}[/red]")
                        raise typer.Exit(1)

                    # Step 5: Export
                    task5 = progress.add_task("[cyan]Exporting reports...", total=None)
                    try:
                        export.export_json(report, output_subdir / "report.json")
                        export.export_markdown(report, clean_segments, output_subdir / "report.md")
                        export.export_raw_transcript(raw_segments, output_subdir / "raw_transcript.json")
                        export.export_clean_transcript(clean_segments, output_subdir / "clean_transcript.md")
                        progress.update(task5, completed=True)
                    except Exception as e:
                        console.print(f"[red]Error exporting reports: {e}[/red]")
                        raise typer.Exit(1)

                console.print(f"[green]✓[/green] Reports exported to: {output_subdir}")

        except KeyboardInterrupt:
            console.print("\n[yellow]Recording stopped by user[/yellow]")
            # Check if file was created
            if output.exists() and output.stat().st_size > 0:
                console.print(f"[green]Recording saved to: {output}[/green]")
            raise typer.Exit(0)
        except recording.RecordingError as e:
            console.print(f"[red]Recording error: {e}[/red]")
            raise typer.Exit(1)

    except recording.RecordingError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    except (KeyboardInterrupt, typer.Exit):
        # Re-raise KeyboardInterrupt and typer.Exit to let them propagate
        raise
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
