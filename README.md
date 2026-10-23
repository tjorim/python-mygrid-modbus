# mygrid-modbus

A standalone async Python device library for **MyGrid ModuleTwo** batteries, implementing manufacturer register map **version 2**. Requires Python **3.12+**.

The library uses `modbus-connection` component models. Applications supply a `ModbusUnit`, choose the transport backend, and own the connection lifetime. No application framework is required. The source is published on GitHub. Version 0.1.0 has not yet been published to PyPI.

## Installation

Before publication, from this checkout:

```sh
python -m pip install '.[tmodbus]'
```

After publication:

```sh
python -m pip install 'mygrid-modbus[tmodbus]==0.1.0'
```

Install the base package without extras when the consuming application supplies its own unit. The optional `[pymodbus]` extra selects the other supported backend.

## Query a battery

The helper is read-only; it never sends power or restart commands:

```sh
uv sync --frozen
uv run script/query.py 192.168.1.20 --port 502
uv run script/query.py 192.168.1.20 --port 502 --raw
# The installed distribution also provides mygrid-query.
```

`--raw` includes an address-keyed register dump, suitable for replay in tests with `mock_modbus_unit.load_raw(payload['registers'])`. The helper uses `modbus_connection.cli_helper` for connection arguments and backend selection. Only the documented TCP socket transport is offered. Unit ID is fixed to **1**.

## Device API

```python
import asyncio

from modbus_connection import ModbusTcpParams
from modbus_connection.tmodbus import ModbusConnection
from mygrid_modbus import MyGridDevice


async def main() -> None:
    connection = ModbusConnection(ModbusTcpParams(host="192.168.1.20", port=502))
    try:
        device = MyGridDevice(connection.for_unit(1))
        report = await device.async_update()
        if "battery" in report.updated:
            print(device.battery.stored_energy)  # typed component attribute
            print(device.snapshot)  # immutable, validated readings
        if report.failed:
            print(report.failed)
        # Explicit commands only, if this application is the power controller:
        # accepted = await device.async_set_power(100)
        # await device.async_set_power(0)
        # await device.async_restart()
        raw = await device.async_read_raw()
        print(raw)
    finally:
        await connection.close()


asyncio.run(main())
```

| API | Contract |
| --- | --- |
| `MyGridDevice(unit)` | `Device` composed of a typed `Battery` component |
| `async_update()` | Returns `UpdateReport`; one pooled read of holding registers 0–17 |
| `battery` | `Component` with declarative signed/scaled/low-word-first fields |
| `snapshot` | Last fully validated `BatteryData`; raises before the first good read |
| `async_read()` | Convenience validated snapshot read; raises on failure |
| `async_set_power(watts)` | Fresh limits, one validated write, confirmed readback |
| `async_restart()` | One function-06 write of value 1 to register 9 |
| `async_read_raw()` | Fresh raw words grouped by Modbus space, replayable by the mock |

Power is in **W**, energy in **Wh**. Positive power charges; negative power discharges. A setpoint is a signed I16 value in 100 W increments and must fall within fresh device limits. A readback confirms acceptance, not actual power delivery.

Status 0 means normal, 1 fault and 2 telemetry stale. The immutable snapshot suppresses SOC, measured power and faults when status is 2; other valid fields remain available. Raw dumps preserve exactly what the device returned. When a poll fails, inspect its report before treating cached component values or the last snapshot as current. An unsupported map or invalid SOC/status fails the component instead of publishing corrupt measurements.

`MyGridError`, `UnsupportedMapError` and `InvalidSetpointError` extend the neutral `ModbusError` hierarchy. Transport connection/timeouts retain their typed backend-neutral exceptions. Raw diagnostics raise the same errors. Operations have a 12-second budget after this device's lock is acquired; the device requests a minimum 3-second request timeout through its unit. The owner resolves timing requirements across consumers.

The library never closes or disconnects the supplied unit, even on a failed command or cancellation. Both supported backends disable write retransmission. The device retains no desired setpoint and never replays commands. A failed confirmation can mean the write was applied; read the battery before manually deciding to issue another command.

Use `async_set_power()` for live-limit validation. Component field metadata describes writable fields and static validators, while the device method handles fresh limits and readback. All other registers are read-only except restart. The component constrains reads to the documented range and uses low-word-first U32 fields, including high fault bits.

## Device prerequisites

Enable external control in the manufacturer's app before connecting; otherwise the TCP port is closed. Use the same LAN and the **Auto leader** for a cluster. The battery accepts one TCP client at a time, so share a connection between local consumers. Choose one writer: sharing the socket does not arbitrate competing power strategies.

There is no TLS/authentication, serial transport, firmware-update API, hardware identity, follower enumeration or documented disconnection watchdog in this map. Keep port 502 on the trusted LAN. Closing the connection does not request idle. Cluster SOC, limits and setpoints have documented aggregate meanings; energy aggregation is not established by the manual. See [protocol details](docs/protocol.md).

## Development and release

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

Tests use the supplied `mock_modbus_unit`/`mock_modbus_connection` pytest fixtures for models, failures and replayed dumps. Independent raw-frame TCP tests exercise both real backends, clamping, lost acknowledgments and connection sharing. CI covers Python 3.12–3.14 and built-wheel installation, including base imports without backend extras.

[Release instructions](docs/releasing.md) describe version checks, trusted publishing and the required `pypi` environment. Publishing is not performed by local validation. The MIT license covers original code; the manufacturer manual is referenced, not republished. Physical hardware validation remains pending.
