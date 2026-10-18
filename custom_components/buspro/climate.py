"""This component provides climate support for Buspro (AC and Floor Heating)."""
import logging
from typing import Optional, List

import homeassistant.helpers.config_validation as cv
try:
    from homeassistant.helpers.device_registry import DeviceInfo
except ImportError:
    from homeassistant.helpers.entity import DeviceInfo
import voluptuous as vol
from homeassistant.components.climate import (
    PLATFORM_SCHEMA,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    HVACAction,
)
from homeassistant.const import (
    CONF_NAME,
    CONF_DEVICES,
    CONF_ADDRESS,
    UnitOfTemperature,
    ATTR_TEMPERATURE,
)
from homeassistant.core import callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_DEVICES as CONF_DEVICES_ENTRY, DOMAIN
# noinspection PyUnresolvedReferences
from .pybuspro.devices.climate import ControlFloorHeatingStatus
# noinspection PyUnresolvedReferences
from .pybuspro.helpers.enums import OnOffStatus

_LOGGER = logging.getLogger(__name__)

PRESET_NONE = "none"
PRESET_AWAY = "away"
PRESET_HOME = "home"
PRESET_SLEEP = "sleep"

HA_PRESET_TO_HDL = {
    PRESET_NONE: 1,     # Normal
    PRESET_HOME: 2,     # Day
    PRESET_SLEEP: 3,    # Night
    PRESET_AWAY: 4,     # Away
}
HDL_TO_HA_PRESET = {
    1: PRESET_NONE,     # Normal
    2: PRESET_HOME,     # Day
    3: PRESET_SLEEP,    # Night
    4: PRESET_AWAY,     # Away
}

CONF_PRESET_MODES = "preset_modes"
CONF_RELAY_ADDRESS = "relay_address"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_DEVICES):
        vol.All(cv.ensure_list, [
            vol.All({
                vol.Required(CONF_ADDRESS): cv.string,
                vol.Required(CONF_NAME): cv.string,
                vol.Optional(CONF_PRESET_MODES, default=[]): vol.All(
                    cv.ensure_list, [vol.In(HA_PRESET_TO_HDL)]
                ),
                vol.Optional(CONF_RELAY_ADDRESS, default=''): cv.string,
            })
        ])
})


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Set up Buspro climate devices from a config entry."""
    # noinspection PyUnresolvedReferences
    from .pybuspro.devices import AC, Climate

    buspro_module = hass.data[DOMAIN][config_entry.entry_id]
    hdl = buspro_module.hdl
    raw_devices = config_entry.data.get(CONF_DEVICES_ENTRY, [])
    entities = []

    for device_info in raw_devices:
        if device_info.get("platform") != "climate":
            continue

        name = device_info.get("name", "Climate")
        subnet_id = device_info.get("subnet_id")
        device_id = device_info.get("device_id")
        channel = device_info.get("channel", 1)
        area_name = device_info.get("area_name", "")
        spk = device_info.get("spk", "")

        device_address = (subnet_id, device_id)

        if "floor_heating" in spk:
            climate = Climate(hdl, device_address, name)
            entities.append(BusproClimate(
                hass, climate, [], None, 
                area_name=area_name, 
                unique_id=device_info.get("unique_id"), 
                buspro_module=buspro_module
            ))
        else:
            ac_device = AC(hdl, device_address, channel, name)
            entities.append(BusproAC(
                hass, ac_device, 
                area_name=area_name, 
                unique_id=device_info.get("unique_id"), 
                buspro_module=buspro_module
            ))

    async_add_entities(entities)


# noinspection PyUnusedLocal
async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up Buspro climate devices from YAML (legacy fallback)."""
    # noinspection PyUnresolvedReferences
    from .pybuspro.devices import Climate
    from .pybuspro.devices import Sensor

    buspro_module = hass.data.get(DOMAIN, {}).get("legacy")
    hdl = buspro_module.hdl if buspro_module else None
    if not hdl:
        return

    devices = []

    for device_config in config[CONF_DEVICES]:
        address = device_config[CONF_ADDRESS]
        name = device_config[CONF_NAME]
        preset_modes = device_config[CONF_PRESET_MODES]

        address2 = address.split('.')
        device_address = (int(address2[0]), int(address2[1]))

        climate = Climate(hdl, device_address, name)

        relay_sensor = None
        relay_address = device_config[CONF_RELAY_ADDRESS]
        if relay_address:
            relay_address2 = relay_address.split('.')
            relay_device_address = (int(relay_address2[0]), int(relay_address2[1]))
            relay_channel_number = int(relay_address2[2])
            relay_sensor = Sensor(hdl, relay_device_address, channel_number=relay_channel_number)

        devices.append(BusproClimate(
            hass, climate, preset_modes, relay_sensor, 
            buspro_module=buspro_module
        ))

    async_add_entities(devices)


