DOMAIN = "buspro"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_DEVICES = "devices"
CONF_AREAS = "areas"
CONF_FLOORS = "floors"
CONF_SCENES = "scenes"
CONF_GATEWAY_INFO = "gateway"
DEFAULT_PORT = 6000

# Registry bookkeeping: floors/areas the integration created itself, so
# re-imports never recreate user-deleted entries or move the user's own areas.
CONF_CREATED_FLOORS = "created_floors"
CONF_CREATED_AREAS = "created_areas"

# SPK code to HA platform mapping
SPK_TO_PLATFORM = {
    "light.switch": "light",
    "light.dimming": "light",
    "light.cct": "light",
    "curtain.roller": "cover",
    "curtain.trietex": "cover",
    "hvac.ac": "climate",
    "hvac.ac_panel": "climate",
    "other.common": "switch",
    "sensor.temperature": "sensor",
    "sensor.humidity": "sensor",
    "sensor.illuminance": "sensor",
    "sensor.lux": "sensor",
    "sensor.motion": "binary_sensor",
    "sensor.dry_contact": "binary_sensor",
    "sensor.universal_switch": "binary_sensor",
    "light.color": "light",
    "hvac.module": "climate",
    "hvac.floor_heating": "climate",
    "fan.relay": "fan",
    "fan.dimmer": "fan",
    "panel.buttons": "event",
    "scene.bus": "button",
    "sequence.bus": "button",
}

# Bridged non-HDL entities (virtual HDL devices answering on the bus).
CONF_BRIDGES = "bridges"

# Options (entry.options)
CONF_GATEWAY_IP_FILTER = "gateway_ip_filter"
CONF_ONLINE_CHECK_INTERVAL = "online_check_interval"
CONF_BUS_MONITOR = "bus_monitor"
CONF_EXPERIMENTAL = "experimental"

# Bus events fired on the Home Assistant event bus
EVENT_PANEL_BUTTON = "buspro_panel_button"
EVENT_TELEGRAM = "buspro_telegram"

# Platform list for entity forwarding
PLATFORMS = [
    "light",
    "cover",
    "climate",
    "switch",
    "sensor",
    "binary_sensor",
    "event",
    "button",
    "fan",
]