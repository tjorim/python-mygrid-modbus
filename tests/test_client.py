"""Protocol decoding, signed commands, failure modes and serialization."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from modbus_connection import (
    IllegalDataAddressError,
    ModbusConnectionError,
    ModbusError,
    ModbusProtocolError,
    ModbusTimeoutError,
    ModbusUnit,
)

from mygrid_modbus import (
    FAULTS,
    InvalidSetpointError,
    MyGridClient,
    MyGridError,
    UnsupportedMapError,
    decode_registers,
    signed16,
    unsigned32,
)


@pytest.mark.parametrize(
    ("word", "expected"), [(0, 0), (32767, 32767), (32768, -32768), (65535, -1)]
)
def test_signed(word, expected):
    assert signed16(word) == expected


def test_decode(registers):
    data = decode_registers(registers)
    assert data.state_of_charge == 82
    assert data.setpoint == -800
    assert data.power == -800
    assert data.max_charge == 1200
    assert data.max_discharge == 1000
    assert data.lifetime_charged == 131079
    assert data.lifetime_discharged == 196617
    assert data.stored_energy == 3000
    assert data.total_capacity == 5000
    assert unsigned32(65535, 65535) == 4294967295
    assert data.active_faults == []


@pytest.mark.parametrize("bit", list(FAULTS))
def test_fault_bits(registers, bit):
    flags = 1 << bit
    registers[7:9] = [flags & 65535, flags >> 16]
    data = decode_registers(registers)
    assert data.fault_flags == flags
    assert data.active_faults == [FAULTS[bit]]


def test_stale(registers):
    registers[6] = 2
    registers[1] = 65535
    data = decode_registers(registers)
    assert (
        data.state_of_charge
        is data.power
        is data.fault_flags
        is data.active_faults
        is None
    )
    assert data.stored_energy == 3000
    assert data.max_charge == 1200


@pytest.mark.parametrize(
    ("index", "value", "error"),
    [
        (0, 1, UnsupportedMapError),
        (1, 101, MyGridError),
        (6, 3, MyGridError),
        (1, -1, MyGridError),
        (1, 65536, MyGridError),
        (1, True, MyGridError),
    ],
)
def test_invalid_register(registers, index, value, error):
    registers[index] = value
    with pytest.raises(error):
        decode_registers(registers)


@pytest.mark.parametrize("size", [0, 1, 17, 19])
def test_invalid_length(size):
    with pytest.raises(MyGridError):
        decode_registers([0] * size)


@pytest.fixture
def unit(registers):
    """Mock the public backend-neutral unit boundary, not a socket client."""
    unit = MagicMock(spec=ModbusUnit)
    unit.read_holding_registers.return_value = registers
    return unit


async def test_read(unit):
    client = MyGridClient(unit)
    assert (await client.async_read()).state_of_charge == 82
    unit.read_holding_registers.assert_awaited_once_with(0, 18)
    unit.write_register.assert_not_called()
    unit.disconnect.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [
        ModbusConnectionError("bad"),
        ModbusError("bad"),
        ModbusTimeoutError("bad"),
        ModbusProtocolError("bad"),
        IllegalDataAddressError(),
        OSError("bad"),
        TimeoutError(),
    ],
)
async def test_transport_failure_keeps_owner_connection(unit, error):
    unit.read_holding_registers.side_effect = error
    with pytest.raises(MyGridError):
        await MyGridClient(unit).async_read()
    unit.disconnect.assert_not_called()


@pytest.mark.parametrize(
    "watts", [float("nan"), float("inf"), 1, 150, -3276900, 3276800]
)
async def test_invalid_setpoint(unit, watts):
    with pytest.raises(InvalidSetpointError):
        await MyGridClient(unit).async_set_power(watts)
    unit.write_register.assert_not_called()
    unit.read_holding_registers.assert_not_called()
    unit.disconnect.assert_not_called()


async def test_fresh_limits(unit):
    with pytest.raises(InvalidSetpointError):
        await MyGridClient(unit).async_set_power(1300)
    unit.read_holding_registers.assert_awaited_once()
    unit.write_register.assert_not_called()
    unit.disconnect.assert_not_called()


@pytest.mark.parametrize("watts", [-1000, -800, 0, 1200])
async def test_write_and_readback(unit, watts):
    # Readback deliberately differs from the request; never publish optimism.
    assert (await MyGridClient(unit).async_set_power(watts)).setpoint == -800
    unit.write_register.assert_awaited_once_with(2, int(watts / 100) & 65535)
    assert unit.read_holding_registers.await_count == 2


async def test_rejected_write(unit):
    unit.write_register.side_effect = IllegalDataAddressError()
    with pytest.raises(MyGridError):
        await MyGridClient(unit).async_set_power(-800)
    assert unit.write_register.await_count == 1
    assert unit.read_holding_registers.await_count == 1
    unit.disconnect.assert_not_called()


async def test_readback_failure_not_retried(unit, registers):
    unit.read_holding_registers.side_effect = [registers, ModbusTimeoutError()]
    client = MyGridClient(unit)
    with pytest.raises(MyGridError):
        await client.async_set_power(-800)
    assert unit.write_register.await_count == 1
    unit.read_holding_registers.side_effect = None
    await client.async_read()
    assert unit.write_register.await_count == 1
    unit.disconnect.assert_not_called()


async def test_restart(unit):
    await MyGridClient(unit).async_restart()
    unit.write_register.assert_awaited_once_with(9, 1)
    unit.read_holding_registers.assert_not_called()
    unit.disconnect.assert_not_called()


async def test_serialization(unit, registers):
    entered = asyncio.Event()
    release = asyncio.Event()

    async def delayed(*args):
        entered.set()
        await release.wait()
        return registers

    unit.read_holding_registers.side_effect = delayed
    client = MyGridClient(unit)
    first = asyncio.create_task(client.async_read())
    await entered.wait()
    second = asyncio.create_task(client.async_set_power(-800))
    await asyncio.sleep(0)
    assert unit.read_holding_registers.await_count == 1
    unit.write_register.assert_not_called()
    release.set()
    await asyncio.gather(first, second)
    assert unit.read_holding_registers.await_count == 3
    assert unit.write_register.await_count == 1


async def test_cancellation_preserves_owner_connection(unit, registers):
    entered = asyncio.Event()

    async def hanging(*args):
        entered.set()
        await asyncio.Event().wait()

    unit.read_holding_registers.side_effect = hanging
    client = MyGridClient(unit)
    task = asyncio.create_task(client.async_read())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    unit.disconnect.assert_not_called()
    unit.write_register.assert_not_called()
    unit.read_holding_registers.side_effect = None
    assert (await client.async_read()).state_of_charge == 82


async def test_operation_timeout_preserves_owner_connection(unit):
    async def hanging(*args):
        await asyncio.Event().wait()

    unit.read_holding_registers.side_effect = hanging
    with patch("mygrid_modbus.client.timeout", return_value=asyncio.timeout(0.01)):
        with pytest.raises(MyGridError):
            await MyGridClient(unit).async_read()
    unit.disconnect.assert_not_called()
    unit.write_register.assert_not_called()
