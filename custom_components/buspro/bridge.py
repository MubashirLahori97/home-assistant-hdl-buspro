"""HDL bridge: control any Home Assistant entity from an HDL panel.

Home Assistant answers on the bus as a virtual HDL device at an unused
address. A panel button pointed at that address (universal switch, relay
channel or dimmer channel) reaches Home Assistant, which drives the bridged
entity: a Tuya light, a Zigbee plug, a script and so on. Home Assistant
replies like a real module would, and announces state changes made outside
HDL, so the panel's button LED follows the real device.
"""
import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, STATE_ON, STATE_OPEN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_BRIDGES
from .pybuspro.core.telegram import Telegram
from .pybuspro.helpers.enums import OperateCode

_LOGGER = logging.getLogger(__name__)

KIND_UNIVERSAL_SWITCH = "universal_switch"
KIND_RELAY = "relay"
KIND_DIMMER = "dimmer"
BRIDGE_KINDS = [KIND_UNIVERSAL_SWITCH, KIND_RELAY, KIND_DIMMER]

BROADCAST_ADDRESS = (255, 255)
SUCCESS = 0xF8

# A state change within this many seconds of a bus command that reported the
# same level is the echo of that command, so it is not announced again.
ECHO_WINDOW = 2.0


def entity_level(state):
    """Return a bridged entity's state as an HDL level (0-100)."""
    if state is None:
        return 0
    domain = state.entity_id.split(".")[0]
    if domain == "light":
        if state.state != STATE_ON:
            return 0
        brightness = state.attributes.get("brightness")
        if brightness is None:
            return 100
        return max(1, int(round(brightness / 255 * 100)))
    if domain == "cover":
        position = state.attributes.get("current_position")
        if position is not None:
            return int(position)
        return 100 if state.state == STATE_OPEN else 0
    if domain == "fan":
        if state.state != STATE_ON:
            return 0
        percentage = state.attributes.get("percentage")
        return int(percentage) if percentage else 100
    return 100 if state.state in (STATE_ON, STATE_OPEN) else 0


def service_for_level(entity_id, level, kind):
    """Return (domain, service, data) that brings the entity to an HDL level."""
    domain = entity_id.split(".")[0]
    data = {ATTR_ENTITY_ID: entity_id}
    on = level > 0
    if domain in ("scene", "script"):
        return (domain, "turn_on", data) if on else None
    if domain == "cover":
        if kind == KIND_DIMMER:
            return ("cover", "set_cover_position", {**data, "position": level})
        return ("cover", "open_cover" if on else "close_cover", data)
    if domain == "light" and on and kind == KIND_DIMMER:
        return ("light", "turn_on", {**data, "brightness_pct": level})
    if domain == "fan" and on and kind == KIND_DIMMER:
        return ("fan", "turn_on", {**data, "percentage": level})
    if domain in ("light", "switch", "fan", "input_boolean", "media_player",
                  "climate", "humidifier", "siren", "automation"):
        return (domain, "turn_on" if on else "turn_off", data)
    return ("homeassistant", "turn_on" if on else "turn_off", data)


async def async_setup_bridges(hass: HomeAssistant, config_entry: ConfigEntry, buspro_module):
    """Start the bridge for this config entry, if it has bridged entities."""
    bridges = config_entry.data.get(CONF_BRIDGES, []) or []
    if not bridges:
        return None
    bridge = HdlBridge(hass, buspro_module, bridges)
    bridge.start()
    config_entry.async_on_unload(bridge.stop)
    return bridge


