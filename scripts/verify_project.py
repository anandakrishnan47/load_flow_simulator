
"""
APSA final project verification.

Usage:
    python scripts/verify_project.py

Returns a nonzero exit code if a required check fails.
"""

import importlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "main.py",
    "run_gui.py",
    "requirements.txt",
    "loadflow/models.py",
    "loadflow/ybus.py",
    "loadflow/power.py",
    "loadflow/jacobian.py",
    "loadflow/solver.py",
    "loadflow/qlimits.py",
    "loadflow/branch_flows.py",
    "loadflow/ieee_validation.py",
    "loadflow/results_export.py",
    "gui/controller.py",
    "gui/worker.py",
    "gui/main_window.py",
    "gui/diagram_items.py",
    "gui/diagram_scene.py",
    "gui/diagram_editor.py",
    "gui/results_charts.py",
    "gui/export_dialog.py",
    "data/ieee/case14.m",
    "data/ieee/case30.m",
    "data/ieee/case57.m",
    "data/ieee/case118.m",
    "tests/test_integration.py",
    "tests/test_gui_workflow.py",
    "docs/USER_GUIDE.md",
    "docs/ARCHITECTURE.md",
]

IMPORTS = [
    "numpy",
    "scipy",
    "pandas",
    "matplotlib",
    "PySide6",
    "openpyxl",
    "reportlab",
    "pypower",
    "pypdf",
    "pytest",
    "pytestqt",
    "loadflow.solver",
    "loadflow.results_export",
    "gui.main_window",
]


def verify_files():
    missing = [
        name for name in REQUIRED_FILES
        if not (ROOT / name).is_file()
    ]

    return {
        "passed": not missing,
        "missing": missing,
    }


def verify_imports():
    missing = {}

    sys.path.insert(0, str(ROOT))

    for name in IMPORTS:
        try:
            importlib.import_module(name)
        except Exception as exc:
            missing[name] = (
                f"{type(exc).__name__}: {exc}"
            )

    return {
        "passed": not missing,
        "errors": missing,
    }


def run_tests():
    environment = os.environ.copy()

    # Safe for headless CI.
    environment.setdefault(
        "QT_QPA_PLATFORM",
        "offscreen",
    )

    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        "-q",
        "--tb=short",
    ]

    result = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    output = (
        result.stdout + "\n" + result.stderr
    )

    return {
        "passed": result.returncode == 0,
        "exit_code": result.returncode,
        "output": output[-20000:],
    }


def main():
    print("=" * 65)
    print("APSA FINAL PROJECT VERIFICATION")
    print("=" * 65)

    report = {
        "timestamp_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
    }

    print("\n[1/3] Checking project files...")
    report["files"] = verify_files()

    print(
        "PASS" if report["files"]["passed"]
        else "FAIL"
    )

    print("\n[2/3] Checking imports...")
    report["imports"] = verify_imports()

    print(
        "PASS" if report["imports"]["passed"]
        else "FAIL"
    )

    print("\n[3/3] Running automated tests...")
    report["tests"] = run_tests()

    print(report["tests"]["output"])

    passed = all(
        report[key]["passed"]
        for key in ("files", "imports", "tests")
    )

    report["overall_passed"] = passed

    output_dir = ROOT / "results" / "verification"
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        output_dir / "verification_report.json"
    )

    output_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("\n" + "=" * 65)
    print(
        "FINAL STATUS:",
        "PASS" if passed else "FAIL",
    )
    print("Report:", output_path)
    print("=" * 65)

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
