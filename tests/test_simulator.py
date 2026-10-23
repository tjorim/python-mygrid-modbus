"""Exercise shared caller-owned units using both real transport backends."""

import asyncio

from modbus_connection import ModbusError, ModbusTcpParams
import pytest

from mygrid_modbus import InvalidSetpointError, MyGridDevice
from tests.simulator import BatterySimulator

pytestmark = pytest.mark.simulator


@pytest.fixture(params=["tmodbus", "pymodbus"])
def connection_factory(request):
    """Use both public backend implementations, independent of Home Assistant."""
    if request.param == "tmodbus":
        from modbus_connection.tmodbus import ModbusConnection
    else:
        from modbus_connection.pymodbus import ModbusConnection
    return ModbusConnection


async def test_wire_read_write_restart(registers, connection_factory):
    async with BatterySimulator(registers) as battery:
        connection = connection_factory(ModbusTcpParams(host="127.0.0.1", port=battery.port), timeout=0.3)
        client = MyGridDevice(connection.for_unit(1))
        try:
            data = await client.async_read()
            assert data.state_of_charge == 82
            assert data.power == -800
            assert data.lifetime_discharged == 196617
            assert (await client.async_set_power(-500)).setpoint == -500
            assert (await client.async_set_power(700)).setpoint == 700
            assert (await client.async_set_power(0)).setpoint == 0
            await client.async_restart()
            assert battery.writes == [(2, 65531), (2, 7), (2, 0), (9, 1)]
            assert battery.requests[0] == (3, 0, 18)
            assert battery.maximum_connections == 1
        finally:
            await connection.close()


async def test_wire_clamp(registers, connection_factory):
    async with BatterySimulator(registers) as battery:
        connection = connection_factory(ModbusTcpParams(host="127.0.0.1", port=battery.port), timeout=0.3)
        client = MyGridDevice(connection.for_unit(1))
        try:
            battery.clamp_charge_to = 5
            assert (await client.async_set_power(1000)).setpoint == 500
            assert battery.writes == [(2, 10)]
        finally:
            await connection.close()


async def test_wire_exception_recovery(registers, connection_factory):
    async with BatterySimulator(registers) as battery:
        connection = connection_factory(ModbusTcpParams(host="127.0.0.1", port=battery.port), timeout=0.3)
        client = MyGridDevice(connection.for_unit(1))
        try:
            battery.next_exception = 2
            with pytest.raises(ModbusError):
                await client.async_read()
            assert (await client.async_read()).state_of_charge == 82
            assert battery.writes == []
            assert battery.total_connections == 1
        finally:
            await connection.close()


async def test_lost_ack_never_replayed(registers, connection_factory):
    async with BatterySimulator(registers) as battery:
        connection = connection_factory(ModbusTcpParams(host="127.0.0.1", port=battery.port), timeout=0.3)
        client = MyGridDevice(connection.for_unit(1))
        try:
            battery.drop_write_response = True
            with pytest.raises(ModbusError):
                await client.async_set_power(500)
            assert battery.writes == [(2, 5)]
            assert (await client.async_read()).setpoint == 500
            assert battery.writes == [(2, 5)]
        finally:
            await connection.close()


async def test_shared_unit_concurrency_and_validation(registers, connection_factory):
    async with BatterySimulator(registers) as battery:
        connection = connection_factory(ModbusTcpParams(host="127.0.0.1", port=battery.port), timeout=0.3)
        client = MyGridDevice(connection.for_unit(1))
        peer = connection.for_unit(1)
        try:
            await asyncio.gather(
                client.async_read(),
                client.async_set_power(-500),
                peer.read_holding_registers(0, 18),
            )
            with pytest.raises(InvalidSetpointError):
                await client.async_set_power(1300)
            assert (await peer.read_holding_registers(0, 18))[1] == 82
            assert battery.total_connections == 1
            assert battery.maximum_connections == 1
            assert battery.rejects == 0
            assert battery.writes == [(2, 65531)]
        finally:
            await connection.close()
