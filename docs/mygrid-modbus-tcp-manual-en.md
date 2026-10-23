# MyGrid ModuleTwo Modbus TCP user manual

ModuleTwo can be read and controlled on your local network with Modbus TCP. The connection is direct to the battery. It does not use TLS and it does not go through the cloud.

Use one controller for power commands. Home Assistant and Modbus TCP share the same setpoint. If both write, the last write wins.

## 1. Before you start

In the MyGrid app, set the battery’s control source to **Home Assistant**. That is the switch that opens this Modbus port. While the control source is **MyGrid**, the battery does not listen. Home Assistant appears as a choice only when it has been configured for that battery.

The battery and your Modbus client must be on the same Wi-Fi or LAN.

On a cluster, set Home Assistant only on the unit whose cluster mode is **Auto**. That unit is the leader. The power setpoint is the household total, and the leader splits it across the followers. Do not point Modbus at a Follow unit.

## 2. What you need

A Modbus TCP client. The battery is the server.

| Client | Examples | Typical use |
|--------|----------|-------------|
| Test software on a computer | Modbus Poll, QModMaster | Check the IP, port, and registers |
| Smart-home platform | Home Assistant, Domoticz | Show live values and run automations |
| Automation | Node-RED | Time schedules or price-based control |
| Own application | Dashboard, logger | Store or display the values |

## 3. Connect

1. Find the battery’s local IP address in the router’s DHCP client list.
2. Connect with the values below.
3. Read register **1** first. That is the state of charge in percent. A reply of `82` means 82%.

| Field | Value | Note |
|-------|--------|------|
| Protocol | Modbus TCP | Not Modbus RTU |
| Host | IP address of the battery | For example `192.168.1.20` |
| Port | `502` | |
| Unit id | `1` | Also called slave id or device address |
| Function | `03` | Read holding registers |
| First test register | `1` | State of charge, percent, unsigned |
| Length | `1` | Or `18` to read the whole map |

Only one client is served at a time. A second connection is closed.

The register numbers in this manual are the addresses to put in the request. They start at 0. Some programs show holding registers as 40001 and up, and some subtract 1 from the number you type. If register 1 does not return the state of charge, try 0 in that same program.

## 4. Function codes

| Code | Meaning | Use |
|------|---------|-----|
| `03` | Read holding registers | Read state of charge, power, limits, status, energy |
| `06` | Write a single register | Set the power setpoint, or reboot |
| `16` (`10` hex) | Write multiple registers | Write one or more registers in one request |

Any other function returns exception `01`. A wrong unit id returns exception `0A`.

## 5. Control

Read registers at any time while the port is open. Writes are accepted on two registers only.

1. Read register **3** (max charge) and register **4** (max discharge). Both are in steps of 0.1 kW. On a cluster leader these limits grow with the number of live batteries.
2. Write the setpoint to register **2**, in the same 0.1 kW steps. A positive value charges. A negative value discharges. `0` is idle. `12` means 1.2 kW charge. `-8` means 0.8 kW discharge.
3. A value outside registers 3 and 4 is clamped to that limit. Read register 2 again to see the value that was kept.
4. Read register **5** (battery power, watts) and register **6** (status) to see whether the battery is following the command.

The setpoint is applied about once a second. It uses the same power path as the Home Assistant power slider.

To reboot, write `1` to register **9**. Any other value returns exception `03` and does nothing. A write to a read-only register returns exception `02`.

Do not run a Home Assistant power automation and a Modbus power writer at the same time. They overwrite each other.

## 6. Register table

Read with function `03`. Write only where the access column says R/W or W.

Power and the setpoint use this sign: **positive is charge, negative is discharge**.

