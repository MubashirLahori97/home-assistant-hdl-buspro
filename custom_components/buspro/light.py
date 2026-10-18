"""This component provides light support for Buspro."""
import logging

import homeassistant.helpers.config_validation as cv
try:
    from homeassistant.helpers.device_registry import DeviceInfo
except ImportError:
    from homeassistant.helpers.entity import DeviceInfo
import voluptuous as vol
from homeassistant.components.light import (
    LightEntity, 
    ColorMode, 
    PLATFORM_SCHEMA, 
    ATTR_BRIGHTNESS,
    ATTR_TRANSITION
)
from homeassistant.const import (CONF_NAME, CONF_DEVICES)
from homeassistant.core import callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_DEVICES as CONF_DEVICES_ENTRY, DOMAIN

_LOGGER = logging.getLogger(__name__)

DEFAULT_DEVICE_RUNNING_TIME = 0
DEFAULT_PLATFORM_RUNNING_TIME = 0
DEFAULT_DIMMABLE = True

DEVICE_SCHEMA = vol.Schema({
    vol.Optional("running_time", default=DEFAULT_DEVICE_RUNNING_TIME): cv.positive_int,
    vol.Optional("dimmable", default=DEFAULT_DIMMABLE): cv.boolean,
    vol.Required(CONF_NAME): cv.string,
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional("running_time", default=DEFAULT_PLATFORM_RUNNING_TIME): cv.positive_int,
    vol.Required(CONF_DEVICES): {cv.string: DEVICE_SCHEMA},
})


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Set up Buspro light devices from a config entry."""
    # noinspection PyUnresolvedReferences
    from .pybuspro.devices import Light

    buspro_module = hass.data[DOMAIN][config_entry.entry_id]
    hdl = buspro_module.hdl
    raw_devices = config_entry.data.get(CONF_DEVICES_ENTRY, [])
    entities = []

    for device_info in raw_devices:
        if device_info.get("platform") != "light":
            continue

        name = device_info.get("name", "Light")
        subnet_id = device_info.get("subnet_id")
        device_id = device_info.get("device_id")
        channel = device_info.get("channel")
        area_name = device_info.get("area_name", "")
        capabilities = device_info.get("capabilities", [])
        spk = device_info.get("spk", "")

        dimmable = ("brightness" in capabilities) or (spk in ("light.dimming", "light.cct"))

        device_address = (subnet_id, device_id)
        light = Light(hdl, device_address, channel, name)
        entities.append(BusproLight(
            hass, light, 0, dimmable, 
            area_name=area_name, 
            unique_id=device_info.get("unique_id"), 
            buspro_module=buspro_module
        ))

    async_add_entities(entities)


# noinspection PyUnusedLocal
async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up Buspro light devices from YAML (legacy fallback)."""
    # noinspection PyUnresolvedReferences
    from .pybuspro.devices import Light

    buspro_module = hass.data.get(DOMAIN, {}).get("legacy")
    hdl = buspro_module.hdl if buspro_module else None
    if not hdl:
        return

    devices = []
    platform_running_time = int(config.get("running_time", 0))

    for address, device_config in config.get(CONF_DEVICES, {}).items():
        name = device_config[CONF_NAME]
        device_running_time = int(device_config.get("running_time", 0))
        dimmable = bool(device_config.get("dimmable", True))

        if device_running_time == 0:
            device_running_time = platform_running_time
        if dimmable:
            device_running_time = 0

        address2 = address.split('.')
        device_address = (int(address2[0]), int(address2[1]))
        channel_number = int(address2[2])

        light = Light(hdl, device_address, channel_number, name)
        devices.append(BusproLight(
            hass, light, device_running_time, dimmable, 
            buspro_module=buspro_module
        ))

    async_add_entities(devices)


class BusproLight(LightEntity):
    """Representation of a Buspro light."""

    def __init__(self, hass, device, running_time=0, dimmable=True, area_name="", unique_id=None, buspro_module=None):
        self._hass = hass
        self._device = device
        self._running_time = running_time
        self._dimmable = dimmable
        self._area_name = area_name
        self._custom_unique_id = unique_id
        self._buspro_module = buspro_module

        if self._dimmable:
            self._attr_color_mode = ColorMode.BRIGHTNESS
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
        else:
            self._attr_color_mode = ColorMode.ONOFF
            self._attr_supported_color_modes = {ColorMode.ONOFF}

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
        """Return the display name of this light."""
        return self._device.name

    @property
    def available(self):
        """Return True if entity is available."""
        if self._buspro_module:
            return self._buspro_module.connected
        return True

    @property
    def brightness(self):
        """Return the brightness of the light."""
        if not self._dimmable:
            return None
        brightness = self._device.current_brightness / 100 * 255
        return brightness

    @property
    def is_on(self):
        """Return true if light is on."""
        return self._device.is_on

    async def async_turn_on(self, **kwargs):
        """Instruct the light to turn on."""
        running_time = kwargs.get(ATTR_TRANSITION, self._running_time)
        if self._dimmable:
            brightness = int(kwargs.get(ATTR_BRIGHTNESS, 255) / 255 * 100)
            if not self.is_on and self._device.previous_brightness is not None and brightness == 100:
                brightness = self._device.previous_brightness
            await self._device.set_brightness(brightness, running_time)
        else:
            await self._device.set_on(running_time)

    async def async_turn_off(self, **kwargs):
        """Instruct the light to turn off."""
        await self._device.set_off(kwargs.get(ATTR_TRANSITION, self._running_time))

    @property
    def unique_id(self):
        """Return the unique id."""
        if self._custom_unique_id:
            return self._custom_unique_id
        return self._device.device_identifier
