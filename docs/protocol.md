# Protocol reference

Source: user-supplied **MyGrid ModuleTwo Modbus TCP user manual**, `mygrid-modbus-tcp-manual-en.md`, map version 2. This is an implementation summary, not a redistribution of the manual. When changing support, check changes against a versioned manufacturer manual and add fixtures/tests for the new map.

TCP port 502; unit 1; zero-based wire addresses. Read the entire map with function 03, address 0, count 18. Single-register writes use function 06. Only addresses 2 and 9 are writable. No address offset or 40001 notation is used in code.

| Address | Value | Decoding |
| --- | --- | --- |
| 0 | Map version | U16, must be 2 |
| 1 | State of charge | U16, % |
| 2 | Power setpoint | I16 × 100 W |
| 3 / 4 | Maximum charge / discharge | U16 × 100 W; discharge limit is positive |
| 5 | Measured battery power | I16, W |
| 6 | Status | 0 normal, 1 fault, 2 telemetry stale |
| 7–8 | Fault bits | U32, low word first |
| 9 | Reboot | Write 1; reads as 0 |
| 10–11 | Stored energy | U32, Wh, low word first |
| 12–13 | Lifetime charged | U32, Wh, low word first |
| 14–15 | Lifetime discharged | U32, Wh, low word first |
| 16–17 | Total capacity | U32, Wh, low word first |

Positive power charges; negative power discharges. U32 = low + high × 65536. I16 is two's complement. For status 2 only the explicitly documented measurements (SOC, power, fault flags) are discarded; snapshots retain other valid registers. SOC must be 0–100 when fresh; status must be known. Malformed/short responses fail the update instead of publishing a partial snapshot.

## Faults

Bit positions below are global across the 32-bit word; register 8 bit 3 is global bit 19.

| Bit | Meaning |
| --- | --- |
| 0 | Battery communication fault or battery-system error |
| 1 | Battery internal communication fault |
| 2 / 3 | Over-voltage / under-voltage |
| 4 / 5 | Charge / discharge over-current |
| 6 / 7 | Over-temperature / under-temperature |
| 8 | Cell voltage imbalance |
| 9 | Hardware protection |
| 11 | Other fault |
| 12 / 13 / 14 | Voltage / temperature / current sensor fault |
| 15 | Relay fault |
| 19 | AC parallel alarm |
| 20 | Battery to solar-input communication fault |
| 21 | Forced charge failed |
| 23 | Parallel power fault |
| 26 | Fuse fault |
| 27 | Precharge fault |
| 29 | Temperature difference fault |

Unused bits are preserved in raw flags. They have no invented individual names or entities.
