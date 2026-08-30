"""Config flow and Options flow for HDL Buspro integration."""
import logging
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_PORT,
    CONF_DEVICES,
    CONF_AREAS,
    CONF_FLOORS,
    CONF_SCENES,
    CONF_GATEWAY_INFO,
    DEFAULT_PORT,
)
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
    "switch": ("switch", "other.common", ["on_off"]),
    "sensor_temp": ("sensor", "sensor.temperature", ["temperature"]),
    "sensor_lux": ("sensor", "sensor.illuminance", ["illuminance"]),
    "binary_motion": ("binary_sensor", "sensor.motion", ["motion"]),
    "binary_dry_contact": ("binary_sensor", "sensor.dry_contact", ["opening"]),
    "binary_universal_switch": ("binary_sensor", "sensor.universal_switch", ["switch"]),
}

DEVICE_TYPE_CHOICES = {
    "light_switch": "Light (Switch)",
    "light_dimming": "Light (Dimmable)",
    "cover": "Cover (Curtain/Blind)",
    "climate": "Climate (AC)",
    "switch": "Switch (Relay)",
    "sensor_temp": "Sensor (Temperature °C)",
    "sensor_lux": "Sensor (Illuminance / Lux)",
    "binary_motion": "Binary Sensor (Motion / PIR)",
    "binary_dry_contact": "Binary Sensor (Dry Contact)",
    "binary_universal_switch": "Binary Sensor (Universal Switch)",
}


class BusproConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HDL Buspro."""

    VERSION = 2
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    def __init__(self):
        """Initialize the config flow."""
        self._parsed_data: Optional[Dict[str, Any]] = None
        self._discovered_host: str = "192.168.1.250"
        self._discovered_port: int = DEFAULT_PORT

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
                self._parsed_data = parse_any(target_source)
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

    async def async_step_manual_gateway(self, user_input=None):
        """Manual gateway IP and port entry when no file is imported."""
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

        return self.async_show_form(
            step_id="manual_gateway",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=self._discovered_host): cv.string,
                vol.Required(CONF_PORT, default=self._discovered_port): cv.port,
            }),
            errors=errors,
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

    async def async_step_init(self, user_input=None):
        """Manage the options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_device", "import_file"],
        )

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

            # Update existing devices
            data = dict(self._config_entry.data)
            devices = list(data.get(CONF_DEVICES, []))
            
            # Remove any existing device with same unique_id to avoid duplicate
            devices = [d for d in devices if d.get("unique_id") != new_device["unique_id"]]
            devices.append(new_device)
            data[CONF_DEVICES] = devices

            # Update areas list if new area
            if area_name:
                areas = list(data.get(CONF_AREAS, []))
                if not any(a.get("name") == area_name for a in areas):
                    areas.append({"id": area_name, "name": area_name, "floor": ""})
                data[CONF_AREAS] = areas

            self.hass.config_entries.async_update_entry(self._config_entry, data=data)
            await self.hass.config_entries.async_reload(self._config_entry.entry_id)

            return self.async_create_entry(title="", data={})

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
                    parsed = parse_any(target_source)
                    data = dict(self._config_entry.data)
                    data[CONF_DEVICES] = parsed.get("devices", [])
                    data[CONF_AREAS] = parsed.get("areas", [])
                    data[CONF_FLOORS] = parsed.get("floors", [])
                    data[CONF_SCENES] = parsed.get("scenes", [])

                    self.hass.config_entries.async_update_entry(self._config_entry, data=data)
                    await self.hass.config_entries.async_reload(self._config_entry.entry_id)

                    return self.async_create_entry(title="", data={})
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
