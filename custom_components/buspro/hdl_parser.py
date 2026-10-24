"""
HDL Buspro Project File Parser
================================

Supports parsing HDL project files and exports from multiple formats:
- HDL Gateway Backup JSON (.json, .busproj)
- Extractor Spreadsheet (.xlsx via openpyxl)
- Extractor CSV export (.csv)
- Raw pasted JSON or CSV content

Extracts:
- Gateway connection info (IP, port, subnet, device ID)
- Building hierarchy (floors, clean HA rooms/areas)
- All devices with name, type, address, channel, room assignment, and capabilities (lights, covers, climate, switches, sensors, binary_sensors)
- Scenes
"""

from collections import Counter, defaultdict
import csv
import io
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from .const import SPK_TO_PLATFORM
except ImportError:
    from const import SPK_TO_PLATFORM

_LOGGER = logging.getLogger(__name__)

# Fields a dict must have to be recognized as a device entry in JSON
REQUIRED_FUNCTION_FIELDS = {"name", "net_id", "dev_id", "channel", "spk", "sid"}

KNOWN_DRIVER_KEYS = [
    "myAddDeviceDBToGWDriverBus",
    "myAddDeviceDBToGWDriverKnx",
    "myAddDeviceDBToGWDriverAiPlus",
]

CSV_TYPE_MAP = {
    "lighting-switch": ("light", "light.switch", False),
    "light.switch": ("light", "light.switch", False),
    "lighting-dimming": ("light", "light.dimming", True),
    "light.dimming": ("light", "light.dimming", True),
    "lighting-color temp.": ("light", "light.cct", True),
    "light.cct": ("light", "light.cct", True),
    "shading-roller shutters": ("cover", "curtain.roller", False),
    "curtain.roller": ("cover", "curtain.roller", False),
    "shading-trietex curtain": ("cover", "curtain.trietex", False),
    "curtain.trietex": ("cover", "curtain.trietex", False),
    "ac-control": ("climate", "hvac.ac", False),
    "hvac.ac": ("climate", "hvac.ac", False),
    "ac-panel": ("climate", "hvac.ac_panel", False),
    "hvac.ac_panel": ("climate", "hvac.ac_panel", False),
    "other": ("switch", "other.common", False),
    "other.common": ("switch", "other.common", False),
    # Sensors
    "sensor-temperature": ("sensor", "sensor.temperature", False),
    "sensor.temperature": ("sensor", "sensor.temperature", False),
    "temperature": ("sensor", "sensor.temperature", False),
    "sensor-humidity": ("sensor", "sensor.humidity", False),
    "sensor.humidity": ("sensor", "sensor.humidity", False),
    "humidity": ("sensor", "sensor.humidity", False),
    "sensor-illuminance": ("sensor", "sensor.illuminance", False),
    "sensor.illuminance": ("sensor", "sensor.illuminance", False),
    "sensor.lux": ("sensor", "sensor.lux", False),
    "illuminance": ("sensor", "sensor.illuminance", False),
    "lux": ("sensor", "sensor.lux", False),
    "sensor-motion": ("binary_sensor", "sensor.motion", False),
    "sensor.motion": ("binary_sensor", "sensor.motion", False),
    "motion": ("binary_sensor", "sensor.motion", False),
    "pir": ("binary_sensor", "sensor.motion", False),
    "sensor-dry contact": ("binary_sensor", "sensor.dry_contact", False),
    "sensor.dry_contact": ("binary_sensor", "sensor.dry_contact", False),
    "dry contact": ("binary_sensor", "sensor.dry_contact", False),
    "dry_contact": ("binary_sensor", "sensor.dry_contact", False),
    "sensor.universal_switch": ("binary_sensor", "sensor.universal_switch", False),
    "universal switch": ("binary_sensor", "sensor.universal_switch", False),
    "universal_switch": ("binary_sensor", "sensor.universal_switch", False),
}


class HDLParseError(Exception):
    """Raised when the HDL project file cannot be parsed."""


