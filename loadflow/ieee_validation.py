"""Module 8: MATPOWER IEEE benchmark import and PYPOWER validation.

Reads MATPOWER IEEE benchmark cases and validates load-flow results
against PYPOWER reference solutions.
"""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re

import numpy as np
from pypower.api import ppoption, runpf

from loadflow.models import (
    Network, Bus, Line, Transformer, Generator, Load, Shunt, ExternalGrid,
)
from loadflow.solver import solve_load_flow
from loadflow.branch_flows import calculate_branch_flows

CASE_NAMES = ("case14", "case30", "case57", "case118")


def _matrix(source, name):
    """Read a numeric MATPOWER matrix, stripping MATLAB comments."""
    match = re.search(rf"mpc\.{name}\s*=\s*\[(.*?)\]\s*;", source, flags=re.DOTALL)
    if match is None:
        raise ValueError(f"MATPOWER matrix '{name}' not found")
    rows = []
    for row in match.group(1).split(';'):
        row = re.sub(r'%[^\n]*', '', row).strip()
        if not row:
            continue
        values = np.fromstring(row.replace('\n', ' '), sep=' ')
        if values.size == 0:
            raise ValueError(f"Invalid numeric row in {name}")
        rows.append(values)
    if not rows:
        raise ValueError(f"Empty MATPOWER matrix: {name}")
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ValueError(f"Inconsistent column count in {name}")
    return np.vstack(rows)


def read_matpower_case(path):
    """Read MATPOWER version-2 case matrices and base MVA."""
    path = Path(path)
    source = path.read_text(encoding='utf-8')
    base_match = re.search(r'mpc\.baseMVA\s*=\s*([0-9.eE+-]+)\s*;', source)
    if base_match is None:
        raise ValueError('Missing MATPOWER baseMVA')
    base_mva = float(base_match.group(1))
    if not np.isfinite(base_mva) or base_mva <= 0:
        raise ValueError('Invalid MATPOWER baseMVA')
    bus = _matrix(source, 'bus')
    gen = _matrix(source, 'gen')
    branch = _matrix(source, 'branch')
    if bus.shape[1] < 13 or gen.shape[1] < 10 or branch.shape[1] < 13:
        raise ValueError('Unsupported MATPOWER column format')
    return {'version': '2', 'baseMVA': base_mva,
            'bus': bus, 'gen': gen, 'branch': branch}