| Name | Register | Length | Access | Factor | Unit | Type | Description |
|------|----------|--------|--------|--------|------|------|-------------|
| Map version | 0 | 1 | R | 1 | — | U16 | `2` for this map. |
| State of charge | 1 | 1 | R | 1 | % | U16 | Battery state of charge. `82` means 82%. On the cluster leader this is the nameplate-weighted average of the leader and each live follower. |
| Power setpoint | 2 | 1 | R/W | 0.1 | kW | I16 | Requested power. Positive charges, negative discharges. `10` means 1.0 kW charge. `-8` means 0.8 kW discharge. |
| Max charge | 3 | 1 | R | 0.1 | kW | U16 | Highest charge setpoint the battery will accept right now. |
| Max discharge | 4 | 1 | R | 0.1 | kW | U16 | Highest discharge setpoint, as a positive number. A discharge write is the negative of this value. |
| Battery power | 5 | 1 | R | 1 | W | I16 | Measured battery power. Positive is charging, negative is discharging. |
| Status | 6 | 1 | R | 1 | — | U16 | `0` normal, `1` fault, `2` telemetry stale. |
| Fault flags | 7 | 2 | R | 1 | — | U32 | Fault bits. Low word is register 7, high word is register 8. `0` means no faults in this word. See the table below. |
| Reboot | 9 | 1 | W | 1 | — | U16 | Write `1` to reboot. Other values do nothing and return an error. A read returns `0`. |
| Stored energy | 10 | 2 | R | 1 | Wh | U32 | Energy currently stored. Low word on register 10, high word on register 11. |
| Lifetime charged | 12 | 2 | R | 1 | Wh | U32 | Energy charged into the battery over its life. Low word first. |
| Lifetime discharged | 14 | 2 | R | 1 | Wh | U32 | Energy discharged from the battery over its life. Low word first. |
| Total capacity | 16 | 2 | R | 1 | Wh | U32 | Full capacity of this battery. Low word on register 16, high word on register 17. |

Status `2` means the measurements or the fault word are not available. Treat the state of charge, battery power, and fault bits as unknown until status returns to `0` or `1`.

A two-register value is an unsigned 32-bit number, low word first:

`value = low + (high × 65536)`

A bit is active when it is 1. Bits that are not listed are unused.

### Fault bits

Register 7 holds bits 0–15. Register 8 holds bits 16–31. Bit 0 is also set when the battery system itself is in an error state, so it can be set together with “battery communication fault”.

| Register | Bit | Meaning |
|----------|-----|---------|
| 7 | 0 | Battery communication fault, or the battery system is in an error state |
| 7 | 1 | Battery internal communication fault |
| 7 | 2 | Battery over-voltage |
| 7 | 3 | Battery under-voltage |
| 7 | 4 | Charge over-current |
| 7 | 5 | Discharge over-current |
| 7 | 6 | Battery over-temperature |
| 7 | 7 | Battery under-temperature |
| 7 | 8 | Cell voltage imbalance |
| 7 | 9 | Hardware protection |
| 7 | 11 | Other fault |
| 7 | 12 | Voltage sensor fault |
| 7 | 13 | Temperature sensor fault |
| 7 | 14 | Current sensor fault |
| 7 | 15 | Relay fault |
| 8 | 3 | AC parallel alarm |
| 8 | 4 | Battery to solar-input communication fault |
| 8 | 5 | Forced charge failed |
| 8 | 7 | Parallel power fault |
| 8 | 10 | Fuse fault |
| 8 | 11 | Precharge fault |
| 8 | 13 | Temperature difference fault |

## 7. Troubleshooting

| What you see | What to check |
|--------------|----------------|
| The client cannot connect | Same network, correct IP, port `502`. The control source must be Home Assistant. On a cluster, connect to the Auto leader. |
| The connection opens and no value comes back | Modbus TCP, unit id `1`, function `03` for reads. |
| Register 1 is not the state of charge | Try address 0 in that client. Some programs shift the address by one. |
| Negative power looks like a large positive number | Interpret registers 2 and 5 as signed 16-bit integers. |
| A power write seems to do nothing | Control source is Home Assistant, and no other controller is writing the setpoint. Read registers 3 and 4, then read register 2 again. Status `2` means measurements are stale. |
| The battery keeps changing power | Home Assistant and Modbus are both writing. Stop one of them. |
| A second program cannot connect | Disconnect the first client. The battery accepts one connection. |