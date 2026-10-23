"""Offline tests for the live-test helper, so its classification is verified without a battery."""

from unittest.mock import AsyncMock, MagicMock

from modbus_connection import ModbusError
import pytest

from mygrid_modbus import MyGridError, UnsupportedMapError
from tests.live.live_device import INCOMPATIBLE, UNAVAILABLE, UNSUPPORTED_MAP, LiveDevice


@pytest.mark.parametrize(
    ("error", "label"),
    [
        (UnsupportedMapError("map 3"), UNSUPPORTED_MAP),
        (MyGridError("bad status"), INCOMPATIBLE),
        (ModbusError("no response"), UNAVAILABLE),
        (ConnectionRefusedError("refused"), UNAVAILABLE),
        (TimeoutError(), UNAVAILABLE),
    ],
)
async def test_failures_are_classified(error: Exception, label: str) -> None:
    request = AsyncMock(side_effect=error)
    with pytest.raises(pytest.fail.Exception) as raised:
        await LiveDevice(MagicMock()).fetch("read", request)
    assert label in str(raised.value)


async def test_success_passes_through() -> None:
    assert await LiveDevice(MagicMock()).fetch("read", AsyncMock(return_value=42)) == 42
