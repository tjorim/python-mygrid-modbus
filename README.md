# mygrid-modbus

A fully asynchronous, typed Python library for **MyGrid ModuleTwo** home batteries over local Modbus TCP. It implements the supplied manufacturer register map **version 2** and has no Home Assistant dependency.

Requires **Python 3.12+**. This is an independent package and repository, consumed by the [MyGrid Home Assistant integration](https://github.com/tjorim/ha-mygrid). Version 0.1.0 is prepared locally; GitHub and PyPI publication have not yet been performed. The URLs in package metadata are the intended publication locations.

## Install

From this checkout before publication:

```sh
python -m pip install .
```

After publishing version 0.1.0 to PyPI:

```sh
python -m pip install mygrid-modbus==0.1.0
```

## Use

```python
import asyncio

from mygrid_modbus import MyGridClient


async def main() -> None:
    client = MyGridClient("192.168.1.20", port=502)
    try:
        snapshot = await client.async_read()
        print(snapshot.state_of_charge, snapshot.power)

        # Commands are optional and explicit. Positive charges; negative
        # discharges; zero requests idle. Values must be multiples of 100 W.
        # snapshot = await client.async_set_power(100)
        # print(snapshot.setpoint)  # confirmed device value, in watts
        # await client.async_set_power(0)
        # await client.async_restart()  # explicit reboot; never retried
    finally:
        await client.async_close()


asyncio.run(main())
```

Create the client inside an active event loop. Keep one client per battery or cluster leader and always close it. Closing a client does not idle the battery.

## Public API

Import from `mygrid_modbus`; implementation submodules are not the public API.

| API | Contract |
| --- | --- |
| `MyGridClient(host, port=502)` | One async TCP connection, serialized operations, fixed documented unit ID 1 |
| `await client.async_read()` | One full-map read; returns `BatteryData`; never writes |
| `await client.async_set_power(watts)` | Fresh limits, one validated write, readback; returns confirmed `BatteryData` |
| `await client.async_restart()` | Write register 9 with value 1 once; returns `None` |
| `await client.async_close()` | Wait for active operations and close the socket; does not change the setpoint |
| `BatteryData` | Frozen typed snapshot: SOC, setpoint, limits, measured power, status, flags, energy counters, capacity and map version |
| `MyGridError` | Communication, rejected requests, malformed map, or uncertain write confirmation |
| `UnsupportedMapError` | Subclass of `MyGridError` for maps other than version 2 |
| `InvalidSetpointError` | Subclass of `MyGridError` for invalid increments, signed range or fresh limits |
| `FAULTS` | Mapping of documented global bit positions to stable diagnostic keys |
| `MAP_VERSION`, `UNIT_ID`, `REGISTER_COUNT` | Supported protocol constants (2, 1, 18) |
| `decode_registers(words)` | Validate/decode exactly 18 unsigned words into `BatteryData` |
| `signed16(word)`, `unsigned32(low, high)` | Protocol decoding helpers for valid unsigned words |

All power values in `BatteryData` are **watts**; all energy values are **Wh**. Positive power charges; negative discharges. Status is `0` normal, `1` fault, `2` telemetry stale. Status 2 makes SOC, measured power and fault flags `None`; `active_faults` is also `None`. Other documented registers remain available. Faults preserve unknown raw bits; `active_faults` lists names for known bits only. The library has no caches, polling schedules, stored desired setpoints or Home Assistant entities.

Operations use a 3-second request timeout and a 12-second total IO budget once their lock is acquired. Reads and complete command sequences share the lock. Request retries and background reconnection are disabled. A later operation may establish a new connection, but no old command is retained or replayed. Cancellation closes the connection. A command that raises `MyGridError` may have been applied with a lost acknowledgment; inspect readings before manually repeating it. `InvalidSetpointError` and `UnsupportedMapError` reject a power command before a write. A returned setpoint confirms acceptance, not measured delivery; firmware applies power about once a second.

The package depends on `pymodbus>=3.13.1,<4`. Home Assistant may pin a compatible exact version itself. `py.typed` is included in wheels and source distributions for downstream strict typing.

## Device prerequisites and limits

Enable **Home Assistant** as the battery's control source in the MyGrid app; otherwise the Modbus port is closed. Use the same LAN/Wi-Fi and the **Auto leader** for a cluster. The battery allows only **one client** at a time. Choose one power controller: app controls and other integrations/writers share the same setpoint.

No TLS, authentication, discovery, serial transport, firmware update, identity/serial number, or follower enumeration is defined by this map. Do not expose port 502 to the internet. Cluster SOC, limits and setpoints have documented aggregate meanings; do not infer aggregation for other registers. The manual defines no loss-of-connection power watchdog. See the [protocol reference](docs/protocol.md). Physical hardware validation remains pending.

## Development

```sh
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv build
uv run twine check dist/*
uv run python scripts/check_artifacts.py
```

The tests run with only this library's dependencies. They cover register decoding, faults, stale snapshots, limits, cancellation, signed commands and a raw-frame TCP battery simulator. They neither import Home Assistant nor contact real hardware. CI tests Python 3.12, 3.13 and 3.14, builds the wheel/sdist, and runs the suite against the built wheel in a clean environment.

See [release instructions](docs/releasing.md). The original code is MIT licensed; the manufacturer manual is referenced, not republished.
