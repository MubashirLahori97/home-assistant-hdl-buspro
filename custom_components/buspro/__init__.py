"""Support for Buspro devices."""
import logging

import homeassistant.helpers.config_validation as cv
try:
    from homeassistant.helpers import floor_registry as fr
except ImportError:
    fr = None
from homeassistant.helpers import area_registry as ar
import voluptuous as vol
from homeassistant.const import (
    CONF_HOST, 
    CONF_PORT, 
    CONF_NAME,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import (
    DOMAIN,
    CONF_DEVICES,
    CONF_AREAS,
    CONF_FLOORS,
    CONF_SCENES,
    PLATFORMS,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_CONF_NAME = ""

DEFAULT_SCENE_NAME = "BUSPRO SCENE"
DEFAULT_SEND_MESSAGE_NAME = "BUSPRO MESSAGE"

SERVICE_BUSPRO_SEND_MESSAGE = "send_message"
SERVICE_BUSPRO_ACTIVATE_SCENE = "activate_scene"
SERVICE_BUSPRO_UNIVERSAL_SWITCH = "set_universal_switch"

SERVICE_BUSPRO_ATTR_OPERATE_CODE = "operate_code"
SERVICE_BUSPRO_ATTR_ADDRESS = "address"
SERVICE_BUSPRO_ATTR_PAYLOAD = "payload"
SERVICE_BUSPRO_ATTR_SCENE_ADDRESS = "scene_address"
SERVICE_BUSPRO_ATTR_SWITCH_NUMBER = "switch_number"
SERVICE_BUSPRO_ATTR_STATUS = "status"

SERVICE_BUSPRO_ACTIVATE_SCENE_SCHEMA = vol.Schema({
    vol.Required(SERVICE_BUSPRO_ATTR_ADDRESS): vol.Any([cv.positive_int]),
    vol.Required(SERVICE_BUSPRO_ATTR_SCENE_ADDRESS): vol.Any([cv.positive_int]),
})

SERVICE_BUSPRO_SEND_MESSAGE_SCHEMA = vol.Schema({
    vol.Required(SERVICE_BUSPRO_ATTR_ADDRESS): vol.Any([cv.positive_int]),
    vol.Required(SERVICE_BUSPRO_ATTR_OPERATE_CODE): vol.Any([cv.positive_int]),
    vol.Required(SERVICE_BUSPRO_ATTR_PAYLOAD): vol.Any([cv.positive_int]),
})

SERVICE_BUSPRO_UNIVERSAL_SWITCH_SCHEMA = vol.Schema({
    vol.Required(SERVICE_BUSPRO_ATTR_ADDRESS): vol.Any([cv.positive_int]),
    vol.Required(SERVICE_BUSPRO_ATTR_SWITCH_NUMBER): vol.Any(cv.positive_int),
    vol.Required(SERVICE_BUSPRO_ATTR_STATUS): vol.Any(cv.positive_int),
})

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_PORT): cv.port,
        vol.Optional(CONF_NAME, default=DEFAULT_CONF_NAME): cv.string
    })
}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Setup the Buspro component from YAML (legacy fallback)."""
    if DOMAIN not in config:
        return True

    hass.data.setdefault(DOMAIN, {})
    host = config[DOMAIN][CONF_HOST]
    port = config[DOMAIN][CONF_PORT]

    buspro_module = BusproModule(hass, host, port)
    hass.data[DOMAIN]["legacy"] = buspro_module
    await buspro_module.start()
    buspro_module.register_services()

    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Setup the Buspro component from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    host = config_entry.data.get(CONF_HOST, "")
    port = config_entry.data.get(CONF_PORT, 6000)
    floors = config_entry.data.get(CONF_FLOORS, [])
    areas = config_entry.data.get(CONF_AREAS, [])

    # Auto-create HA Floors in Floor Registry if supported
    floor_id_map = {}
    if fr is not None and floors:
        try:
            floor_reg = fr.async_get(hass)
            for floor_name in floors:
                if floor_name:
                    floor_entry = floor_reg.async_get_or_create(floor_name)
                    floor_id_map[floor_name] = floor_entry.floor_id
        except Exception as err:
            _LOGGER.debug("Could not auto-create floors: %s", err)

    # Auto-create HA Areas in Area Registry and link them to their respective floors
    if areas:
        area_reg = ar.async_get(hass)
        for area_info in areas:
            area_name = area_info.get("name")
            floor_name = area_info.get("floor")
            if area_name:
                area_entry = area_reg.async_get_or_create(area_name)
                if floor_name and floor_name in floor_id_map:
                    try:
                        area_reg.async_update(area_entry.id, floor_id=floor_id_map[floor_name])
                    except Exception:
                        pass

    buspro_module = BusproModule(hass, host, port)
    await buspro_module.start()

    hass.data[DOMAIN][config_entry.entry_id] = buspro_module

    buspro_module.register_services()

    # Forward setup to all supported platforms
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    config_entry.async_on_unload(
        config_entry.add_update_listener(async_reload_entry)
    )

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when data/options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)
    if unload_ok:
        buspro_module = hass.data[DOMAIN].pop(config_entry.entry_id, None)
        if buspro_module:
            await buspro_module.stop(None)
    return unload_ok


class BusproModule:
    """Representation of Buspro Object."""

    def __init__(self, hass, host, port):
        """Initialize of Buspro module."""
        self.hass = hass
        self.connected = False
        self.hdl = None
        self.gateway_address_send_receive = ((host, port), ('', port))
        self.init_hdl()

    def init_hdl(self):
        """Initialize of Buspro object."""
        # noinspection PyUnresolvedReferences
        from .pybuspro.buspro import Buspro
        self.hdl = Buspro(self.gateway_address_send_receive, self.hass.loop)

    async def start(self):
        """Start Buspro object. Connect to tunneling device."""
        await self.hdl.start(state_updater=False)
        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self.stop)
        self.connected = True

    # noinspection PyUnusedLocal
    async def stop(self, event=None):
        """Stop Buspro object. Disconnect from tunneling device."""
        if self.hdl:
            await self.hdl.stop()
        self.connected = False

    async def service_activate_scene(self, call):
        """Service for activating a scene."""
        # noinspection PyUnresolvedReferences
        from .pybuspro.devices.scene import Scene

        attr_address = call.data.get(SERVICE_BUSPRO_ATTR_ADDRESS)
        attr_scene_address = call.data.get(SERVICE_BUSPRO_ATTR_SCENE_ADDRESS)
        scene = Scene(self.hdl, attr_address, attr_scene_address, DEFAULT_SCENE_NAME)
        await scene.run()

    async def service_send_message(self, call):
        """Service for sending an arbitrary message."""
        # noinspection PyUnresolvedReferences
        from .pybuspro.devices.generic import Generic

        attr_address = call.data.get(SERVICE_BUSPRO_ATTR_ADDRESS)
        attr_payload = call.data.get(SERVICE_BUSPRO_ATTR_PAYLOAD)
        attr_operate_code = call.data.get(SERVICE_BUSPRO_ATTR_OPERATE_CODE)
        generic = Generic(self.hdl, attr_address, attr_payload, attr_operate_code, DEFAULT_SEND_MESSAGE_NAME)
        await generic.run()

    async def service_set_universal_switch(self, call):
        """Service for setting a universal switch."""
        # noinspection PyUnresolvedReferences
        from .pybuspro.devices.universal_switch import UniversalSwitch

        attr_address = call.data.get(SERVICE_BUSPRO_ATTR_ADDRESS)
        attr_switch_number = call.data.get(SERVICE_BUSPRO_ATTR_SWITCH_NUMBER)
        universal_switch = UniversalSwitch(self.hdl, attr_address, attr_switch_number)

        status = call.data.get(SERVICE_BUSPRO_ATTR_STATUS)
        if status == 1:
            await universal_switch.set_on()
        else:
            await universal_switch.set_off()

    def register_services(self):
        """Register Buspro custom services."""
        self.hass.services.async_register(
            DOMAIN, SERVICE_BUSPRO_ACTIVATE_SCENE,
            self.service_activate_scene,
            schema=SERVICE_BUSPRO_ACTIVATE_SCENE_SCHEMA)

        self.hass.services.async_register(
            DOMAIN, SERVICE_BUSPRO_SEND_MESSAGE,
            self.service_send_message,
            schema=SERVICE_BUSPRO_SEND_MESSAGE_SCHEMA)

        self.hass.services.async_register(
            DOMAIN, SERVICE_BUSPRO_UNIVERSAL_SWITCH,
            self.service_set_universal_switch,
            schema=SERVICE_BUSPRO_UNIVERSAL_SWITCH_SCHEMA)
