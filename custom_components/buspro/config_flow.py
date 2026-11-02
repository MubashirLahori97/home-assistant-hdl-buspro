"""Config flow and Options flow for HDL Buspro integration."""
import logging
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_PORT,
    CONF_DEVICES,
    CONF_AREAS,
    CONF_FLOORS,
    CONF_SCENES,
    CONF_GATEWAY_INFO,
    CONF_BRIDGES,
    CONF_GATEWAY_IP_FILTER,
    CONF_ONLINE_CHECK_INTERVAL,
    CONF_BUS_MONITOR,
    CONF_EXPERIMENTAL,
    DEFAULT_PORT,
)
from . import async_setup_floors_and_areas
from .hdl_parser import parse_any, get_device_summary, HDLParseError

_LOGGER = logging.getLogger(__name__)

CONF_FILE_PATH = "file_path"
CONF_FILE_CONTENT = "file_content"

CONF_DEVICE_NAME = "name"
CONF_DEVICE_TYPE = "device_type"
CONF_SUBNET_ID = "subnet_id"
CONF_DEVICE_ID = "device_id"
CONF_CHANNEL = "channel"
CONF_AREA_NAME = "area_name"

DEVICE_TYPE_MAP = {
    "light_switch": ("light", "light.switch", ["on_off"]),
    "light_dimming": ("light", "light.dimming", ["on_off", "brightness"]),
    "cover": ("cover", "curtain.trietex", ["open", "close", "stop", "position"]),
    "climate": ("climate", "hvac.ac", ["temperature", "mode", "fan"]),
    "climate_hvac": ("climate", "hvac.module", ["temperature", "mode", "fan", "swing"]),
    "climate_floor_heating": ("climate", "hvac.floor_heating", ["temperature", "preset"]),
    "switch": ("switch", "other.common", ["on_off"]),
    "fan_relay": ("fan", "fan.relay", ["on_off"]),
    "fan_dimmer": ("fan", "fan.dimmer", ["on_off", "speed"]),
    "panel_events": ("event", "panel.buttons", []),
    "sensor_temp": ("sensor", "sensor.temperature", ["temperature"]),
    "sensor_humidity": ("sensor", "sensor.humidity", ["humidity"]),
    "panel_temp": ("sensor", "sensor.temperature", ["temperature"]),
    "panel_humidity": ("sensor", "sensor.humidity", ["humidity"]),
    "sensor_lux": ("sensor", "sensor.illuminance", ["illuminance"]),
    "binary_motion": ("binary_sensor", "sensor.motion", ["motion"]),
    "binary_dry_contact": ("binary_sensor", "sensor.dry_contact", ["opening"]),
    "binary_universal_switch": ("binary_sensor", "sensor.universal_switch", ["switch"]),
}

# pybuspro device kind per manual device type. "panel" covers the wall
# panels with built-in sensors: the DLP family, Enviro, Granite Display and
# the Tile climate panels. "sensors_in_one" covers the HDL sensors-in-one
# modules, whose status reply also carries humidity.
DEVICE_KIND_MAP = {
    "panel_temp": "panel",
    "panel_humidity": "panel",
    "sensor_humidity": "sensors_in_one",
}

DEVICE_TYPE_CHOICES = {
    "light_switch": "Light (Switch)",
    "light_dimming": "Light (Dimmable)",
    "cover": "Cover (Curtain/Blind)",
    "climate": "Climate (AC, 0xE0EA commands)",
    "climate_hvac": "Climate (HVAC module, with swing) — channel = AC number",
    "climate_floor_heating": "Climate (Floor heating, DLP / heating module)",
    "switch": "Switch (Relay)",
    "fan_relay": "Fan (Relay channel, on/off)",
    "fan_dimmer": "Fan (Dimmer / 0-10V channel, speed %)",
    "panel_events": "Panel button events (DLP / Granite / Tile / keypads)",
    "sensor_temp": "Sensor (Temperature °C)",
    "sensor_humidity": "Sensor (Humidity %)",
    "panel_temp": "Panel Sensor (Temperature °C) — DLP / Enviro / Granite / Tile",
    "panel_humidity": "Panel Sensor (Humidity %) — Granite Display / Tile",
    "sensor_lux": "Sensor (Illuminance / Lux)",
    "binary_motion": "Binary Sensor (Motion / PIR)",
    "binary_dry_contact": "Binary Sensor (Dry Contact)",
    "binary_universal_switch": "Binary Sensor (Universal Switch)",
}

