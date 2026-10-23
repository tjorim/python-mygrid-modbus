"""ModuleTwo register-map constants and documented fault names."""

MAP_VERSION = 2
UNIT_ID = 1
REGISTER_COUNT = 18

FAULTS: dict[int, str] = {
    0: "battery_communication",
    1: "internal_communication",
    2: "over_voltage",
    3: "under_voltage",
    4: "charge_over_current",
    5: "discharge_over_current",
    6: "over_temperature",
    7: "under_temperature",
    8: "cell_imbalance",
    9: "hardware_protection",
    11: "other",
    12: "voltage_sensor",
    13: "temperature_sensor",
    14: "current_sensor",
    15: "relay",
    19: "ac_parallel",
    20: "solar_communication",
    21: "forced_charge",
    23: "parallel_power",
    26: "fuse",
    27: "precharge",
    29: "temperature_difference",
}
