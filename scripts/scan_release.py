#!/usr/bin/env python3
"""Reject secrets, personal paths, and local media from release inputs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from build_release import ROOT, release_files


MEDIA_SUFFIXES = {
    ".aac",
    ".avi",
    ".heic",
    ".m4a",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".wav",
    ".webm",
}
TEXT_SUFFIXES = {"", ".json", ".md", ".py", ".txt", ".yaml", ".yml"}
PATTERNS = {
    "private_key": re.compile("BEGIN " + r"(?:RSA |EC |OPENSSH )?PRIVATE KEY"),
    "github_token": re.compile(r"(?:github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,})"),
    "openai_key": re.compile(r"sk-[A-Za-z0-9]{20,}"),
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "macos_personal_path": re.compile(r"/Users/[A-Za-z0-9._-]+/"),
    "linux_personal_path": re.compile(r"/home/[A-Za-z0-9._-]+/"),
    "windows_personal_path": re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+\\", re.IGNORECASE),
}


def scan() -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    files = release_files()
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        if path.suffix.lower() in MEDIA_SUFFIXES:
            findings.append({"file": relative, "kind": "local_media"})
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append({"file": relative, "kind": "unexpected_binary"})
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for kind, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings.append({"file": relative, "line": line_number, "kind": kind})
    return {
        "schema_version": "1.0",
        "status": "passed" if not findings else "failed",
        "files_scanned": len(files),
        "findings": findings,
    }


def main() -> None:
    report = scan()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
