
"""
Module 8 demonstration:
IEEE benchmark comparison against PYPOWER.
"""

from pathlib import Path
import json

from loadflow.ieee_validation import (
    CASE_NAMES,
    validate_case,
    passes_validation,
)


DATA_DIR = Path("data/ieee")
REPORT_DIR = Path("results")


def main():
    REPORT_DIR.mkdir(
        parents=True, exist_ok=True
    )

    print("=" * 100)
    print("E4234 APSA LOAD FLOW SIMULATOR")
    print("MODULE 8: IEEE BENCHMARK VALIDATION")
    print("=" * 100)

    print(
        f"{'Case':<12}"
        f"{'Buses':<8}"
        f"{'Iter':<8}"
        f"{'Max |dV|':<16}"
        f"{'Max |dAngle|':<16}"
        f"{'Loss error MW':<17}"
        f"{'Status':<10}"
    )

    results = []

    for name in CASE_NAMES:
        path = DATA_DIR / f"{name}.m"

        result = validate_case(path)
        passed = passes_validation(result)

        results.append({
            **result.__dict__,
            "passed": passed,
        })

        print(
            f"{result.case_name:<12}"
            f"{result.buses:<8}"
            f"{result.apsa_iterations:<8}"
            f"{result.max_vm_error:<16.8e}"
            f"{result.max_angle_error:<16.8e}"
            f"{result.p_loss_error:<17.8e}"
            f"{'PASS' if passed else 'FAIL':<10}"
        )

    report_path = (
        REPORT_DIR / "ieee_validation.json"
    )

    report_path.write_text(
        json.dumps(
            results,
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )

    print("\nReference: PYPOWER AC Newton-Raphson")
    print("Generator Q-limit enforcement: Disabled")
    print("Report saved to:", report_path)

    if not all(row["passed"] for row in results):
        raise SystemExit(
            "One or more benchmark cases failed"
        )

    print("\nAll IEEE benchmarks passed.")


if __name__ == "__main__":
    main()
