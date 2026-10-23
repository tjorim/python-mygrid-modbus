"""A ModuleTwo device composed of a typed battery component."""

from asyncio import Lock, timeout
from collections.abc import Iterable

from modbus_connection import ModbusUnit
from modbus_connection.model import Device, Raw, UpdateReport

from .battery import Battery, validate_power
from .data import BatteryData
from .exceptions import InvalidSetpointError, MyGridError

COMPONENTS = ("battery",)


class MyGridDevice(Device):
    """Caller-owned transport, typed fields, one block per poll, no write retry."""

    def __init__(self, unit: ModbusUnit) -> None:
        super().__init__(unit)
        self.battery = Battery(unit)
        self._lock = Lock()
        self._snapshot: BatteryData | None = None

    async def _async_setup(self) -> None:
        """The device states its timing needs; the connection owner resolves them."""
        self.modbus_unit.require_timeout(3)

    @property
    def snapshot(self) -> BatteryData:
        """The last fully validated snapshot; inspect the poll report for freshness."""
        if self._snapshot is None:
            raise MyGridError("No valid battery snapshot yet")
        return self._snapshot

    async def _update(self) -> UpdateReport:
        report = await self.async_poll(COMPONENTS)
        if "battery" in report.updated:
            self._snapshot = self.battery.snapshot()
        return report

    async def async_update(self) -> UpdateReport:
        """Refresh the component and report success or a per-component failure."""
        async with self._lock, timeout(12):
            return await self._update()

    async def _read(self) -> BatteryData:
        report = await self._update()
        if report.failed:
            raise next(iter(report.failed.values()))
        return self.snapshot

    async def async_read(self) -> BatteryData:
        """Convenience snapshot read; never write or close the connection."""
        async with self._lock, timeout(12):
            return await self._read()

    async def async_set_power(self, watts: float) -> BatteryData:
        """Read fresh limits, write once through the field, return confirmed state."""
        validate_power(watts)
        async with self._lock, timeout(12):
            current = await self._read()
            if not -current.max_discharge <= watts <= current.max_charge:
                raise InvalidSetpointError("Power exceeds current battery limits")
            await self.battery.write("power_setpoint", watts)
            return await self._read()

    async def async_restart(self) -> None:
        """Send one restart command through its declared writable field."""
        async with self._lock, timeout(12):
            await self.battery.write("restart", 1)

    async def async_read_raw(self, names: Iterable[str] = COMPONENTS) -> Raw:
        """Fresh replayable raw words, without changing the validated snapshot."""
        async with self._lock, timeout(12):
            return await super().async_read_raw(names)