def convert_to_network(case):
    """Convert MATPOWER case to APSA network with accurate Ybus modeling."""
    net = Network(base_mva=float(case['baseMVA']))
    type_map = {1: 'PQ', 2: 'PV', 3: 'Slack'}

    for row in case['bus']:
        number, kind = int(row[0]), int(row[1])
        if kind not in type_map:
            raise ValueError(f'Unsupported bus type {kind} at bus {number}')
        base_kv = float(row[9])
        if base_kv <= 0:
            base_kv = 1.0  # Nominal-voltage metadata only
        net.add_bus(Bus(number=number, name=f'Bus {number}', base_kv=base_kv,
                        bus_type=type_map[kind], vm=float(row[7]), va=float(row[8]),
                        vmin=float(row[12]), vmax=float(row[11])))
        if row[2] != 0 or row[3] != 0:
            net.add_load(Load(bus=number, pd=float(row[2]), qd=float(row[3])))
        if row[4] != 0 or row[5] != 0:
            net.add_shunt(Shunt(bus=number, gs=float(row[4]), bs=float(row[5])))

    grouped = {}
    for row in case['gen']:
        if int(row[7]) > 0:
            grouped.setdefault(int(row[0]), []).append(row)
    for number, generators in grouped.items():
        vg_values = [float(gen[5]) for gen in generators]
        if max(vg_values) - min(vg_values) > 1e-6:
            raise ValueError(f'Inconsistent generator voltage setpoints at bus {number}')
        net.add_generator(Generator(
            bus=number,
            pg=sum(float(gen[1]) for gen in generators),
            qg=sum(float(gen[2]) for gen in generators),
            vg=vg_values[0],
            qmin=sum(float(gen[4]) for gen in generators),
            qmax=sum(float(gen[3]) for gen in generators),
        ))

    slack_buses = [bus for bus in net.buses if bus.bus_type == 'Slack']
    if len(slack_buses) != 1:
        raise ValueError('Exactly one slack bus is required')
    slack = slack_buses[0]
    slack_vm = float(grouped[slack.number][0][5]) if slack.number in grouped else float(slack.vm)
    net.add_external_grid(ExternalGrid(bus=slack.number, vm=slack_vm, va=float(slack.va)))

    for row in case['branch']:
        if int(row[10]) <= 0:
            continue
        from_bus, to_bus = int(row[0]), int(row[1])
        r, x, b = float(row[2]), float(row[3]), float(row[4])
        raw_rating = float(row[5])
        if not np.isfinite(raw_rating) or raw_rating < 0:
            raise ValueError(f'Invalid MATPOWER rateA on branch {from_bus}-{to_bus}')
        # MATPOWER rateA=0 means no rating was supplied.
        rating = 1e12 if raw_rating == 0 else raw_rating
        tap, shift = float(row[8]), float(row[9])
        if tap == 0 and shift == 0:
            branch = Line(from_bus=from_bus, to_bus=to_bus,
                          r=r, x=x, b=b, rating_mva=rating)
            net.add_line(branch)
        else:
            effective_tap = tap if tap != 0 else 1.0
            branch = Transformer(
                from_bus=from_bus, to_bus=to_bus, r=r, x=x,
                rating_mva=rating, tap_ratio=effective_tap,
                phase_shift=shift, tap_side='from',
            )
            net.add_transformer(branch)
            # Preserve transformer line charging through equivalent shunts.
            if abs(b) > 1e-12:
                net.add_shunt(Shunt(bus=from_bus, gs=0.0,
                                    bs=b * net.base_mva / (2.0 * effective_tap**2)))
                net.add_shunt(Shunt(bus=to_bus, gs=0.0,
                                    bs=b * net.base_mva / 2.0))
    return net


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


def validate_case(path, tolerance=1e-8, max_iterations=50):
    """Compare APSA voltage/angle/loss solution with PYPOWER."""
    path = Path(path)
    case = read_matpower_case(path)
    network = convert_to_network(case)
    apsa = solve_load_flow(network, tolerance=tolerance, max_iterations=max_iterations)
    if not apsa.converged:
        raise RuntimeError(f'APSA failed for {path.name}: {apsa.message}')
    options = ppoption(PF_ALG=1, PF_TOL=1e-10, PF_MAX_IT=50,
                       ENFORCE_Q_LIMS=0, VERBOSE=0, OUT_ALL=0)
    reference, success = runpf(case, options)
    if not success:
        raise RuntimeError(f'PYPOWER failed for {path.name}')
    reference_buses = {int(row[0]): row for row in reference['bus']}
    vm_errors, angle_errors = [], []
    for bus in network.buses:
        i = apsa.bus_index[bus.number]
        ref_row = reference_buses[bus.number]
        vm_errors.append(abs(apsa.vm[i] - ref_row[7]))
        angle_errors.append(abs((apsa.va[i] - ref_row[8] + 180.0) % 360.0 - 180.0))
    apsa_p_loss = calculate_branch_flows(network, apsa).total_p_loss
    reference_p_loss = float(np.sum(reference['branch'][:, 13] + reference['branch'][:, 15]))
    return ValidationResult(
        case_name=path.stem, buses=len(network.buses),
        branches=len(network.lines) + len(network.transformers),
        apsa_converged=True, reference_converged=True,
        apsa_iterations=apsa.iterations,
        max_vm_error=float(max(vm_errors)), max_angle_error=float(max(angle_errors)),
        apsa_p_loss=float(apsa_p_loss), reference_p_loss=reference_p_loss,
        p_loss_error=float(abs(apsa_p_loss - reference_p_loss)),
        final_mismatch=float(apsa.mismatch),
        sha256_hash=sha256(path.read_bytes()).hexdigest(),
    )


def passes_validation(result):
    """Module 8 project numerical tolerances (not official IEEE limits)."""
    return (result.apsa_converged and result.reference_converged
            and result.max_vm_error < 1e-5
            and result.max_angle_error < 1e-3
            and result.p_loss_error < 1e-3
            and result.final_mismatch < 1e-8)
