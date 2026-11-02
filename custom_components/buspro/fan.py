"""Fans on HDL relay or dimmer / 0-10V channels."""
import logging
import math

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .entity import entry_devices, room_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Set up Buspro fans from a config entry."""
    from .pybuspro.devices import Light

    buspro_module = hass.data[DOMAIN][config_entry.entry_id]
    entities = []
    for device_info in entry_devices(config_entry, "fan"):
        address = (device_info.get("subnet_id"), device_info.get("device_id"))
        channel = Light(buspro_module.hdl, address, device_info.get("channel", 1),
                        device_info.get("name", "Fan"))
        entities.append(BusproFan(
            buspro_module, channel, device_info,
            variable_speed=device_info.get("spk") == "fan.dimmer",
        ))
    async_add_entities(entities)


class BusproFan(FanEntity):
    """A fan driven by one HDL output channel.

    On a relay channel the fan is on/off. On a dimmer or 0-10V channel the
    channel level (0-100) is the fan speed in percent.
    """

    _attr_should_poll = False

    def __init__(self, buspro_module, device, device_info, variable_speed=False):
        self._buspro_module = buspro_module
        self._device = device
        self._variable_speed = variable_speed
        self._attr_name = device_info.get("name", "Fan")
        self._attr_unique_id = device_info.get("unique_id") or (
            f"buspro_{device._device_address[0]}_{device._device_address[1]}_"
            f"{device_info.get('channel', 1)}_fan"
        )
        features = FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
        if variable_speed:
            features |= FanEntityFeature.SET_SPEED
        self._attr_supported_features = features
        area_name = device_info.get("area_name", "")
        if area_name:
            self._attr_suggested_area = area_name
            self._attr_device_info = room_device_info(area_name)

    async def async_added_to_hass(self) -> None:
        async def _updated(device):
            self.async_write_ha_state()

        self._device.register_device_updated_cb(_updated)
        self.async_on_remove(lambda: self._device.unregister_device_updated_cb(_updated))

    @property
    def available(self):
        return self._buspro_module.is_available(self._device._device_address)

    @property
    def is_on(self):
        return self._device.is_on

    @property
    def percentage(self):
        if not self._variable_speed:
            return None
        return self._device.current_brightness

    @property
    def speed_count(self):
        return 100 if self._variable_speed else 1

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs) -> None:
        if self._variable_speed:
            if percentage is None:
                percentage = self._device.previous_brightness or 100
            await self._device.set_brightness(int(math.ceil(percentage)))
        else:
            await self._device.set_on()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self._device.set_off()
        self.async_write_ha_state()

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage == 0:
            await self.async_turn_off()
            return
        await self._device.set_brightness(int(percentage))
        self.async_write_ha_state()
