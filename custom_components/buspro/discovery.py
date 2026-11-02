"""Find HDL gateways on the LAN and modules on the bus."""
import logging
import socket
import time

from .pybuspro.core.telegram import Telegram
from .pybuspro.helpers.enums import OperateCode
from .pybuspro.helpers.telegram_helper import TelegramHelper

_LOGGER = logging.getLogger(__name__)

BROADCAST_ADDRESS = (255, 255)

# Module type code (hex) -> (model, role). Roles decide which entities a
# scan offers: relay, dimmer, panel, sensor_12in1, sensor_8in1,
# sensors_in_one, dry_contact.
DEVICE_CATALOGUE = {
    "0011": ("SB-DN-6B0-10V", "dimmer"),
    "01ac": ("SB-DN-R0816 relay", "relay"),
    "0260": ("SB-DN-DT0601 dimmer", "dimmer"),
    "026d": ("HDL-MDT0601 dimmer", "dimmer"),
    "0134": ("SB-CMS-12in1 sensor", "sensor_12in1"),
    "0135": ("SB-CMS-8in1 sensor", "sensor_8in1"),
    "0150": ("HDL-MSP07M sensors-in-one", "sensors_in_one"),
    "0077": ("SB-DRY-4Z dry contact", "dry_contact"),
    "0086": ("DLP panel", "panel"),
    "0095": ("DLP panel", "panel"),
    "009c": ("DLP panel v2", "panel"),
    "012b": ("SB-WS8M 8-key panel", "panel"),
    "00c0": ("HDL-MPTLC43 Enviro panel", "panel"),
    "0890": ("HDL-MPTL4C Granite Display", "panel"),
    "0872": ("HDL-MPTL4C Granite Display", "panel"),
    "087f": ("HDL-MPL35C Tile panel", "panel"),
    "088e": ("HDL-MPL40E Tile panel", "panel"),
    "0be9": ("SB-DN-SEC250K security", "unsupported"),
    "0453": ("SB-DN-Logic960 logic", "unsupported"),
}


def decode_remark(payload):
    """Decode an HDL remark (name) field: up to 20 bytes, NUL padded."""
    raw = bytes(payload).split(b"\x00")[0]
    for encoding in ("utf-8", "gbk"):
        try:
            return raw.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1").strip()


