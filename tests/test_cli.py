"""The query helper reads and closes its own link, without issuing commands."""

import json
from unittest.mock import AsyncMock, patch

from modbus_connection import ModbusConnectionError
import pytest

from mygrid_modbus.cli import async_query, main, parser


async def test_raw_query(mock_modbus_connection, mock_modbus_unit, registers, capsys):
    mock_modbus_unit.holding[0] = registers
    writes = []
    mock_modbus_unit.on_write(writes.append)
    with patch("mygrid_modbus.cli.connect_from_args", return_value=mock_modbus_connection):
        assert await async_query(parser().parse_args(["192.168.1.20", "--raw"])) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["setpoint"] == -800
    assert payload["registers"]["holding"]["5"] == 64736
    assert writes == []
    assert not mock_modbus_connection.connected


async def test_query_without_raw(mock_modbus_connection, mock_modbus_unit, registers, capsys):
    mock_modbus_unit.holding[0] = registers
    with patch("mygrid_modbus.cli.connect_from_args", return_value=mock_modbus_connection):
        assert await async_query(parser().parse_args(["192.168.1.20"])) == 0
    assert "registers" not in json.loads(capsys.readouterr().out)


async def test_connect_error(capsys):
    with patch("mygrid_modbus.cli.connect_from_args", side_effect=ModbusConnectionError()):
        assert await async_query(parser().parse_args(["192.168.1.20"])) == 1
    assert "Could not connect" in capsys.readouterr().out


async def test_read_error_closes_owner(mock_modbus_connection, mock_modbus_unit, capsys):
    mock_modbus_unit.fail_requests(ModbusConnectionError())
    with patch("mygrid_modbus.cli.connect_from_args", return_value=mock_modbus_connection):
        assert await async_query(parser().parse_args(["192.168.1.20"])) == 1
    assert "Could not read" in capsys.readouterr().out
    assert not mock_modbus_connection.connected


def test_main():
    with (
        patch("sys.argv", ["mygrid-query", "192.168.1.20"]),
        patch("mygrid_modbus.cli.async_query", new=AsyncMock(return_value=0)),
    ):
        with pytest.raises(SystemExit) as result:
            main()
        assert result.value.code == 0