def parse_any(source_path_or_content: str) -> dict:
    """Auto-detect format (JSON, CSV, XLSX) from path or content and parse it."""
    source_clean = source_path_or_content.strip()

    # 1. Check if it's an existing file path
    if os.path.exists(source_clean):
        ext = os.path.splitext(source_clean)[1].lower()
        if ext in (".xlsx", ".xlsm"):
            return parse_excel_file(source_clean)
        elif ext == ".csv":
            with open(source_clean, "r", encoding="utf-8-sig", errors="ignore") as f:
                return parse_csv_data(f.read())
        else:
            # Assume JSON / busproj
            with open(source_clean, "r", encoding="utf-8", errors="ignore") as f:
                raw_text = f.read()
                try:
                    data = json.loads(raw_text)
                    return parse_project_file(data)
                except Exception as json_err:
                    # Fallback to CSV if json fails
                    try:
                        return parse_csv_data(raw_text)
                    except Exception:
                        raise HDLParseError(f"Could not parse file '{source_clean}' as JSON or CSV: {json_err}")

    # 2. Check if content starts with JSON marker
    if source_clean.startswith("{") or source_clean.startswith("["):
        try:
            data = json.loads(source_clean)
            return parse_project_file(data)
        except Exception as json_err:
            raise HDLParseError(f"Invalid JSON content: {json_err}")

    # 3. Try parsing as CSV text
    try:
        return parse_csv_data(source_clean)
    except Exception as csv_err:
        raise HDLParseError(f"Could not parse input as JSON or CSV: {csv_err}")


def parse_csv_data(csv_text: str) -> dict:
    """Parse CSV text rows from the extractor format."""
    f = io.StringIO(csv_text.strip())
    reader = csv.DictReader(f)
    rows = list(reader)
    if not rows:
        raise HDLParseError("CSV file is empty or missing headers.")
    return _parse_tabular_rows(rows)


def parse_excel_file(file_path: str) -> dict:
    """Parse Excel (.xlsx) file rows using openpyxl."""
    try:
        import openpyxl
    except ImportError as err:
        raise HDLParseError("openpyxl library is required to read Excel files. Please save as CSV or JSON.") from err

    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows or len(rows) < 2:
        raise HDLParseError("Excel worksheet contains no data rows.")

    headers = [str(cell).strip() if cell is not None else "" for cell in rows[0]]
    dict_rows = []
    for r in rows[1:]:
        row_dict = {}
        for h, val in zip(headers, r):
            if h:
                row_dict[h] = str(val).strip() if val is not None else ""
        dict_rows.append(row_dict)

    return _parse_tabular_rows(dict_rows)


def _parse_tabular_rows(rows: List[Dict[str, str]]) -> dict:
    """Parse normalized rows from CSV or Excel into the common integration data structure."""
    devices = []
    areas_map: Dict[str, str] = {}
    floors_set = set()

    # Pass 1: analyze zone floors and duplicate room names
    room_floors = defaultdict(set)
    for r in rows:
        norm_r = {k.strip(): str(v).strip() for k, v in r.items() if k}
        zone = norm_r.get("Zone") or norm_r.get("zone") or norm_r.get("Area") or ""
        if "-" in zone:
            floor_part, room_part = [p.strip() for p in zone.split("-", 1)]
        elif "/" in zone:
            floor_part, room_part = [p.strip() for p in zone.split("/", 1)]
        else:
            floor_part, room_part = "", zone.strip()
        if room_part:
            room_floors[room_part].add(floor_part)

    # Pass 2: generate devices and clean deduplicated area names
    for r in rows:
        norm_r = {k.strip(): str(v).strip() for k, v in r.items() if k}
        name = norm_r.get("Name") or norm_r.get("name") or ""
        if not name:
            continue

        type_str = (norm_r.get("Type") or norm_r.get("type") or norm_r.get("spk") or "").lower()
        zone = norm_r.get("Zone") or norm_r.get("zone") or norm_r.get("Area") or ""

        # Parse numeric addresses (can be decimal or hex)
        try:
            sub_raw = norm_r.get("Subnet ID") or norm_r.get("Subnet") or norm_r.get("net_id") or "0"
            dev_raw = norm_r.get("Device ID") or norm_r.get("Device") or norm_r.get("dev_id") or "0"
            ch_raw = norm_r.get("CH No") or norm_r.get("Channel") or norm_r.get("channel") or "1"

            subnet_id = int(sub_raw, 16) if sub_raw.startswith("0x") else int(sub_raw)
            device_id = int(dev_raw, 16) if dev_raw.startswith("0x") else int(dev_raw)
            channel = int(ch_raw, 16) if ch_raw.startswith("0x") else int(ch_raw)
        except (ValueError, TypeError):
            continue

        platform_info = CSV_TYPE_MAP.get(type_str)
        if not platform_info:
            if "light" in type_str:
                platform, spk, dimmable = "light", "light.switch", ("dim" in type_str or "cct" in type_str)
            elif "curtain" in type_str or "shading" in type_str or "blind" in type_str:
                platform, spk, dimmable = "cover", "curtain.trietex", False
            elif "ac" in type_str or "hvac" in type_str or "climate" in type_str:
                platform, spk, dimmable = "climate", "hvac.ac", False
            elif "motion" in type_str or "pir" in type_str or "dry" in type_str or "contact" in type_str:
                platform, spk, dimmable = "binary_sensor", "sensor.motion" if ("motion" in type_str or "pir" in type_str) else "sensor.dry_contact", False
            elif "humid" in type_str:
                platform, spk, dimmable = "sensor", "sensor.humidity", False
            elif "temp" in type_str or "lux" in type_str or "illuminance" in type_str:
                platform, spk, dimmable = "sensor", "sensor.temperature" if "temp" in type_str else "sensor.illuminance", False
            else:
                platform, spk, dimmable = "switch", "other.common", False
        else:
            platform, spk, dimmable = platform_info

        # Zone / Floor / Room separation
        floor_name = ""
        room_name = zone
        if "-" in zone:
            parts = zone.split("-", 1)
            floor_name = parts[0].strip()
            room_name = parts[1].strip()
        elif "/" in zone:
            parts = zone.split("/", 1)
            floor_name = parts[0].strip()
            room_name = parts[1].strip()

        # If a room name appears across multiple floors, qualify it with the floor name
        if len(room_floors[room_name]) > 1 and floor_name:
            area_name = f"{floor_name} {room_name}"
        else:
            area_name = room_name

        if floor_name:
            floors_set.add(floor_name)
        if area_name:
            areas_map[area_name] = floor_name

        caps = ["on_off"]
        if dimmable:
            caps.append("brightness")

        devices.append({
            "name": name,
            "platform": platform,
            "spk": spk,
            "subnet_id": subnet_id,
            "device_id": device_id,
            "channel": channel,
            "area_name": area_name,
            "capabilities": caps,
            "unique_id": f"buspro_{subnet_id}_{device_id}_{channel}_{spk.replace('.', '_')}",
        })

    areas = [{"id": name, "name": name, "floor": floor} for name, floor in areas_map.items()]
    floors = list(floors_set)

    return {
        "gateway": {"ip": "", "port": 6000, "name": "HDL Gateway", "subnet_id": 0, "device_id": 0},
        "floors": floors,
        "areas": areas,
        "devices": devices,
        "scenes": [],
    }


