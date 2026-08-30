"""This component provides cover (curtain/blind) support for Buspro."""
import logging

from homeassistant.components.cover import (
    CoverEntity,
    CoverEntityFeature,
    CoverDeviceClass,
)
from homeassistant.core import callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, entity_registry as er
try:
    from homeassistant.helpers.device_registry import DeviceInfo
except ImportError:
    from homeassistant.helpers.entity import DeviceInfo

from .const import CONF_DEVICES as CONF_DEVICES_ENTRY, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Set up Buspro cover devices from a config entry."""
    # noinspection PyUnresolvedReferences
    from .pybuspro.devices import Cover

    buspro_module = hass.data[DOMAIN][config_entry.entry_id]
    hdl = buspro_module.hdl
    raw_devices = config_entry.data.get(CONF_DEVICES_ENTRY, [])
    entities = []

    for device_info in raw_devices:
        if device_info.get("platform") != "cover":
            continue

        name = device_info.get("name", "Curtain")
        subnet_id = device_info.get("subnet_id")
        device_id = device_info.get("device_id")
        channel = device_info.get("channel")
        area_name = device_info.get("area_name", "")
        spk = device_info.get("spk", "")

        device_address = (subnet_id, device_id)
        cover = Cover(hdl, device_address, channel, name)
        entities.append(BusproCover(
            hass, cover, spk=spk, 
            area_name=area_name, 
            unique_id=device_info.get("unique_id"), 
            buspro_module=buspro_module
        ))

    async_add_entities(entities)


class BusproCover(CoverEntity):
    """Representation of a Buspro cover (curtain/blind)."""

    def __init__(self, hass, device, spk="", area_name="", unique_id=None, buspro_module=None):
        self._hass = hass
        self._device = device
        self._area_name = area_name
        self._custom_unique_id = unique_id
        self._buspro_module = buspro_module

        if "roller" in spk or "shutter" in spk or "blind" in spk:
            self._attr_device_class = CoverDeviceClass.SHUTTER
        else:
            self._attr_device_class = CoverDeviceClass.CURTAIN

        self._attr_supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.SET_POSITION
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

    async def async_added_to_hass(self):
        """Assign entity directly to its area in Entity Registry."""
        await super().async_added_to_hass()
        if self._area_name and self.registry_entry:
            area_reg = ar.async_get(self.hass)
            area_entry = area_reg.async_get_area_by_name(self._area_name)
            if area_entry and self.registry_entry.area_id != area_entry.id:
                ent_reg = er.async_get(self.hass)
                ent_reg.async_update_entity(self.entity_id, area_id=area_entry.id)

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
        """Return the display name of this cover."""
        return self._device.name

    @property
    def available(self):
        """Return True if entity is available."""
        if self._buspro_module:
            return self._buspro_module.connected
        return True

    @property
    def current_cover_position(self):
        """Return current position of cover (0 is closed, 100 is open)."""
        return self._device.current_position

    @property
    def is_closed(self):
        """Return if the cover is closed."""
        return self._device.is_closed

    async def async_open_cover(self, **kwargs):
        """Open the cover."""
        await self._device.open_cover()

    async def async_close_cover(self, **kwargs):
        """Close cover."""
        await self._device.close_cover()

    async def async_set_cover_position(self, **kwargs):
        """Move the cover to a specific position."""
        position = kwargs.get("position", 100)
        await self._device.set_position(position)

    async def async_stop_cover(self, **kwargs):
        """Stop the cover."""
        await self._device.stop_cover()

    @property
    def unique_id(self):
        """Return the unique id."""
        if self._custom_unique_id:
            return self._custom_unique_id
        return self._device.device_identifier
