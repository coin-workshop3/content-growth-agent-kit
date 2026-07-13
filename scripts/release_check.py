#!/usr/bin/env python3
"""Offline release acceptance check for a clean Content Growth Agent Kit copy."""

from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "content_growth.py"
VERSION_PATTERN = re.compile(r'^TOOLKIT_VERSION\s*=\s*"([^"]+)"', re.MULTILINE)


def toolkit_version() -> str:
    match = VERSION_PATTERN.search(ENTRYPOINT.read_text(encoding="utf-8"))
    if not match:
        raise RuntimeError("TOOLKIT_VERSION is missing from content_growth.py")
    return match.group(1)


def command_check(name: str, command: list[str]) -> dict[str, Any]:
    process = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    result: dict[str, Any] = {
        "name": name,
        "status": "passed" if process.returncode == 0 else "failed",
        "returncode": process.returncode,
    }
    stdout = process.stdout.strip()
    stderr = process.stderr.strip()
    if stdout:
        result["stdout_tail"] = stdout[-1200:]
    if stderr:
        result["stderr_tail"] = stderr[-1200:]
    return result


def file_check(version: str) -> dict[str, Any]:
    required = [
        "AGENTS.md",
        "CLAUDE.md",
        "README.md",
        "CHANGELOG.md",
        "LICENSE",
        "NOTICE",
        "content_growth.py",
        "protocols/base-methodology.json",
        "scripts/smoke_test.py",
        "scripts/validate_contracts.py",
        "scripts/build_release.py",
        "scripts/scan_release.py",
        "scripts/verify_release_archive.py",
        "docs/AGENT_HANDOFF.md",
        "docs/SUPPORT_MATRIX.md",
        "docs/TROUBLESHOOTING.md",
        "docs/RELEASE_ACCEPTANCE.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/usage_report.yml",
    ]
    missing = [path for path in required if not (ROOT / path).is_file()]
    readme = (ROOT / "README.md").read_text(encoding="utf-8") if (ROOT / "README.md").is_file() else ""
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8") if (ROOT / "CHANGELOG.md").is_file() else ""
    version_markers = {
        "readme": f"v{version}" in readme,
        "changelog": f"## v{version}" in changelog,
    }
    passed = not missing and all(version_markers.values())
    return {
        "name": "release_files_and_version",
        "status": "passed" if passed else "failed",
        "missing": missing,
        "version_markers": version_markers,
    }


def doctor_check() -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
    process = subprocess.run(
        [sys.executable, str(ENTRYPOINT), "doctor", "--json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    report: Optional[dict[str, Any]] = None
    error = process.stderr.strip()
    if process.returncode == 0:
        try:
            value = json.loads(process.stdout)
            if isinstance(value, dict):
                report = value
        except json.JSONDecodeError as exc:
            error = str(exc)
    passed = bool(report and (report.get("core") or {}).get("ready"))
    result: dict[str, Any] = {
        "name": "doctor_core",
        "status": "passed" if passed else "failed",
        "returncode": process.returncode,
    }
    if error:
        result["error"] = error[-1200:]
    return result, report


def handoff_check(core_only: bool) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="content-growth-handoff-") as temporary:
        base = Path(temporary)
        demo = base / "demo-output"
        project = base / "projects" / "first-project"
        demo_command = [sys.executable, str(ENTRYPOINT), "demo", "--out", str(demo)]
        if core_only:
            demo_command.append("--skip-video")
        demo_process = subprocess.run(demo_command, cwd=ROOT, text=True, capture_output=True, check=False)
        init_process = subprocess.run(
            [sys.executable, str(ENTRYPOINT), "init", str(project)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        required_demo = [demo / "run-summary.json", demo / "geo-tasks.json", demo / "score-result.json"]
        required_project = [
            project / "AGENT_TASK.md",
            project / "enterprise-profile.json",
            project / "draft.md",
            project / "media",
            project / "output",
        ]
        missing = [str(path.relative_to(base)) for path in required_demo + required_project if not path.exists()]
        passed = demo_process.returncode == 0 and init_process.returncode == 0 and not missing
        result: dict[str, Any] = {
            "name": "agent_handoff_demo_and_init",
            "status": "passed" if passed else "failed",
            "core_only": core_only,
            "missing": missing,
            "demo_returncode": demo_process.returncode,
            "init_returncode": init_process.returncode,
        }
        if demo_process.stderr.strip():
            result["demo_error"] = demo_process.stderr.strip()[-1200:]
        if init_process.stderr.strip():
            result["init_error"] = init_process.stderr.strip()[-1200:]
        return result


def build_report(core_only: bool) -> dict[str, Any]:
    version = toolkit_version()
    checks = [file_check(version)]
    doctor_result, doctor = doctor_check()
    checks.append(doctor_result)
    checks.append(command_check("contracts", [sys.executable, str(ROOT / "scripts/validate_contracts.py")]))
    checks.append(command_check("release_privacy_scan", [sys.executable, str(ROOT / "scripts/scan_release.py")]))
    if not core_only:
        checks.append(command_check("smoke", [sys.executable, str(ROOT / "scripts/smoke_test.py")]))
    else:
        checks.append({"name": "smoke", "status": "skipped", "reason": "--core-only"})
    checks.append(handoff_check(core_only))
    failed = [check["name"] for check in checks if check.get("status") == "failed"]
    basic_video = bool(doctor and (doctor.get("basic_video") or {}).get("ready"))
    whisper = bool(doctor and (doctor.get("local_transcription") or {}).get("ready"))
    return {
        "schema_version": "1.0",
        "toolkit_version": version,
        "status": "passed" if not failed else "failed",
        "platform": platform.system() or "unknown",
        "python": platform.python_version(),
        "scope": {
            "core_geo_score": "ready" if doctor and (doctor.get("core") or {}).get("ready") else "blocked",
            "basic_video": "ready" if basic_video else "optional_dependency_missing",
            "local_whisper": "optional_ready" if whisper else "optional_not_installed",
            "publication": "always_requires_human_review",
        },
        "failed_checks": failed,
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline release acceptance checks")
    parser.add_argument("--core-only", action="store_true", help="Skip the full smoke test and video demo")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument("--out", help="Also write the JSON report to this path")
    args = parser.parse_args()
    report = build_report(args.core_only)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        output = Path(args.out).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    if args.json:
        print(rendered)
    else:
        print(f"Content Growth Agent Kit release-check: {report['status'].upper()}")
        print(f"  version: {report['toolkit_version']}")
        print(f"  platform: {report['platform']} / Python {report['python']}")
        for check in report["checks"]:
            print(f"  {check['name']}: {str(check['status']).upper()}")
        print(f"  basic video: {report['scope']['basic_video']}")
        print(f"  local Whisper: {report['scope']['local_whisper']}")
        print("  publication: always_requires_human_review")
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
