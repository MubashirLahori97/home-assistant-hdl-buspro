"""Buspro scenes and sequences as button entities."""
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .entity import entry_devices, room_device_info
from .pybuspro.devices.control import _SceneControl, _SequenceControl

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Set up scene and sequence buttons from a config entry."""
    buspro_module = hass.data[DOMAIN][config_entry.entry_id]
    entities = [
        BusproSceneButton(buspro_module, device_info)
        for device_info in entry_devices(config_entry, "button")
    ]
    async_add_entities(entities)


class BusproSceneButton(ButtonEntity):
    """Run a scene or sequence stored in an HDL module."""

    _attr_should_poll = False

    def __init__(self, buspro_module, device_info):
        self._buspro_module = buspro_module
        self._address = (device_info.get("subnet_id"), device_info.get("device_id"))
        self._area_number = device_info.get("area_number", 1)
        self._number = device_info.get("channel", 1)
        self._is_sequence = device_info.get("spk") == "sequence.bus"
        kind = "sequence" if self._is_sequence else "scene"
        self._attr_name = device_info.get("name") or f"{kind.title()} {self._number}"
        self._attr_icon = "mdi:play-box-multiple" if self._is_sequence else "mdi:palette"
        self._attr_unique_id = device_info.get("unique_id") or (
            f"buspro_{self._address[0]}_{self._address[1]}_"
            f"{kind}_{self._area_number}_{self._number}"
        )
        area_name = device_info.get("area_name", "")
        if area_name:
            self._attr_suggested_area = area_name
            self._attr_device_info = room_device_info(area_name)

    @property
    def available(self):
        return self._buspro_module.is_available(self._address)

    async def async_press(self) -> None:
        hdl = self._buspro_module.hdl
        control = _SequenceControl(hdl) if self._is_sequence else _SceneControl(hdl)
        control.subnet_id, control.device_id = self._address
        control.area_number = self._area_number
        if self._is_sequence:
            control.sequence_number = self._number
        else:
            control.scene_number = self._number
        await control.send()
