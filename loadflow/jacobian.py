
"""
Module 4: Analytical Newton-Raphson Jacobian.

Jacobian blocks:
    H = dP / d(delta)
    N = dP / d(V)
    M = dQ / d(delta)
    L = dQ / d(V)

State ordering:
    Voltage angles: PV buses, then PQ buses
    Voltage magnitudes: PQ buses

All voltage angles are in radians.
All electrical quantities are in per unit.

The Jacobian contains derivatives of calculated
power injections, not derivatives of mismatches.
"""

import numpy as np
from scipy.sparse import (
    issparse,
    coo_matrix,
    csr_matrix,
)

from loadflow.power import calculate_power


def build_jacobian(ybus, vm, va, pv, pq):
    """
    Construct the analytical sparse Jacobian.

    Parameters
    ----------
    ybus : scipy sparse matrix or numpy.ndarray
        Bus admittance matrix, in per unit.
    vm : array_like
        Bus voltage magnitudes, in per unit.
    va : array_like
        Bus voltage angles, in radians.
    pv : array_like
        PV bus indices in Ybus ordering.
    pq : array_like
        PQ bus indices in Ybus ordering.

    Returns
    -------
    jacobian : scipy.sparse.csr_matrix
        Reduced Newton-Raphson Jacobian.

    Jacobian row ordering:
        P equations at PV and PQ buses
        Q equations at PQ buses

    Jacobian column ordering:
        Angles at PV and PQ buses
        Magnitudes at PQ buses
    """

    vm = np.asarray(vm, dtype=float)
    va = np.asarray(va, dtype=float)
    pv = np.asarray(pv, dtype=int)
    pq = np.asarray(pq, dtype=int)

    if vm.ndim != 1 or va.ndim != 1:
        raise ValueError("Voltage arrays must be 1D")

    if vm.shape != va.shape:
        raise ValueError("Voltage array sizes must match")

    nbus = len(vm)

    if ybus.shape != (nbus, nbus):
        raise ValueError("Ybus dimensions do not match")

    if not np.all(np.isfinite(vm)):
        raise ValueError("Invalid voltage magnitude")

    if not np.all(np.isfinite(va)):
        raise ValueError("Invalid voltage angle")

    if np.any(vm <= 0):
        raise ValueError(
            "Voltage magnitudes must be positive"
        )

    if pv.ndim != 1 or pq.ndim != 1:
        raise ValueError("Bus index arrays must be 1D")

    p_buses = np.concatenate((pv, pq))

    if np.any(p_buses < 0) or np.any(p_buses >= nbus):
        raise ValueError("Invalid bus index")

    if len(np.unique(p_buses)) != len(p_buses):
        raise ValueError("Duplicate PV/PQ bus indices")

    n_angle = len(p_buses)
    n_pq = len(pq)
    n_state = n_angle + n_pq

    # Calculate P and Q injections using Module 3.
    p_calc, q_calc = calculate_power(
        ybus, vm, va
    )

    # Map original bus indices to reduced Jacobian
    # row and column positions.
    angle_pos = {
        int(bus): k
        for k, bus in enumerate(p_buses)
    }

    magnitude_pos = {
        int(bus): k
        for k, bus in enumerate(pq)
    }

    # Sparse triplet representation.
    rows = []
    cols = []
    values = []

    def add(row, col, value):
        if value != 0:
            rows.append(row)
            cols.append(col)
            values.append(value)

    # CSR enables efficient row-wise access.
    if issparse(ybus):
        y = ybus.tocsr()
    else:
        y = csr_matrix(
            np.asarray(ybus, dtype=complex)
        )

    # Diagonal elements of Ybus.
    diagonal = y.diagonal()

    # Process active-power equations at PV/PQ buses.
    for i in p_buses:
        i = int(i)

        row_p = angle_pos[i]

        gii = diagonal[i].real
        bii = diagonal[i].imag

        # Hii = dPi / d(delta_i)
        hii = -q_calc[i] - bii * vm[i] ** 2

        add(row_p, angle_pos[i], hii)

        # Nii = dPi / d(V_i), for PQ buses only.
        if i in magnitude_pos:
            nii = p_calc[i] / vm[i] + gii * vm[i]

            add(
                row_p,
                n_angle + magnitude_pos[i],
                nii,
            )

        # Off-diagonal H and N elements.
        start = y.indptr[i]
        end = y.indptr[i + 1]

        for k in range(start, end):
            j = int(y.indices[k])

            if i == j:
                continue

            yij = y.data[k]
            gij = yij.real
            bij = yij.imag

            angle = va[i] - va[j]

            cos_angle = np.cos(angle)
            sin_angle = np.sin(angle)

            # Hij = dPi / d(delta_j)
            if j in angle_pos:
                hij = vm[i] * vm[j] * (
                    gij * sin_angle
                    - bij * cos_angle
                )

                add(
                    row_p,
                    angle_pos[j],
                    hij,
                )

            # Nij = dPi / d(V_j)
            if j in magnitude_pos:
                nij = vm[i] * (
                    gij * cos_angle
                    + bij * sin_angle
                )

                add(
                    row_p,
                    n_angle + magnitude_pos[j],
                    nij,
                )

    # Process reactive-power equations at PQ buses.
    for i in pq:
        i = int(i)

        row_q = n_angle + magnitude_pos[i]

        gii = diagonal[i].real
        bii = diagonal[i].imag

        # Mii = dQi / d(delta_i)
        mii = p_calc[i] - gii * vm[i] ** 2

        add(
            row_q,
            angle_pos[i],
            mii,
        )

        # Lii = dQi / d(V_i)
        lii = q_calc[i] / vm[i] - bii * vm[i]

        add(
            row_q,
            n_angle + magnitude_pos[i],
            lii,
        )

        # Off-diagonal M and L elements.
        start = y.indptr[i]
        end = y.indptr[i + 1]

        for k in range(start, end):
            j = int(y.indices[k])

            if i == j:
                continue

            yij = y.data[k]
            gij = yij.real
            bij = yij.imag

            angle = va[i] - va[j]

            cos_angle = np.cos(angle)
            sin_angle = np.sin(angle)

            # Mij = dQi / d(delta_j)
            if j in angle_pos:
                mij = -vm[i] * vm[j] * (
                    gij * cos_angle
                    + bij * sin_angle
                )

                add(
                    row_q,
                    angle_pos[j],
                    mij,
                )

            # Lij = dQi / d(V_j)
            if j in magnitude_pos:
                lij = vm[i] * (
                    gij * sin_angle
                    - bij * cos_angle
                )

                add(
                    row_q,
                    n_angle + magnitude_pos[j],
                    lij,
                )

    jacobian = coo_matrix(
        (
            np.asarray(values, dtype=float),
            (rows, cols),
        ),
        shape=(n_state, n_state),
        dtype=float,
    ).tocsr()

    jacobian.sum_duplicates()
    jacobian.eliminate_zeros()

    return jacobian


def split_jacobian(jacobian, n_pv, n_pq):
    """
    Split reduced Jacobian into H, N, M, L blocks.
    """
    n_angle = n_pv + n_pq

    if jacobian.shape != (
        n_angle + n_pq,
        n_angle + n_pq,
    ):
        raise ValueError("Invalid Jacobian dimensions")

    h = jacobian[:n_angle, :n_angle]
    n = jacobian[:n_angle, n_angle:]
    m = jacobian[n_angle:, :n_angle]
    l = jacobian[n_angle:, n_angle:]

    return h.tocsr(), n.tocsr(), m.tocsr(), l.tocsr()
