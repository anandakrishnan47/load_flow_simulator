
"""
E4234 assignment acceptance tests.
"""

import pytest

from validate import (
    CASES,
    TOLERANCES,
    validate_one_case,
)


@pytest.mark.parametrize(
    "name,filename",
    list(CASES.items()),
)
def test_ieee_assignment_validation(name, filename):
    result = validate_one_case(name, filename)

    assert result["passed"], (
        f"{name} failed: "
        f"{result['checks']} "
        f"{result['metrics']}"
    )


def test_required_tolerances():
    assert TOLERANCES["mismatch"] == 1e-8
    assert TOLERANCES["voltage"] == 1e-4
    assert TOLERANCES["angle"] == 0.01
    assert TOLERANCES["branch"] == 0.01
    assert TOLERANCES["loss_percent"] == 0.1
    assert TOLERANCES["ieee118_iterations"] == 7
