
"""
Module 3: Power injection and mismatch calculations.

Power sign convention:
    Positive P, Q = injection into the network
    Generation = positive
    Consumption = negative

Voltage and calculated power use per-unit values.
Generator and load data use MW and MVAr.
"""

import numpy as np
from scipy.sparse import issparse

from loadflow.models import Network


def calculate_power(ybus, vm, va):
    """
    Calculate bus active and reactive power injections.

    Parameters
    ----------
    ybus : sparse matrix or numpy array
        Bus admittance matrix in per unit.
    vm : array_like
        Bus voltage magnitudes in per unit.
    va : array_like
        Bus voltage angles in radians.

    Returns
    -------
    p : numpy.ndarray
        Active power injections in per unit.
    q : numpy.ndarray
        Reactive power injections in per unit.
    """
    vm = np.asarray(vm, dtype=float)
    va = np.asarray(va, dtype=float)

    if vm.ndim != 1 or va.ndim != 1:
        raise ValueError("Voltage arrays must be 1D")

    if vm.shape != va.shape:
        raise ValueError("Voltage array sizes must match")

    n = len(vm)

    if ybus.shape != (n, n):
        raise ValueError("Ybus dimensions do not match")

    if not np.all(np.isfinite(vm)):
        raise ValueError("Invalid voltage magnitude")

    if not np.all(np.isfinite(va)):
        raise ValueError("Invalid voltage angle")

    if np.any(vm <= 0):
        raise ValueError("Voltage magnitudes must be positive")

    # Convert polar voltages to complex form.
    voltage = vm * np.exp(1j * va)

    # Bus current injections.
    current = ybus @ voltage

    # Complex power: S = V * conjugate(I)
    power = voltage * np.conj(current)

    return power.real, power.imag


def specified_power(network: Network, bus_index):
    """
    Calculate specified net bus injections.

    Pspec = (generation - load) / base_mva
    Qspec = (generation - load) / base_mva

    Only constant-power loads are supported here.
    """
    if network.base_mva <= 0:
        raise ValueError("Base MVA must be positive")

    n = len(bus_index)

    p_spec = np.zeros(n, dtype=float)
    q_spec = np.zeros(n, dtype=float)

    # Add generator power injections.
    for gen in network.generators:
        if not gen.in_service:
            continue

        if gen.bus not in bus_index:
            raise ValueError(
                f"Generator bus {gen.bus} is inactive"
            )

        i = bus_index[gen.bus]

        p_spec[i] += gen.pg / network.base_mva
        q_spec[i] += gen.qg / network.base_mva

    # Subtract load consumption.
    for load in network.loads:
        if not load.in_service:
            continue

        if load.bus not in bus_index:
            raise ValueError(
                f"Load bus {load.bus} is inactive"
            )

        if load.model != "PQ":
            raise NotImplementedError(
                "Voltage-dependent Z/ZIP loads "
                "will be implemented later"
            )

        i = bus_index[load.bus]

        p_spec[i] -= load.pd / network.base_mva
        q_spec[i] -= load.qd / network.base_mva

    return p_spec, q_spec


def get_bus_types(network: Network, bus_index):
    """
    Return bus indices grouped by type.

    Uses the explicit bus types in Module 1.
    Automatic bus-type assignment comes later.
    """
    slack = []
    pv = []
    pq = []

    for bus in network.buses:
        if not bus.in_service:
            continue

        i = bus_index[bus.number]

        if bus.bus_type == "Slack":
            slack.append(i)

        elif bus.bus_type == "PV":
            pv.append(i)

        elif bus.bus_type == "PQ":
            pq.append(i)

        else:
            raise ValueError(
                f"Invalid bus type: {bus.bus_type}"
            )

    if len(slack) != 1:
        raise ValueError(
            "Exactly one slack bus is required"
        )

    return (
        np.array(slack, dtype=int),
        np.array(pv, dtype=int),
        np.array(pq, dtype=int),
    )


def calculate_mismatch(
    ybus, vm, va, p_spec, q_spec, pv, pq
):
    """
    Calculate the Newton-Raphson mismatch vector.

    Ordering:
        Active power mismatches at PV and PQ buses
        Reactive power mismatches at PQ buses

    Returns
    -------
    mismatch : numpy.ndarray
    p_calc : numpy.ndarray
    q_calc : numpy.ndarray
    """
    p_calc, q_calc = calculate_power(
        ybus, vm, va
    )

    p_spec = np.asarray(p_spec, dtype=float)
    q_spec = np.asarray(q_spec, dtype=float)
    pv = np.asarray(pv, dtype=int)
    pq = np.asarray(pq, dtype=int)

    n = len(p_calc)

    if p_spec.shape != (n,) or q_spec.shape != (n,):
        raise ValueError(
            "Specified power dimensions do not match"
        )

    if np.any(pv < 0) or np.any(pv >= n):
        raise ValueError("Invalid PV bus index")

    if np.any(pq < 0) or np.any(pq >= n):
        raise ValueError("Invalid PQ bus index")

    if len(set(pv.tolist() + pq.tolist())) != (
        len(pv) + len(pq)
    ):
        raise ValueError("Duplicate PV/PQ bus indices")

    p_indices = np.concatenate((pv, pq))

    delta_p = p_spec[p_indices] - p_calc[p_indices]
    delta_q = q_spec[pq] - q_calc[pq]

    mismatch = np.concatenate(
        (delta_p, delta_q)
    )

    return mismatch, p_calc, q_calc


def maximum_mismatch(mismatch):
    """Return infinity norm of the mismatch vector."""
    mismatch = np.asarray(mismatch, dtype=float)

    if mismatch.size == 0:
        return 0.0

    return float(np.max(np.abs(mismatch)))
