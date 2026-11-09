
"""
E4234 Advanced Power System Analysis
Assignment Numerical Validation

Validates APSA against PYPOWER for:
    IEEE 14, 30, 57 and 118-bus systems.

Checks:
    1. NR convergence and mismatch
    2. Voltage magnitude error
    3. Voltage angle error
    4. Branch terminal P/Q flow errors
    5. Total active loss error
    6. IEEE 118-bus iteration limit

Exit code:
    0 = all validation criteria passed
    1 = one or more criteria failed

Run:
    python validate.py
"""

from collections import defaultdict, deque
from pathlib import Path
import sys

import numpy as np

from pypower.api import ppoption, runpf
from pypower.idx_brch import (
    F_BUS,
    T_BUS,
    BR_STATUS,
    PF,
    QF,
    PT,
    QT,
)
from pypower.idx_bus import (
    BUS_I,
    VM,
    VA,
)

from loadflow.ieee_validation import (
    read_matpower_case,
    convert_to_network,
)
from loadflow.solver import solve_load_flow
from loadflow.branch_flows import calculate_branch_flows


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "ieee"

CASES = {
    "IEEE 14": "case14.m",
    "IEEE 30": "case30.m",
    "IEEE 57": "case57.m",
    "IEEE 118": "case118.m",
}

TOLERANCES = {
    "mismatch": 1e-8,
    "voltage": 1e-4,
    "angle": 0.01,
    "branch": 0.01,
    "loss_percent": 0.1,
    "ieee118_iterations": 7,
}



def reference_solution(path):
    """
    Solve a MATPOWER benchmark using PYPOWER.

    The existing APSA MATPOWER parser reads the .m
    file and produces a dictionary of numeric arrays.

    PYPOWER runpf() then solves that dictionary.
    """
    import numpy as np

    from pypower.api import ppoption, runpf

    case = read_matpower_case(path)

    required = (
        "baseMVA",
        "bus",
        "gen",
        "branch",
    )

    for key in required:
        if key not in case:
            raise ValueError(
                f"MATPOWER case missing '{key}'"
            )

    # PYPOWER expects independent writable arrays.
    ppc = {
        "version": "2",
        "baseMVA": float(case["baseMVA"]),
        "bus": np.array(
            case["bus"],
            dtype=float,
            copy=True,
        ),
        "gen": np.array(
            case["gen"],
            dtype=float,
            copy=True,
        ),
        "branch": np.array(
            case["branch"],
            dtype=float,
            copy=True,
        ),
    }

    if "gencost" in case:
        ppc["gencost"] = np.array(
            case["gencost"],
            dtype=float,
            copy=True,
        )

    options = ppoption(
        VERBOSE=0,
        OUT_ALL=0,
        PF_ALG=1,
        PF_TOL=1e-10,
        PF_MAX_IT=50,
        ENFORCE_Q_LIMS=0,
    )

    solved, success = runpf(
        ppc,
        options,
    )

    if not success:
        raise RuntimeError(
            f"PYPOWER did not converge: {path.name}"
        )

    return solved


def compare_bus_results(solution, reference):
    """
    Compare bus voltages by bus number.

    Angle differences are wrapped to [-180, 180]
    to avoid artificial 360-degree errors.
    """
    reference_bus_index = {
        int(row[BUS_I]): i
        for i, row in enumerate(reference["bus"])
    }

    vm_errors = []
    va_errors = []

    for number, i in solution.bus_index.items():
        if number not in reference_bus_index:
            raise ValueError(
                f"Reference missing bus {number}"
            )

        j = reference_bus_index[number]

        vm_errors.append(
            abs(
                float(solution.vm[i])
                - float(reference["bus"][j, VM])
            )
        )

        difference = (
            float(solution.va[i])
            - float(reference["bus"][j, VA])
            + 180.0
        ) % 360.0 - 180.0

        va_errors.append(abs(difference))

    if len(reference_bus_index) != len(
        solution.bus_index
    ):
        raise ValueError(
            "APSA and PYPOWER bus counts differ"
        )

    return max(vm_errors), max(va_errors)



