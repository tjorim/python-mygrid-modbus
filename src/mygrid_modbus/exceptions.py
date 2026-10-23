"""Device-specific errors, compatible with the neutral Modbus hierarchy."""

from modbus_connection import ModbusError


class MyGridError(ModbusError):
    """The battery returned data that cannot be used."""


class UnsupportedMapError(MyGridError):
    """The firmware's register map is not supported."""


class InvalidSetpointError(MyGridError):
    """A power request is not representable or exceeds live limits."""
