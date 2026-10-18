"""This component provides binary sensor support for Buspro."""
import logging
from datetime import timedelta

import homeassistant.helpers.config_validation as cv
try:
    from homeassistant.helpers.device_registry import DeviceInfo
except ImportError:
    from homeassistant.helpers.entity import DeviceInfo
import voluptuous as vol
from homeassistant.components.binary_sensor import (
    PLATFORM_SCHEMA, 
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.const import (
    CONF_NAME, 
    CONF_DEVICES, 
    CONF_ADDRESS, 
    CONF_TYPE, 
    CONF_DEVICE_CLASS, 
    CONF_SCAN_INTERVAL,
)
from homeassistant.core import callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_DEVICES as CONF_DEVICES_ENTRY, DOMAIN

_LOGGER = logging.getLogger(__name__)

DEFAULT_CONF_DEVICE_CLASS = "None"
DEFAULT_CONF_SCAN_INTERVAL = 0

CONF_MOTION = 'motion'
CONF_DRY_CONTACT_1 = 'dry_contact_1'
CONF_DRY_CONTACT_2 = 'dry_contact_2'
CONF_UNIVERSAL_SWITCH = 'universal_switch'
CONF_SINGLE_CHANNEL = 'single_channel'
CONF_DRY_CONTACT = 'dry_contact'

SENSOR_TYPES = {
    CONF_MOTION,
    CONF_DRY_CONTACT_1,
    CONF_DRY_CONTACT_2,
    CONF_UNIVERSAL_SWITCH,
    CONF_SINGLE_CHANNEL,
    CONF_DRY_CONTACT,
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_DEVICES):
        vol.All(cv.ensure_list, [
            vol.All({
                vol.Required(CONF_ADDRESS): cv.string,
                vol.Required(CONF_NAME): cv.string,
                vol.Required(CONF_TYPE): vol.In(SENSOR_TYPES),
                vol.Optional(CONF_DEVICE_CLASS, default=DEFAULT_CONF_DEVICE_CLASS): cv.string,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_CONF_SCAN_INTERVAL): cv.string,
            })
        ])
})


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Set up Buspro binary sensor devices from a config entry."""
    # noinspection PyUnresolvedReferences
    from .pybuspro.devices import Sensor

    buspro_module = hass.data[DOMAIN][config_entry.entry_id]
    hdl = buspro_module.hdl
    raw_devices = config_entry.data.get(CONF_DEVICES_ENTRY, [])
    entities = []

    for device_info in raw_devices:
        if device_info.get("platform") != "binary_sensor":
            continue

        name = device_info.get("name", "Binary Sensor")
        subnet_id = device_info.get("subnet_id")
        device_id = device_info.get("device_id")
        channel = device_info.get("channel", 1)
        area_name = device_info.get("area_name", "")
        spk = device_info.get("spk", "")

        device_address = (subnet_id, device_id)

        if "motion" in spk or "pir" in spk:
            sensor_type = CONF_MOTION
            device_class = BinarySensorDeviceClass.MOTION
            sensor = Sensor(hdl, device_address, name=name)
        elif "universal" in spk:
            sensor_type = CONF_UNIVERSAL_SWITCH
            device_class = None
            sensor = Sensor(hdl, device_address, universal_switch_number=channel, name=name)
        else:
            sensor_type = CONF_DRY_CONTACT
            device_class = BinarySensorDeviceClass.OPENING
            sensor = Sensor(hdl, device_address, switch_number=channel, name=name)

        entities.append(BusproBinarySensor(
            hass, sensor, sensor_type=sensor_type, 
            device_class=device_class, area_name=area_name, 
            unique_id=device_info.get("unique_id"), 
            buspro_module=buspro_module
        ))

    async_add_entities(entities)


# noinspection PyUnusedLocal
async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up Buspro binary sensor devices from YAML (legacy fallback)."""
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
        device_class = device_config[CONF_DEVICE_CLASS]
        universal_switch_number = None
        channel_number = None
        switch_number = None

        scan_interval = device_config[CONF_SCAN_INTERVAL]
        interval = int(scan_interval) if scan_interval is not None else 0

        address2 = address.split('.')
        device_address = (int(address2[0]), int(address2[1]))

        if sensor_type == CONF_UNIVERSAL_SWITCH:
            universal_switch_number = int(address2[2])
        elif sensor_type == CONF_SINGLE_CHANNEL:
            channel_number = int(address2[2])
        elif sensor_type == CONF_DRY_CONTACT:
            switch_number = int(address2[2])

        sensor = Sensor(hdl, device_address, universal_switch_number=universal_switch_number,
                        channel_number=channel_number, switch_number=switch_number, name=name)

        devices.append(BusproBinarySensor(
            hass, sensor, sensor_type=sensor_type, 
            device_class=device_class, scan_interval=interval, 
            buspro_module=buspro_module
        ))

    async_add_entities(devices)


class BusproBinarySensor(BinarySensorEntity):
    """Representation of a Buspro binary sensor."""

    def __init__(self, hass, device, sensor_type=CONF_MOTION, device_class=None, scan_interval=0, area_name="", unique_id=None, buspro_module=None):
        self._hass = hass
        self._device = device
        self._attr_device_class = device_class
        self._sensor_type = sensor_type
        self._area_name = area_name
        self._custom_unique_id = unique_id
        self._buspro_module = buspro_module
        self._should_poll = scan_interval > 0

        if self._area_name:
            self._attr_suggested_area = self._area_name
            area_slug = self._area_name.lower().replace(" ", "_")
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"room_{area_slug}")},
                name=self._area_name,
                manufacturer="HDL Automation",
                suggested_area=self._area_name,
            )

        self.async_register_callbacks()

    @callback
    def async_register_callbacks(self):
        """Register callbacks to update hass after device was changed."""
        async def after_update_callback(device):
            """Call after device was updated."""
            self.async_write_ha_state()

        self._device.register_device_updated_cb(after_update_callback)

    @property
    def should_poll(self):
        """No polling needed within Buspro."""
        return self._should_poll

    async def async_update(self):
        if self._sensor_type == CONF_UNIVERSAL_SWITCH:
            await self._device.read_sensor_status()

    @property
    def name(self):
        """Return the display name of this binary sensor."""
        return self._device.name

    @property
    def available(self):
        """Return True if entity is available."""
        if self._buspro_module:
            return self._buspro_module.connected
        return True

    @property
    def unique_id(self):
        """Return the unique id."""
        if self._custom_unique_id:
            return self._custom_unique_id
        return f"{self._device.device_identifier}-{self._sensor_type}"

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        if self._sensor_type == CONF_MOTION:
            return self._device.movement
        if self._sensor_type == CONF_DRY_CONTACT_1:
            return self._device.dry_contact_1_is_on
        if self._sensor_type == CONF_DRY_CONTACT_2:
            return self._device.dry_contact_2_is_on
        if self._sensor_type == CONF_UNIVERSAL_SWITCH:
            return self._device.universal_switch_is_on
        if self._sensor_type == CONF_SINGLE_CHANNEL:
            return self._device.single_channel_is_on
        if self._sensor_type == CONF_DRY_CONTACT:
            return self._device.switch_status
        return False