def parse_project_file(data: dict) -> dict:
    """Parse native HDL gateway backup JSON dictionary."""
    gateway = _extract_gateway_info(data)
    floors, areas, zone_lookup = _extract_building_structure(data)
    sid_to_room = _build_sid_to_room(data)
    devices = _extract_devices(data, zone_lookup, sid_to_room)
    scenes = _extract_scenes(data, zone_lookup)

    return {
        "gateway": gateway,
        "floors": floors,
        "areas": areas,
        "devices": devices,
        "scenes": scenes,
    }


def _extract_gateway_info(data: dict) -> dict:
    """Extract gateway connection info from the project file."""
    try:
        device_root = data["myDeviceList"][0]
    except (KeyError, IndexError, TypeError) as err:
        raise HDLParseError("Could not find 'myDeviceList[0]' in the project file.") from err

    ip = device_root.get("IPAddressForConnectTmp", "")
    if not ip:
        ip = device_root.get("DeviceIP", "")

    return {
        "ip": ip,
        "port": 6000,
        "name": device_root.get("Remark", "HDL Gateway"),
        "subnet_id": device_root.get("SubnetID", 0),
        "device_id": device_root.get("DeviceID", 0),
    }


def _extract_building_structure(data: dict) -> tuple[list[str], list[dict], dict[str, str]]:
    """Extract clean HA floors, areas, and zone lookup mapping."""
    building_list = data.get("myBuildingList", [])
    if not building_list:
        return [], [], {}

    guid_info = {b["BuildingGuid"]: b for b in building_list}

    floors = [
        b["Room"].strip()
        for b in building_list
        if b.get("Level", 0) == 0 and b.get("Room")
    ]

    rooms = [b for b in building_list if b.get("Level", 0) > 0 and b.get("Room")]
    room_name_counts = Counter(b["Room"].strip() for b in rooms)

    areas = []
    zone_lookup: dict[str, str] = {}

    for b in rooms:
        guid = b["BuildingGuid"]
        room_name = b["Room"].strip()
        parent_guid = b.get("ParentGuid", "")
        parent_floor = (
            guid_info.get(parent_guid, {}).get("Room", "").strip()
            if parent_guid
            else ""
        )

        if room_name_counts[room_name] > 1 and parent_floor:
            clean_name = f"{parent_floor} {room_name}"
        else:
            clean_name = room_name

        areas.append({
            "id": guid,
            "name": clean_name,
            "floor": parent_floor,
        })
        zone_lookup[guid] = clean_name

    return floors, areas, zone_lookup


