"""Support for Buspro devices."""
import asyncio
import logging
import socket
import time

import homeassistant.helpers.config_validation as cv
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
    CONF_GATEWAY_INFO,
    CONF_CREATED_FLOORS,
    CONF_CREATED_AREAS,
    CONF_GATEWAY_IP_FILTER,
    CONF_ONLINE_CHECK_INTERVAL,
    CONF_BUS_MONITOR,
    EVENT_TELEGRAM,
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
    vol.Required(SERVICE_BUSPRO_ATTR_OPERATE_CODE): vol.All(
        cv.positive_int, vol.Range(max=65535)
    ),
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


async def async_setup_floors_and_areas(hass: HomeAssistant, entry_data: dict) -> dict:
    """Create floors and areas once, when the user completes a project import.

    Runs only from the config flow (new entry) or options flow (re-import).
    It never runs on startup/reload, so it cannot resurrect floors/areas the
    user deleted, and it only ever touches areas the integration created
    itself (tracked in entry_data).
    """
    try:
        from homeassistant.helpers import floor_registry as fr
    except ImportError:
        fr = None
    from homeassistant.helpers import area_registry as ar

    created_floors = set(entry_data.get(CONF_CREATED_FLOORS, []) or [])
    created_areas = list(entry_data.get(CONF_CREATED_AREAS, []) or [])
    created_area_ids = {a.get("area_id") for a in created_areas if a.get("area_id")}

    floors = entry_data.get(CONF_FLOORS, []) or []
    areas = entry_data.get(CONF_AREAS, []) or []

    # Create any new floors (skip ones already created on a previous import).
    # Existing floors are only looked up, never recreated.
    floor_id_map = {}
    if fr is not None and floors:
        try:
            floor_reg = fr.async_get(hass)
            get_by_name = getattr(floor_reg, "async_get_floor_by_name", None)
            for floor_name in floors:
                if not floor_name:
                    continue
                if floor_name in created_floors:
                    if get_by_name is not None:
                        existing = get_by_name(floor_name)
                        if existing is not None:
                            floor_id_map[floor_name] = existing.floor_id
                    continue
                floor_entry = floor_reg.async_get_or_create(floor_name)
                floor_id_map[floor_name] = floor_entry.floor_id
                created_floors.add(floor_name)
        except Exception as err:
            _LOGGER.debug("Could not create floors: %s", err)

    # Create any new areas; only ever update floor assignment for areas
    # this integration created itself.
    if areas:
        try:
            area_reg = ar.async_get(hass)
            for area_info in areas:
                area_name = area_info.get("name")
                floor_name = area_info.get("floor")
                if not area_name:
                    continue
                known = next(
                    (a for a in created_areas if a.get("name") == area_name), None
                )
                if known is None:
                    # A pre-existing area with this name belongs to the user:
                    # leave it alone (no floor change, not recorded as ours).
                    if area_reg.async_get_area_by_name(area_name) is not None:
                        continue
                    area_entry = area_reg.async_get_or_create(area_name)
                    if floor_name and floor_name in floor_id_map:
                        try:
                            area_reg.async_update(
                                area_entry.id, floor_id=floor_id_map[floor_name]
                            )
                        except Exception:
                            pass
                    created_areas.append(
                        {"name": area_name, "area_id": area_entry.id}
                    )
                    created_area_ids.add(area_entry.id)
                else:
                    # Re-import: only ever update the floor assignment of an
                    # area this integration created itself (same registry id,
                    # resolved by name so deleted/renamed areas are skipped).
                    current = area_reg.async_get_area_by_name(area_name)
                    if (
                        current is not None
                        and current.id == known.get("area_id")
                        and current.id in created_area_ids
                        and floor_name
                        and floor_name in floor_id_map
                    ):
                        try:
                            area_reg.async_update(
                                current.id, floor_id=floor_id_map[floor_name]
                            )
                        except Exception:
                            pass
        except Exception as err:
            _LOGGER.debug("Could not create areas: %s", err)

    entry_data[CONF_CREATED_FLOORS] = sorted(created_floors)
    entry_data[CONF_CREATED_AREAS] = created_areas
    return entry_data


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Setup the Buspro component from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    host = config_entry.data.get(CONF_HOST, "")
    port = config_entry.data.get(CONF_PORT, 6000)
    options = config_entry.options

    header_ip = await hass.async_add_executor_job(_local_ip_towards, host)
    buspro_module = BusproModule(
        hass, host, port,
        header_ip=header_ip,
        gateway_ip_filter=options.get(CONF_GATEWAY_IP_FILTER, False),
    )
    await buspro_module.start()

    hass.data[DOMAIN][config_entry.entry_id] = buspro_module

    buspro_module.register_services()

    if options.get(CONF_BUS_MONITOR, False):
        buspro_module.enable_bus_monitor()

    # Forward setup to all supported platforms
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    interval = options.get(CONF_ONLINE_CHECK_INTERVAL, 0) or 0
    if interval > 0:
        buspro_module.start_online_check(interval)

    from .bridge import async_setup_bridges
    await async_setup_bridges(hass, config_entry, buspro_module)

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


