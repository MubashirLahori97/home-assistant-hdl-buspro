"""Config and options flow steps."""
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.buspro.const import DOMAIN
from custom_components.buspro.discovery import decode_remark, modules_to_devices
from custom_components.buspro.pybuspro.helpers.enums import DeviceType, OperateCode

from .conftest import build_frame, setup_entry


async def test_manual_gateway_prefills_found_gateway(hass, fake_bus):
    with patch("custom_components.buspro.discovery.search_gateways",
               return_value=["192.168.1.77"]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"file_path": "", "file_content": ""})
    assert result["step_id"] == "manual_gateway"
    assert result["description_placeholders"]["found"] == "192.168.1.77"
    schema = result["data_schema"].schema
    host_key = next(k for k in schema if k == "host")
    assert host_key.default() == "192.168.1.77"


async def _options(hass, entry, step, data):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": step})
    if data is None:
        return result
    return await hass.config_entries.options.async_configure(result["flow_id"], data)


async def test_settings_are_saved_and_kept(hass, fake_bus):
    entry = await setup_entry(hass)
    result = await _options(hass, entry, "settings", {
        "gateway_ip_filter": True, "online_check_interval": 60,
        "bus_monitor": True, "experimental": True,
    })
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["experimental"] is True

    # A later device add must not wipe the settings.
    await _options(hass, entry, "add_scene", {
        "name": "Movie", "kind": "scene", "subnet_id": 1, "device_id": 80,
        "area_number": 2, "number": 5, "area_name": "",
    })
    await hass.async_block_till_done()
    assert entry.options["bus_monitor"] is True
    assert any(d["spk"] == "scene.bus" for d in entry.data["devices"])

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert "add_raw_sensor" in result["menu_options"]


async def test_bus_monitor_fires_events(hass, fake_bus):
    await setup_entry(hass, options={"bus_monitor": True})
    events = []
    hass.bus.async_listen("buspro_telegram", events.append)
    fake_bus.inject(build_frame((1, 9), (1, 10), OperateCode.SceneControl, [1, 2]))
    await hass.async_block_till_done()
    assert events[0].data["operate_code"] == "0002"
    assert events[0].data["payload"] == [1, 2]


async def test_color_light_validation(hass, fake_bus):
    entry = await setup_entry(hass)
    result = await _options(hass, entry, "add_color_light", {
        "name": "Strip", "color_mode": "rgb", "subnet_id": 1, "device_id": 60,
        "channels": "1, 2", "min_kelvin": 2700, "max_kelvin": 6500, "area_name": "",
    })
    assert result["errors"] == {"channels": "wrong_channel_count"}
    result = await hass.config_entries.options.async_configure(result["flow_id"], {
        "name": "Strip", "color_mode": "rgb", "subnet_id": 1, "device_id": 60,
        "channels": "1, 2, 3", "min_kelvin": 2700, "max_kelvin": 6500, "area_name": "",
    })
    assert result["type"] == FlowResultType.CREATE_ENTRY
    device = next(d for d in entry.data["devices"] if d["spk"] == "light.color")
    assert device["channels"] == [1, 2, 3]


async def test_bridge_address_collision(hass, fake_bus):
    hass.states.async_set("light.tuya_lamp", "off")
    entry = await setup_entry(hass, devices=[{
        "name": "Dimmer", "platform": "light", "spk": "light.dimming", "subnet_id": 1,
        "device_id": 74, "channel": 1, "area_name": "", "capabilities": [],
        "unique_id": "dimmer_1_74_1",
    }])
    result = await _options(hass, entry, "add_bridge", {
        "name": "Lamp", "entity_id": "light.tuya_lamp", "kind": "universal_switch",
        "subnet_id": 1, "device_id": 74, "number": 1,
    })
    assert result["errors"] == {"base": "address_in_use"}
    result = await hass.config_entries.options.async_configure(result["flow_id"], {
        "name": "Lamp", "entity_id": "light.tuya_lamp", "kind": "universal_switch",
        "subnet_id": 1, "device_id": 200, "number": 1,
    })
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.data["bridges"][0]["entity_id"] == "light.tuya_lamp"

    result = await _options(hass, entry, "remove_bridge", {"bridges": ["0"]})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.data["bridges"] == []


async def test_scan_bus_adds_modules(hass, fake_bus):
    entry = await setup_entry(hass)

    def responder(sent):
        if sent.operate_code == OperateCode.ReadStatusOfChannels and sent.target_address == (1, 12):
            return build_frame((1, 12), (200, 200), OperateCode.ReadStatusOfChannelsResponse,
                               [2, 0, 0])
        return None

    fake_bus.responder = responder

    async def fake_collect(self, telegram, response_code, duration=3.0):
        from .conftest import decode_frame
        return [
            decode_frame(build_frame((1, 12), (200, 200), OperateCode.ReadDeviceRemarkResponse,
                                     list(b"Kitchen dimmer\x00"),
                                     source_type=DeviceType.HDL_MDT0601)),
            decode_frame(build_frame((1, 25), (200, 200), OperateCode.ReadDeviceRemarkResponse,
                                     list(b"Hall\x00"), source_type=DeviceType.HDL_MPTL4C)),
        ]

    with patch("custom_components.buspro.pybuspro.buspro.Buspro.collect", fake_collect):
        result = await _options(hass, entry, "scan_bus", {"relay_platform": "light"})
    assert result["step_id"] == "scan_select"
    assert result["description_placeholders"]["count"] == "2"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"modules": ["1.12", "1.25"]})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    spks = sorted(d["spk"] for d in entry.data["devices"])
    assert spks == ["light.dimming", "light.dimming", "panel.buttons", "sensor.temperature"]


def test_decode_remark():
    assert decode_remark(list(b"Kitchen\x00\x00garbage")) == "Kitchen"
    assert decode_remark(list("客厅".encode("gbk") + b"\x00")) == "客厅"


def test_modules_to_devices_relay_as_switch():
    module = {"subnet_id": 1, "device_id": 30, "type_code": "01ac", "model": "relay",
              "role": "relay", "remark": "Relays",
              "channels": [{"number": 1, "name": "Pump"}]}
    devices = modules_to_devices([module], relay_platform="switch")
    assert devices[0]["platform"] == "switch" and devices[0]["name"] == "Pump"
