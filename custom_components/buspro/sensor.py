"""This component provides sensor support for Buspro."""
import logging
from datetime import timedelta

import homeassistant.helpers.config_validation as cv
try:
    from homeassistant.helpers.device_registry import DeviceInfo
except ImportError:
    from homeassistant.helpers.entity import DeviceInfo
import voluptuous as vol
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
    PLATFORM_SCHEMA,
)
from homeassistant.const import (
    CONF_NAME, 
    CONF_DEVICES, 
    CONF_ADDRESS, 
    CONF_TYPE, 
    CONF_UNIT_OF_MEASUREMENT,
    CONF_DEVICE_CLASS, 
    CONF_SCAN_INTERVAL,
    UnitOfTemperature,
    LIGHT_LUX,
)
from homeassistant.core import callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_DEVICES as CONF_DEVICES_ENTRY, DOMAIN

DEFAULT_CONF_UNIT_OF_MEASUREMENT = ""
DEFAULT_CONF_DEVICE_CLASS = "None"
DEFAULT_CONF_SCAN_INTERVAL = 0
DEFAULT_CONF_OFFSET = 0
CONF_DEVICE = "device"
CONF_OFFSET = "offset"

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_DEVICES):
        vol.All(cv.ensure_list, [
            vol.All({
                vol.Required(CONF_ADDRESS): cv.string,
                vol.Required(CONF_NAME): cv.string,
                vol.Required(CONF_TYPE): cv.string,
                vol.Optional(CONF_UNIT_OF_MEASUREMENT, default=DEFAULT_CONF_UNIT_OF_MEASUREMENT): cv.string,
                vol.Optional(CONF_DEVICE_CLASS, default=DEFAULT_CONF_DEVICE_CLASS): cv.string,
                vol.Optional(CONF_DEVICE, default=None): cv.string,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_CONF_SCAN_INTERVAL): cv.string,
                vol.Optional(CONF_OFFSET, default=DEFAULT_CONF_OFFSET): cv.string,
            })
        ])
})


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Set up Buspro sensor devices from a config entry."""
    # noinspection PyUnresolvedReferences
    from .pybuspro.devices import Sensor

    buspro_module = hass.data[DOMAIN][config_entry.entry_id]
    hdl = buspro_module.hdl
    raw_devices = config_entry.data.get(CONF_DEVICES_ENTRY, [])
    entities = []

    for device_info in raw_devices:
        if device_info.get("platform") != "sensor":
            continue

        name = device_info.get("name", "Sensor")
        subnet_id = device_info.get("subnet_id")
        device_id = device_info.get("device_id")
        area_name = device_info.get("area_name", "")
        spk = device_info.get("spk", "")

        device_address = (subnet_id, device_id)
        sensor_type = "illuminance" if ("lux" in spk or "illuminance" in spk) else "temperature"

        sensor = Sensor(hdl, device_address, name=name)
        entities.append(BusproSensor(
            hass, sensor, sensor_type=sensor_type, 
            area_name=area_name, 
            unique_id=device_info.get("unique_id"), 
            buspro_module=buspro_module
        ))

    async_add_entities(entities)


# noinspection PyUnusedLocal
async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up Buspro sensor devices from YAML (legacy fallback)."""
    # noinspection PyUnresolvedReferences
    from .pybuspro.devices import Sensor

    buspro_module = hass.data.get(DOMAIN, {}).get("legacy")
    hdl = buspro_module.hdl if buspro_module else None
    if not hdl:
        return

    devices = []

    for device_config in config[CONF_DEVICES]:
        address = device_config[CONF_ADDRESS]
        name = device_config[CONF_NAME]
        sensor_type = device_config[CONF_TYPE]
        device = device_config[CONF_DEVICE]
        offset = device_config[CONF_OFFSET]
        
        scan_interval = device_config[CONF_SCAN_INTERVAL]
        interval = int(scan_interval) if scan_interval is not None else 0
            
        address2 = address.split('.')
        device_address = (int(address2[0]), int(address2[1]))

        sensor = Sensor(hdl, device_address, device=device, name=name)
        devices.append(BusproSensor(
            hass, sensor, sensor_type=sensor_type, 
            scan_interval=interval, offset=offset, 
            buspro_module=buspro_module
        ))

    async_add_entities(devices)


class BusproSensor(SensorEntity):
    """Representation of a Buspro analog sensor."""

    def __init__(self, hass, device, sensor_type="temperature", scan_interval=0, offset=0, area_name="", unique_id=None, buspro_module=None):
        self._hass = hass
        self._device = device
        self._sensor_type = sensor_type
        self._offset = offset
        self._area_name = area_name
        self._custom_unique_id = unique_id
        self._buspro_module = buspro_module
        self._temperature = None
        self._brightness = None

        self._attr_state_class = SensorStateClass.MEASUREMENT
        if self._sensor_type == "temperature":
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        elif self._sensor_type == "illuminance":
            self._attr_device_class = SensorDeviceClass.ILLUMINANCE
            self._attr_native_unit_of_measurement = LIGHT_LUX

        if self._area_name:
            self._attr_suggested_area = self._area_name
            area_slug = self._area_name.lower().replace(" ", "_")
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"room_{area_slug}")},
                name=self._area_name,
                manufacturer="HDL Automation",
                suggested_area=self._area_name,
            )

        self._should_poll = scan_interval > 0
        self.async_register_callbacks()

    @callback
    def async_register_callbacks(self):
        """Register callbacks to update hass after device was changed."""
        async def after_update_callback(device):
            """Call after device was updated."""
            if self._hass is not None:
                self._temperature = self._device.temperature
                self._brightness = self._device.brightness
                self.async_write_ha_state()

        self._device.register_device_updated_cb(after_update_callback)

    @property
    def should_poll(self):
        """No polling needed within Buspro unless explicitly set."""
        return self._should_poll

    async def async_update(self):
        await self._device.read_sensor_status()

    @property
    def name(self):
        """Return the display name of this sensor."""
        return self._device.name

    @property
    def available(self):
        """Return True if entity is available."""
        if self._buspro_module:
            return self._buspro_module.connected
        return True

    @property
    def native_value(self):
        """Return the state/value of the sensor."""
        if self._sensor_type == "temperature":
            if self._temperature is None:
                return None
            val = self._temperature
            if self._offset:
                val += int(self._offset)
            return val

        if self._sensor_type == "illuminance":
            return self._brightness

        return None

    @property
    def unique_id(self):
        """Return the unique id."""
        if self._custom_unique_id:
            return self._custom_unique_id
        return f"{self._device.device_identifier}-{self._sensor_type}"
