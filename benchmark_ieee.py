"""Benchmark APSA Newton-Raphson solver on IEEE 14/30/57/118 cases.

Run from the load_flow_simulator project root:
    python benchmark_ieee.py

Measures solve_load_flow() only (excludes import, GUI, and PDF export).
"""

import csv
import statistics
import time
from pathlib import Path

from loadflow.ieee_validation import read_matpower_case, convert_to_network
from loadflow.solver import solve_load_flow

ROOT = Path(__file__).resolve().parent
CASE_DIR = ROOT / "data" / "ieee"
OUTPUT = ROOT / "ieee_performance_results.csv"
CASES = (14, 30, 57, 118)
WARMUP_RUNS = 3
MEASURED_RUNS = 20
TOLERANCE = 1e-8
MAX_ITERATIONS = 50


def main():
    rows = []
    print("APSA IEEE Newton-Raphson Performance Benchmark")
    print(f"Solver-only timing | warmups={WARMUP_RUNS} | repetitions={MEASURED_RUNS}")
    print(f"Tolerance={TOLERANCE:g} | Max iterations={MAX_ITERATIONS}")
    print("-" * 85)
    print(f"{'Case':<12} {'Buses':>6} {'Branches':>9} {'NR iter':>8} {'Total ms':>13} {'ms/iter':>12}")

    for buses in CASES:
        case_path = CASE_DIR / f"case{buses}.m"
        if not case_path.is_file():
            raise FileNotFoundError(
                f"Missing {case_path}. Run: python download_ieee_cases.py"
            )

        network = convert_to_network(read_matpower_case(case_path))
        branches = sum(x.in_service for x in network.lines) + sum(
            x.in_service for x in network.transformers
        )

        for _ in range(WARMUP_RUNS):
            warmup = solve_load_flow(
                network, tolerance=TOLERANCE, max_iterations=MAX_ITERATIONS
            )
            if not warmup.converged:
                raise RuntimeError(f"IEEE {buses} warmup did not converge")

        durations_ms = []
        iterations = []
        for _ in range(MEASURED_RUNS):
            start = time.perf_counter()
            result = solve_load_flow(
                network, tolerance=TOLERANCE, max_iterations=MAX_ITERATIONS
            )
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            if not result.converged:
                raise RuntimeError(f"IEEE {buses} failed to converge")
            durations_ms.append(elapsed_ms)
            iterations.append(int(result.iterations))

        if len(set(iterations)) != 1:
            raise RuntimeError(f"IEEE {buses}: inconsistent iteration counts: {iterations}")

        nr_iterations = iterations[0]
        median_total_ms = statistics.median(durations_ms)
        row = {
            "case": f"IEEE {buses}",
            "buses": buses,
            "branches": branches,
            "nr_iterations": nr_iterations,
            "median_total_ms": round(median_total_ms, 6),
            "median_ms_per_iteration": round(
                median_total_ms / nr_iterations, 6
            ) if nr_iterations else "N/A",
            "mean_total_ms": round(statistics.mean(durations_ms), 6),
            "min_total_ms": round(min(durations_ms), 6),
            "max_total_ms": round(max(durations_ms), 6),
            "repetitions": MEASURED_RUNS,
        }
        rows.append(row)
        print(
            f"{row['case']:<12} {buses:>6} {branches:>9} "
            f"{nr_iterations:>8} {median_total_ms:>13.4f} "
            f"{row['median_ms_per_iteration']:>12}"
        )

    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print("-" * 85)
    print(f"Saved CSV: {OUTPUT}")
    print("Time/iteration = median total solver time / NR iterations.")
    print("Note: this is average per iteration, not separately instrumented iteration timing.")


if __name__ == "__main__":
    main()
