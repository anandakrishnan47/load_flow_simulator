
"""
Module 3: Power injection and mismatch calculations.

Power sign convention:
    Positive P, Q = injection into the network
    Generation = positive
    Consumption = negative

Voltage and calculated power use per-unit values.
Generator and load data use MW and MVAr.

Supported load models:
    PQ  - Constant power
    Z   - Constant impedance
    I   - Constant current
    ZIP - Combined impedance/current/power

ZIP coefficients use the order:
    (Z fraction, I fraction, P fraction)

For a ZIP load:
    P(V) = P0 * (a_p*V^2 + b_p*V + c_p)
    Q(V) = Q0 * (a_q*V^2 + b_q*V + c_q)

Voltage-dependent specified injections:
    Pspec(V) = Pgen - Pload(V)
    Qspec(V) = Qgen - Qload(V)
"""

import numpy as np

from loadflow.models import Network


def calculate_power(ybus, vm, va):
    """
    Calculate bus active and reactive power injections.

    Parameters
    ----------
    ybus : sparse matrix or numpy.ndarray
        Bus admittance matrix in per unit.
    vm : array_like
        Bus voltage magnitudes in per unit.
    va : array_like
        Bus voltage angles in radians.

    Returns
    -------
    p, q : numpy.ndarray
        Active and reactive injections in per unit.
    """

    vm = np.asarray(vm, dtype=float)
    va = np.asarray(va, dtype=float)

    if vm.ndim != 1 or va.ndim != 1:
        raise ValueError(
            "Voltage arrays must be 1D"
        )

    if vm.shape != va.shape:
        raise ValueError(
            "Voltage array sizes must match"
        )

    n = len(vm)

    if ybus.shape != (n, n):
        raise ValueError(
            "Ybus dimensions do not match"
        )

    if not np.all(np.isfinite(vm)):
        raise ValueError(
            "Invalid voltage magnitude"
        )

    if not np.all(np.isfinite(va)):
        raise ValueError(
            "Invalid voltage angle"
        )

    if np.any(vm <= 0):
        raise ValueError(
            "Voltage magnitudes must be positive"
        )

    voltage = vm * np.exp(1j * va)

    current = ybus @ voltage

    power = voltage * np.conj(current)

    return power.real, power.imag


def _zip_coefficients(load):
    """
    Return active and reactive ZIP coefficients.

    Coefficient ordering:
        (constant impedance,
         constant current,
         constant power)

    Returns
    -------
    zip_p, zip_q : tuple
    """

    model = str(load.model).upper()

    if model == "PQ":
        zip_p = (0.0, 0.0, 1.0)
        zip_q = (0.0, 0.0, 1.0)

    elif model == "Z":
        zip_p = (1.0, 0.0, 0.0)
        zip_q = (1.0, 0.0, 0.0)

    elif model == "I":
        zip_p = (0.0, 1.0, 0.0)
        zip_q = (0.0, 1.0, 0.0)

    elif model == "ZIP":
        zip_p = tuple(load.zip_p)
        zip_q = tuple(load.zip_q)

    else:
        raise ValueError(
            f"Unsupported load model: {load.model}"
        )

    for name, coeff in (
        ("Active", zip_p),
        ("Reactive", zip_q),
    ):

        if len(coeff) != 3:
            raise ValueError(
                f"{name} ZIP coefficients "
                "must contain three values"
            )

        if not np.all(np.isfinite(coeff)):
            raise ValueError(
                f"{name} ZIP coefficients "
                "must be finite"
            )

        if not np.isclose(
            sum(coeff),
            1.0,
            atol=1e-9,
            rtol=0.0,
        ):
            raise ValueError(
                f"{name} ZIP coefficients "
                "must sum to 1"
            )

    return zip_p, zip_q


def calculate_load_power(
    network: Network,
    bus_index,
    vm,
):
    """
    Calculate voltage-dependent load consumption.

    Parameters
    ----------
    network : Network
        Power-system network.

    bus_index : dict
        Mapping from bus number to array index.

    vm : array_like
        Voltage magnitudes in per unit.

    Returns
    -------
    p_load : numpy.ndarray
        Active load consumption in per unit.

    q_load : numpy.ndarray
        Reactive load consumption in per unit.

    dp_load_dv : numpy.ndarray
        Active load derivative in pu/pu.

    dq_load_dv : numpy.ndarray
        Reactive load derivative in pu/pu.
    """

    if network.base_mva <= 0:
        raise ValueError(
            "Base MVA must be positive"
        )

    vm = np.asarray(vm, dtype=float)

    n = len(bus_index)

    if vm.shape != (n,):
        raise ValueError(
            "Voltage dimensions do not match"
        )

    if not np.all(np.isfinite(vm)):
        raise ValueError(
            "Invalid voltage magnitude"
        )

    if np.any(vm <= 0):
        raise ValueError(
            "Voltage magnitudes must be positive"
        )

    p_load = np.zeros(n, dtype=float)
    q_load = np.zeros(n, dtype=float)

    dp_load_dv = np.zeros(n, dtype=float)
    dq_load_dv = np.zeros(n, dtype=float)

    for load in network.loads:

        if not load.in_service:
            continue

        if load.bus not in bus_index:
            raise ValueError(
                f"Load bus {load.bus} is inactive"
            )

        i = bus_index[load.bus]

        v = vm[i]

        zip_p, zip_q = _zip_coefficients(load)

        ap, bp, cp = zip_p
        aq, bq, cq = zip_q

        p0 = load.pd / network.base_mva
        q0 = load.qd / network.base_mva

        # Voltage-dependent load power.

        p_factor = (
            ap * v**2
            + bp * v
            + cp
        )

        q_factor = (
            aq * v**2
            + bq * v
            + cq
        )

        p_load[i] += p0 * p_factor
        q_load[i] += q0 * q_factor

        # Derivatives with respect to voltage.

        dp_load_dv[i] += (
            p0 * (2.0 * ap * v + bp)
        )

        dq_load_dv[i] += (
            q0 * (2.0 * aq * v + bq)
        )

    return (
        p_load,
        q_load,
        dp_load_dv,
        dq_load_dv,
    )


