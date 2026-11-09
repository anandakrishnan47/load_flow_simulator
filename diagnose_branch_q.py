
from pathlib import Path

from validate import (
    DATA_DIR,
    reference_solution,
)

from loadflow.ieee_validation import (
    read_matpower_case,
    convert_to_network,
)

from loadflow.solver import solve_load_flow
from loadflow.branch_flows import calculate_branch_flows

from pypower.idx_brch import (
    F_BUS, T_BUS, BR_STATUS,
    PF, QF, PT, QT,
)

path = DATA_DIR / "case118.m"

network = convert_to_network(
    read_matpower_case(path)
)

solution = solve_load_flow(
    network,
    tolerance=1e-8,
    max_iterations=50,
)

flows = calculate_branch_flows(
    network,
    solution,
)

reference = reference_solution(path)

# Match the reference rows using the same
# bus-pair and occurrence-order approach
# as validate.py.
from collections import defaultdict, deque

groups = defaultdict(deque)

for row in reference["branch"]:
    if int(row[BR_STATUS]) == 0:
        continue

    groups[
        (int(row[F_BUS]), int(row[T_BUS]))
    ].append(row)

differences = []

for branch in flows.branches:
    key = (branch.from_bus, branch.to_bus)
    reverse = (key[1], key[0])

    if groups[key]:
        row = groups[key].popleft()
        qf_ref = float(row[QF])
        qt_ref = float(row[QT])

    elif groups[reverse]:
        row = groups[reverse].popleft()
        qf_ref = float(row[QT])
        qt_ref = float(row[QF])

    else:
        raise RuntimeError(
            f"Unmatched branch: {key}"
        )

    error_from = branch.q_from - qf_ref
    error_to = branch.q_to - qt_ref

    differences.append(
        (
            max(abs(error_from), abs(error_to)),
            branch.kind,
            branch.from_bus,
            branch.to_bus,
            error_from,
            error_to,
        )
    )

differences.sort(reverse=True)

print("\nLargest branch reactive-power errors")
print("-" * 85)

for error, kind, f, t, ef, et in differences[:15]:
    print(
        f"{kind:12s} "
        f"{f:4d} -> {t:4d} | "
        f"From error: {ef:+12.6f} MVAr | "
        f"To error: {et:+12.6f} MVAr"
    )
