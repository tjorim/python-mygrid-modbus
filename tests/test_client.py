"""Protocol decoding, signed commands, failure modes and serialization."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pymodbus.exceptions import ModbusException
from pymodbus.pdu import ExceptionResponse
from pymodbus.pdu.register_message import (
    ReadHoldingRegistersResponse,
    WriteSingleRegisterResponse,
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
def transport(registers):
    transport = MagicMock()
    transport.connected = True
    transport.connect = AsyncMock(return_value=True)
    transport.read_holding_registers = AsyncMock(
        return_value=ReadHoldingRegistersResponse(registers=registers)
    )
    transport.write_register = AsyncMock(
        return_value=WriteSingleRegisterResponse(address=2, registers=[65528])
    )
    with patch(
        "mygrid_modbus.client.AsyncModbusTcpClient", return_value=transport
    ) as factory:
        transport.factory = factory
        yield transport


async def test_read(transport):
    client = MyGridClient("battery")
    assert (await client.async_read()).state_of_charge == 82
    transport.read_holding_registers.assert_awaited_once_with(
        address=0, count=18, device_id=1
    )
    transport.factory.assert_called_once_with(
        "battery", port=502, timeout=3, retries=0, reconnect_delay=0
    )
    transport.write_register.assert_not_called()
    await client.async_close()
    transport.close.assert_called_once()


async def test_connect(transport):
    transport.connected = False
    client = MyGridClient("battery")
    await client.async_read()
    transport.connect.assert_awaited_once()
    transport.connect.return_value = False
    with pytest.raises(MyGridError, match="Cannot connect"):
        await client.async_read()


@pytest.mark.parametrize(
    "error", [ModbusException("bad"), OSError("bad"), TimeoutError()]
)
async def test_transport_failure(transport, error):
    transport.read_holding_registers.side_effect = error
    client = MyGridClient("battery")
    with pytest.raises(MyGridError):
        await client.async_read()
    transport.close.assert_called_once()


async def test_modbus_exception(transport):
    transport.read_holding_registers.return_value = ExceptionResponse(3, 2)
    with pytest.raises(MyGridError, match="rejected"):
        await MyGridClient("battery").async_read()


@pytest.mark.parametrize(
    "watts", [float("nan"), float("inf"), 1, 150, -3276900, 3276800]
)
async def test_invalid_setpoint(transport, watts):
    with pytest.raises(InvalidSetpointError):
        await MyGridClient("battery").async_set_power(watts)
    transport.write_register.assert_not_called()
    transport.read_holding_registers.assert_not_called()


async def test_fresh_limits(transport):
    with pytest.raises(InvalidSetpointError):
        await MyGridClient("battery").async_set_power(1300)
    transport.read_holding_registers.assert_awaited_once()
    transport.write_register.assert_not_called()


@pytest.mark.parametrize("watts", [-1000, -800, 0, 1200])
async def test_write_and_readback(transport, registers, watts):
    transport.write_register.return_value = WriteSingleRegisterResponse(
        address=2, registers=[int(watts / 100) & 65535]
    )
    client = MyGridClient("battery")
    # The readback is deliberately different: confirmed state, not optimism.
    assert (await client.async_set_power(watts)).setpoint == -800
    transport.write_register.assert_awaited_once_with(
        address=2, value=int(watts / 100) & 65535, device_id=1
    )
    assert transport.read_holding_registers.await_count == 2


@pytest.mark.parametrize(
    "response",
    [
        ExceptionResponse(6, 2),
        WriteSingleRegisterResponse(address=3, registers=[65528]),
        WriteSingleRegisterResponse(address=2, registers=[123]),
    ],
)
async def test_rejected_write(transport, response):
    transport.write_register.return_value = response
    with pytest.raises(MyGridError):
        await MyGridClient("battery").async_set_power(-800)
    assert transport.write_register.await_count == 1
    assert transport.read_holding_registers.await_count == 1


async def test_readback_failure_not_retried(transport):
    transport.read_holding_registers.side_effect = [
        transport.read_holding_registers.return_value,
        OSError(),
    ]
    client = MyGridClient("battery")
    with pytest.raises(MyGridError):
        await client.async_set_power(-800)
    assert transport.write_register.await_count == 1
    transport.read_holding_registers.side_effect = None
    await client.async_read()
    assert transport.write_register.await_count == 1


async def test_restart(transport):
    transport.write_register.return_value = WriteSingleRegisterResponse(
        address=9, registers=[1]
    )
    await MyGridClient("battery").async_restart()
    transport.write_register.assert_awaited_once_with(address=9, value=1, device_id=1)
    transport.read_holding_registers.assert_not_called()


async def test_serialization(transport):
    entered = asyncio.Event()
    release = asyncio.Event()
    response = transport.read_holding_registers.return_value

    async def delayed(**kwargs):
        entered.set()
        await release.wait()
        return response

    transport.read_holding_registers.side_effect = delayed
    client = MyGridClient("battery")
    first = asyncio.create_task(client.async_read())
    await entered.wait()
    second = asyncio.create_task(client.async_set_power(-800))
    close = asyncio.create_task(client.async_close())
    await asyncio.sleep(0)
    assert transport.read_holding_registers.await_count == 1
    transport.write_register.assert_not_called()
    release.set()
    await asyncio.gather(first, second, close)
    assert transport.read_holding_registers.await_count == 3
    assert transport.write_register.await_count == 1


async def test_cancelled_operation_closes_connection(transport):
    entered = asyncio.Event()

    async def hanging(**kwargs):
        entered.set()
        await asyncio.Event().wait()

    transport.read_holding_registers.side_effect = hanging
    client = MyGridClient("battery")
    task = asyncio.create_task(client.async_read())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    transport.close.assert_called_once()
    transport.write_register.assert_not_called()


async def test_operation_timeout_closes_connection(transport):
    async def hanging(**kwargs):
        await asyncio.Event().wait()

    transport.read_holding_registers.side_effect = hanging
    client = MyGridClient("battery")
    with patch("mygrid_modbus.client.timeout", return_value=asyncio.timeout(0.01)):
        with pytest.raises(MyGridError):
            await client.async_read()
    transport.close.assert_called_once()
    transport.write_register.assert_not_called()
