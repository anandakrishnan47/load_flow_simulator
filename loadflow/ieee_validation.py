
"""
Module 8: IEEE Benchmark Validation
E4234 APSA Load Flow Simulator

Features
--------
1. Read MATPOWER IEEE benchmark files.
2. Convert MATPOWER data to APSA Network objects.
3. Preserve transformer charging using equivalent shunts.
4. Solve using the APSA Newton-Raphson solver.
5. Solve independently using PYPOWER.
6. Compare bus voltages, angles, and total active losses.
7. Calculate numerical validation errors.
8. Record SHA-256 hashes for reproducibility.

Supported cases
---------------
IEEE 14-bus
IEEE 30-bus
IEEE 57-bus
IEEE 118-bus

Generator reactive power limits are disabled during
benchmark comparison.
"""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re

import numpy as np

from pypower.api import ppoption, runpf

from loadflow.models import (
    Network,
    Bus,
    Line,
    Transformer,
    Generator,
    Load,
    Shunt,
    ExternalGrid,
)

from loadflow.solver import solve_load_flow

from loadflow.branch_flows import (
    calculate_branch_flows,
)


CASE_NAMES = (
    "case14",
    "case30",
    "case57",
    "case118",
)


# ---------------------------------------------------------
# 1. MATPOWER MATRIX READER
# ---------------------------------------------------------

def _matrix(source, name):
    """
    Extract a numeric matrix from a MATPOWER .m file.

    This parser supports the standard numeric matrices
    used in the selected IEEE benchmark datasets.
    """

    match = re.search(
        rf"mpc\.{name}\s*=\s*\[(.*?)\]\s*;",
        source,
        flags=re.DOTALL,
    )

    if match is None:
        raise ValueError(
            f"MATPOWER matrix '{name}' not found"
        )

    rows = []

    for row in match.group(1).split(";"):

        # Remove MATLAB comments.
        row = re.sub(
            r"%[^\n]*",
            "",
            row,
        ).strip()

        if not row:
            continue

        values = np.fromstring(
            row.replace("\n", " "),
            sep=" ",
        )

        if values.size == 0:
            raise ValueError(
                f"Invalid numeric row in {name}"
            )

        rows.append(values)

    if not rows:
        raise ValueError(
            f"Empty MATPOWER matrix: {name}"
        )

    width = len(rows[0])

    if any(len(row) != width for row in rows):
        raise ValueError(
            f"Inconsistent column count in {name}"
        )

    return np.vstack(rows)


# ---------------------------------------------------------
# 2. READ MATPOWER CASE
# ---------------------------------------------------------

def read_matpower_case(path):
    """
    Read MATPOWER version-2 case data.

    Returns
    -------
    dict
        baseMVA, bus, gen, branch, version
    """

    path = Path(path)

    source = path.read_text(
        encoding="utf-8"
    )

    base_match = re.search(
        r"mpc\.baseMVA\s*=\s*"
        r"([0-9.eE+-]+)\s*;",
        source,
    )

    if base_match is None:
        raise ValueError(
            "Missing MATPOWER baseMVA"
        )

    base_mva = float(
        base_match.group(1)
    )

    if not np.isfinite(base_mva) or base_mva <= 0:
        raise ValueError(
            "Invalid MATPOWER baseMVA"
        )

    bus = _matrix(source, "bus")
    gen = _matrix(source, "gen")
    branch = _matrix(source, "branch")

    if (
        bus.shape[1] < 13
        or gen.shape[1] < 10
        or branch.shape[1] < 13
    ):
        raise ValueError(
            "Unsupported MATPOWER column format"
        )

    return {
        "version": "2",
        "baseMVA": base_mva,
        "bus": bus,
        "gen": gen,
        "branch": branch,
    }


# ---------------------------------------------------------
# 3. CONVERT MATPOWER CASE TO APSA NETWORK
# ---------------------------------------------------------