def compare_branch_results(
    flows,
    reference,
    network,
    solution,
    original_case,
):
    """
    Compare APSA and PYPOWER branch terminal powers.

    For transformers whose charging susceptance was
    converted into equivalent bus shunts, restore
    the terminal charging contributions for the
    comparison only.

    This does not modify the solved network.
    """
    from collections import defaultdict, deque

    from pypower.idx_brch import (
        F_BUS, T_BUS, BR_STATUS,
        BR_B, TAP, PF, QF, PT, QT,
    )

    groups = defaultdict(deque)

    for row in reference["branch"]:
        if int(row[BR_STATUS]) == 0:
            continue

        key = (
            int(row[F_BUS]),
            int(row[T_BUS]),
        )

        groups[key].append(row)

    # Use original MATPOWER branch rows to identify
    # transformer charging values.
    original_groups = defaultdict(deque)

    for row in original_case["branch"]:
        if int(row[BR_STATUS]) == 0:
            continue

        key = (
            int(row[F_BUS]),
            int(row[T_BUS]),
        )

        original_groups[key].append(row)

    p_errors = []
    q_errors = []

    base_mva = network.base_mva

    for branch in flows.branches:
        key = (
            int(branch.from_bus),
            int(branch.to_bus),
        )

        reverse_key = (key[1], key[0])

        reversed_orientation = False

        if groups[key]:
            row = groups[key].popleft()
            original = original_groups[key].popleft()

        elif groups[reverse_key]:
            row = groups[reverse_key].popleft()
            original = original_groups[reverse_key].popleft()
            reversed_orientation = True

        else:
            raise ValueError(
                f"Unmatched branch {key}"
            )

        if reversed_orientation:
            p_ref_from = float(row[PT])
            q_ref_from = float(row[QT])
            p_ref_to = float(row[PF])
            q_ref_to = float(row[QF])
        else:
            p_ref_from = float(row[PF])
            q_ref_from = float(row[QF])
            p_ref_to = float(row[PT])
            q_ref_to = float(row[QT])

        p_from = float(branch.p_from)
        q_from = float(branch.q_from)
        p_to = float(branch.p_to)
        q_to = float(branch.q_to)

        tap = float(original[TAP])
        b = float(original[BR_B])

        # MATPOWER uses tap=0 to mean unity tap.
        is_transformer = (
            branch.kind.lower() == "transformer"
        )

        if is_transformer and b != 0.0:
            if tap == 0.0:
                tap = 1.0

            vf = float(
                solution.vm[
                    solution.bus_index[branch.from_bus]
                ]
            )

            vt = float(
                solution.vm[
                    solution.bus_index[branch.to_bus]
                ]
            )

            q_from -= (
                base_mva * b * vf**2
                / (2.0 * tap**2)
            )

            q_to -= (
                base_mva * b * vt**2
                / 2.0
            )

        p_errors.extend([
            abs(p_from - p_ref_from),
            abs(p_to - p_ref_to),
        ])

        q_errors.extend([
            abs(q_from - q_ref_from),
            abs(q_to - q_ref_to),
        ])

    unmatched = sum(
        len(rows) for rows in groups.values()
    )

    if unmatched:
        raise ValueError(
            f"{unmatched} unmatched reference branches"
        )

    return max(p_errors), max(q_errors)


def reference_active_loss(reference):
    """
    Calculate total active branch loss in MW.
    """
    total = 0.0

    for row in reference["branch"]:
        if int(row[BR_STATUS]) == 0:
            continue

        total += float(row[PF] + row[PT])

    return total


