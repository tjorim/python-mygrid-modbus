"""Live smoke tests: check a real ModuleTwo still speaks register map 2.

They assert structure and internal consistency, never specific readings, and they never
write. Detailed behaviour, including every write path, is covered by the offline suite.
"""

from mygrid_modbus import MAP_VERSION, REGISTER_COUNT, BatteryData
from tests.live.live_device import LiveDevice

POWER_STEP = 100
KNOWN_STATUSES = (0, 1, 2)


async def test_snapshot_is_valid_and_consistent(live: LiveDevice) -> None:
    data: BatteryData = await live.fetch("read", lambda device: device.async_read())
    assert data.map_version == MAP_VERSION
    assert data.status in KNOWN_STATUSES
    if data.status != KNOWN_STATUSES[-1]:  # stale telemetry is reported as unknown, not zero
        assert data.state_of_charge is not None
        assert 0 <= data.state_of_charge <= 100
    assert data.max_charge >= 0
    assert data.max_discharge >= 0
    assert data.max_charge % POWER_STEP == 0
    assert data.max_discharge % POWER_STEP == 0
    assert data.setpoint % POWER_STEP == 0
    assert -data.max_discharge <= data.setpoint <= data.max_charge
    assert data.total_capacity > 0
    assert 0 <= data.stored_energy <= data.total_capacity


async def test_raw_registers_match_the_documented_map(live: LiveDevice) -> None:
    raw = await live.fetch("raw", lambda device: device.async_read_raw())
    registers = raw["holding"]
    assert sorted(registers) == list(range(REGISTER_COUNT))
    assert registers[0] == MAP_VERSION
    assert registers[9] == 0  # the reboot register always reads 0
