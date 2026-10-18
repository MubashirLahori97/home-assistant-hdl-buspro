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
    "sensor.illuminance": "sensor",
    "sensor.lux": "sensor",
    "sensor.motion": "binary_sensor",
    "sensor.dry_contact": "binary_sensor",
    "sensor.universal_switch": "binary_sensor",
}

# Platform list for entity forwarding
PLATFORMS = ["light", "cover", "climate", "switch", "sensor", "binary_sensor"]