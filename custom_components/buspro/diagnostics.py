"""Diagnostics download for HDL Buspro."""
from datetime import datetime, timezone

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_BRIDGES, CONF_DEVICES, DOMAIN


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    """Return gateway, configured devices, what the bus has seen, firmware."""
    buspro_module = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    devices = entry.data.get(CONF_DEVICES, []) or []
    addresses = sorted({(d.get("subnet_id"), d.get("device_id")) for d in devices
                        if d.get("subnet_id") is not None})

    seen = {}
    firmware = {}
    offline = []
    connected = False
    if buspro_module is not None:
        connected = buspro_module.connected
        # Only ask modules that have talked on the bus, so an offline
        # module cannot stall the download.
        for address in addresses:
            if address in buspro_module.seen_devices:
                await buspro_module.async_read_firmware(address)
        firmware = {f"{a[0]}.{a[1]}": v for a, v in buspro_module.firmware.items()}
        seen = {
            f"{a[0]}.{a[1]}": {
                "last_seen": datetime.fromtimestamp(info["last_seen"], timezone.utc).isoformat(),
                "device_type": info["device_type"],
            }
            for a, info in sorted(buspro_module.seen_devices.items())
        }
        offline = [f"{a[0]}.{a[1]}" for a in sorted(buspro_module.offline_devices)]

    return {
        "gateway": {
            "host": entry.data.get("host"),
            "port": entry.data.get("port"),
            "connected": connected,
            "header_ip": list(buspro_module.header_ip) if buspro_module and buspro_module.header_ip else None,
        },
        "options": dict(entry.options),
        "configured_devices": devices,
        "bridges": entry.data.get(CONF_BRIDGES, []),
        "firmware": firmware,
        "offline_devices": offline,
        "seen_on_bus": seen,
    }
