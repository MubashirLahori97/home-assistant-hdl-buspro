"""Experimental: a sensor that polls any HDL read command and decodes bytes.

HDL's command list names power-meter reads (voltage 0xD902, power factor
0xD904, current 0xD908, power 0xD90A, energy 0xD91A) but no public source
documents their reply layout. Rather than guess, this sensor lets the user
say which bytes of the reply hold the value. Capture a reply with the bus
monitor, then set the byte offset, length, byte order and scale.
"""
import asyncio
import logging

from homeassistant.components.sensor import SensorEntity

from .entity import room_device_info
from .pybuspro.core.telegram import Telegram

_LOGGER = logging.getLogger(__name__)

# Presets fill in the request code, unit and classes; the byte layout is
# still the user's to confirm against a captured reply.
RAW_SENSOR_PRESETS = {
    "custom": {},
    "voltage": {"request_code": 0xD902, "unit": "V", "device_class": "voltage",
                "state_class": "measurement"},
    "current": {"request_code": 0xD908, "unit": "A", "device_class": "current",
                "state_class": "measurement"},
    "power": {"request_code": 0xD90A, "unit": "W", "device_class": "power",
              "state_class": "measurement"},
    "power_factor": {"request_code": 0xD904, "unit": None, "device_class": "power_factor",
                     "state_class": "measurement"},
    "energy": {"request_code": 0xD91A, "unit": "kWh", "device_class": "energy",
               "state_class": "total_increasing"},
}


class _RawCode:
    """Operate code holder with the .value shape the telegram builder reads."""

    def __init__(self, code):
        self.value = bytes(((code >> 8) & 0xFF, code & 0xFF))
        self.name = f"0x{code:04X}"


def decode_value(payload, offset, length, byteorder="big", signed=False, scale=1.0):
    """Read an integer from payload bytes and scale it. None if too short."""
    if offset < 0 or length < 1 or len(payload) < offset + length:
        return None
    raw = int.from_bytes(bytes(payload[offset:offset + length]), byteorder, signed=signed)
    value = raw * scale
    return round(value, 6)


class BusproRawSensor(SensorEntity):
    """Poll an HDL read command and expose one decoded value."""

    _attr_should_poll = False

    def __init__(self, buspro_module, device_info):
        self._buspro_module = buspro_module
        self._address = (device_info.get("subnet_id"), device_info.get("device_id"))
        self._request_code = int(device_info.get("request_code", 0))
        self._response_code = int(device_info.get("response_code") or self._request_code + 1)
        self._request_payload = list(device_info.get("request_payload", []) or [])
        self._offset = int(device_info.get("byte_offset", 0))
        self._length = int(device_info.get("byte_length", 2))
        self._byteorder = device_info.get("byteorder", "big")
        self._signed = bool(device_info.get("signed", False))
        self._scale = float(device_info.get("scale", 1.0))
        self._interval = max(5, int(device_info.get("scan_interval", 30)))
        self._task = None

        self._attr_name = device_info.get("name", "Raw sensor")
        self._attr_unique_id = device_info.get("unique_id")
        self._attr_native_unit_of_measurement = device_info.get("unit") or None
        self._attr_device_class = device_info.get("device_class") or None
        self._attr_state_class = device_info.get("state_class") or None
        area_name = device_info.get("area_name", "")
        if area_name:
            self._attr_suggested_area = area_name
            self._attr_device_info = room_device_info(area_name)

    async def async_added_to_hass(self) -> None:
        self._task = self.hass.async_create_background_task(
            self._poll(), f"buspro raw sensor {self._attr_unique_id}")

    async def async_will_remove_from_hass(self) -> None:
        if self._task is not None:
            self._task.cancel()

    @property
    def available(self):
        return self._buspro_module.is_available(self._address)

    async def _poll(self):
        await asyncio.sleep(5)
        while True:
            await self.async_read()
            await asyncio.sleep(self._interval)

    async def async_read(self):
        telegram = Telegram()
        telegram.target_address = self._address
        telegram.operate_code = _RawCode(self._request_code)
        telegram.payload = list(self._request_payload)
        reply = await self._buspro_module.hdl.request(
            telegram, _RawCode(self._response_code).value, timeout=1.5, retries=1)
        if reply is None:
            return
        payload = list(reply.payload or [])
        _LOGGER.debug("Raw sensor %s reply payload: %s", self._attr_unique_id, payload)
        value = decode_value(payload, self._offset, self._length,
                             self._byteorder, self._signed, self._scale)
        if value is None:
            _LOGGER.warning(
                "Raw sensor %s: reply has %d bytes, expected at least %d. Payload: %s",
                self._attr_name, len(payload), self._offset + self._length, payload)
            return
        self._attr_native_value = value
        self._attr_extra_state_attributes = {"raw_payload": payload}
        self.async_write_ha_state()
