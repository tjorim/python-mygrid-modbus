"""Independent protocol fixtures; no Home Assistant or HA pytest plugin."""

import pytest


@pytest.fixture
def registers() -> list[int]:
    """Map includes signed power and low-word-first energy counters."""
    return [2, 82, 65528, 12, 10, 64736, 0, 0, 0, 0, 3000, 0, 7, 2, 9, 3, 5000, 0]
