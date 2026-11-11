import pytest

from primes import count_prime_batches, is_prime, validate_limit


@pytest.mark.parametrize(
    "number,expected",
    [
        (-1, False),
        (0, False),
        (1, False),
        (2, True),
        (3, True),
        (4, False),
        (9, False),
        (25, False),
        (97, True),
    ],
)
def test_primality(number, expected):
    assert is_prime(number) is expected


@pytest.mark.parametrize(
    "limit,expected",
    [
        (0, 0),
        (1, 0),
        (2, 1),
        (3, 2),
        (10, 4),
        (100, 25),
        (10_000, 1229),
    ],
)
@pytest.mark.parametrize("batch_size", [1, 7, 1000])
def test_count_includes_upper_bound_and_is_independent_of_batch_size(
    limit, expected, batch_size
):
    counts = list(count_prime_batches(limit, batch_size))
    assert (counts[-1] if counts else 0) == expected


def test_batches_yield_cumulative_counts():
    assert list(count_prime_batches(12, 4)) == [3, 4, 5]


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"limit": True},
        {"limit": "10"},
        {"limit": 2.5},
        {"limit": -1},
        {"limit": None},
        {"limit": 100_000_001},
    ],
)
def test_invalid_limit(params):
    with pytest.raises(ValueError, match="limit must be an integer"):
        validate_limit(params)
