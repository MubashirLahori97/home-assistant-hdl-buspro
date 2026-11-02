"""HDL bridge: panel buttons controlling non-HDL entities."""
from homeassistant.core import ServiceCall

from custom_components.buspro.bridge import entity_level, service_for_level
from custom_components.buspro.pybuspro.helpers.enums import OperateCode

from .conftest import build_frame, setup_entry

PANEL = (1, 25)
VIRTUAL = (1, 200)


def _bridge(entity_id, kind, number, name="Bridge"):
    return {"name": name, "entity_id": entity_id, "kind": kind,
            "subnet_id": VIRTUAL[0], "device_id": VIRTUAL[1], "number": number}


def _mock_service(hass, domain, service):
    calls = []

    async def handler(call: ServiceCall):
        calls.append(call)

    hass.services.async_register(domain, service, handler)
    return calls


def _replies(fake_bus, code):
    return [t for t in fake_bus.telegrams() if t.operate_code == code]


async def test_universal_switch_drives_entity_and_replies(hass, fake_bus):
    hass.states.async_set("light.tuya_lamp", "off")
    await setup_entry(hass, bridges=[_bridge("light.tuya_lamp", "universal_switch", 7)])
    # Mock after setup: the light platform registers the real services.
    turn_on = _mock_service(hass, "light", "turn_on")
    turn_off = _mock_service(hass, "light", "turn_off")

    fake_bus.sent.clear()
    fake_bus.inject(build_frame(PANEL, VIRTUAL, OperateCode.UniversalSwitchControl, [7, 255]))
    await hass.async_block_till_done()
    assert turn_on and turn_on[0].data["entity_id"] == "light.tuya_lamp"

    reply = _replies(fake_bus, OperateCode.UniversalSwitchControlResponse)[0]
    assert reply.source_address == VIRTUAL
    assert reply.target_address == PANEL
    assert reply.payload == [7, 1]

    fake_bus.inject(build_frame(PANEL, VIRTUAL, OperateCode.UniversalSwitchControl, [7, 0]))
    await hass.async_block_till_done()
    assert turn_off

    # Other switch numbers and addresses are not ours.
    count = len(turn_on) + len(turn_off)
    fake_bus.inject(build_frame(PANEL, VIRTUAL, OperateCode.UniversalSwitchControl, [8, 255]))
    fake_bus.inject(build_frame(PANEL, (1, 201), OperateCode.UniversalSwitchControl, [7, 255]))
    await hass.async_block_till_done()
    assert len(turn_on) + len(turn_off) == count


async def test_status_read_and_external_change_announced(hass, fake_bus):
    hass.states.async_set("switch.tuya_plug", "on")
    await setup_entry(hass, bridges=[_bridge("switch.tuya_plug", "universal_switch", 3)])

    fake_bus.sent.clear()
    fake_bus.inject(build_frame(PANEL, VIRTUAL, OperateCode.ReadStatusOfUniversalSwitch, [3]))
    await hass.async_block_till_done()
    reply = _replies(fake_bus, OperateCode.ReadStatusOfUniversalSwitchResponse)[0]
    assert reply.payload == [3, 1]

    # Someone switches the plug off in the Tuya app: panels are told.
    fake_bus.sent.clear()
    hass.states.async_set("switch.tuya_plug", "off")
    await hass.async_block_till_done()
    announce = _replies(fake_bus, OperateCode.UniversalSwitchControlResponse)[0]
    assert announce.source_address == VIRTUAL
    assert announce.target_address == (255, 255)
    assert announce.payload == [3, 0]


async def test_dimmer_channel_sets_brightness(hass, fake_bus):
    hass.states.async_set("light.tuya_bulb", "on", {"brightness": 128})
    await setup_entry(hass, bridges=[
        _bridge("light.tuya_bulb", "dimmer", 2),
        _bridge("light.tuya_bulb", "relay", 4),
    ])
    turn_on = _mock_service(hass, "light", "turn_on")

    fake_bus.sent.clear()
    fake_bus.inject(build_frame(PANEL, VIRTUAL, OperateCode.SingleChannelControl, [2, 40, 0, 0]))
    await hass.async_block_till_done()
    assert turn_on[-1].data["brightness_pct"] == 40
    reply = _replies(fake_bus, OperateCode.SingleChannelControlResponse)[0]
    assert reply.payload == [2, 0xF8, 40]

    fake_bus.sent.clear()
    fake_bus.inject(build_frame(PANEL, VIRTUAL, OperateCode.ReadStatusOfChannels, []))
    await hass.async_block_till_done()
    status = _replies(fake_bus, OperateCode.ReadStatusOfChannelsResponse)[0]
    assert status.payload == [4, 0, 50, 0, 100]


async def test_command_echo_not_reannounced(hass, fake_bus):
    _mock_service(hass, "switch", "turn_on")
    hass.states.async_set("switch.tuya_plug", "off")
    await setup_entry(hass, bridges=[_bridge("switch.tuya_plug", "universal_switch", 1)])

    fake_bus.inject(build_frame(PANEL, VIRTUAL, OperateCode.UniversalSwitchControl, [1, 255]))
    await hass.async_block_till_done()
    fake_bus.sent.clear()
    # The Tuya device reports back on: this is the echo of the panel press.
    hass.states.async_set("switch.tuya_plug", "on")
    await hass.async_block_till_done()
    assert _replies(fake_bus, OperateCode.UniversalSwitchControlResponse) == []


def test_level_and_service_mapping(hass):
    from homeassistant.core import State
    assert entity_level(State("light.a", "on", {"brightness": 255})) == 100
    assert entity_level(State("light.a", "off")) == 0
    assert entity_level(State("cover.a", "open", {"current_position": 30})) == 30
    assert entity_level(State("fan.a", "on", {"percentage": 66})) == 66
    assert entity_level(State("switch.a", "on")) == 100
    assert entity_level(None) == 0

    assert service_for_level("cover.blind", 30, "dimmer") == \
        ("cover", "set_cover_position", {"entity_id": "cover.blind", "position": 30})
    assert service_for_level("cover.blind", 100, "relay")[1] == "open_cover"
    assert service_for_level("scene.movie", 0, "universal_switch") is None
    assert service_for_level("script.x", 100, "universal_switch")[1] == "turn_on"
    assert service_for_level("lock.door", 0, "relay")[0] == "homeassistant"


async def test_bridge_stops_on_unload(hass, fake_bus):
    hass.states.async_set("light.tuya_lamp", "off")
    entry = await setup_entry(hass, bridges=[_bridge("light.tuya_lamp", "universal_switch", 7)])
    turn_on = _mock_service(hass, "light", "turn_on")
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not fake_bus.clients
    fake_bus.inject(build_frame(PANEL, VIRTUAL, OperateCode.UniversalSwitchControl, [7, 255]))
    await hass.async_block_till_done()
    assert not turn_on