class HdlBridge:
    """Virtual HDL devices that front Home Assistant entities."""

    def __init__(self, hass, buspro_module, bridges):
        self.hass = hass
        self._buspro_module = buspro_module
        self._bridges = [dict(b) for b in bridges]
        self._addresses = {(b["subnet_id"], b["device_id"]) for b in self._bridges}
        # bridge index -> (level, time) last reported because of a bus command
        self._last_command = {}
        self._unsub_state = None

    @property
    def hdl(self):
        return self._buspro_module.hdl

    def start(self):
        self.hdl.register_telegram_received_all_messages_cb(self._telegram_received)
        entity_ids = sorted({b["entity_id"] for b in self._bridges})
        self._unsub_state = async_track_state_change_event(
            self.hass, entity_ids, self._entity_changed)

    def stop(self):
        self.hdl.unregister_telegram_received_all_messages_cb(self._telegram_received)
        if self._unsub_state is not None:
            self._unsub_state()
            self._unsub_state = None

    def _find(self, address, kinds, number):
        for index, bridge in enumerate(self._bridges):
            if ((bridge["subnet_id"], bridge["device_id"]) == address
                    and bridge["kind"] in kinds and bridge["number"] == number):
                return index, bridge
        return None, None

    def _channel_bridges(self, address):
        return [b for b in self._bridges
                if (b["subnet_id"], b["device_id"]) == address
                and b["kind"] in (KIND_RELAY, KIND_DIMMER)]

    def _level(self, bridge):
        level = entity_level(self.hass.states.get(bridge["entity_id"]))
        if bridge["kind"] == KIND_RELAY and level:
            return 100
        return level

    # ---- bus -> Home Assistant -------------------------------------------

    @callback
    def _telegram_received(self, telegram):
        target = tuple(telegram.target_address)
        source = tuple(telegram.source_address)
        if target not in self._addresses or source == target:
            return
        payload = telegram.payload or []
        code = telegram.operate_code

        if code == OperateCode.UniversalSwitchControl and len(payload) >= 2:
            index, bridge = self._find(target, (KIND_UNIVERSAL_SWITCH,), payload[0])
            if bridge is None:
                return
            level = 100 if payload[1] else 0
            self._command(index, bridge, level)
            self._reply(target, source, OperateCode.UniversalSwitchControlResponse,
                        [payload[0], 1 if level else 0])

        elif code == OperateCode.ReadStatusOfUniversalSwitch and len(payload) >= 1:
            _, bridge = self._find(target, (KIND_UNIVERSAL_SWITCH,), payload[0])
            if bridge is None:
                return
            self._reply(target, source, OperateCode.ReadStatusOfUniversalSwitchResponse,
                        [payload[0], 1 if self._level(bridge) else 0])

        elif code == OperateCode.SingleChannelControl and len(payload) >= 2:
            index, bridge = self._find(target, (KIND_RELAY, KIND_DIMMER), payload[0])
            if bridge is None:
                return
            level = min(100, payload[1])
            if bridge["kind"] == KIND_RELAY and level:
                level = 100
            self._command(index, bridge, level)
            self._reply(target, source, OperateCode.SingleChannelControlResponse,
                        [payload[0], SUCCESS, level])

        elif code == OperateCode.ReadStatusOfChannels:
            channels = self._channel_bridges(target)
            if not channels:
                return
            self._reply(target, source, OperateCode.ReadStatusOfChannelsResponse,
                        self._channel_status(channels))

    def _channel_status(self, channels):
        count = max(b["number"] for b in channels)
        levels = [0] * count
        for bridge in channels:
            levels[bridge["number"] - 1] = self._level(bridge)
        return [count] + levels

    def _command(self, index, bridge, level):
        self._last_command[index] = (level, time.monotonic())
        call = service_for_level(bridge["entity_id"], level, bridge["kind"])
        if call is None:
            return
        domain, service, data = call
        _LOGGER.debug("HDL bridge %s.%s -> %s.%s %s", bridge["subnet_id"],
                      bridge["device_id"], domain, service, data)
        self.hass.async_create_task(
            self.hass.services.async_call(domain, service, data, blocking=False))

    def _reply(self, virtual_address, target, operate_code, payload):
        telegram = Telegram()
        telegram.source_address = virtual_address
        telegram.target_address = target
        telegram.operate_code = operate_code
        telegram.payload = payload
        self.hass.async_create_task(self.hdl.send_telegram(telegram))

    # ---- Home Assistant -> bus (keeps panel LEDs in sync) -----------------

    @callback
    def _entity_changed(self, event):
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        for index, bridge in enumerate(self._bridges):
            if bridge["entity_id"] != entity_id:
                continue
            level = entity_level(new_state)
            last = self._last_command.get(index)
            if last is not None:
                last_level, at = last
                if time.monotonic() - at < ECHO_WINDOW and bool(last_level) == bool(level):
                    continue
            self._announce(bridge, level)

    def _announce(self, bridge, level):
        address = (bridge["subnet_id"], bridge["device_id"])
        if bridge["kind"] == KIND_UNIVERSAL_SWITCH:
            self._reply(address, BROADCAST_ADDRESS,
                        OperateCode.UniversalSwitchControlResponse,
                        [bridge["number"], 1 if level else 0])
        else:
            if bridge["kind"] == KIND_RELAY and level:
                level = 100
            self._reply(address, BROADCAST_ADDRESS,
                        OperateCode.SingleChannelControlResponse,
                        [bridge["number"], SUCCESS, level])
