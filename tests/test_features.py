"""Panel events, scene buttons, fans, colour lights, HVAC, raw sensors."""
import pytest

from homeassistant.const import STATE_ON, STATE_OFF

from custom_components.buspro.light import (
    cct_to_levels, levels_to_cct, color_to_levels, levels_to_color,
)
from custom_components.buspro.raw_sensor import decode_value
from custom_components.buspro.pybuspro.helpers.enums import OperateCode

from .conftest import build_frame, setup_entry


def _device(platform, spk, subnet, device, channel=1, **extra):
    return {
        "name": extra.pop("name", f"{spk} {subnet}.{device}.{channel}"),
        "platform": platform,
        "spk": spk,
        "subnet_id": subnet,
        "device_id": device,
        "channel": channel,
        "area_name": "",
        "capabilities": [],
        "unique_id": f"test_{spk}_{subnet}_{device}_{channel}",
        **extra,
    }


async def test_panel_button_events(hass, fake_bus):
    await setup_entry(hass, [_device("event", "panel.buttons", 1, 25, name="Hall panel")])
    state = hass.states.get("event.hall_panel")
    assert state is not None

    fired = []
    hass.bus.async_listen("buspro_panel_button", fired.append)

    fake_bus.inject(build_frame((1, 25), (1, 200), OperateCode.UniversalSwitchControl, [7, 255]))
    await hass.async_block_till_done()
    state = hass.states.get("event.hall_panel")
    assert state.attributes["event_type"] == "universal_switch_on"
    assert state.attributes["switch"] == 7
    assert fired[-1].data["panel_address"] == [1, 25]

    fake_bus.inject(build_frame((1, 25), (1, 74), OperateCode.SingleChannelControl, [3, 0, 0, 0]))
    await hass.async_block_till_done()
    state = hass.states.get("event.hall_panel")
    assert state.attributes["event_type"] == "channel_off"
    assert state.attributes["channel"] == 3

    fake_bus.inject(build_frame((1, 25), (1, 80), OperateCode.SceneControl, [2, 5]))
    await hass.async_block_till_done()
    assert hass.states.get("event.hall_panel").attributes["event_type"] == "scene"

    # Messages from other addresses are ignored.
    count = len(fired)
    fake_bus.inject(build_frame((1, 26), (1, 80), OperateCode.SceneControl, [2, 5]))
    await hass.async_block_till_done()
    assert len(fired) == count


async def test_scene_and_sequence_buttons(hass, fake_bus):
    await setup_entry(hass, [
        _device("button", "scene.bus", 1, 80, channel=5, area_number=2, name="Movie"),
        _device("button", "sequence.bus", 1, 81, channel=3, area_number=1, name="Party"),
    ])
    fake_bus.sent.clear()
    await hass.services.async_call("button", "press", {"entity_id": "button.movie"}, blocking=True)
    await hass.services.async_call("button", "press", {"entity_id": "button.party"}, blocking=True)
    sent = fake_bus.telegrams()
    assert (sent[0].operate_code, sent[0].target_address, sent[0].payload) == \
        (OperateCode.SceneControl, (1, 80), [2, 5])
    assert (sent[1].operate_code, sent[1].target_address, sent[1].payload) == \
        (OperateCode.SequenceControl, (1, 81), [1, 3])


async def test_dimmer_fan(hass, fake_bus):
    await setup_entry(hass, [_device("fan", "fan.dimmer", 1, 40, channel=2, name="Ceiling fan")])
    fake_bus.sent.clear()
    await hass.services.async_call("fan", "set_percentage",
                                   {"entity_id": "fan.ceiling_fan", "percentage": 60}, blocking=True)
    sent = fake_bus.telegrams()[-1]
    assert sent.operate_code == OperateCode.SingleChannelControl
    assert sent.payload[:2] == [2, 60]
    assert hass.states.get("fan.ceiling_fan").attributes["percentage"] == 60


def test_cct_math():
    assert cct_to_levels(100, 2700, 2700, 6500) == (100, 0)
    assert cct_to_levels(100, 6500, 2700, 6500) == (0, 100)
    assert cct_to_levels(50, 4600, 2700, 6500) == (50, 50)
    assert levels_to_cct(50, 50, 2700, 6500) == (50, 4600)
    assert levels_to_cct(0, 0, 2700, 6500) == (0, None)


def test_color_math():
    assert color_to_levels(100, (255, 0, 128)) == [100, 0, 50]
    assert levels_to_color([100, 0, 50]) == (100, (255, 0, 128))
    assert levels_to_color([0, 0, 0]) == (0, None)