def convert_to_network(case):
    """
    Convert MATPOWER network data into APSA models.

    Transformer charging is represented using equivalent
    shunts so that its contribution to Ybus is preserved.

    The conversion supports fixed-bus-type AC load flow.
    """

    net = Network(
        base_mva=float(case["baseMVA"])
    )

    bus_data = case["bus"]
    gen_data = case["gen"]
    branch_data = case["branch"]

    type_map = {
        1: "PQ",
        2: "PV",
        3: "Slack",
    }

    # -----------------------------------------------------
    # 3.1 BUS DATA
    # -----------------------------------------------------

    for row in bus_data:

        number = int(row[0])
        bus_type = int(row[1])

        if bus_type not in type_map:
            raise ValueError(
                f"Unsupported bus type {bus_type} "
                f"at bus {number}"
            )

        # Some MATPOWER datasets use baseKV=0
        # when no nominal voltage is specified.
        # APSA requires a positive base_kv.
        # The fallback is metadata only; all
        # impedances are already in per unit.
        base_kv = float(row[9])

        if base_kv <= 0:
            base_kv = 1.0

        net.add_bus(
            Bus(
                number=number,
                name=f"Bus {number}",
                base_kv=base_kv,
                bus_type=type_map[bus_type],
                vm=float(row[7]),
                va=float(row[8]),
                vmin=float(row[12]),
                vmax=float(row[11]),
            )
        )

        # Constant-power load.
        if row[2] != 0 or row[3] != 0:

            net.add_load(
                Load(
                    bus=number,
                    pd=float(row[2]),
                    qd=float(row[3]),
                )
            )

        # Bus shunt.
        #
        # MATPOWER Gs and Bs are specified in
        # MW and MVAr at 1 pu voltage.
        if row[4] != 0 or row[5] != 0:

            net.add_shunt(
                Shunt(
                    bus=number,
                    gs=float(row[4]),
                    bs=float(row[5]),
                )
            )

    # -----------------------------------------------------
    # 3.2 GENERATOR DATA
    # -----------------------------------------------------

    grouped = {}

    for row in gen_data:

        # Generator status.
        if int(row[7]) <= 0:
            continue

        number = int(row[0])

        grouped.setdefault(
            number, []
        ).append(row)

    for number, generators in grouped.items():

        vg_values = [
            float(gen[5])
            for gen in generators
        ]

        if (
            max(vg_values) - min(vg_values)
            > 1e-6
        ):
            raise ValueError(
                f"Inconsistent generator "
                f"voltage setpoints at bus {number}"
            )

        net.add_generator(
            Generator(
                bus=number,
                pg=sum(
                    float(gen[1])
                    for gen in generators
                ),
                qg=sum(
                    float(gen[2])
                    for gen in generators
                ),
                vg=vg_values[0],
                qmin=sum(
                    float(gen[4])
                    for gen in generators
                ),
                qmax=sum(
                    float(gen[3])
                    for gen in generators
                ),
            )
        )

    # -----------------------------------------------------
    # 3.3 SLACK BUS
    # -----------------------------------------------------

    slack_buses = [
        bus
        for bus in net.buses
        if bus.bus_type == "Slack"
    ]

    if len(slack_buses) != 1:
        raise ValueError(
            "Exactly one slack bus is required"
        )

    slack = slack_buses[0]

    if slack.number in grouped:
        slack_vm = float(
            grouped[slack.number][0][5]
        )
    else:
        slack_vm = float(slack.vm)

    net.add_external_grid(
        ExternalGrid(
            bus=slack.number,
            vm=slack_vm,
            va=float(slack.va),
        )
    )

    # -----------------------------------------------------
    # 3.4 TRANSMISSION LINES AND TRANSFORMERS
    # -----------------------------------------------------

    for row in branch_data:

        # Branch status.
        if int(row[10]) <= 0:
            continue

        from_bus = int(row[0])
        to_bus = int(row[1])

        r = float(row[2])
        x = float(row[3])
        b = float(row[4])

        rating = float(row[5])
        tap = float(row[8])
        shift = float(row[9])

        # MATPOWER rateA = 0 indicates
        # no specified MVA limit.
        #
        # APSA requires a positive rating.
        # This placeholder is only used
        # for branch-loading reporting.
        if rating <= 0:
            rating = 1e12

        # -------------------------------------------------
        # NORMAL TRANSMISSION LINE
        # -------------------------------------------------

        if tap == 0 and shift == 0:

            net.add_line(
                Line(
                    from_bus=from_bus,
                    to_bus=to_bus,
                    r=r,
                    x=x,
                    b=b,
                    rating_mva=rating,
                )
            )

        # -------------------------------------------------
        # TRANSFORMER WITH OFF-NOMINAL TAP
        # -------------------------------------------------

        else:

            effective_tap = (
                tap if tap != 0 else 1.0
            )

            net.add_transformer(
                Transformer(
                    from_bus=from_bus,
                    to_bus=to_bus,
                    r=r,
                    x=x,
                    rating_mva=rating,
                    tap_ratio=effective_tap,
                    phase_shift=shift,
                    tap_side="from",
                )
            )

            # ---------------------------------------------
            # TRANSFORMER CHARGING CORRECTION
            # ---------------------------------------------
            #
            # MATPOWER transformer branch model:
            #
            # yff = (y + j*b/2) / |tap|^2
            # yft = -y / conj(tap)
            # ytf = -y / tap
            # ytt = y + j*b/2
            #
            # APSA Transformer already implements
            # the series and tap components.
            #
            # Add the missing charging as
            # equivalent bus shunts.
            #
            # Shunt.bs is specified in MVAr
            # at nominal 1 pu voltage.
            #
            # This preserves the complete Ybus.
            #
            # Note:
            # Transformer terminal reactive-flow
            # reporting remains separated from
            # these equivalent shunts.

            if abs(b) > 1e-12:

                from_bs = (
                    b * net.base_mva
                    / (2.0 * effective_tap**2)
                )

                to_bs = (
                    b * net.base_mva / 2.0
                )

                net.add_shunt(
                    Shunt(
                        bus=from_bus,
                        gs=0.0,
                        bs=from_bs,
                    )
                )

                net.add_shunt(
                    Shunt(
                        bus=to_bus,
                        gs=0.0,
                        bs=to_bs,
                    )
                )

    return net