def _build_sid_to_room(data: dict) -> dict[str, str]:
    """Build a mapping of device sid -> room BuildingGuid."""
    try:
        device_root = data["myDeviceList"][0]
    except (KeyError, IndexError, TypeError):
        return {}

    sid_to_room: dict[str, str] = {}
    home_bind_objects = device_root.get("myHomeBindList", {}).get("objects", [])
    for entry in home_bind_objects:
        uid = entry.get("uid")
        for fn in entry.get("functions", []):
            sid = fn.get("sid")
            if sid:
                sid_to_room[sid] = uid

    scene_objects = device_root.get("SceneLists", {}).get("objects", [])
    for scene in scene_objects:
        room_guid = scene.get("RoomGuid")
        for fn in scene.get("functions", []):
            sid = fn.get("sid")
            if sid and room_guid and sid not in sid_to_room:
                sid_to_room[sid] = room_guid

    return sid_to_room


def _find_driver_blocks(device_root: dict) -> list[tuple[str, list]]:
    """Find all driver blocks containing device/function entries."""
    found = []
    seen: set[str] = set()

    def qualifies(objects: Any) -> bool:
        if not isinstance(objects, list) or not objects:
            return False
        sample = objects[0]
        return isinstance(sample, dict) and REQUIRED_FUNCTION_FIELDS.issubset(sample.keys())

    for key in KNOWN_DRIVER_KEYS:
        block = device_root.get(key)
        if isinstance(block, dict):
            objects = block.get("objects")
            if qualifies(objects):
                found.append((key, objects))
                seen.add(key)

    for key, block in device_root.items():
        if key in seen or not isinstance(block, dict):
            continue
        objects = block.get("objects")
        if qualifies(objects):
            found.append((key, objects))
            seen.add(key)

    return found


def _extract_devices(
    data: dict,
    zone_lookup: dict[str, str],
    sid_to_room: dict[str, str],
) -> list[dict]:
    """Extract all devices from driver blocks."""
    try:
        device_root = data["myDeviceList"][0]
    except (KeyError, IndexError, TypeError) as err:
        raise HDLParseError("Could not find 'myDeviceList[0]' in the project file.") from err

    driver_blocks = _find_driver_blocks(device_root)
    if not driver_blocks:
        raise HDLParseError(
            "No driver blocks found with device entries. Expected blocks with fields: "
            + ", ".join(sorted(REQUIRED_FUNCTION_FIELDS))
        )

    devices = []
    for _block_name, objects in driver_blocks:
        for obj in objects:
            spk = obj.get("spk", "")
            platform = SPK_TO_PLATFORM.get(spk)
            if platform is None:
                continue

            try:
                subnet_id = int(obj.get("net_id", "0"), 16)
                device_id = int(obj.get("dev_id", "0"), 16)
                channel = int(obj.get("channel", "0"), 16)
            except (TypeError, ValueError):
                continue

            sid = obj.get("sid", "")
            room_guid = sid_to_room.get(sid)
            area_name = zone_lookup.get(room_guid, "") if room_guid else ""

            fn_list = obj.get("function", [])
            capabilities = [f.get("name") for f in fn_list if f.get("name")]

            devices.append({
                "name": obj.get("name", ""),
                "platform": platform,
                "spk": spk,
                "subnet_id": subnet_id,
                "device_id": device_id,
                "channel": channel,
                "area_name": area_name,
                "capabilities": capabilities,
                "unique_id": f"buspro_{subnet_id}_{device_id}_{channel}_{spk.replace('.', '_')}",
            })

    return devices


def _extract_scenes(data: dict, zone_lookup: dict[str, str]) -> list[dict]:
    """Extract scenes from the project file."""
    try:
        device_root = data["myDeviceList"][0]
    except (KeyError, IndexError, TypeError):
        return []

    scene_objects = device_root.get("SceneLists", {}).get("objects", [])
    scenes = []

    for scene in scene_objects:
        name = scene.get("name", "")
        if not name:
            continue

        room_guid = scene.get("RoomGuid", "")
        area_name = zone_lookup.get(room_guid, "")

        functions = []
        for fn in scene.get("functions", []):
            functions.append({
                "sid": fn.get("sid", ""),
                "status": fn.get("status", ""),
                "delay": fn.get("delay", 0),
            })

        scenes.append({
            "name": name,
            "area_name": area_name,
            "functions": functions,
        })

    return scenes


def get_device_summary(parsed_data: dict) -> dict[str, int]:
    """Return a summary count of devices by platform."""
    summary: dict[str, int] = {}
    for device in parsed_data.get("devices", []):
        platform = device["platform"]
        summary[platform] = summary.get(platform, 0) + 1
    return summary