def search_gateways(port=6000, duration=3.0):
    """Broadcast a read-remark request and return the IPs that answer.

    Every reply on the bus reaches us through an HDL gateway, so the UDP
    sender of a reply is a gateway. Blocking: run in an executor.
    """
    telegram = Telegram()
    telegram.target_address = BROADCAST_ADDRESS
    telegram.operate_code = OperateCode.ReadDeviceRemark
    telegram.payload = []
    frame = TelegramHelper().build_send_buffer(telegram)

    found = set()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", port))
        sock.settimeout(0.3)
        sock.sendto(bytes(frame), ("255.255.255.255", port))
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            try:
                data, (ip, _port) = sock.recvfrom(1024)
            except socket.timeout:
                continue
            if len(data) >= 16 and data[4:14] == b"HDLMIRACLE":
                found.add(ip)
    except OSError as err:
        _LOGGER.warning("Gateway search failed: %s", err)
    finally:
        sock.close()

    # Our own broadcast can come back to us; drop local addresses.
    local = set()
    try:
        local = set(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    return sorted(found - local)


async def scan_bus(hdl, duration=4.0):
    """Ask every module for its name; return a list of found modules.

    Each item: {"subnet_id", "device_id", "type_code", "model", "role",
    "remark", "channels"}.
    """
    telegram = Telegram()
    telegram.target_address = BROADCAST_ADDRESS
    telegram.operate_code = OperateCode.ReadDeviceRemark
    telegram.payload = []
    replies = await hdl.collect(
        telegram, OperateCode.ReadDeviceRemarkResponse.value, duration)

    modules = {}
    for reply in replies:
        address = tuple(reply.source_address)
        if address in modules:
            continue
        type_code = reply.source_device_type_raw.hex() if reply.source_device_type_raw else ""
        model, role = DEVICE_CATALOGUE.get(type_code, (f"Unknown type 0x{type_code}", "unknown"))
        modules[address] = {
            "subnet_id": address[0],
            "device_id": address[1],
            "type_code": type_code,
            "model": model,
            "role": role,
            "remark": decode_remark(reply.payload or []),
            "channels": [],
        }

    for module in modules.values():
        if module["role"] in ("relay", "dimmer"):
            module["channels"] = await _read_channels(hdl, module)

    return sorted(modules.values(), key=lambda m: (m["subnet_id"], m["device_id"]))


async def _read_channels(hdl, module):
    """Read how many channels an output module has and their names."""
    address = (module["subnet_id"], module["device_id"])
    status = Telegram()
    status.target_address = address
    status.operate_code = OperateCode.ReadStatusOfChannels
    status.payload = []
    reply = await hdl.request(status, OperateCode.ReadStatusOfChannelsResponse.value)
    if reply is None or not reply.payload:
        return []
    count = reply.payload[0]

    channels = []
    for number in range(1, count + 1):
        name = f"{module['remark'] or module['model']} {number}"
        remark = Telegram()
        remark.target_address = address
        remark.operate_code = _ReadChannelRemark
        remark.payload = [number]
        answer = await hdl.request(remark, _ReadChannelRemark.response, timeout=0.5, retries=0)
        if answer is not None and len(answer.payload or []) > 1 and answer.payload[0] == number:
            decoded = decode_remark(answer.payload[1:])
            if decoded:
                name = decoded
        channels.append({"number": number, "name": name})
    return channels


class _ReadChannelRemarkCode:
    """Read channel remark (0xF00E, reply 0xF00F: [channel, name...])."""

    value = b"\xF0\x0E"
    response = b"\xF0\x0F"
    name = "ReadChannelRemark"


_ReadChannelRemark = _ReadChannelRemarkCode()


def modules_to_devices(modules, relay_platform="light"):
    """Turn selected scan results into config entry device dicts."""
    devices = []
    for module in modules:
        subnet_id, device_id = module["subnet_id"], module["device_id"]
        label = module["remark"] or f"{module['model']} {subnet_id}.{device_id}"
        role = module["role"]

        def add(name, platform, spk, channel=1, caps=None, kind=None, suffix=None):
            device = {
                "name": name,
                "platform": platform,
                "spk": spk,
                "subnet_id": subnet_id,
                "device_id": device_id,
                "channel": channel,
                "area_name": "",
                "capabilities": caps or [],
                "unique_id": f"buspro_{subnet_id}_{device_id}_{channel}_"
                             f"{(suffix or spk).replace('.', '_')}",
            }
            if kind:
                device["device"] = kind
            devices.append(device)

        if role in ("relay", "dimmer"):
            for channel in module["channels"]:
                if role == "dimmer":
                    add(channel["name"], "light", "light.dimming", channel["number"],
                        ["on_off", "brightness"])
                elif relay_platform == "switch":
                    add(channel["name"], "switch", "other.common", channel["number"], ["on_off"])
                else:
                    add(channel["name"], "light", "light.switch", channel["number"], ["on_off"])
        elif role == "panel":
            add(f"{label} buttons", "event", "panel.buttons")
            add(f"{label} temperature", "sensor", "sensor.temperature",
                caps=["temperature"], kind="panel")
        elif role == "sensor_12in1":
            add(f"{label} temperature", "sensor", "sensor.temperature",
                caps=["temperature"], kind="12in1")
            add(f"{label} illuminance", "sensor", "sensor.illuminance", caps=["illuminance"])
            add(f"{label} motion", "binary_sensor", "sensor.motion", caps=["motion"])
        elif role == "sensor_8in1":
            add(f"{label} temperature", "sensor", "sensor.temperature", caps=["temperature"])
            add(f"{label} illuminance", "sensor", "sensor.illuminance", caps=["illuminance"])
            add(f"{label} motion", "binary_sensor", "sensor.motion", caps=["motion"])
        elif role == "sensors_in_one":
            add(f"{label} humidity", "sensor", "sensor.humidity",
                caps=["humidity"], kind="sensors_in_one")
            add(f"{label} illuminance", "sensor", "sensor.illuminance", caps=["illuminance"])
        elif role == "dry_contact":
            for number in range(1, 5):
                add(f"{label} input {number}", "binary_sensor", "sensor.dry_contact",
                    number, ["opening"])
    return devices
