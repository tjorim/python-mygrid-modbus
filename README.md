# mygrid-modbus

A fully asynchronous, typed Python library for **MyGrid ModuleTwo** home batteries over local Modbus TCP. It implements the supplied manufacturer register map **version 2** and has no Home Assistant dependency.

Requires **Python 3.12+**. This is an independent package and repository, consumed by the [MyGrid Home Assistant integration](https://github.com/tjorim/ha-mygrid). Version 0.1.0 is prepared locally; GitHub and PyPI publication have not yet been performed. The URLs in package metadata are the intended publication locations.

## Install

From this checkout before publication:

```sh
python -m pip install ".[tmodbus]"
```

After publishing version 0.1.0 to PyPI:

```sh
python -m pip install "mygrid-modbus[tmodbus]==0.1.0"
```

## Use

```python
import asyncio

from modbus_connection import ModbusTcpParams
from modbus_connection.tmodbus import ModbusConnection
from mygrid_modbus import MyGridClient


async def main() -> None:
    # The application owns the connection and chooses the transport backend.
    connection = ModbusConnection(
        ModbusTcpParams(host="192.168.1.20", port=502), timeout=3
    )
    client = MyGridClient(connection.for_unit(1))
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
        await connection.close()


asyncio.run(main())
```

Create the connection and client inside an active event loop. Bind unit ID **1** and keep one connection per battery or cluster leader. Close that connection when its last consumer is finished; closing does not idle the battery.

The base package is backend-neutral: `pip install mygrid-modbus` is sufficient when an application supplies a `ModbusUnit`. For standalone use choose `[tmodbus]` as above, or install `[pymodbus]` and import `ModbusConnection` from `modbus_connection.pymodbus`. Both satisfy the same unit interface. Inside Home Assistant, borrow a managed unit with `homeassistant.components.modbus.async_get_unit`; Home Assistant owns and releases that connection. Config flows use `async_get_temporary_unit`.

This pre-release API replaces the earlier local host/port constructor with `MyGridClient(unit)` and removes `client.async_close()`. Connection owners now perform cleanup; the battery snapshot and command methods are unchanged.

## Public API

Import from `mygrid_modbus`; implementation submodules are not the public API.

| API | Contract |
| --- | --- |
| `MyGridClient(unit: ModbusUnit)` | Inject a caller-owned unit bound to ID 1; serialize battery operations without owning the connection |
| `await client.async_read()` | One full-map read; returns `BatteryData`; never writes |
| `await client.async_set_power(watts)` | Fresh limits, one validated write, readback; returns confirmed `BatteryData` |
| `await client.async_restart()` | Write register 9 with value 1 once; returns `None` |
| `BatteryData` | Frozen typed snapshot: SOC, setpoint, limits, measured power, status, flags, energy counters, capacity and map version |
| `MyGridError` | Communication, rejected requests, malformed map, or uncertain write confirmation |
| `UnsupportedMapError` | Subclass of `MyGridError` for maps other than version 2 |
| `InvalidSetpointError` | Subclass of `MyGridError` for invalid increments, signed range or fresh limits |
| `FAULTS` | Mapping of documented global bit positions to stable diagnostic keys |
| `MAP_VERSION`, `UNIT_ID`, `REGISTER_COUNT` | Supported protocol constants (2, 1, 18) |
| `decode_registers(words)` | Validate/decode exactly 18 unsigned words into `BatteryData` |
| `signed16(word)`, `unsigned32(low, high)` | Protocol decoding helpers for valid unsigned words |

All power values in `BatteryData` are **watts**; all energy values are **Wh**. Positive power charges; negative discharges. Status is `0` normal, `1` fault, `2` telemetry stale. Status 2 makes SOC, measured power and fault flags `None`; `active_faults` is also `None`. Other documented registers remain available. Faults preserve unknown raw bits; `active_faults` lists names for known bits only. The library has no caches, polling schedules, stored desired setpoints or Home Assistant entities.

Operations have a 12-second IO budget after acquiring this client's lock, including time queued on the shared transport. The connection owner selects per-request timeouts (3 seconds in the standalone example and the integration's requested timeout). Other consumers may require a longer shared timeout. Reads and complete command sequences are serialized within this battery client; `modbus-connection` serializes individual requests across all consumers of the physical connection. Use one power controller: sharing a socket does not coordinate competing control strategies.

The library never connects, closes or disconnects a supplied unit, including on cancellation, invalid data or an uncertain write. Connection lifecycle and transport recovery belong to the owner/backend. Both supported `modbus-connection` backends disable request retransmission; the MyGrid library performs no command retry and retains no desired setpoint. A later read may reconnect through the owner-managed backend, but no previous write is replayed. Custom `ModbusUnit` implementations must provide equivalent no-write-retry semantics. A command that raises `MyGridError` may have been applied with a lost acknowledgment; inspect readings before manually repeating it. `InvalidSetpointError` and `UnsupportedMapError` reject a power command before a write. A returned setpoint confirms acceptance, not measured delivery; firmware applies power about once a second.

The base dependency is **`modbus-connection>=4.12.4,<5`**, with optional `tmodbus` and `pymodbus` backend extras. Core library imports require neither backend nor Home Assistant. `py.typed` is included in wheels and source distributions for downstream strict typing.

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

The tests run with only this library's dependencies. They cover register decoding, faults, stale snapshots, limits, cancellation, signed commands and a raw-frame TCP battery simulator exercised against both transport backends. They neither import Home Assistant nor contact real hardware. CI tests Python 3.12, 3.13 and 3.14, builds the wheel/sdist, and runs the suite against the built wheel in a clean environment.

See [release instructions](docs/releasing.md). The original code is MIT licensed; the manufacturer manual is referenced, not republished.
