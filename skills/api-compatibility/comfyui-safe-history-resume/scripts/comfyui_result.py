#!/usr/bin/env python3
"""Poll one ComfyUI prompt, safely extract, download and validate its media."""

import argparse
import contextlib
import fcntl
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
MEDIA_KEYS = ("images", "image", "video", "videos", "gifs", "audio")


class ResultError(RuntimeError):
    pass


class ExecutionResultError(ResultError):
    pass


class CompletedWithoutMediaError(ResultError):
    pass


def get_json(url, timeout=20):
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with DIRECT_OPENER.open(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def history_entry(payload, prompt_id):
    if not isinstance(payload, dict):
        return None
    entry = payload.get(prompt_id)
    if isinstance(entry, dict):
        return entry
    if payload.get("id") == prompt_id and "outputs" in payload:
        return payload
    return None


def extract_execution_error(entry):
    messages = entry.get("status", {}).get("messages", [])
    for message in reversed(messages):
        if not isinstance(message, (list, tuple)) or not message:
            continue
        if message[0] == "execution_error":
            detail = message[1] if len(message) > 1 else {}
            if isinstance(detail, dict):
                return {
                    "node_id": detail.get("node_id"),
                    "exception_type": detail.get("exception_type"),
                    "exception_message": detail.get("exception_message"),
                    "detail": detail,
                }
            return {"detail": detail}
    return None


def extract_media(entry):
    media = []
    seen = set()
    outputs = entry.get("outputs") or {}
    if not isinstance(outputs, dict):
        return media

    for node_id, node_output in outputs.items():
        if not isinstance(node_output, dict):
            continue
        for media_key in MEDIA_KEYS:
            items = node_output.get(media_key) or []
            if isinstance(items, dict):
                items = [items]
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                filename = item.get("filename") or item.get("name")
                if not filename:
                    continue
                result = {
                    "node_id": str(node_id),
                    "media_key": media_key,
                    "filename": filename,
                    "subfolder": item.get("subfolder", ""),
                    "type": item.get("type", "output"),
                }
                identity = (
                    result["filename"],
                    result["subfolder"],
                    result["type"],
                    result["media_key"],
                )
                if identity not in seen:
                    seen.add(identity)
                    media.append(result)
    return media


def poll_history(server, prompt_id, timeout_seconds=900, poll_seconds=2):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        payload = get_json(f"{server}/history/{urllib.parse.quote(prompt_id)}")
        entry = history_entry(payload, prompt_id)
        if not entry:
            time.sleep(poll_seconds)
            continue

        error = extract_execution_error(entry)
        if error:
            raise ExecutionResultError(json.dumps(error, ensure_ascii=False))

        media = extract_media(entry)
        if media:
            return entry, media

        status = entry.get("status") or {}
        if status.get("status_str") == "error":
            raise ExecutionResultError(
                f"task failed without execution_error detail: prompt_id={prompt_id}, "
                f"status={json.dumps(status, ensure_ascii=False)}"
            )
        if status.get("completed") or status.get("status_str") == "success":
            raise CompletedWithoutMediaError(
                f"task completed but produced no media: prompt_id={prompt_id}, "
                f"status={json.dumps(status, ensure_ascii=False)}"
            )
        time.sleep(poll_seconds)
    raise TimeoutError(f"timed out waiting for prompt_id={prompt_id}")


def download_media(server, item, output):
    query = urllib.parse.urlencode(
        {
            "filename": item["filename"],
            "subfolder": item.get("subfolder", ""),
            "type": item.get("type", "output"),
        }
    )
    request = urllib.request.Request(f"{server}/view?{query}")
    with DIRECT_OPENER.open(request, timeout=90) as response:
        data = response.read()
    if not data:
        raise ResultError("downloaded media is empty")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as handle:
        handle.write(data)
        temporary = Path(handle.name)
    temporary.replace(output)


def signature_valid(path):
    data = path.read_bytes()[:32]
    suffix = path.suffix.lower()
    if suffix == ".png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix in {".jpg", ".jpeg"}:
        return data.startswith(b"\xff\xd8\xff")
    if suffix == ".gif":
        return data.startswith((b"GIF87a", b"GIF89a"))
    if suffix == ".webp":
        return data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    if suffix in {".mp4", ".mov", ".m4v"}:
        return b"ftyp" in data
    if suffix == ".webm":
        return data.startswith(b"\x1aE\xdf\xa3")
    return len(data) > 0


def validate_media(path):
    if not path.is_file() or path.stat().st_size <= 0:
        raise ResultError(f"output is missing or empty: {path}")
    if not signature_valid(path):
        raise ResultError(f"file signature does not match expected media: {path}")

    suffix = path.suffix.lower()
    method = "size+signature"
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        try:
            from PIL import Image

            with Image.open(path) as image:
                image.verify()
            method = "Pillow.verify"
        except ImportError:
            pass
        except Exception as exc:
            raise ResultError(f"image decode validation failed: {exc}") from exc
    elif suffix in {".mp4", ".mov", ".m4v", ".webm"} and shutil.which("ffprobe"):
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "json",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise ResultError(f"ffprobe validation failed: {result.stderr.strip()}")
        probe = json.loads(result.stdout)
        if not probe.get("streams"):
            raise ResultError("ffprobe found no media streams")
        method = "ffprobe"
    return {"bytes": path.stat().st_size, "method": method}


@contextlib.contextmanager
def project_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ResultError(f"another result worker holds lock: {path}") from exc
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps({"pid": os.getpid(), "started": int(time.time())}) + "\n")
        handle.flush()
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def update_manifest(path, prompt_id, record):
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = {"schema_version": 1, "tasks": {}}
    payload.setdefault("tasks", {})[prompt_id] = record
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", required=True)
    parser.add_argument("--prompt-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--lock-file", type=Path)
    parser.add_argument("--media-index", type=int, default=0)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--poll-seconds", type=float, default=2)
    parser.add_argument("--force-download", action="store_true")
    args = parser.parse_args()
    args.server = args.server.rstrip("/")
    lock_file = args.lock_file or args.output.parent / ".comfyui-history.lock"

    with project_lock(lock_file):
        if args.output.exists() and not args.force_download:
            validation = validate_media(args.output)
            record = {
                "state": "downloaded_and_verified",
                "prompt_id": args.prompt_id,
                "output": str(args.output),
                "validation": validation,
                "resume": "existing_file",
            }
            if args.manifest:
                update_manifest(args.manifest, args.prompt_id, record)
            print(json.dumps(record, ensure_ascii=False))
            return

        _, media = poll_history(
            args.server,
            args.prompt_id,
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
        )
        if args.media_index < 0 or args.media_index >= len(media):
            raise ResultError(
                f"media index {args.media_index} out of range; found {len(media)} item(s)"
            )
        selected = media[args.media_index]
        download_media(args.server, selected, args.output)
        validation = validate_media(args.output)
        record = {
            "state": "downloaded_and_verified",
            "prompt_id": args.prompt_id,
            "remote_media": selected,
            "output": str(args.output),
            "validation": validation,
        }
        if args.manifest:
            update_manifest(args.manifest, args.prompt_id, record)
        print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (
        OSError,
        ValueError,
        KeyError,
        urllib.error.URLError,
        ResultError,
        TimeoutError,
    ) as exc:
        print(json.dumps({"state": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
