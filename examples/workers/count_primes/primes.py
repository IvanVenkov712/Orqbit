"""Prime counting without HTTP or worker configuration."""

from collections.abc import Iterator
from math import isqrt

MAX_LIMIT = 100_000_000


def validate_limit(params: dict) -> int:
    limit = params.get("limit")
    if type(limit) is not int or not 0 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be an integer between 0 and {MAX_LIMIT}")
    return limit


def is_prime(number: int) -> bool:
    if number < 2:
        return False
    if number == 2:
        return True
    if number % 2 == 0:
        return False
    for divisor in range(3, isqrt(number) + 1, 2):
        if number % divisor == 0:
            return False
    return True


def count_prime_batches(limit: int, batch_size: int) -> Iterator[int]:
    """Yield the cumulative count after each bounded batch."""
    count = 0
    for start in range(2, limit + 1, batch_size):
        stop = min(start + batch_size, limit + 1)
        count += sum(is_prime(number) for number in range(start, stop))
        yield count