def validate_one_case(name, filename):
    """
    Run all assignment checks for one IEEE case.
    """
    path = DATA_DIR / filename

    if not path.is_file():
        raise FileNotFoundError(
            f"Missing benchmark file: {path}"
        )

    case = read_matpower_case(path)
    network = convert_to_network(case)

    # Flat-start behaviour follows the solver's
    # existing initialization implementation.
    solution = solve_load_flow(
        network,
        tolerance=TOLERANCES["mismatch"],
        max_iterations=50,
    )

    if not solution.converged:
        raise RuntimeError(
            f"APSA did not converge: {solution.message}"
        )

    flows = calculate_branch_flows(
        network,
        solution,
    )

    reference = reference_solution(path)

    vm_error, va_error = compare_bus_results(
        solution,
        reference,
    )

    p_error, q_error = compare_branch_results(
    flows,
    reference,
    network,
    solution,
    case,
    )

    ref_loss = reference_active_loss(reference)
    apsa_loss = float(flows.total_p_loss)

    if abs(ref_loss) > 1e-12:
        loss_percent = (
            abs(apsa_loss - ref_loss)
            / abs(ref_loss)
            * 100.0
        )
    else:
        loss_percent = (
            0.0
            if abs(apsa_loss - ref_loss) <= 1e-9
            else float("inf")
        )

    checks = {
        "mismatch": (
            float(solution.mismatch)
            <= TOLERANCES["mismatch"]
        ),
        "voltage": (
            vm_error <= TOLERANCES["voltage"]
        ),
        "angle": (
            va_error <= TOLERANCES["angle"]
        ),
        "branch_p": (
            p_error <= TOLERANCES["branch"]
        ),
        "branch_q": (
            q_error <= TOLERANCES["branch"]
        ),
        "loss": (
            loss_percent
            <= TOLERANCES["loss_percent"]
        ),
    }

    if name == "IEEE 118":
        checks["iterations"] = (
            solution.iterations
            <= TOLERANCES["ieee118_iterations"]
        )

    metrics = {
        "iterations": solution.iterations,
        "mismatch": float(solution.mismatch),
        "vm_error": float(vm_error),
        "va_error": float(va_error),
        "p_error": float(p_error),
        "q_error": float(q_error),
        "loss_percent": float(loss_percent),
        "apsa_loss": apsa_loss,
        "reference_loss": ref_loss,
    }

    # Reject NaN and infinity even if comparisons
    # would otherwise behave unexpectedly.
    finite = all(
        np.isfinite(value)
        for value in metrics.values()
    )

    return {
        "name": name,
        "passed": finite and all(checks.values()),
        "checks": checks,
        "metrics": metrics,
    }


def print_result(result):
    """
    Print detailed results for one benchmark.
    """
    name = result["name"]
    metrics = result["metrics"]
    checks = result["checks"]

    print(f"\n{name}")
    print("-" * 65)

    print(
        f"NR iterations       : "
        f"{metrics['iterations']}"
    )

    print(
        f"Final mismatch      : "
        f"{metrics['mismatch']:.3e} pu"
    )

    print(
        f"Maximum Vm error    : "
        f"{metrics['vm_error']:.6e} pu"
    )

    print(
        f"Maximum angle error : "
        f"{metrics['va_error']:.6e} deg"
    )

    print(
        f"Maximum branch P err: "
        f"{metrics['p_error']:.6e} MW"
    )

    print(
        f"Maximum branch Q err: "
        f"{metrics['q_error']:.6e} MVAr"
    )

    print(
        f"Active loss error   : "
        f"{metrics['loss_percent']:.6f} %"
    )

    print("\nAcceptance checks:")

    for check_name, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        print(
            f"  {check_name:<18} {status}"
        )


def main():
    print("=" * 76)
    print("E4234 APSA - IEEE LOAD FLOW VALIDATION")
    print("=" * 76)

    print(
        "\nReference: PYPOWER Newton-Raphson"
    )

    print(
        "Generator Q-limit enforcement: disabled"
    )

    results = []

    for name, filename in CASES.items():
        try:
            result = validate_one_case(
                name,
                filename,
            )

            print_result(result)
            results.append(result)

        except Exception as exc:
            print(
                f"\n{name}: ERROR - "
                f"{type(exc).__name__}: {exc}"
            )

            results.append({
                "name": name,
                "passed": False,
                "checks": {},
                "metrics": {},
            })

    print("\n" + "=" * 76)
    print("FINAL VALIDATION SUMMARY")
    print("=" * 76)

    print(
        f"{'Case':<15}"
        f"{'Result':<12}"
        f"{'Iterations':<15}"
    )

    print("-" * 76)

    for result in results:
        status = (
            "PASS" if result["passed"]
            else "FAIL"
        )

        iterations = result["metrics"].get(
            "iterations",
            "N/A",
        )

        print(
            f"{result['name']:<15}"
            f"{status:<12}"
            f"{str(iterations):<15}"
        )

    all_passed = all(
        result["passed"]
        for result in results
    )

    print("\n" + "=" * 76)

    print(
        "OVERALL VALIDATION:",
        "PASS" if all_passed else "FAIL",
    )

    print("=" * 76)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
