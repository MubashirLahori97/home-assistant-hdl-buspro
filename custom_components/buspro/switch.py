"""This component provides switch support for Buspro."""
import logging

import homeassistant.helpers.config_validation as cv
try:
    from homeassistant.helpers.device_registry import DeviceInfo
except ImportError:
    from homeassistant.helpers.entity import DeviceInfo
import voluptuous as vol
from homeassistant.components.switch import SwitchEntity, PLATFORM_SCHEMA
from homeassistant.const import (CONF_NAME, CONF_DEVICES)
from homeassistant.core import callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_DEVICES as CONF_DEVICES_ENTRY, DOMAIN

_LOGGER = logging.getLogger(__name__)

DEVICE_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME): cv.string,
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_DEVICES): {cv.string: DEVICE_SCHEMA},
})


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Set up Buspro switch devices from a config entry."""
    # noinspection PyUnresolvedReferences
    from .pybuspro.devices import Switch

    buspro_module = hass.data[DOMAIN][config_entry.entry_id]
    hdl = buspro_module.hdl
    raw_devices = config_entry.data.get(CONF_DEVICES_ENTRY, [])
    entities = []

    for device_info in raw_devices:
        if device_info.get("platform") != "switch":
            continue

        name = device_info.get("name", "Switch")
        subnet_id = device_info.get("subnet_id")
        device_id = device_info.get("device_id")
        channel = device_info.get("channel")
        area_name = device_info.get("area_name", "")

        device_address = (subnet_id, device_id)
        switch = Switch(hdl, device_address, channel, name)
        entities.append(BusproSwitch(
            hass, switch, 
            area_name=area_name, 
            unique_id=device_info.get("unique_id"), 
            buspro_module=buspro_module
        ))

    async_add_entities(entities)


# noinspection PyUnusedLocal
async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up Buspro switch devices from YAML (legacy fallback)."""
    # noinspection PyUnresolvedReferences
    from .pybuspro.devices import Switch

    buspro_module = hass.data.get(DOMAIN, {}).get("legacy")
    hdl = buspro_module.hdl if buspro_module else None
    if not hdl:
        return

    devices = []

    for address, device_config in config.get(CONF_DEVICES, {}).items():
        name = device_config[CONF_NAME]

        address2 = address.split('.')
        device_address = (int(address2[0]), int(address2[1]))
        channel_number = int(address2[2])

        switch = Switch(hdl, device_address, channel_number, name)
        devices.append(BusproSwitch(
            hass, switch, 
            buspro_module=buspro_module
        ))

    async_add_entities(devices)


class BusproSwitch(SwitchEntity):
    """Representation of a Buspro switch."""

    def __init__(self, hass, device, area_name="", unique_id=None, buspro_module=None):
        self._hass = hass
        self._device = device
        self._area_name = area_name
        self._custom_unique_id = unique_id
        self._buspro_module = buspro_module

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
        return False

    @property
    def name(self):
        """Return the display name of this switch."""
        return self._device.name

    @property
    def available(self):
        """Return True if entity is available."""
        if self._buspro_module:
            return self._buspro_module.connected
        return True

    @property
    def is_on(self):
        """Return true if switch is on."""
        return self._device.is_on

    async def async_turn_on(self, **kwargs):
        """Instruct the switch to turn on."""
        await self._device.set_on()

    async def async_turn_off(self, **kwargs):
        """Instruct the switch to turn off."""
        await self._device.set_off()

    @property
    def unique_id(self):
        """Return the unique id."""
        if self._custom_unique_id:
            return self._custom_unique_id
        return self._device.device_identifier