def specified_power(
    network: Network,
    bus_index,
    vm=None,
):
    """
    Calculate specified net bus injections.

    Pspec(V) = Pgen - Pload(V)
    Qspec(V) = Qgen - Qload(V)

    Parameters
    ----------
    vm : array_like, optional
        Bus voltage magnitudes.

        If omitted, nominal voltage (1 pu)
        is used for load calculations.

    Returns
    -------
    p_spec, q_spec : numpy.ndarray
        Specified net injections in per unit.
    """

    if network.base_mva <= 0:
        raise ValueError(
            "Base MVA must be positive"
        )

    n = len(bus_index)

    if vm is None:
        vm = np.ones(n, dtype=float)
    else:
        vm = np.asarray(vm, dtype=float)

    p_spec = np.zeros(n, dtype=float)
    q_spec = np.zeros(n, dtype=float)

    # Generator injections.

    for gen in network.generators:

        if not gen.in_service:
            continue

        if gen.bus not in bus_index:
            raise ValueError(
                f"Generator bus {gen.bus} is inactive"
            )

        i = bus_index[gen.bus]

        p_spec[i] += (
            gen.pg / network.base_mva
        )

        q_spec[i] += (
            gen.qg / network.base_mva
        )

    # Voltage-dependent load consumption.

    p_load, q_load, _, _ = calculate_load_power(
        network,
        bus_index,
        vm,
    )

    p_spec -= p_load
    q_spec -= q_load

    return p_spec, q_spec


def get_bus_types(
    network: Network,
    bus_index,
):
    """
    Return bus indices grouped by type.

    Uses explicit bus types defined in Module 1.

    Returns
    -------
    slack, pv, pq : numpy.ndarray
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
    ybus,
    vm,
    va,
    p_spec,
    q_spec,
    pv,
    pq,
):
    """
    Calculate the Newton-Raphson mismatch vector.

    Ordering:
        Active mismatches at PV and PQ buses.
        Reactive mismatches at PQ buses.

    Returns
    -------
    mismatch : numpy.ndarray
    p_calc : numpy.ndarray
    q_calc : numpy.ndarray
    """

    p_calc, q_calc = calculate_power(
        ybus,
        vm,
        va,
    )

    p_spec = np.asarray(
        p_spec,
        dtype=float,
    )

    q_spec = np.asarray(
        q_spec,
        dtype=float,
    )

    pv = np.asarray(pv, dtype=int)
    pq = np.asarray(pq, dtype=int)

    n = len(p_calc)

    if p_spec.shape != (n,):
        raise ValueError(
            "Specified active power dimensions "
            "do not match"
        )

    if q_spec.shape != (n,):
        raise ValueError(
            "Specified reactive power dimensions "
            "do not match"
        )

    if np.any(pv < 0) or np.any(pv >= n):
        raise ValueError(
            "Invalid PV bus index"
        )

    if np.any(pq < 0) or np.any(pq >= n):
        raise ValueError(
            "Invalid PQ bus index"
        )

    all_indices = np.concatenate(
        (pv, pq)
    )

    if len(np.unique(all_indices)) != (
        len(all_indices)
    ):
        raise ValueError(
            "Duplicate PV/PQ bus indices"
        )

    delta_p = (
        p_spec[all_indices]
        - p_calc[all_indices]
    )

    delta_q = (
        q_spec[pq]
        - q_calc[pq]
    )

    mismatch = np.concatenate(
        (delta_p, delta_q)
    )

    return mismatch, p_calc, q_calc


def maximum_mismatch(mismatch):
    """
    Return infinity norm of mismatch vector.
    """

    mismatch = np.asarray(
        mismatch,
        dtype=float,
    )

    if mismatch.size == 0:
        return 0.0

    return float(
        np.max(np.abs(mismatch))
    )