async def test_cct_light(hass, fake_bus):
    await setup_entry(hass, [_device(
        "light", "light.color", 1, 60, channel=1, name="Kitchen strip",
        color_mode="cct", channels=[1, 2], min_kelvin=2700, max_kelvin=6500)])
    state = hass.states.get("light.kitchen_strip")
    assert state.attributes["supported_color_modes"] == ["color_temp"]

    fake_bus.sent.clear()
    await hass.services.async_call("light", "turn_on", {
        "entity_id": "light.kitchen_strip", "brightness": 255, "color_temp_kelvin": 6500,
    }, blocking=True)
    sent = [t for t in fake_bus.telegrams() if t.operate_code == OperateCode.SingleChannelControl]
    assert [(t.payload[0], t.payload[1]) for t in sent] == [(1, 0), (2, 100)]
    state = hass.states.get("light.kitchen_strip")
    assert state.state == STATE_ON
    assert state.attributes["color_temp_kelvin"] == 6500

    # Channel status from the bus updates the light.
    fake_bus.inject(build_frame((1, 60), (1, 1), OperateCode.ReadStatusOfChannelsResponse,
                                [2, 50, 50]))
    await hass.async_block_till_done()
    state = hass.states.get("light.kitchen_strip")
    assert state.attributes["color_temp_kelvin"] == 4600
    assert state.attributes["brightness"] == 128


async def test_rgb_light(hass, fake_bus):
    await setup_entry(hass, [_device(
        "light", "light.color", 1, 61, channel=1, name="Cove",
        color_mode="rgb", channels=[4, 5, 6])])
    fake_bus.sent.clear()
    await hass.services.async_call("light", "turn_on", {
        "entity_id": "light.cove", "rgb_color": [255, 0, 128], "brightness": 255,
    }, blocking=True)
    sent = [t for t in fake_bus.telegrams() if t.operate_code == OperateCode.SingleChannelControl]
    assert [(t.payload[0], t.payload[1]) for t in sent] == [(4, 100), (5, 0), (6, 50)]

    await hass.services.async_call("light", "turn_off", {"entity_id": "light.cove"}, blocking=True)
    assert hass.states.get("light.cove").state == STATE_OFF


async def test_hvac_module(hass, fake_bus):
    await setup_entry(hass, [_device("climate", "hvac.module", 1, 90, channel=1, name="Office AC")])
    status = [1, 0, 26, 22, 28, 24, 23, 0x01, 1, 0, 1, 22, 0x10]
    fake_bus.inject(build_frame((1, 90), (1, 1), OperateCode.ReadHvacStatusResponse, status))
    await hass.async_block_till_done()
    state = hass.states.get("climate.office_ac")
    assert state.state == "cool"
    assert state.attributes["current_temperature"] == 26
    assert state.attributes["temperature"] == 22
    assert state.attributes["fan_mode"] == "high"
    assert state.attributes["swing_mode"] == "off"

    fake_bus.sent.clear()
    await hass.services.async_call("climate", "set_swing_mode",
                                   {"entity_id": "climate.office_ac", "swing_mode": "on"}, blocking=True)
    await hass.services.async_call("climate", "set_temperature",
                                   {"entity_id": "climate.office_ac", "temperature": 20}, blocking=True)
    sent = [t for t in fake_bus.telegrams() if t.operate_code == OperateCode.ControlHvacStatus]
    last = sent[-1].payload
    assert len(last) == 13
    assert last[12] == 0x11      # swing enabled + active
    assert last[3] == 20 and last[11] == 20   # cooling setpoint and setup temperature
    assert last[7] == (0 << 4) | 1


def test_raw_decode():
    assert decode_value([0, 0x01, 0x2C], 1, 2) == 300
    assert decode_value([0x2C, 0x01], 0, 2, "little") == 300
    assert decode_value([0xFF, 0xFE], 0, 2, signed=True) == -2
    assert decode_value([0x00, 0x64], 0, 2, scale=0.1) == 10.0
    assert decode_value([1], 0, 2) is None


async def test_raw_sensor_needs_experimental(hass, fake_bus):
    raw = _device("sensor", "sensor.raw", 1, 70, channel=0, name="Meter power",
                  request_code=0xD90A, byte_offset=1, byte_length=2, scale=1.0,
                  unit="W", device_class="power", state_class="measurement")
    await setup_entry(hass, [raw])
    assert hass.states.get("sensor.meter_power") is None


@pytest.mark.parametrize("value", [123])
async def test_raw_sensor_reads(hass, fake_bus, value):
    raw = _device("sensor", "sensor.raw", 1, 70, channel=0, name="Meter power",
                  request_code=0xD90A, byte_offset=1, byte_length=2, scale=1.0,
                  unit="W", device_class="power", state_class="measurement")
    entry = await setup_entry(hass, [raw], options={"experimental": True})

    class Reply:
        value = b"\xD9\x0B"

    def responder(sent):
        if sent.operate_code_raw == b"\xD9\x0A":
            return build_frame((1, 70), (200, 200), Reply(), [1, 0, value])
        return None

    fake_bus.responder = responder
    entity = hass.data["entity_components"]["sensor"].get_entity("sensor.meter_power")
    await entity.async_read()
    await hass.async_block_till_done()
    state = hass.states.get("sensor.meter_power")
    assert float(state.state) == value
    assert state.attributes["unit_of_measurement"] == "W"
    await hass.config_entries.async_unload(entry.entry_id)
