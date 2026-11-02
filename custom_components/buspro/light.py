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
    LightEntityFeature,
    PLATFORM_SCHEMA,
    ATTR_BRIGHTNESS,
    ATTR_TRANSITION,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ATTR_RGBW_COLOR,
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

        if device_info.get("spk") == "light.color":
            entities.append(BusproColorLight.from_device_info(
                hass, hdl, device_info, buspro_module))
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

        # Transition support: without this flag Home Assistant strips the
        # transition value from the call before the entity ever sees it.
        self._attr_supported_features = LightEntityFeature.TRANSITION

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
            return self._buspro_module.is_available(
                getattr(self._device, "_device_address", None))
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
        transition = kwargs.get(ATTR_TRANSITION)
        # Transition arrives as a float; the telegram payload only takes
        # whole bytes, so convert before it reaches the bus.
        running_time = (
            int(round(transition)) if transition is not None else self._running_time
        )
        if self._dimmable:
            brightness = int(kwargs.get(ATTR_BRIGHTNESS, 255) / 255 * 100)
            if not self.is_on and self._device.previous_brightness is not None and brightness == 100:
                brightness = self._device.previous_brightness
            await self._device.set_brightness(brightness, running_time)
        else:
            await self._device.set_on(running_time)

    async def async_turn_off(self, **kwargs):
        """Instruct the light to turn off."""
        transition = kwargs.get(ATTR_TRANSITION)
        running_time = (
            int(round(transition)) if transition is not None else self._running_time
        )
        await self._device.set_off(running_time)

    @property
    def unique_id(self):
        """Return the unique id."""
        if self._custom_unique_id:
            return self._custom_unique_id
        return self._device.device_identifier


DEFAULT_MIN_KELVIN = 2700
DEFAULT_MAX_KELVIN = 6500


def cct_to_levels(brightness_pct, kelvin, min_kelvin, max_kelvin):
    """Split a brightness (0-100) and colour temperature over warm/cool."""
    kelvin = max(min_kelvin, min(max_kelvin, kelvin))
    ratio = (kelvin - min_kelvin) / (max_kelvin - min_kelvin)
    peak = max(ratio, 1 - ratio)
    warm = brightness_pct * (1 - ratio) / peak
    cool = brightness_pct * ratio / peak
    return int(round(warm)), int(round(cool))


def levels_to_cct(warm, cool, min_kelvin, max_kelvin):
    """Return (brightness 0-100, kelvin) from warm/cool levels."""
    total = warm + cool
    if total == 0:
        return 0, None
    ratio = cool / total
    return max(warm, cool), int(round(min_kelvin + ratio * (max_kelvin - min_kelvin)))


def color_to_levels(brightness_pct, color):
    """Scale an RGB(W) colour (0-255 each) so its brightest part is brightness_pct."""
    peak = max(color) or 1
    return [int(round(c / peak * brightness_pct)) for c in color]


def levels_to_color(levels):
    """Return (brightness 0-100, colour 0-255 each) from channel levels."""
    peak = max(levels)
    if peak == 0:
        return 0, None
    return peak, tuple(int(round(level / peak * 255)) for level in levels)


