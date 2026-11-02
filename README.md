# HDL Buspro for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Release](https://img.shields.io/github/v/release/MubashirLahori97/home-assistant-hdl-buspro)](https://github.com/MubashirLahori97/home-assistant-hdl-buspro/releases)
[![Validate](https://github.com/MubashirLahori97/home-assistant-hdl-buspro/actions/workflows/validate.yml/badge.svg)](https://github.com/MubashirLahori97/home-assistant-hdl-buspro/actions/workflows/validate.yml)

Local control of **HDL Buspro** (HDL Smart Bus) lights, curtains, climate, switches and sensors from Home Assistant. Home Assistant talks to the HDL IP gateway directly over UDP on your network, with no cloud service.

Import your **HDL Studio project backup or export** and the integration sets up your floors, rooms and devices for you.

---

## ✨ Features at a glance

| | |
|---|---|
| 🚀 **Automatic setup** | Import an HDL Studio export (JSON, CSV or XLSX): floors, rooms, areas and devices are created in one step. |
| 💡 **Lighting** | On/off and dimmable lights, brightness, fade (`transition`), live state. |
| 🪟 **Curtains & blinds** | Open, close, stop, position, live position feedback. |
| ❄️ **Climate / AC** | Cool, heat, fan, auto and dry modes; setpoint; fan speed; swing. |
| 🔌 **Switches** | HDL relay channels. |
| 🌡️ **Sensors & wall panels** | Temperature, humidity, illuminance, motion and dry contacts from sensor modules and DLP / Enviro / Granite / Tile panels. |
| 🛠️ **Services** | Run scenes, set universal switches, send raw HDL messages. |
| ⚡ **Local push** | Real-time updates from the bus, low latency, no cloud. |

---

## 📦 Installation

### HACS (recommended)

The integration is waiting for review to join the HACS default list. Until then, add it as a custom repository:

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=MubashirLahori97&repository=home-assistant-hdl-buspro&category=integration)

Or by hand:

1. Open **HACS** in Home Assistant.
2. Open the **⋮** menu (top right) → **Custom repositories**.
3. Add `https://github.com/MubashirLahori97/home-assistant-hdl-buspro` with type **Integration**.
4. Search for **HDL Buspro** in HACS and click **Download**.
5. Restart Home Assistant.

### Manual

Copy `custom_components/buspro` into your Home Assistant `config/custom_components/` folder and restart Home Assistant.

### Requirements

- Home Assistant must reach the HDL IP gateway over **UDP port 6000**, and receive the gateway's UDP broadcasts on that port. In Docker, this means host networking.
- For automatic setup: an HDL Studio backup or export in JSON, CSV or XLSX format, placed where Home Assistant can read it (for example `/config`). You can also paste its content into the setup form.
- `openpyxl` is installed automatically for XLSX files.

---

## ⚙️ Configuration

1. Go to **Settings → Devices & services → Add integration**.
2. Search for **HDL Buspro**.
3. Either:
   - enter the path to your HDL Studio export (or paste its content). The integration reads the gateway address, floors, rooms and devices from it, and shows a summary to confirm. Or:
   - leave both fields empty to enter the gateway IP and port yourself, and add devices afterwards.

Floors and areas are created **once**, when you complete an import. They are not recreated on restart. Areas you already have with the same name are left alone. You can move entities between areas freely; the integration won't move them back.

### Adding or updating devices later

Open the integration's **Configure** menu:

- **Add Device or Sensor Manually**: pick the type, then enter the address as subnet, device and channel (or switch number).
- **Import / Update from File**: re-import an updated HDL Studio export.

---

## 💡 Lighting

- On/off and dimmable lights, with brightness.
- **Fade**: the `transition` option on `light.turn_on` / `light.turn_off` sets the HDL running time in whole seconds.
- Live state from the bus, including changes made from panels.

> CCT (tunable white) lights come in from an HDL Studio import as **dimmable lights with brightness only**. Colour temperature is not supported in this release.

## 🪟 Curtains & blinds

Open, close, stop and position, with live position feedback.

## ❄️ Climate / AC

- **Modes:** off, cool, heat, fan only, auto, dry.
- **Target temperature:** 16–32 °C in 1 °C steps.
- **Fan speed:** auto, high, medium, low.
- **Swing:** on / off.

## 🔌 Switches

Generic HDL relay channels as switches.

## 🌡️ Sensors & wall panels

- **Sensor modules:** temperature, illuminance, motion and dry contacts from HDL sensor modules, including the 8-in-1, 12-in-1 and Sensors-in-One. The Sensors-in-One also provides **humidity**.
- **Wall panels:** the DLP family, **Enviro** (HDL-MPTLC43), **Granite Display** (HDL-MPTL4C) and the **Tile** climate / multifunction panels expose their built-in **temperature**. Panels with a humidity sensor (Granite Display, Tile climate panels) also expose **humidity**.
- Panel temperature is read with the panel's channel-addressed temperature command and from its temperature broadcasts, including the decimal part. Panel readings are *not* offset-corrected like the sensor modules.

Add a panel's sensors from **Configure → Add device** and choose a *Panel Sensor* type, or in YAML:

```yaml
sensor:
  - platform: buspro
    devices:
      - address: "1.25"
        name: "Living Room Panel Temperature"
        type: temperature
        device: panel
      - address: "1.25"
        name: "Living Room Panel Humidity"
        type: humidity
        device: panel
```

The AC and floor-heating pages of these panels drive the AC / floor-heating modules on the bus; control those from the module's climate entity.

---

## 🏠 Entities

| HDL device | Home Assistant entity |
|---|---|
| Lighting (on/off, dimmable) | Light |
| Relay | Switch |
| Curtain / blind | Cover |
| AC / HVAC | Climate |
| Sensor modules (temperature, humidity, illuminance) | Sensor |
| Sensor modules (motion, dry contact), universal switch status | Binary sensor |
| Wall panels (DLP, Enviro, Granite Display, Tile) | Sensor (temperature, humidity) |

The entities you get depend on the devices in your HDL project.

---

## 🛠️ Actions (services)

Use these from automations, scripts and **Developer tools → Actions**.

### `buspro.activate_scene`

Run a scene stored in an HDL module.

```yaml
action: buspro.activate_scene
data:
  address: [1, 74]
  scene_address: [3, 5]
```

- `address`: the module that holds the scene, as `[subnet_id, device_id]`.
- `scene_address`: `[area_number, scene_number]`, as numbered in HDL Buspro Setup Tool.

### `buspro.set_universal_switch`

```yaml
action: buspro.set_universal_switch
data:
  address: [1, 74]
  switch_number: 9
  status: 1
```

- `address`: target device as `[subnet_id, device_id]`.
- `switch_number`: universal switch number.
- `status`: `1` for on, `0` for off.

### `buspro.send_message`

Send any HDL Buspro message. For advanced use.

```yaml
action: buspro.send_message
data:
  address: [1, 74]
  operate_code: 49      # 0x0031, single channel control
  payload: [1, 100, 0, 0]
```

- `address`: target device as `[subnet_id, device_id]`.
- `operate_code`: the HDL operate code as an integer (for example `49` = `0x0031`).
- `payload`: the payload bytes as a list of integers. For `0x0031` the bytes are channel, level 0–100, then running time as minutes and seconds.

---

## 🧰 Troubleshooting

**Nothing updates, or devices stay unavailable.**
- Check that Home Assistant can reach the gateway IP on UDP port 6000.
- Check that it receives broadcasts on that port: in Docker, use `network_mode: host`.
- Check that no other program on the same host is bound to UDP port 6000.

**Debug logging.** Add this to `configuration.yaml` and restart:

```yaml
logger:
  default: warning
  logs:
    custom_components.buspro: debug
    buspro.telegram: debug   # every message on the bus
```

**Report a problem.** Open an [issue](https://github.com/MubashirLahori97/home-assistant-hdl-buspro/issues) with your Home Assistant version, the device type and address, and the debug log.

---

## 🗺️ Roadmap

The next version (2.2.0) is in development on the [`dev` branch](https://github.com/MubashirLahori97/home-assistant-hdl-buspro/tree/dev). **None of these features are in the current release.**

- **Control non-HDL devices from HDL panels:** Home Assistant answers as a virtual HDL device, so a panel button can switch, for example, a Tuya light, and the button LED follows its state.
- **Panel button events:** use any panel button to trigger automations.
- Scene and sequence buttons.
- Tunable-white and RGB / RGBW lights.
- HVAC modules with swing, floor heating from the setup UI, and fans.
- Gateway search and a scan that finds modules on the bus.
- Online check, a bus monitor and diagnostics.

See [CHANGELOG.md on `dev`](https://github.com/MubashirLahori97/home-assistant-hdl-buspro/blob/dev/CHANGELOG.md) for the full list.

---

## 📄 License

[MIT](LICENSE)
