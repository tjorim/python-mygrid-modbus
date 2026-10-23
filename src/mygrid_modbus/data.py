"""Immutable, validated battery readings in watts and watt-hours."""

from dataclasses import dataclass

from .const import FAULTS


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
