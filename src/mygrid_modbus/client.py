"""Typed, asynchronous ModuleTwo protocol client; independent of Home Assistant."""

import math
from asyncio import CancelledError, Lock, timeout
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

MAP_VERSION = 2
UNIT_ID = 1
REGISTER_COUNT = 18

FAULTS: dict[int, str] = {
    0: "battery_communication",
    1: "internal_communication",
    2: "over_voltage",
    3: "under_voltage",
    4: "charge_over_current",
    5: "discharge_over_current",
    6: "over_temperature",
    7: "under_temperature",
    8: "cell_imbalance",
    9: "hardware_protection",
    11: "other",
    12: "voltage_sensor",
    13: "temperature_sensor",
    14: "current_sensor",
    15: "relay",
    19: "ac_parallel",
    20: "solar_communication",
    21: "forced_charge",
    23: "parallel_power",
    26: "fuse",
    27: "precharge",
    29: "temperature_difference",
}


class MyGridError(Exception):
    """Communication failed or the device returned an invalid response."""


class UnsupportedMapError(MyGridError):
    """The device has an unsupported register map."""


class InvalidSetpointError(MyGridError):
    """A command cannot be represented or exceeds current limits."""


def signed16(value: int) -> int:
    """Interpret a Modbus word as a signed integer."""
    return value - 65536 if value & 0x8000 else value


def unsigned32(low: int, high: int) -> int:
    """Decode the manual's low-word-first ordering."""
    return low | (high << 16)


@dataclass(frozen=True)
class BatteryData:
    """One coherent snapshot; stale measurements are explicitly unknown."""

    map_version: int
    state_of_charge: int | None
    setpoint: int
    max_charge: int
    max_discharge: int
    power: int | None
    status: int
    fault_flags: int | None
    stored_energy: int
    lifetime_charged: int
    lifetime_discharged: int
    total_capacity: int

    @property
    def active_faults(self) -> list[str] | None:
        """Decode known bits without discarding unknown bits from the raw word."""
        if self.fault_flags is None:
            return None
        return [name for bit, name in FAULTS.items() if self.fault_flags & (1 << bit)]


def decode_registers(registers: Sequence[int]) -> BatteryData:
    """Validate and decode exactly the documented map, using watts and Wh."""
    if len(registers) != REGISTER_COUNT or any(
        type(word) is not int or not 0 <= word <= 65535 for word in registers
    ):
        raise MyGridError("Invalid register response")
    if registers[0] != MAP_VERSION:
        raise UnsupportedMapError(f"Unsupported map version: {registers[0]}")
    status = registers[6]
    if status not in (0, 1, 2):
        raise MyGridError("Invalid battery status")
    stale = status == 2
    if not stale and registers[1] > 100:
        raise MyGridError("Invalid state of charge")
    return BatteryData(
        map_version=registers[0],
        state_of_charge=None if stale else registers[1],
        setpoint=signed16(registers[2]) * 100,
        max_charge=registers[3] * 100,
        max_discharge=registers[4] * 100,
        power=None if stale else signed16(registers[5]),
        status=status,
        fault_flags=None if stale else unsigned32(registers[7], registers[8]),
        stored_energy=unsigned32(registers[10], registers[11]),
        lifetime_charged=unsigned32(registers[12], registers[13]),
        lifetime_discharged=unsigned32(registers[14], registers[15]),
        total_capacity=unsigned32(registers[16], registers[17]),
    )


class MyGridClient:
    """Own one TCP connection and serialize complete operations.

    Automatic reconnect and request retries are disabled in pymodbus so an
    uncertain write is never silently repeated. Each later operation may connect
    again, but it never carries a previous command with it.
    """

    def __init__(self, host: str, port: int = 502) -> None:
        self._client = AsyncModbusTcpClient(
            host, port=port, timeout=3, retries=0, reconnect_delay=0
        )
        self._lock = Lock()

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[None]:
        async with self._lock:
            try:
                # Includes connect, fresh limits, write and readback; no
                # unbounded wait when a peer accepts TCP but stops responding.
                async with timeout(12):
                    if not self._client.connected and not await self._client.connect():
                        raise MyGridError("Cannot connect to battery")
                    yield
            except (ModbusException, OSError, TimeoutError) as err:
                self._client.close()
                raise MyGridError("Battery communication failed") from err
            except (MyGridError, CancelledError):
                self._client.close()
                raise

    async def _read(self) -> BatteryData:
        response = await self._client.read_holding_registers(
            address=0, count=REGISTER_COUNT, device_id=UNIT_ID
        )
        if response.isError():
            raise MyGridError("Battery rejected register read")
        return decode_registers(response.registers)

    async def _write(self, address: int, value: int) -> None:
        response = await self._client.write_register(
            address=address, value=value, device_id=UNIT_ID
        )
        if (
            response.isError()
            or response.address != address
            or response.registers != [value]
        ):
            raise MyGridError("Battery did not confirm register write")

    async def async_read(self) -> BatteryData:
        """Read the map once; never issue a write."""
        async with self._session():
            return await self._read()

    async def async_set_power(self, watts: float) -> BatteryData:
        """Validate fresh limits, write once, then return confirmed device state."""
        if not math.isfinite(watts) or watts % 100 or not -3276800 <= watts <= 3276700:
            raise InvalidSetpointError(
                "Power must be a signed 16-bit multiple of 100 W"
            )
        async with self._session():
            current = await self._read()
            if not -current.max_discharge <= watts <= current.max_charge:
                raise InvalidSetpointError("Power exceeds current battery limits")
            await self._write(2, int(watts / 100) & 0xFFFF)
            return await self._read()

    async def async_restart(self) -> None:
        """Write the documented reboot command once, without retry."""
        async with self._session():
            await self._write(9, 1)

    async def async_close(self) -> None:
        """Close after any in-flight operation; do not change battery power."""
        async with self._lock:
            self._client.close()
