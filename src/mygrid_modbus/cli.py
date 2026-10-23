"""Read-only device query helper with replayable raw JSON output."""

import argparse
import asyncio
from dataclasses import asdict
import json

from modbus_connection import ModbusError
from modbus_connection.cli_helper import add_connection_args, connect_from_args

from .const import UNIT_ID
from .device import MyGridDevice


def parser() -> argparse.ArgumentParser:
    """Offer only the TCP socket transport defined by the device manual."""
    result = argparse.ArgumentParser(description=__doc__)
    add_connection_args(result, connections=(("tcp", "socket"),))
    result.add_argument("--raw", action="store_true", help="Include replayable raw registers")
    return result


async def async_query(args: argparse.Namespace) -> int:
    """Query the battery on a connection this helper owns; never write any register."""
    try:
        connection = await connect_from_args(args)
    except (ModbusError, OSError, TimeoutError) as err:
        print(f"Could not connect: {err}")  # noqa: T201 - the CLI exists to print
        return 1
    try:
        device = MyGridDevice(connection.for_unit(UNIT_ID))
        await device.async_read()
        result: dict[str, object] = {"data": asdict(device.snapshot)}
        if args.raw:
            result["registers"] = await device.async_read_raw()
        print(json.dumps(result, indent=2))  # noqa: T201
    except (ModbusError, OSError, TimeoutError) as err:
        print(f"Could not read the battery: {err}")  # noqa: T201
        return 1
    else:
        return 0
    finally:
        await connection.close()


def main() -> None:
    """Run the read-only CLI."""
    raise SystemExit(asyncio.run(async_query(parser().parse_args())))
