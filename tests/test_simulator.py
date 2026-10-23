"""Real Modbus TCP framing and recovery, without Home Assistant."""

import asyncio

import pytest

from mygrid_modbus import MyGridClient, MyGridError
from tests.simulator import BatterySimulator

pytestmark = pytest.mark.simulator


async def test_wire_read_write_restart(registers):
    async with BatterySimulator(registers) as battery:
        client = MyGridClient("127.0.0.1", battery.port)
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
            await client.async_close()


async def test_wire_clamp(registers):
    async with BatterySimulator(registers) as battery:
        battery.clamp_charge_to = 5
        client = MyGridClient("127.0.0.1", battery.port)
        try:
            assert (await client.async_set_power(1000)).setpoint == 500
            assert battery.writes == [(2, 10)]
        finally:
            await client.async_close()


async def test_wire_exception_recovery(registers):
    async with BatterySimulator(registers) as battery:
        battery.next_exception = 2
        client = MyGridClient("127.0.0.1", battery.port)
        try:
            with pytest.raises(MyGridError):
                await client.async_read()
            # Let the server observe the closed session before reconnecting.
            await asyncio.sleep(0.01)
            assert (await client.async_read()).state_of_charge == 82
            assert battery.writes == []
        finally:
            await client.async_close()


async def test_lost_ack_never_replayed(registers):
    async with BatterySimulator(registers) as battery:
        battery.drop_write_response = True
        client = MyGridClient("127.0.0.1", battery.port)
        try:
            with pytest.raises(MyGridError):
                await client.async_set_power(500)
            assert battery.writes == [(2, 5)]
            assert (await client.async_read()).setpoint == 500
            assert battery.writes == [(2, 5)]
        finally:
            await client.async_close()


async def test_concurrent_operations_one_session(registers):
    async with BatterySimulator(registers) as battery:
        client = MyGridClient("127.0.0.1", battery.port)
        try:
            await asyncio.gather(
                client.async_read(), client.async_set_power(-500), client.async_read()
            )
            assert battery.maximum_connections == 1
            assert battery.rejects == 0
            assert battery.writes == [(2, 65531)]
        finally:
            await client.async_close()
