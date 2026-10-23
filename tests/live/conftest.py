"""Fixtures for the live smoke tests, which read a real ModuleTwo over Modbus TCP.

Every test below tests/live is marked ``live`` and excluded from ordinary runs (see
``addopts`` in pyproject.toml). They are strictly read-only: no setpoint or restart is
ever sent. Run them with::

    MYGRID_HOST=192.168.0.15 uv run pytest -m live

Without ``MYGRID_HOST`` they are skipped. ``MYGRID_PORT`` overrides the default port 502.
"""

from collections.abc import AsyncIterator
import os

from modbus_connection import ModbusTcpParams
from modbus_connection.tmodbus import ModbusConnection
import pytest

from mygrid_modbus import UNIT_ID, MyGridDevice
from tests.live.live_device import LiveDevice


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every test in this directory as live so ordinary runs deselect it."""
    for item in items:
        if "tests/live/" in item.nodeid:
            item.add_marker(pytest.mark.live)


@pytest.fixture(scope="session")
def host() -> str:
    """Return the battery address, or skip when none is configured."""
    value = os.environ.get("MYGRID_HOST")
    if value is None or value == "":
        pytest.skip("set MYGRID_HOST to run the live smoke tests")
    return value


@pytest.fixture
async def live(host: str) -> AsyncIterator[LiveDevice]:
    """Provide a read-only device on its own connection, closed afterwards."""
    connection = ModbusConnection(ModbusTcpParams(host=host, port=int(os.environ.get("MYGRID_PORT", "502"))))
    try:
        yield LiveDevice(MyGridDevice(connection.for_unit(UNIT_ID)))
    finally:
        await connection.close()
