#!/usr/bin/env python3
"""Offline parser tests for current, legacy, error and empty history shapes."""

import json
from pathlib import Path

from comfyui_result import (
    CompletedWithoutMediaError,
    ExecutionResultError,
    extract_execution_error,
    extract_media,
    history_entry,
)


ROOT = Path(__file__).resolve().parent.parent
FIXTURES = json.loads(
    (ROOT / "assets" / "history-fixtures.json").read_text(encoding="utf-8")
)


def main():
    current = history_entry(FIXTURES["current_image"], "prompt-current")
    current_media = extract_media(current)
    assert current_media[0]["filename"] == "shot01_00001_.png"
    assert current_media[0]["media_key"] == "images"

    legacy = history_entry(FIXTURES["legacy_video"], "prompt-legacy")
    legacy_media = extract_media(legacy)
    assert legacy_media[0]["filename"] == "clip_00001_.mp4"
    assert legacy_media[0]["media_key"] == "video"

    failed = history_entry(FIXTURES["execution_error"], "prompt-error")
    error = extract_execution_error(failed)
    assert error["exception_message"] == "fixture failure"

    empty = history_entry(FIXTURES["completed_empty"], "prompt-empty")
    assert not extract_media(empty)
    assert empty["status"]["completed"] is True

    assert issubclass(ExecutionResultError, RuntimeError)
    assert issubclass(CompletedWithoutMediaError, RuntimeError)
    print("all offline history parser tests passed")


if __name__ == "__main__":
    main()
