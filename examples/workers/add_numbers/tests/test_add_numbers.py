import pytest

import worker


@pytest.mark.parametrize("numbers,total", [([2, 3, 5], 10), ([-2, 0.5], -1.5), ([], 0)])
def test_add_numbers(numbers, total):
    assert worker.add_numbers({"numbers": numbers}) == {"sum": total}


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"numbers": [True]},
        {"numbers": ["2"]},
        {"numbers": None},
        {"numbers": "123"},
        {"numbers": [float("nan")]},
        {"numbers": [float("inf")]},
        {"numbers": [float("-inf")]},
    ],
)
def test_add_numbers_rejects_invalid_input(params):
    with pytest.raises(ValueError):
        worker.add_numbers(params)


@pytest.mark.parametrize(
    ("numbers", "message"),
    [
        ([1e308, 1e308], "sum must be finite"),
        ([10**400, 1.0], "sum is outside the supported numeric range"),
    ],
)
def test_add_numbers_rejects_overflow(numbers, message):
    with pytest.raises(ValueError, match=message):
        worker.add_numbers({"numbers": numbers})