class BusproAC(ClimateEntity):
    """Representation of an HDL Buspro AC unit."""

    HDL_MODE_TO_HA = {
        0: HVACMode.COOL,
        1: HVACMode.HEAT,
        2: HVACMode.FAN_ONLY,
        3: HVACMode.AUTO,
        4: HVACMode.DRY,
    }
    HA_MODE_TO_HDL = {v: k for k, v in HDL_MODE_TO_HA.items()}

    HDL_FAN_TO_HA = {
        0: "auto",
        1: "high",
        2: "medium",
        3: "low",
    }
    HA_FAN_TO_HDL = {v: k for k, v in HDL_FAN_TO_HA.items()}

    def __init__(self, hass, device, area_name="", unique_id=None, buspro_module=None):
        self._hass = hass
        self._device = device
        self._area_name = area_name
        self._custom_unique_id = unique_id
        self._buspro_module = buspro_module

        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_hvac_modes = [
            HVACMode.OFF,
            HVACMode.COOL,
            HVACMode.HEAT,
            HVACMode.FAN_ONLY,
            HVACMode.AUTO,
            HVACMode.DRY,
        ]
        self._attr_fan_modes = ["auto", "high", "medium", "low"]
        self._attr_swing_modes = ["off", "on"]
        self._attr_min_temp = 16
        self._attr_max_temp = 32
        self._attr_target_temperature_step = 1

        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.SWING_MODE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )

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
        """Return the display name of this AC unit."""
        return self._device.name

    @property
    def available(self):
        """Return True if entity is available."""
        if self._buspro_module:
            return self._buspro_module.connected
        return True

    @property
    def current_temperature(self):
        """Return the current room temperature."""
        return self._device.temperature

    @property
    def target_temperature(self):
        """Return the target temperature."""
        return self._device.target_temperature

    @property
    def hvac_mode(self):
        """Return current HVAC mode."""
        if not self._device.is_on:
            return HVACMode.OFF
        return self.HDL_MODE_TO_HA.get(self._device.mode, HVACMode.COOL)

    @property
    def fan_mode(self):
        """Return current fan mode."""
        return self.HDL_FAN_TO_HA.get(self._device.fan_speed, "auto")

    @property
    def swing_mode(self):
        """Return current swing mode."""
        return "on" if self._device.swing else "off"

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self._device.set_off()
        else:
            if not self._device.is_on:
                await self._device.set_on()
            hdl_mode = self.HA_MODE_TO_HDL.get(hvac_mode, 0)
            await self._device.set_mode(hdl_mode)
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            await self._device.set_target_temperature(temp)
            self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new fan mode."""
        hdl_fan = self.HA_FAN_TO_HDL.get(fan_mode, 0)
        await self._device.set_fan_speed(hdl_fan)
        self.async_write_ha_state()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set new swing mode."""
        await self._device.set_swing(swing_mode == "on")
        self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        """Turn on AC."""
        await self._device.set_on()
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        """Turn off AC."""
        await self._device.set_off()
        self.async_write_ha_state()

    @property
    def unique_id(self):
        """Return the unique id."""
        if self._custom_unique_id:
            return self._custom_unique_id
        return self._device.device_identifier


