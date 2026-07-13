#!/usr/bin/env python3
"""Build a deterministic, whitelist-only release ZIP."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = re.compile(r'^TOOLKIT_VERSION\s*=\s*"([^"]+)"', re.MULTILINE)
TOP_LEVEL_FILES = {
    ".gitignore",
    "AGENTS.md",
    "CHANGELOG.md",
    "CLAUDE.md",
    "LICENSE",
    "NOTICE",
    "README.md",
    "content_growth.py",
}
TOP_LEVEL_DIRS = {".github", "docs", "examples", "protocols", "schemas", "scripts", "skills"}
IGNORED_NAMES = {".DS_Store", "__pycache__"}
IGNORED_SUFFIXES = {".pyc", ".pyo", ".swp", ".tmp"}
FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)


def toolkit_version() -> str:
    source = (ROOT / "content_growth.py").read_text(encoding="utf-8")
    match = VERSION_PATTERN.search(source)
    if not match:
        raise SystemExit("TOOLKIT_VERSION is missing from content_growth.py")
    return match.group(1)


def allowed_file(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if any(part in IGNORED_NAMES for part in relative.parts):
        return False
    if path.suffix.lower() in IGNORED_SUFFIXES:
        return False
    if len(relative.parts) == 1:
        return relative.name in TOP_LEVEL_FILES
    return relative.parts[0] in TOP_LEVEL_DIRS


def release_files() -> list[Path]:
    files = [path for path in ROOT.rglob("*") if path.is_file() and allowed_file(path)]
    return sorted(files, key=lambda path: path.relative_to(ROOT).as_posix())


def zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def write_entry(archive: zipfile.ZipFile, name: str, content: bytes) -> None:
    archive.writestr(zip_info(name), content)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_release_inputs(files: Iterable[Path]) -> None:
    required = {
        "README.md",
        "content_growth.py",
        "scripts/release_check.py",
        "scripts/scan_release.py",
        "scripts/verify_release_archive.py",
        "docs/SUPPORT_MATRIX.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
    }
    present = {path.relative_to(ROOT).as_posix() for path in files}
    missing = sorted(required - present)
    if missing:
        raise SystemExit(f"release input is incomplete: {', '.join(missing)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a deterministic Content Growth Agent Kit release ZIP")
    parser.add_argument("--out", help="Output ZIP path; defaults to dist/content-growth-agent-kit-v<version>.zip")
    args = parser.parse_args()
    version = toolkit_version()
    output = Path(args.out).expanduser().resolve() if args.out else ROOT / "dist" / f"content-growth-agent-kit-v{version}.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    files = release_files()
    validate_release_inputs(files)
    prefix = f"content-growth-agent-kit-{version}"
    manifest = {
        "schema_version": "1.0",
        "toolkit_version": version,
        "archive_root": prefix,
        "file_count": len(files),
        "files": [path.relative_to(ROOT).as_posix() for path in files],
        "privacy": "whitelist-only package; generated media and user projects are excluded",
    }
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = path.relative_to(ROOT).as_posix()
            write_entry(archive, f"{prefix}/{relative}", path.read_bytes())
        write_entry(
            archive,
            f"{prefix}/release-manifest.json",
            (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
    checksum = sha256(output)
    checksum_path = output.with_suffix(output.suffix + ".sha256")
    checksum_path.write_text(f"{checksum}  {output.name}\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "built",
                "toolkit_version": version,
                "archive": str(output),
                "sha256_file": str(checksum_path),
                "sha256": checksum,
                "file_count": len(files) + 1,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
