"""Tests for quick-mode recording fallbacks in CLI."""

from pathlib import Path
from unittest.mock import MagicMock

from typer.testing import CliRunner

from meetbrief import cli
from meetbrief import record as recording


runner = CliRunner()


def test_record_quick_retries_without_mic_then_succeeds(monkeypatch, tmp_path):
    """Quick mode retries with --no-include-mic after default failure."""
    monkeypatch.setattr(cli.utils, "load_env", lambda: None)
    monkeypatch.setattr(recording, "detect_platform", lambda: "linux")
    monkeypatch.setattr(recording, "detect_audio_system", lambda: "pulse")

    calls = []

    def fake_record_system_audio(output_path, source=None, duration=None, include_mic=True):
        calls.append({"source": source, "include_mic": include_mic})
        if len(calls) == 1:
            raise recording.RecordingError("initial setup failed")
        return Path(output_path)

    monkeypatch.setattr(recording, "record_system_audio", fake_record_system_audio)

    def fake_run(*args, **kwargs):
        return MagicMock(returncode=1, stdout="")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    out = tmp_path / "quick.wav"
    result = runner.invoke(
        cli.app,
        ["record", "--quick", "--no-auto-process", "--output", str(out)],
    )

    assert result.exit_code == 0
    assert len(calls) == 2
    assert calls[0]["include_mic"] is True
    assert calls[1]["include_mic"] is False
    assert "Fallback used:" in result.stdout


def test_record_quick_uses_pulse_default_source_fallback(monkeypatch, tmp_path):
    """Quick mode eventually retries with explicit Pulse default source."""
    monkeypatch.setattr(cli.utils, "load_env", lambda: None)
    monkeypatch.setattr(recording, "detect_platform", lambda: "linux")
    monkeypatch.setattr(recording, "detect_audio_system", lambda: "pulse")

    calls = []

    def fake_record_system_audio(output_path, source=None, duration=None, include_mic=True):
        calls.append({"source": source, "include_mic": include_mic})
        if len(calls) < 3:
            raise recording.RecordingError("attempt failed")
        return Path(output_path)

    monkeypatch.setattr(recording, "record_system_audio", fake_record_system_audio)
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: MagicMock(returncode=0, stdout="alsa_input.default\n"),
    )

    out = tmp_path / "quick.wav"
    result = runner.invoke(
        cli.app,
        ["record", "--quick", "--no-auto-process", "--output", str(out)],
    )

    assert result.exit_code == 0
    assert len(calls) == 3
    assert calls[-1]["source"] == "alsa_input.default"
    assert calls[-1]["include_mic"] is False
    assert "explicit Pulse default source" in result.stdout