class BusproClimate(ClimateEntity):
    """Representation of a Buspro floor heating climate device."""

    def __init__(self, hass, device, preset_modes, relay_sensor=None, area_name="", unique_id=None, buspro_module=None):
        self._hass = hass
        self._device = device
        self._target_temperature = self._device.target_temperature
        self._is_on = self._device.is_on
        self._preset_modes = preset_modes
        self._mode = self._device.mode
        self._area_name = area_name
        self._custom_unique_id = unique_id
        self._buspro_module = buspro_module

        self._relay_sensor = relay_sensor
        self._relay_sensor_is_on = None
        if self._relay_sensor is not None:
            self._relay_sensor_is_on = self._relay_sensor.single_channel_is_on

        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.PRESET_MODE
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TURN_ON
        )

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

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.HEAT)
    
    @callback
    def async_register_callbacks(self):
        """Register callbacks to update hass after device was changed."""
        async def after_update_callback(device):
            """Call after device was updated."""
            self._device = device
            self._target_temperature = device.target_temperature
            self._is_on = device.is_on
            self._mode = device.mode

            if self._hass is not None:
                self.async_write_ha_state()

        async def after_relay_sensor_update_callback(device):
            """Call after device was updated."""
            self._relay_sensor_is_on = device.single_channel_is_on
            self.async_write_ha_state()

        self._device.register_device_updated_cb(after_update_callback)

        if self._relay_sensor is not None:
            self._relay_sensor.register_device_updated_cb(after_relay_sensor_update_callback)

    @property
    def should_poll(self):
        """No polling needed within Buspro."""
        return False

    @property
    def name(self):
        """Return the display name of this climate device."""
        return self._device.name

    @property
    def available(self):
        """Return True if entity is available."""
        if self._buspro_module:
            return self._buspro_module.connected
        return True

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return UnitOfTemperature.CELSIUS

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._device.temperature

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        target_temperature = self._target_temperature
        if target_temperature is None:
            target_temperature = self._device.target_temperature
        return target_temperature

    @property
    def preset_mode(self) -> Optional[str]:
        """Return the current preset mode."""
        if self._mode not in list(HDL_TO_HA_PRESET):
            return PRESET_NONE
        return HDL_TO_HA_PRESET[self._mode]

    @property
    def preset_modes(self) -> Optional[List[str]]:
        """Return a list of available preset modes."""
        if len(self._preset_modes) == 0:
            return None
        keys = HA_PRESET_TO_HDL.keys() & self._preset_modes
        ha_preset_to_hdl_configured = {k: HA_PRESET_TO_HDL[k] for k in keys}
        return list(ha_preset_to_hdl_configured)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if preset_mode not in list(HA_PRESET_TO_HDL):
            preset_mode = PRESET_NONE
        mode = HA_PRESET_TO_HDL[preset_mode]

        climate_control = ControlFloorHeatingStatus()
        climate_control.mode = mode
        await self._device.control_heating_status(climate_control)
        self.async_write_ha_state()

    @property
    def hvac_action(self) -> Optional[str]:
        """Return current action ie. heating, idle, off."""
        if self._is_on:
            if self._relay_sensor_is_on is None:
                return HVACAction.HEATING
            else:
                if self._relay_sensor_is_on:
                    return HVACAction.HEATING
                else:
                    return HVACAction.IDLE
        else:
            return HVACAction.OFF

    @property
    def hvac_mode(self) -> Optional[str]:
        """Return current operation ie. heat, off."""
        if self._is_on:
            return HVACMode.HEAT
        else:
            return HVACMode.OFF

    @property
    def hvac_modes(self) -> Optional[List[str]]:
        """Return the list of available operation modes."""
        return [HVACMode.HEAT, HVACMode.OFF]

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Set operation mode."""
        if hvac_mode == HVACMode.OFF:
            climate_control = ControlFloorHeatingStatus()
            climate_control.status = OnOffStatus.OFF.value
            await self._device.control_heating_status(climate_control)
            self.async_write_ha_state()
        elif hvac_mode == HVACMode.HEAT:
            climate_control = ControlFloorHeatingStatus()
            climate_control.status = OnOffStatus.ON.value
            await self._device.control_heating_status(climate_control)
            self.async_write_ha_state()

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        return 1

    @property
    def unique_id(self):
        """Return the unique id."""
        if self._custom_unique_id:
            return self._custom_unique_id
        return self._device.device_identifier

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        climate_control = ControlFloorHeatingStatus()
        preset = HDL_TO_HA_PRESET.get(self._mode, PRESET_NONE)
        target_temperature = int(temperature)

        if preset == PRESET_NONE:
            climate_control.normal_temperature = target_temperature
        elif preset == PRESET_HOME:
            climate_control.day_temperature = target_temperature
        elif preset == PRESET_SLEEP:
            climate_control.night_temperature = target_temperature
        elif preset == PRESET_AWAY:
            climate_control.away_temperature = target_temperature
        else:
            climate_control.normal_temperature = target_temperature

        await self._device.control_heating_status(climate_control)
        self.async_write_ha_state()
