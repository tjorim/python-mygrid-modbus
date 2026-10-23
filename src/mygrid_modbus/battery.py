"""ModuleTwo map 2: one contiguous holding-register component."""

import math
from typing import Any, override

from modbus_connection.model import Component, gauge, integer, uint32

from .const import MAP_VERSION
from .data import BatteryData
from .exceptions import InvalidSetpointError, MyGridError, UnsupportedMapError

POWER_STEP = 100  # W per register unit
MIN_SETPOINT = -32768 * POWER_STEP
MAX_SETPOINT = 32767 * POWER_STEP
MAX_STATUS = 2  # 0 normal, 1 fault, 2 telemetry stale
MAX_SOC = 100


def validate_power(value: float) -> float:
    """Return ``value`` if it fits a signed I16 register in exact 100 W increments."""
    if not math.isfinite(value) or value % POWER_STEP or not MIN_SETPOINT <= value <= MAX_SETPOINT:
        msg = "Power must be a signed 16-bit multiple of 100 W"
        raise InvalidSetpointError(msg)
    return value


def validate_restart(value: int) -> int:
    """Only the documented restart command is permitted."""
    if value != 1:
        msg = "Restart requires value 1"
        raise ValueError(msg)
    return value


class Battery(Component):
    """Typed map; the planner pools the whole documented 0-17 range once."""

    register_ranges = ((0, 17),)
    max_span = 18

    map_version = integer(0, signed=False)
    """Register-map version; only 2 is supported."""
    state_of_charge = integer(1, signed=False, unit="%")
    """State of charge, invalid while status is telemetry stale."""
    power_setpoint = gauge(2, 100, unit="W", writable=validate_power)
    """Accepted power request; positive charges and negative discharges."""
    max_charge = gauge(3, 100, signed=False, unit="W")
    """Current maximum charge request."""
    max_discharge = gauge(4, 100, signed=False, unit="W")
    """Current maximum discharge magnitude, expressed positively."""
    power = integer(5, unit="W")
    """Measured power, invalid while status is telemetry stale."""
    status = integer(6, signed=False)
    """0 normal, 1 fault, 2 telemetry stale."""
    fault_flags = uint32(7, word_order="little")
    """All 32 fault bits, low word first; unknown bits are preserved."""
    restart = integer(9, signed=False, writable=validate_restart)
    """Write 1 to restart; reads return zero."""
    stored_energy = uint32(10, word_order="little", unit="Wh")
    """Energy currently stored."""
    lifetime_charged = uint32(12, word_order="little", unit="Wh")
    """Lifetime charged energy."""
    lifetime_discharged = uint32(14, word_order="little", unit="Wh")
    """Lifetime discharged energy."""
    total_capacity = uint32(16, word_order="little", unit="Wh")
    """Reported full capacity."""

    def snapshot(self) -> BatteryData:
        """Validate the map and suppress only explicitly stale measurements."""
        if self.map_version != MAP_VERSION:
            msg = f"Unsupported map version: {self.map_version}"
            raise UnsupportedMapError(msg)
        if self.status not in range(MAX_STATUS + 1):
            msg = "Invalid battery status"
            raise MyGridError(msg)
        stale = self.status == MAX_STATUS
        soc = self.state_of_charge
        if not stale and (soc is None or not 0 <= soc <= MAX_SOC):
            msg = "Invalid state of charge"
            raise MyGridError(msg)
        # The fixed map has no unimplemented-value sentinels. After a successful
        # full update every field is numeric, including zero-valued registers.
        values: dict[str, Any] = {name: getattr(self, name) for name in self.declared_fields}
        if any(value is None for value in values.values()):
            msg = "Incomplete battery map"
            raise MyGridError(msg)
        return BatteryData(
            map_version=MAP_VERSION,
            state_of_charge=None if stale else soc,
            setpoint=int(values["power_setpoint"]),
            max_charge=int(values["max_charge"]),
            max_discharge=int(values["max_discharge"]),
            power=None if stale else self.power,
            status=int(values["status"]),
            fault_flags=None if stale else self.fault_flags,
            stored_energy=int(values["stored_energy"]),
            lifetime_charged=int(values["lifetime_charged"]),
            lifetime_discharged=int(values["lifetime_discharged"]),
            total_capacity=int(values["total_capacity"]),
        )

    @override
    async def async_update(self, *, notify: bool = True) -> None:
        """Validate before notifying consumers of a successful component read."""
        await super().async_update(notify=False)
        self.snapshot()
        if notify:
            self.notify()
