"""Failure-classifying wrapper for the live smoke tests (modelled on pyrail's ``LiveApi``).

A live failure means one of three different things, so each gets its own message: the
battery cannot be reached, it answers with data the library rejects (a firmware or register
map change), or the request itself was refused. The helper only ever reads.
"""

from collections.abc import Awaitable, Callable

from modbus_connection import ModbusError
import pytest

from mygrid_modbus import MyGridDevice, MyGridError, UnsupportedMapError

UNAVAILABLE = "DEVICE UNAVAILABLE"
INCOMPATIBLE = "DEVICE INCOMPATIBLE"
UNSUPPORTED_MAP = "DEVICE USES AN UNSUPPORTED REGISTER MAP"


class LiveDevice:
    """A read-only battery client whose failures fail the test with a classified message."""

    def __init__(self, device: MyGridDevice) -> None:
        """Wrap the given device."""
        self.device = device

    async def fetch[T](self, what: str, request: Callable[[MyGridDevice], Awaitable[T]]) -> T:
        """Run one read, converting every failure into a classified test failure."""
        try:
            return await request(self.device)
        except UnsupportedMapError as err:
            pytest.fail(f"{UNSUPPORTED_MAP}: '{what}': {err}", pytrace=False)
        except MyGridError as err:
            pytest.fail(f"{INCOMPATIBLE}: '{what}' returned unusable data: {err}", pytrace=False)
        except (ModbusError, OSError, TimeoutError) as err:
            pytest.fail(f"{UNAVAILABLE}: '{what}': {type(err).__name__}: {str(err)[:300]}", pytrace=False)
