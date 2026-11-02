"""Shared helpers for HDL Buspro entities."""
try:
    from homeassistant.helpers.device_registry import DeviceInfo
except ImportError:
    from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN


def room_device_info(area_name):
    """Group entities under one device per room, like the other platforms."""
    if not area_name:
        return None
    area_slug = area_name.lower().replace(" ", "_")
    return DeviceInfo(
        identifiers={(DOMAIN, f"room_{area_slug}")},
        name=area_name,
        manufacturer="HDL Automation",
        suggested_area=area_name,
    )


def entry_devices(config_entry, platform):
    """Return the configured device dicts for one platform."""
    from .const import CONF_DEVICES

    return [
        d for d in config_entry.data.get(CONF_DEVICES, [])
        if d.get("platform") == platform
    ]