class BusproColorLight(LightEntity):
    """A tunable-white or RGB(W) light built from several HDL channels.

    HDL has no colour command: each colour is its own dimmer channel, so the
    light sets the channels together and rebuilds its state from them.
    Channels are stored warm, cool (cct) or red, green, blue[, white].
    """

    def __init__(self, hass, channels, color_mode, name, unique_id,
                 area_name="", buspro_module=None,
                 min_kelvin=DEFAULT_MIN_KELVIN, max_kelvin=DEFAULT_MAX_KELVIN):
        self._hass = hass
        self._channels = channels
        self._mode = color_mode
        self._buspro_module = buspro_module
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_should_poll = False
        self._attr_supported_features = LightEntityFeature.TRANSITION
        self._min_kelvin = min_kelvin
        self._max_kelvin = max_kelvin
        self._last_color = None
        self._last_kelvin = None

        if color_mode == "cct":
            self._attr_color_mode = ColorMode.COLOR_TEMP
            self._attr_supported_color_modes = {ColorMode.COLOR_TEMP}
            self._attr_min_color_temp_kelvin = min_kelvin
            self._attr_max_color_temp_kelvin = max_kelvin
        elif color_mode == "rgbw":
            self._attr_color_mode = ColorMode.RGBW
            self._attr_supported_color_modes = {ColorMode.RGBW}
        else:
            self._attr_color_mode = ColorMode.RGB
            self._attr_supported_color_modes = {ColorMode.RGB}

        if area_name:
            self._attr_suggested_area = area_name
            area_slug = area_name.lower().replace(" ", "_")
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"room_{area_slug}")},
                name=area_name,
                manufacturer="HDL Automation",
                suggested_area=area_name,
            )

    @classmethod
    def from_device_info(cls, hass, hdl, device_info, buspro_module):
        """Build the light from a stored config entry device."""
        from .pybuspro.devices import Light

        address = (device_info.get("subnet_id"), device_info.get("device_id"))
        channels = [Light(hdl, address, number) for number in device_info.get("channels", [])]
        return cls(
            hass, channels, device_info.get("color_mode", "cct"),
            device_info.get("name", "Light"),
            device_info.get("unique_id"),
            area_name=device_info.get("area_name", ""),
            buspro_module=buspro_module,
            min_kelvin=device_info.get("min_kelvin", DEFAULT_MIN_KELVIN),
            max_kelvin=device_info.get("max_kelvin", DEFAULT_MAX_KELVIN),
        )

    async def async_added_to_hass(self) -> None:
        async def _updated(device):
            self.async_write_ha_state()

        for channel in self._channels:
            channel.register_device_updated_cb(_updated)

    @property
    def available(self):
        if self._buspro_module and self._channels:
            return self._buspro_module.is_available(self._channels[0]._device_address)
        return True

    @property
    def _levels(self):
        return [channel.current_brightness for channel in self._channels]

    @property
    def is_on(self):
        return any(level > 0 for level in self._levels)

    @property
    def brightness(self):
        levels = self._levels
        if self._mode == "cct":
            pct, _ = levels_to_cct(levels[0], levels[1], self._min_kelvin, self._max_kelvin)
        else:
            pct, _ = levels_to_color(levels)
        return int(round(pct / 100 * 255))

    @property
    def color_temp_kelvin(self):
        if self._mode != "cct":
            return None
        levels = self._levels
        _, kelvin = levels_to_cct(levels[0], levels[1], self._min_kelvin, self._max_kelvin)
        return kelvin or self._last_kelvin or self._max_kelvin

    @property
    def rgb_color(self):
        if self._mode != "rgb":
            return None
        _, color = levels_to_color(self._levels)
        return color or self._last_color or (255, 255, 255)

    @property
    def rgbw_color(self):
        if self._mode != "rgbw":
            return None
        _, color = levels_to_color(self._levels)
        return color or self._last_color or (255, 255, 255, 255)

    async def async_turn_on(self, **kwargs):
        transition = kwargs.get(ATTR_TRANSITION)
        running_time = int(round(transition)) if transition is not None else 0
        if ATTR_BRIGHTNESS in kwargs:
            pct = int(round(kwargs[ATTR_BRIGHTNESS] / 255 * 100))
        elif self.is_on:
            pct = int(round(self.brightness / 255 * 100))
        else:
            pct = 100

        if self._mode == "cct":
            kelvin = kwargs.get(ATTR_COLOR_TEMP_KELVIN) or self.color_temp_kelvin
            self._last_kelvin = kelvin
            levels = cct_to_levels(pct, kelvin, self._min_kelvin, self._max_kelvin)
        else:
            if self._mode == "rgbw":
                color = kwargs.get(ATTR_RGBW_COLOR) or self.rgbw_color
            else:
                color = kwargs.get(ATTR_RGB_COLOR) or self.rgb_color
            self._last_color = tuple(color)
            levels = color_to_levels(pct, color)

        for channel, level in zip(self._channels, levels):
            await channel.set_brightness(level, running_time)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        transition = kwargs.get(ATTR_TRANSITION)
        running_time = int(round(transition)) if transition is not None else 0
        if self._mode == "cct":
            self._last_kelvin = self.color_temp_kelvin
        else:
            _, color = levels_to_color(self._levels)
            if color:
                self._last_color = color
        for channel in self._channels:
            await channel.set_off(running_time)
        self.async_write_ha_state()