def _local_ip_towards(host: str):
    """Return this machine's IP on the route to the gateway, as 4 ints.

    Connecting a UDP socket sends nothing; it only picks the route.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((host, 6000))
            ip = sock.getsockname()[0]
        parts = tuple(int(p) for p in ip.split("."))
        if len(parts) == 4 and parts != (0, 0, 0, 0):
            return parts
    except (OSError, ValueError):
        pass
    return None


class _RawOperateCode:
    """Operate code holder for codes outside the known OperateCode enum.

    Carries the same .value shape (two bytes) the telegram builder reads.
    """

    def __init__(self, value: bytes):
        self.value = value


def _operate_code_from_int(code: int):
    """Convert a single integer operate code to the two-byte form the
    telegram builder expects (an object whose .value is two bytes, big
    endian). Known codes return the real OperateCode member; anything else
    gets a minimal holder so arbitrary codes still build a valid telegram.
    """
    from .pybuspro.helpers.enums import OperateCode

    two_bytes = bytes(((code >> 8) & 0xFF, code & 0xFF))
    try:
        return OperateCode(two_bytes)
    except ValueError:
        return _RawOperateCode(two_bytes)


class BusproModule:
    """Representation of Buspro Object."""

    def __init__(self, hass, host, port, header_ip=None, gateway_ip_filter=False):
        """Initialize of Buspro module."""
        self.hass = hass
        self.connected = False
        self.hdl = None
        self.host = host
        self.port = port
        self.header_ip = header_ip
        self.gateway_ip_filter = gateway_ip_filter
        self.gateway_address_send_receive = ((host, port), ('', port))
        # (subnet, device) -> {"last_seen": epoch, "device_type": hex}
        self.seen_devices = {}
        # Devices whose last online check went unanswered
        self.offline_devices = set()
        self.firmware = {}
        self._online_task = None
        self._unsub_stop = None
        self.init_hdl()

    def init_hdl(self):
        """Initialize of Buspro object."""
        # noinspection PyUnresolvedReferences
        from .pybuspro.buspro import Buspro
        self.hdl = Buspro(
            self.gateway_address_send_receive, self.hass.loop,
            header_ip=self.header_ip,
            gateway_ip_filter=self.gateway_ip_filter,
        )

    async def start(self):
        """Start Buspro object. Connect to tunneling device."""
        await self.hdl.start(state_updater=False)
        self.hdl.register_telegram_received_all_messages_cb(self._track_seen)
        self._unsub_stop = self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, self.stop)
        self.connected = True

    # noinspection PyUnusedLocal
    async def stop(self, event=None):
        """Stop Buspro object. Disconnect from tunneling device."""
        if self._online_task is not None:
            self._online_task.cancel()
            self._online_task = None
        if self._unsub_stop is not None and event is None:
            self._unsub_stop()
        self._unsub_stop = None
        if self.hdl:
            await self.hdl.stop()
        self.connected = False

    def _track_seen(self, telegram):
        address = tuple(telegram.source_address)
        raw_type = telegram.source_device_type_raw
        self.seen_devices[address] = {
            "last_seen": time.time(),
            "device_type": raw_type.hex() if raw_type else None,
        }
        if address in self.offline_devices:
            self.offline_devices.discard(address)
            self._notify_devices(address)

    def is_available(self, address=None):
        """Return False when the gateway is down or the device failed its
        last online check."""
        if not self.connected:
            return False
        if address is None:
            return True
        return tuple(address)[:2] not in self.offline_devices

    def _notify_devices(self, address):
        for device in list(self.hdl.devices):
            device_address = tuple(getattr(device, "_device_address", ()) or ())
            if device_address[:2] == tuple(address):
                device._call_device_updated()

    def enable_bus_monitor(self):
        """Fire a buspro_telegram event for every message on the bus."""
        def _fire(telegram):
            raw = telegram.operate_code_raw
            raw_type = telegram.source_device_type_raw
            self.hass.bus.async_fire(EVENT_TELEGRAM, {
                "source_address": list(telegram.source_address),
                "target_address": list(telegram.target_address),
                "source_device_type": raw_type.hex() if raw_type else None,
                "operate_code": raw.hex() if raw else None,
                "operate_code_name": telegram.operate_code.name
                if telegram.operate_code is not None else None,
                "payload": list(telegram.payload or []),
            })
        self.hdl.register_telegram_received_all_messages_cb(_fire)

    def start_online_check(self, interval):
        """Periodically ask every configured device whether it is online."""
        async def _run():
            while True:
                await asyncio.sleep(interval)
                await self.async_check_online()
        self._online_task = self.hass.async_create_background_task(
            _run(), "buspro online check")

    async def async_check_online(self):
        """Ask each configured device whether it is online (0xF065)."""
        from .pybuspro.core.telegram import Telegram
        from .pybuspro.helpers.enums import OperateCode

        addresses = {
            tuple(getattr(d, "_device_address", ()) or ())[:2]
            for d in list(self.hdl.devices)
        }
        for address in sorted(a for a in addresses if len(a) == 2):
            telegram = Telegram()
            telegram.target_address = address
            telegram.operate_code = OperateCode.IsDeviceOnline
            reply = await self.hdl.request(
                telegram, OperateCode.IsDeviceOnlineResponse.value,
                timeout=1.0, retries=1)
            was_offline = address in self.offline_devices
            if reply is None and not was_offline:
                self.offline_devices.add(address)
                self._notify_devices(address)
            elif reply is not None and was_offline:
                self.offline_devices.discard(address)
                self._notify_devices(address)

    async def async_read_firmware(self, address):
        """Read and cache a device's firmware version string (0xEEFD)."""
        from .pybuspro.core.telegram import Telegram
        from .pybuspro.helpers.enums import OperateCode

        address = tuple(address)
        if address in self.firmware:
            return self.firmware[address]
        telegram = Telegram()
        telegram.target_address = address
        telegram.operate_code = OperateCode.ReadFirmwareVersion
        reply = await self.hdl.request(
            telegram, OperateCode.ReadFirmwareVersionResponse.value,
            timeout=1.0, retries=1)
        if reply is None:
            return None
        version = bytes(reply.payload).split(b"\x00")[0].decode(
            "ascii", errors="replace").strip()
        self.firmware[address] = version
        return version

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
        generic = Generic(
            self.hdl,
            attr_address,
            attr_payload,
            _operate_code_from_int(attr_operate_code),
            DEFAULT_SEND_MESSAGE_NAME,
        )
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
