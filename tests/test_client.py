"""Device models exercised through the supplied in-memory Modbus backend."""

import asyncio
import json
from unittest.mock import patch

import pytest
from modbus_connection import ModbusConnectionError, ModbusTimeoutError
from modbus_connection.model import Component, Device

from mygrid_modbus import (
    FAULTS,
    InvalidSetpointError,
    MyGridDevice,
    MyGridError,
    UnsupportedMapError,
)


@pytest.fixture
def device(mock_modbus_unit, registers):
    mock_modbus_unit.holding[0] = registers
    return MyGridDevice(mock_modbus_unit)


async def test_component_and_single_block(device, mock_modbus_unit):
    assert isinstance(device, Device)
    assert isinstance(device.battery, Component)
    report = await device.async_update()
    assert report.updated == {"battery"} and report.failed == {}
    data = device.snapshot
    assert (data.state_of_charge, data.setpoint, data.power) == (82, -800, -800)
    assert (data.max_charge, data.max_discharge) == (1200, 1000)
    assert (data.lifetime_charged, data.lifetime_discharged) == (131079, 196617)
    assert (data.stored_energy, data.total_capacity) == (3000, 5000)
    assert data.active_faults == []
    assert [
        (e.address, e.count, e.register_type) for e in mock_modbus_unit.read_events
    ] == [(0, 18, "holding")]
    assert mock_modbus_unit.required_timeout == 3


def test_no_snapshot_before_read(device):
    with pytest.raises(MyGridError):
        _ = device.snapshot


@pytest.mark.parametrize("bit", list(FAULTS))
async def test_fault_bits(device, mock_modbus_unit, bit):
    flags = 1 << bit
    mock_modbus_unit.holding[7] = [flags & 65535, flags >> 16]
    data = await device.async_read()
    assert data.fault_flags == flags
    assert data.active_faults == [FAULTS[bit]]


async def test_unknown_bit_preserved(device, mock_modbus_unit):
    mock_modbus_unit.holding[7] = 1 << 10
    data = await device.async_read()
    assert data.fault_flags == 1 << 10
    assert data.active_faults == []


async def test_stale(device, mock_modbus_unit):
    mock_modbus_unit.holding.update({6: 2, 1: 65535, 7: 65535, 8: 65535})
    data = await device.async_read()
    assert (
        data.state_of_charge
        is data.power
        is data.fault_flags
        is data.active_faults
        is None
    )
    assert data.stored_energy == 3000 and data.max_charge == 1200


@pytest.mark.parametrize(
    ("address", "value", "error"),
    [(0, 1, UnsupportedMapError), (1, 101, MyGridError), (6, 3, MyGridError)],
)
async def test_failed_map_report_preserves_good_snapshot(
    device, mock_modbus_unit, address, value, error
):
    previous = await device.async_read()
    mock_modbus_unit.holding[address] = value
    report = await device.async_update()
    assert report.updated == set()
    assert isinstance(report.failed["battery"], error)
    assert device.snapshot == previous
    with pytest.raises(error):
        await device.async_read()


@pytest.mark.parametrize(
    "watts", [float("nan"), float("inf"), 1, 150, -3276900, 3276800]
)
async def test_invalid_setpoint_no_io(device, mock_modbus_unit, watts):
    writes = []
    mock_modbus_unit.on_write(writes.append)
    with pytest.raises(InvalidSetpointError):
        await device.async_set_power(watts)
    assert writes == [] and mock_modbus_unit.read_events == []


async def test_fresh_limits(device, mock_modbus_unit):
    writes = []
    mock_modbus_unit.on_write(writes.append)
    with pytest.raises(InvalidSetpointError):
        await device.async_set_power(1300)
    assert writes == []
    assert len(mock_modbus_unit.read_events) == 1


@pytest.mark.parametrize("watts", [-1000, -800, 0, 1200])
async def test_write_and_readback(device, mock_modbus_unit, watts):
    writes = []
    mock_modbus_unit.on_write(writes.append)
    data = await device.async_set_power(watts)
    assert data.setpoint == watts
    assert len(writes) == 1 and writes[0].address == 2
    assert len(mock_modbus_unit.read_events) == 2


async def test_confirm_clamped_value(device, mock_modbus_unit):
    def clamp(event):
        if event.address == 2:
            mock_modbus_unit.holding[2] = 5

    mock_modbus_unit.on_write(clamp)
    assert (await device.async_set_power(1000)).setpoint == 500


async def test_write_failure_no_replay(device, mock_modbus_unit):
    mock_modbus_unit.fail_write(2, ModbusTimeoutError())
    with pytest.raises(ModbusTimeoutError):
        await device.async_set_power(500)
    mock_modbus_unit.fail_write(2, None)
    assert (await device.async_read()).setpoint == -800


async def test_lost_readback_no_replay(device, mock_modbus_unit):
    writes = []

    def lose_readback(event):
        writes.append(event)
        mock_modbus_unit.fail_read(0, ModbusTimeoutError())

    mock_modbus_unit.on_write(lose_readback)
    with pytest.raises(ModbusTimeoutError):
        await device.async_set_power(500)
    mock_modbus_unit.fail_read(0, None)
    assert (await device.async_read()).setpoint == 500
    assert len(writes) == 1


async def test_restart_and_readonly(device, mock_modbus_unit):
    writes = []
    mock_modbus_unit.on_write(writes.append)
    await device.async_restart()
    assert len(writes) == 1 and writes[0].address == 9
    with pytest.raises(ValueError):
        await device.battery.write("restart", 2)
    with pytest.raises(AttributeError):
        await device.battery.write("state_of_charge", 10)
    assert len(writes) == 1


async def test_raw_dump_replays(device, mock_modbus_unit, mock_modbus_connection):
    snapshot = await device.async_read()
    raw = await device.async_read_raw()
    assert raw["holding"][5] == 64736 and raw["holding"][13] == 2
    other = mock_modbus_connection.for_unit(2)
    other.load_raw(json.loads(json.dumps(raw)))
    assert await MyGridDevice(other).async_read() == snapshot


async def test_raw_error(device, mock_modbus_unit):
    mock_modbus_unit.fail_requests(ModbusTimeoutError())
    with pytest.raises(ModbusTimeoutError):
        await device.async_read_raw()


async def test_offline_and_reconnect(device, mock_modbus_unit, mock_modbus_connection):
    await device.async_read()
    mock_modbus_unit.fail_requests(ModbusConnectionError())
    with pytest.raises(ModbusConnectionError):
        await device.async_update()
    mock_modbus_unit.fail_requests(None)
    mock_modbus_connection.simulate_connection_lost()
    assert (await device.async_update()).updated == {"battery"}


async def test_component_validation_before_notify(device):
    events = []
    device.battery.add_update_listener(lambda: events.append("updated"))
    await device.battery.async_update()
    assert events == ["updated"]


async def test_cancellation_leaves_peer_usable(device, mock_modbus_unit):
    entered = asyncio.Event()

    async def hanging(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    with patch.object(mock_modbus_unit, "read_holding_registers", side_effect=hanging):
        task = asyncio.create_task(device.async_read())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert (await device.async_read()).state_of_charge == 82