# ---------------------------------------------------------
# 4. VALIDATION RESULT DATA CLASS
# ---------------------------------------------------------

@dataclass
class ValidationResult:

    case_name: str
    buses: int
    branches: int

    apsa_converged: bool
    reference_converged: bool

    apsa_iterations: int

    max_vm_error: float
    max_angle_error: float

    apsa_p_loss: float
    reference_p_loss: float
    p_loss_error: float

    final_mismatch: float
    sha256_hash: str


# ---------------------------------------------------------
# 5. RUN BENCHMARK VALIDATION
# ---------------------------------------------------------

def validate_case(
    path,
    tolerance=1e-8,
    max_iterations=50,
):
    """
    Compare APSA against PYPOWER.

    Generator reactive power limits are not enforced.

    Returns
    -------
    ValidationResult
    """

    path = Path(path)

    # Read reference case.
    case = read_matpower_case(path)

    # Convert into APSA network.
    network = convert_to_network(case)

    # -----------------------------------------------------
    # 5.1 APSA SOLUTION
    # -----------------------------------------------------

    apsa = solve_load_flow(
        network,
        tolerance=tolerance,
        max_iterations=max_iterations,
    )

    if not apsa.converged:
        raise RuntimeError(
            f"APSA failed for {path.name}: "
            f"{apsa.message}"
        )

    # -----------------------------------------------------
    # 5.2 PYPOWER REFERENCE SOLUTION
    # -----------------------------------------------------

    options = ppoption(
        PF_ALG=1,
        PF_TOL=1e-10,
        PF_MAX_IT=50,
        ENFORCE_Q_LIMS=0,
        VERBOSE=0,
        OUT_ALL=0,
    )

    reference, success = runpf(
        case,
        options,
    )

    if not success:
        raise RuntimeError(
            f"PYPOWER failed for {path.name}"
        )

    # -----------------------------------------------------
    # 5.3 COMPARE BUS VOLTAGES
    # -----------------------------------------------------

    reference_buses = {
        int(row[0]): row
        for row in reference["bus"]
    }

    vm_errors = []
    angle_errors = []

    for bus in network.buses:

        i = apsa.bus_index[bus.number]

        ref_row = reference_buses[
            bus.number
        ]

        # Voltage magnitude error.
        vm_error = abs(
            apsa.vm[i] - ref_row[7]
        )

        vm_errors.append(vm_error)

        # Wrapped angular difference.
        angle_error = abs(
            (
                apsa.va[i]
                - ref_row[8]
                + 180.0
            ) % 360.0 - 180.0
        )

        angle_errors.append(
            angle_error
        )

    # -----------------------------------------------------
    # 5.4 APSA BRANCH LOSSES
    # -----------------------------------------------------

    apsa_flows = calculate_branch_flows(
        network,
        apsa,
    )

    apsa_p_loss = (
        apsa_flows.total_p_loss
    )

    # -----------------------------------------------------
    # 5.5 PYPOWER BRANCH LOSSES
    # -----------------------------------------------------

    # PYPOWER solved branch matrix:
    # column 13 = Pf
    # column 15 = Pt
    #
    # Total active branch loss = sum(Pf + Pt)

    reference_p_loss = float(
        np.sum(
            reference["branch"][:, 13]
            + reference["branch"][:, 15]
        )
    )

    # -----------------------------------------------------
    # 5.6 CALCULATE ERRORS
    # -----------------------------------------------------

    max_vm_error = float(
        max(vm_errors)
    )

    max_angle_error = float(
        max(angle_errors)
    )

    p_loss_error = abs(
        apsa_p_loss
        - reference_p_loss
    )

    # -----------------------------------------------------
    # 5.7 DATASET HASH
    # -----------------------------------------------------

    file_hash = sha256(
        path.read_bytes()
    ).hexdigest()

    return ValidationResult(
        case_name=path.stem,
        buses=len(network.buses),
        branches=(
            len(network.lines)
            + len(network.transformers)
        ),
        apsa_converged=True,
        reference_converged=True,
        apsa_iterations=apsa.iterations,
        max_vm_error=max_vm_error,
        max_angle_error=max_angle_error,
        apsa_p_loss=float(
            apsa_p_loss
        ),
        reference_p_loss=float(
            reference_p_loss
        ),
        p_loss_error=float(
            p_loss_error
        ),
        final_mismatch=float(
            apsa.mismatch
        ),
        sha256_hash=file_hash,
    )


# ---------------------------------------------------------
# 6. VALIDATION ACCEPTANCE CRITERIA
# ---------------------------------------------------------

def passes_validation(result):
    """
    Apply Module 8 numerical acceptance criteria.

    These are project tolerances, not official
    IEEE benchmark acceptance thresholds.
    """

    return (
        result.apsa_converged
        and result.reference_converged
        and result.max_vm_error < 1e-5
        and result.max_angle_error < 1e-3
        and result.p_loss_error < 1e-3
        and result.final_mismatch < 1e-8
    )
