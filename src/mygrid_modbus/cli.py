"""Read-only device query helper with replayable raw JSON output."""

import argparse
import asyncio
import json
from dataclasses import asdict

from modbus_connection import ModbusError
from modbus_connection.cli_helper import add_connection_args, connect_from_args

from .const import UNIT_ID
from .device import MyGridDevice


def parser() -> argparse.ArgumentParser:
    """Offer only the TCP socket transport defined by the device manual."""
    result = argparse.ArgumentParser(description=__doc__)
    add_connection_args(result, connections=(("tcp", "socket"),))
    result.add_argument(
        "--raw", action="store_true", help="Include replayable raw registers"
    )
    return result


async def async_query(args: argparse.Namespace) -> int:
    """The query owns its connection; it never writes any register."""
    try:
        connection = await connect_from_args(args)
    except (ModbusError, OSError, TimeoutError) as err:
        print(f"Could not connect: {err}")
        return 1
    try:
        device = MyGridDevice(connection.for_unit(UNIT_ID))
        await device.async_read()
        result: dict[str, object] = {"data": asdict(device.snapshot)}
        if args.raw:
            result["registers"] = await device.async_read_raw()
        print(json.dumps(result, indent=2))
        return 0
    except (ModbusError, OSError, TimeoutError) as err:
        print(f"Could not read the battery: {err}")
        return 1
    finally:
        await connection.close()


def main() -> None:
    """Run the read-only CLI."""
    raise SystemExit(asyncio.run(async_query(parser().parse_args())))
