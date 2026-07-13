#!/usr/bin/env python3
"""Extract and verify the exact ZIP intended for GitHub Release delivery."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


FORBIDDEN_TOP_LEVEL = {".git", "demo-output", "dist", "exports", "projects"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checksum(archive: Path) -> dict[str, Any]:
    checksum_path = archive.with_suffix(archive.suffix + ".sha256")
    if not checksum_path.is_file():
        return {"status": "failed", "reason": f"missing checksum file: {checksum_path.name}"}
    fields = checksum_path.read_text(encoding="utf-8").strip().split()
    if len(fields) < 2 or fields[1] != archive.name:
        return {"status": "failed", "reason": "checksum file format or filename is invalid"}
    actual = sha256(archive)
    expected = fields[0].lower()
    return {
        "status": "passed" if actual == expected else "failed",
        "expected": expected,
        "actual": actual,
        "file": checksum_path.name,
    }


def validate_members(members: list[zipfile.ZipInfo]) -> tuple[str, list[str]]:
    errors: list[str] = []
    roots: set[str] = set()
    for member in members:
        name = member.filename
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            errors.append(f"unsafe archive path: {name}")
            continue
        unix_mode = member.external_attr >> 16
        if unix_mode and (unix_mode & 0o170000) == 0o120000:
            errors.append(f"symbolic links are not allowed: {name}")
            continue
        roots.add(path.parts[0])
        if len(path.parts) > 1 and path.parts[1] in FORBIDDEN_TOP_LEVEL:
            errors.append(f"forbidden packaged directory: {name}")
    if len(roots) != 1:
        errors.append(f"archive must have one root directory, found: {sorted(roots)}")
    root = next(iter(roots)) if len(roots) == 1 else ""
    if root and not root.startswith("content-growth-agent-kit-"):
        errors.append(f"unexpected archive root: {root}")
    return root, errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a Content Growth Agent Kit release ZIP from zero extraction")
    parser.add_argument("archive")
    parser.add_argument("--core-only", action="store_true", help="Run the archive release-check without video")
    parser.add_argument("--expect-version", help="Require the archive manifest to use this version")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    archive = Path(args.archive).expanduser().resolve()
    if not archive.is_file():
        raise SystemExit(f"archive does not exist: {archive}")
    checks: dict[str, Any] = {"checksum": verify_checksum(archive)}
    errors: list[str] = []
    try:
        with zipfile.ZipFile(archive) as package:
            members = package.infolist()
            root_name, name_errors = validate_members(members)
            checks["archive_paths"] = {
                "status": "passed" if not name_errors else "failed",
                "root": root_name,
                "entries": len(members),
                "errors": name_errors,
            }
            errors.extend(name_errors)
            if name_errors:
                raise ValueError("unsafe archive structure")
            with tempfile.TemporaryDirectory(prefix="content-growth-release-verify-") as temporary:
                package.extractall(temporary)
                root = Path(temporary) / root_name
                manifest_path = root / "release-manifest.json"
                if manifest_path.is_file():
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest_version = str(manifest.get("toolkit_version") or "")
                    checks["manifest"] = {
                        "status": "passed" if not args.expect_version or manifest_version == args.expect_version else "failed",
                        "toolkit_version": manifest_version,
                        "expected_version": args.expect_version,
                        "file_count": manifest.get("file_count"),
                    }
                    if checks["manifest"]["status"] != "passed":
                        errors.append(
                            f"archive version {manifest_version!r} does not match expected {args.expect_version!r}"
                        )
                else:
                    checks["manifest"] = {"status": "failed", "reason": "release-manifest.json is missing"}
                    errors.append("release-manifest.json is missing")
                command = [sys.executable, str(root / "content_growth.py"), "release-check", "--json"]
                if args.core_only:
                    command.append("--core-only")
                process = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)
                release_report: dict[str, Any] = {}
                if process.returncode == 0:
                    try:
                        value = json.loads(process.stdout)
                        if isinstance(value, dict):
                            release_report = value
                    except json.JSONDecodeError as exc:
                        errors.append(f"release-check returned invalid JSON: {exc}")
                else:
                    errors.append(f"release-check failed with exit code {process.returncode}")
                checks["extracted_release_check"] = {
                    "status": "passed" if process.returncode == 0 and release_report.get("status") == "passed" else "failed",
                    "toolkit_version": release_report.get("toolkit_version"),
                    "failed_checks": release_report.get("failed_checks"),
                    "stderr_tail": process.stderr.strip()[-1200:] if process.stderr.strip() else "",
                }
                if checks["extracted_release_check"]["status"] != "passed":
                    errors.append("extracted release-check did not pass")
    except (zipfile.BadZipFile, json.JSONDecodeError, ValueError) as exc:
        errors.append(str(exc))
    if checks["checksum"]["status"] != "passed":
        errors.append(str(checks["checksum"].get("reason") or "checksum mismatch"))
    report = {
        "schema_version": "1.0",
        "status": "passed" if not errors else "failed",
        "archive": str(archive),
        "errors": errors,
        "checks": checks,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Release archive verification: {report['status'].upper()}")
        print(f"  archive: {archive}")
        print(f"  checksum: {checks['checksum']['status']}")
        print(f"  extracted release-check: {checks.get('extracted_release_check', {}).get('status', 'failed')}")
        for error in errors:
            print(f"  error: {error}")
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
