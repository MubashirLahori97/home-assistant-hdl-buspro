"""Wall-panel button events for HDL Buspro.

HDL panels do not send a "button pressed" message. Each button sends the
command it is programmed with (channel control, scene, sequence or universal
switch) to its target address. This platform listens for commands sent *by*
a panel and turns them into events, so a button can drive any automation.
"""
import logging

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, EVENT_PANEL_BUTTON
from .entity import entry_devices, room_device_info
from .pybuspro.helpers.enums import OperateCode

_LOGGER = logging.getLogger(__name__)

EVENT_CHANNEL_ON = "channel_on"
EVENT_CHANNEL_OFF = "channel_off"
EVENT_SCENE = "scene"
EVENT_SEQUENCE = "sequence"
EVENT_UNIVERSAL_SWITCH_ON = "universal_switch_on"
EVENT_UNIVERSAL_SWITCH_OFF = "universal_switch_off"

EVENT_TYPES = [
    EVENT_CHANNEL_ON,
    EVENT_CHANNEL_OFF,
    EVENT_SCENE,
    EVENT_SEQUENCE,
    EVENT_UNIVERSAL_SWITCH_ON,
    EVENT_UNIVERSAL_SWITCH_OFF,
]


def decode_panel_telegram(telegram):
    """Turn a command sent by a panel into (event_type, attributes).

    Returns None for messages that are not button commands.
    """
    payload = telegram.payload or []
    target = list(telegram.target_address)
    code = telegram.operate_code

    if code == OperateCode.SingleChannelControl and len(payload) >= 2:
        level = payload[1]
        return (
            EVENT_CHANNEL_ON if level > 0 else EVENT_CHANNEL_OFF,
            {"target_address": target, "channel": payload[0], "level": level},
        )
    if code == OperateCode.SceneControl and len(payload) >= 2:
        return (
            EVENT_SCENE,
            {"target_address": target, "area": payload[0], "scene": payload[1]},
        )
    if code == OperateCode.SequenceControl and len(payload) >= 2:
        return (
            EVENT_SEQUENCE,
            {"target_address": target, "area": payload[0], "sequence": payload[1]},
        )
    if code == OperateCode.UniversalSwitchControl and len(payload) >= 2:
        return (
            EVENT_UNIVERSAL_SWITCH_ON if payload[1] else EVENT_UNIVERSAL_SWITCH_OFF,
            {"target_address": target, "switch": payload[0]},
        )
    return None


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Set up panel button event entities from a config entry."""
    buspro_module = hass.data[DOMAIN][config_entry.entry_id]
    entities = [
        BusproPanelEvent(buspro_module, device_info)
        for device_info in entry_devices(config_entry, "event")
    ]
    async_add_entities(entities)


class BusproPanelEvent(EventEntity):
    """Events for the buttons of one HDL wall panel."""

    _attr_should_poll = False
    _attr_event_types = EVENT_TYPES
    _attr_icon = "mdi:gesture-tap-button"

    def __init__(self, buspro_module, device_info):
        self._buspro_module = buspro_module
        self._address = (device_info.get("subnet_id"), device_info.get("device_id"))
        self._attr_name = device_info.get("name", "Panel buttons")
        self._attr_unique_id = device_info.get("unique_id") or (
            f"buspro_{self._address[0]}_{self._address[1]}_panel_buttons"
        )
        area_name = device_info.get("area_name", "")
        if area_name:
            self._attr_suggested_area = area_name
            self._attr_device_info = room_device_info(area_name)

    async def async_added_to_hass(self) -> None:
        hdl = self._buspro_module.hdl
        hdl.register_telegram_received_all_messages_cb(self._telegram_received)
        self.async_on_remove(
            lambda: hdl.unregister_telegram_received_all_messages_cb(self._telegram_received)
        )

    @property
    def available(self):
        return self._buspro_module.is_available(self._address)

    @callback
    def _telegram_received(self, telegram):
        if tuple(telegram.source_address) != self._address:
            return
        decoded = decode_panel_telegram(telegram)
        if decoded is None:
            return
        event_type, attributes = decoded
        self._trigger_event(event_type, attributes)
        self.async_write_ha_state()
        self.hass.bus.async_fire(EVENT_PANEL_BUTTON, {
            "entity_id": self.entity_id,
            "panel_address": list(self._address),
            "type": event_type,
            **attributes,
        })