COLOR_MODE_CHOICES = {
    "cct": "Tunable white (warm channel, cool channel)",
    "rgb": "RGB (red, green, blue channels)",
    "rgbw": "RGBW (red, green, blue, white channels)",
}
COLOR_MODE_CHANNELS = {"cct": 2, "rgb": 3, "rgbw": 4}

BRIDGE_KIND_CHOICES = {
    "universal_switch": "Universal switch (on/off)",
    "relay": "Relay channel (on/off)",
    "dimmer": "Dimmer channel (level 0-100 → brightness / position / speed)",
}
BRIDGE_DOMAINS = [
    "light", "switch", "fan", "cover", "scene", "script", "input_boolean",
    "media_player", "climate", "humidifier", "siren", "automation",
]


def _parse_int_list(text):
    """Parse '1, 2,3' into [1, 2, 3]."""
    return [int(part.strip(), 0) for part in str(text).split(",") if part.strip()]


class BusproConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HDL Buspro."""

    VERSION = 2
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    def __init__(self):
        """Initialize the config flow."""
        self._parsed_data: Optional[Dict[str, Any]] = None
        self._discovered_host: str = "192.168.1.250"
        self._discovered_port: int = DEFAULT_PORT
        self._searched = False

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return BusproOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle the initial step: provide file path or choose manual setup."""
        errors = {}

        if user_input is not None:
            file_path = user_input.get(CONF_FILE_PATH, "").strip()
            file_content = user_input.get(CONF_FILE_CONTENT, "").strip()

            target_source = file_content if file_content else file_path

            if not target_source:
                # If left empty, proceed to manual gateway setup
                return await self.async_step_manual_gateway()

            try:
                self._parsed_data = await self.hass.async_add_executor_job(
                    parse_any, target_source
                )
                gateway = self._parsed_data.get("gateway", {})
                self._discovered_host = gateway.get("ip", "") or "192.168.1.250"
                self._discovered_port = gateway.get("port", DEFAULT_PORT)
                return await self.async_step_confirm()
            except HDLParseError as err:
                _LOGGER.error("Failed to parse HDL project data: %s", err)
                errors["base"] = "parse_error"
            except Exception as err:
                _LOGGER.exception("Unexpected error parsing project data: %s", err)
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Optional(CONF_FILE_PATH, default=""): cv.string,
                vol.Optional(CONF_FILE_CONTENT, default=""): cv.string,
            }),
            errors=errors,
            description_placeholders={},
        )

    async def _async_search_gateways(self):
        """Look for HDL gateways once and pre-fill the first one found."""
        if self._searched:
            return []
        self._searched = True
        from .discovery import search_gateways

        found = await self.hass.async_add_executor_job(search_gateways, DEFAULT_PORT)
        if found:
            self._discovered_host = found[0]
        return found

    async def async_step_manual_gateway(self, user_input=None):
        """Gateway IP and port entry when no file is imported.

        The first time the form opens, the LAN is searched for gateways and
        the first one found is filled in.
        """
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]

            await self.async_set_unique_id(f"buspro_{host}_{port}")
            self._abort_if_unique_id_configured()

            entry_data = {
                CONF_HOST: host,
                CONF_PORT: port,
                CONF_DEVICES: [],
                CONF_AREAS: [],
                CONF_FLOORS: [],
                CONF_SCENES: [],
                CONF_GATEWAY_INFO: {"ip": host, "port": port},
            }

            title = f"HDL Buspro ({host})"
            return self.async_create_entry(title=title, data=entry_data)

        found = await self._async_search_gateways()

        return self.async_show_form(
            step_id="manual_gateway",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=self._discovered_host): cv.string,
                vol.Required(CONF_PORT, default=self._discovered_port): cv.port,
            }),
            errors=errors,
            description_placeholders={
                "found": ", ".join(found) if found else "none",
            },
        )

    async def async_step_confirm(self, user_input=None):
        """Confirm the discovered devices and gateway settings."""
        errors = {}

        if user_input is not None:
            host = user_input.get(CONF_HOST, self._discovered_host)
            port = user_input.get(CONF_PORT, self._discovered_port)

            await self.async_set_unique_id(f"buspro_{host}_{port}")
            self._abort_if_unique_id_configured()

            entry_data = {
                CONF_HOST: host,
                CONF_PORT: port,
                CONF_DEVICES: self._parsed_data.get("devices", []),
                CONF_AREAS: self._parsed_data.get("areas", []),
                CONF_FLOORS: self._parsed_data.get("floors", []),
                CONF_SCENES: self._parsed_data.get("scenes", []),
                CONF_GATEWAY_INFO: self._parsed_data.get("gateway", {}),
            }

            # Create floors/areas once, at import time (never on startup).
            entry_data = await async_setup_floors_and_areas(self.hass, entry_data)

            title = f"HDL Buspro ({host})"
            return self.async_create_entry(title=title, data=entry_data)

        summary = get_device_summary(self._parsed_data) if self._parsed_data else {}
        summary_str = ", ".join(f"{count} {platform}(s)" for platform, count in summary.items())
        area_count = len(self._parsed_data.get("areas", [])) if self._parsed_data else 0

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=self._discovered_host): cv.string,
                vol.Required(CONF_PORT, default=self._discovered_port): cv.port,
            }),
            errors=errors,
            description_placeholders={
                "device_summary": summary_str,
                "area_count": str(area_count),
                "total_devices": str(len(self._parsed_data.get("devices", []))),
            },
        )


class BusproOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for adding devices manually or importing files."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self._config_entry = config_entry
        self._scan_results = []
        self._relay_platform = "light"

    def _finish(self):
        """Close the flow, keeping the current settings."""
        return self.async_create_entry(title="", data=dict(self._config_entry.options))

    async def _save_data(self, data):
        self.hass.config_entries.async_update_entry(self._config_entry, data=data)
        await self.hass.config_entries.async_reload(self._config_entry.entry_id)
        return self._finish()

    async def _save_devices(self, new_devices, area_name=""):
        """Add devices to the entry (replacing same unique_id) and reload."""
        data = dict(self._config_entry.data)
        new_ids = {d["unique_id"] for d in new_devices}
        devices = [d for d in data.get(CONF_DEVICES, []) if d.get("unique_id") not in new_ids]
        devices.extend(new_devices)
        data[CONF_DEVICES] = devices

        if area_name:
            areas = list(data.get(CONF_AREAS, []))
            if not any(a.get("name") == area_name for a in areas):
                areas.append({"id": area_name, "name": area_name, "floor": ""})
            data[CONF_AREAS] = areas

        return await self._save_data(data)

    async def async_step_init(self, user_input=None):
        """Manage the options menu."""
        menu = [
            "add_device", "add_scene", "add_color_light", "add_bridge",
            "remove_bridge", "scan_bus", "import_file", "settings",
        ]
        if self._config_entry.options.get(CONF_EXPERIMENTAL, False):
            menu.append("add_raw_sensor")
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_add_device(self, user_input=None):
        """Add a single device or sensor manually."""
        errors = {}

        if user_input is not None:
            name = user_input[CONF_DEVICE_NAME].strip()
            dev_type_key = user_input[CONF_DEVICE_TYPE]
            subnet_id = user_input[CONF_SUBNET_ID]
            device_id = user_input[CONF_DEVICE_ID]
            channel = user_input[CONF_CHANNEL]
            area_name = user_input.get(CONF_AREA_NAME, "").strip()

            platform, spk, caps = DEVICE_TYPE_MAP.get(
                dev_type_key, ("light", "light.switch", ["on_off"])
            )

            new_device = {
                "name": name,
                "platform": platform,
                "spk": spk,
                "subnet_id": subnet_id,
                "device_id": device_id,
                "channel": channel,
                "area_name": area_name,
                "capabilities": caps,
                "unique_id": f"buspro_{subnet_id}_{device_id}_{channel}_{spk.replace('.', '_')}",
            }

            device_kind = DEVICE_KIND_MAP.get(dev_type_key)
            if device_kind:
                new_device["device"] = device_kind

            return await self._save_devices([new_device], area_name)

        return self.async_show_form(
            step_id="add_device",
            data_schema=vol.Schema({
                vol.Required(CONF_DEVICE_NAME): cv.string,
                vol.Required(CONF_DEVICE_TYPE, default="light_switch"): vol.In(DEVICE_TYPE_CHOICES),
                vol.Required(CONF_SUBNET_ID, default=1): cv.positive_int,
                vol.Required(CONF_DEVICE_ID, default=1): cv.positive_int,
                vol.Required(CONF_CHANNEL, default=1): cv.positive_int,
                vol.Optional(CONF_AREA_NAME, default=""): cv.string,
            }),
            errors=errors,
        )

    async def async_step_add_scene(self, user_input=None):
        """Add a scene or sequence button."""
        if user_input is not None:
            kind = user_input["kind"]
            spk = "sequence.bus" if kind == "sequence" else "scene.bus"
            subnet_id = user_input[CONF_SUBNET_ID]
            device_id = user_input[CONF_DEVICE_ID]
            area_number = user_input["area_number"]
            number = user_input["number"]
            area_name = user_input.get(CONF_AREA_NAME, "").strip()
            device = {
                "name": user_input[CONF_DEVICE_NAME].strip(),
                "platform": "button",
                "spk": spk,
                "subnet_id": subnet_id,
                "device_id": device_id,
                "channel": number,
                "area_number": area_number,
                "area_name": area_name,
                "capabilities": [],
                "unique_id": f"buspro_{subnet_id}_{device_id}_{kind}_{area_number}_{number}",
            }
            return await self._save_devices([device], area_name)

        return self.async_show_form(
            step_id="add_scene",
            data_schema=vol.Schema({
                vol.Required(CONF_DEVICE_NAME): cv.string,
                vol.Required("kind", default="scene"): vol.In(
                    {"scene": "Scene", "sequence": "Sequence"}),
                vol.Required(CONF_SUBNET_ID, default=1): cv.positive_int,
                vol.Required(CONF_DEVICE_ID, default=1): cv.positive_int,
                vol.Required("area_number", default=1): cv.positive_int,
                vol.Required("number", default=1): cv.positive_int,
                vol.Optional(CONF_AREA_NAME, default=""): cv.string,
            }),
        )

    async def async_step_add_color_light(self, user_input=None):
        """Group 2-4 dimmer channels into one tunable-white or RGB(W) light."""
        errors = {}
        if user_input is not None:
            mode = user_input["color_mode"]
            try:
                channels = _parse_int_list(user_input["channels"])
            except ValueError:
                channels = []
            if len(channels) != COLOR_MODE_CHANNELS[mode] or len(set(channels)) != len(channels):
                errors["channels"] = "wrong_channel_count"
            elif user_input["min_kelvin"] >= user_input["max_kelvin"]:
                errors["max_kelvin"] = "bad_kelvin_range"
            else:
                subnet_id = user_input[CONF_SUBNET_ID]
                device_id = user_input[CONF_DEVICE_ID]
                area_name = user_input.get(CONF_AREA_NAME, "").strip()
                device = {
                    "name": user_input[CONF_DEVICE_NAME].strip(),
                    "platform": "light",
                    "spk": "light.color",
                    "color_mode": mode,
                    "subnet_id": subnet_id,
                    "device_id": device_id,
                    "channel": channels[0],
                    "channels": channels,
                    "min_kelvin": user_input["min_kelvin"],
                    "max_kelvin": user_input["max_kelvin"],
                    "area_name": area_name,
                    "capabilities": ["on_off", "brightness", mode],
                    "unique_id": f"buspro_{subnet_id}_{device_id}_"
                                 f"{'_'.join(str(c) for c in channels)}_light_{mode}",
                }
                return await self._save_devices([device], area_name)

        return self.async_show_form(
            step_id="add_color_light",
            data_schema=vol.Schema({
                vol.Required(CONF_DEVICE_NAME): cv.string,
                vol.Required("color_mode", default="cct"): vol.In(COLOR_MODE_CHOICES),
                vol.Required(CONF_SUBNET_ID, default=1): cv.positive_int,
                vol.Required(CONF_DEVICE_ID, default=1): cv.positive_int,
                vol.Required("channels", default="1, 2"): cv.string,
                vol.Required("min_kelvin", default=2700): vol.All(int, vol.Range(min=1000, max=10000)),
                vol.Required("max_kelvin", default=6500): vol.All(int, vol.Range(min=1000, max=10000)),
                vol.Optional(CONF_AREA_NAME, default=""): cv.string,
            }),
            errors=errors,
        )

    def _used_addresses(self):
        """Addresses of configured devices and of modules seen on the bus."""
        used = {(d.get("subnet_id"), d.get("device_id"))
                for d in self._config_entry.data.get(CONF_DEVICES, [])}
        module = self.hass.data.get(DOMAIN, {}).get(self._config_entry.entry_id)
        if module is not None:
            used |= set(module.seen_devices)
        return used

    async def async_step_add_bridge(self, user_input=None):
        """Let an HDL panel button control a non-HDL Home Assistant entity."""
        errors = {}
        bridges = list(self._config_entry.data.get(CONF_BRIDGES, []) or [])
        if user_input is not None:
            subnet_id = user_input[CONF_SUBNET_ID]
            device_id = user_input[CONF_DEVICE_ID]
            kind = user_input["kind"]
            number = user_input["number"]
            group = "switch" if kind == "universal_switch" else "channel"
            bridge_addresses = {(b["subnet_id"], b["device_id"]) for b in bridges}

            if (subnet_id, device_id) in self._used_addresses() - bridge_addresses:
                errors["base"] = "address_in_use"
            elif any(
                (b["subnet_id"], b["device_id"]) == (subnet_id, device_id)
                and ("switch" if b["kind"] == "universal_switch" else "channel") == group
                and b["number"] == number
                for b in bridges
            ):
                errors["base"] = "bridge_exists"
            else:
                bridges.append({
                    "name": user_input[CONF_DEVICE_NAME].strip(),
                    "entity_id": user_input["entity_id"],
                    "kind": kind,
                    "subnet_id": subnet_id,
                    "device_id": device_id,
                    "number": number,
                })
                data = dict(self._config_entry.data)
                data[CONF_BRIDGES] = bridges
                return await self._save_data(data)

        default_subnet = 1
        devices = self._config_entry.data.get(CONF_DEVICES, [])
        if devices:
            default_subnet = devices[0].get("subnet_id", 1) or 1

        return self.async_show_form(
            step_id="add_bridge",
            data_schema=vol.Schema({
                vol.Required(CONF_DEVICE_NAME): cv.string,
                vol.Required("entity_id"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=BRIDGE_DOMAINS)),
                vol.Required("kind", default="universal_switch"): vol.In(BRIDGE_KIND_CHOICES),
                vol.Required(CONF_SUBNET_ID, default=default_subnet): vol.All(int, vol.Range(min=1, max=254)),
                vol.Required(CONF_DEVICE_ID, default=200): vol.All(int, vol.Range(min=1, max=254)),
                vol.Required("number", default=1): vol.All(int, vol.Range(min=1, max=255)),
            }),
            errors=errors,
        )

    async def async_step_remove_bridge(self, user_input=None):
        """Remove bridged entities."""
        bridges = list(self._config_entry.data.get(CONF_BRIDGES, []) or [])
        if not bridges:
            return self.async_abort(reason="no_bridges")
        labels = {
            str(i): f"{b['name']} → {b['entity_id']} "
                    f"({b['subnet_id']}.{b['device_id']} {b['kind']} {b['number']})"
            for i, b in enumerate(bridges)
        }
        if user_input is not None:
            remove = set(user_input.get("bridges", []))
            data = dict(self._config_entry.data)
            data[CONF_BRIDGES] = [b for i, b in enumerate(bridges) if str(i) not in remove]
            return await self._save_data(data)

        return self.async_show_form(
            step_id="remove_bridge",
            data_schema=vol.Schema({
                vol.Optional("bridges", default=[]): cv.multi_select(labels),
            }),
        )

    async def async_step_scan_bus(self, user_input=None):
        """Ask every module on the bus for its name and type."""
        errors = {}
        if user_input is not None:
            module = self.hass.data.get(DOMAIN, {}).get(self._config_entry.entry_id)
            if module is None or not module.connected:
                errors["base"] = "not_connected"
            else:
                from .discovery import scan_bus

                self._relay_platform = user_input["relay_platform"]
                configured = {(d.get("subnet_id"), d.get("device_id"))
                              for d in self._config_entry.data.get(CONF_DEVICES, [])}
                results = await scan_bus(module.hdl)
                self._scan_results = [
                    m for m in results
                    if (m["subnet_id"], m["device_id"]) not in configured
                    and m["role"] not in ("unsupported",)
                ]
                if not self._scan_results:
                    errors["base"] = "nothing_found"
                else:
                    return await self.async_step_scan_select()

        return self.async_show_form(
            step_id="scan_bus",
            data_schema=vol.Schema({
                vol.Required("relay_platform", default="light"): vol.In(
                    {"light": "Lights (on/off)", "switch": "Switches"}),
            }),
            errors=errors,
        )

    async def async_step_scan_select(self, user_input=None):
        """Pick which found modules to add."""
        labels = {
            f"{m['subnet_id']}.{m['device_id']}":
                f"{m['subnet_id']}.{m['device_id']} — {m['model']}"
                + (f" — “{m['remark']}”" if m["remark"] else "")
                + (f" — {len(m['channels'])} channels" if m["channels"] else "")
                + (" (unknown type: will add nothing)" if m["role"] == "unknown" else "")
            for m in self._scan_results
        }
        if user_input is not None:
            from .discovery import modules_to_devices

            chosen = set(user_input.get("modules", []))
            selected = [m for m in self._scan_results
                        if f"{m['subnet_id']}.{m['device_id']}" in chosen]
            devices = modules_to_devices(selected, self._relay_platform)
            if not devices:
                return self._finish()
            return await self._save_devices(devices)

        return self.async_show_form(
            step_id="scan_select",
            data_schema=vol.Schema({
                vol.Optional("modules", default=[]): cv.multi_select(labels),
            }),
            description_placeholders={"count": str(len(self._scan_results))},
        )

    async def async_step_settings(self, user_input=None):
        """Connection and advanced settings."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self._config_entry.options
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema({
                vol.Required(CONF_GATEWAY_IP_FILTER,
                             default=options.get(CONF_GATEWAY_IP_FILTER, False)): bool,
                vol.Required(CONF_ONLINE_CHECK_INTERVAL,
                             default=options.get(CONF_ONLINE_CHECK_INTERVAL, 0)): vol.All(
                    int, vol.Any(0, vol.Range(min=30, max=3600))),
                vol.Required(CONF_BUS_MONITOR,
                             default=options.get(CONF_BUS_MONITOR, False)): bool,
                vol.Required(CONF_EXPERIMENTAL,
                             default=options.get(CONF_EXPERIMENTAL, False)): bool,
            }),
        )

    async def async_step_add_raw_sensor(self, user_input=None):
        """Experimental: poll any read command and decode bytes of the reply."""
        from .raw_sensor import RAW_SENSOR_PRESETS

        errors = {}
        if user_input is not None:
            preset = RAW_SENSOR_PRESETS.get(user_input["preset"], {})
            try:
                request_text = user_input.get("request_code", "").strip()
                request_code = int(request_text, 16) if request_text else preset.get("request_code")
                response_text = user_input.get("response_code", "").strip()
                response_code = int(response_text, 16) if response_text else None
                request_payload = _parse_int_list(user_input.get("request_payload", ""))
            except ValueError:
                request_code = None
            if not request_code:
                errors["request_code"] = "bad_code"
            else:
                subnet_id = user_input[CONF_SUBNET_ID]
                device_id = user_input[CONF_DEVICE_ID]
                area_name = user_input.get(CONF_AREA_NAME, "").strip()
                unit = user_input.get("unit", "").strip() or preset.get("unit")
                device = {
                    "name": user_input[CONF_DEVICE_NAME].strip(),
                    "platform": "sensor",
                    "spk": "sensor.raw",
                    "subnet_id": subnet_id,
                    "device_id": device_id,
                    "channel": 0,
                    "area_name": area_name,
                    "capabilities": [],
                    "request_code": request_code,
                    "response_code": response_code,
                    "request_payload": request_payload,
                    "byte_offset": user_input["byte_offset"],
                    "byte_length": user_input["byte_length"],
                    "byteorder": user_input["byteorder"],
                    "signed": user_input["signed"],
                    "scale": user_input["scale"],
                    "unit": unit,
                    "device_class": preset.get("device_class"),
                    "state_class": preset.get("state_class"),
                    "scan_interval": user_input["scan_interval"],
                    "unique_id": f"buspro_{subnet_id}_{device_id}_raw_{request_code:04x}_"
                                 f"{user_input['byte_offset']}",
                }
                return await self._save_devices([device], area_name)

        return self.async_show_form(
            step_id="add_raw_sensor",
            data_schema=vol.Schema({
                vol.Required(CONF_DEVICE_NAME): cv.string,
                vol.Required("preset", default="custom"): vol.In({
                    "custom": "Custom",
                    "voltage": "Power meter: voltage (0xD902)",
                    "current": "Power meter: current (0xD908)",
                    "power": "Power meter: power (0xD90A)",
                    "power_factor": "Power meter: power factor (0xD904)",
                    "energy": "Power meter: energy kWh (0xD91A)",
                }),
                vol.Required(CONF_SUBNET_ID, default=1): cv.positive_int,
                vol.Required(CONF_DEVICE_ID, default=1): cv.positive_int,
                vol.Optional("request_code", default=""): cv.string,
                vol.Optional("request_payload", default=""): cv.string,
                vol.Optional("response_code", default=""): cv.string,
                vol.Required("byte_offset", default=0): vol.All(int, vol.Range(min=0, max=60)),
                vol.Required("byte_length", default=2): vol.All(int, vol.Range(min=1, max=4)),
                vol.Required("byteorder", default="big"): vol.In(
                    {"big": "Big endian", "little": "Little endian"}),
                vol.Required("signed", default=False): bool,
                vol.Required("scale", default=1.0): vol.Coerce(float),
                vol.Optional("unit", default=""): cv.string,
                vol.Required("scan_interval", default=30): vol.All(int, vol.Range(min=5, max=3600)),
                vol.Optional(CONF_AREA_NAME, default=""): cv.string,
            }),
            errors=errors,
        )

    async def async_step_import_file(self, user_input=None):
        """Import or update from Excel (.xlsx), CSV (.csv), or JSON file."""
        errors = {}

        if user_input is not None:
            file_path = user_input.get(CONF_FILE_PATH, "").strip()
            file_content = user_input.get(CONF_FILE_CONTENT, "").strip()
            target_source = file_content if file_content else file_path

            if not target_source:
                errors["base"] = "missing_input"
            else:
                try:
                    parsed = await self.hass.async_add_executor_job(
                        parse_any, target_source
                    )
                    data = dict(self._config_entry.data)
                    data[CONF_DEVICES] = parsed.get("devices", [])
                    data[CONF_AREAS] = parsed.get("areas", [])
                    data[CONF_FLOORS] = parsed.get("floors", [])
                    data[CONF_SCENES] = parsed.get("scenes", [])

                    # Create any new floors/areas at import time (never on startup).
                    data = await async_setup_floors_and_areas(self.hass, data)

                    return await self._save_data(data)
                except HDLParseError as err:
                    _LOGGER.error("Failed to parse file: %s", err)
                    errors["base"] = "parse_error"
                except Exception as err:
                    _LOGGER.exception("Unexpected error: %s", err)
                    errors["base"] = "unknown"

        return self.async_show_form(
            step_id="import_file",
            data_schema=vol.Schema({
                vol.Optional(CONF_FILE_PATH, default=""): cv.string,
                vol.Optional(CONF_FILE_CONTENT, default=""): cv.string,
            }),
            errors=errors,
        )
