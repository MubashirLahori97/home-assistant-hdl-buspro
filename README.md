# HDL Buspro for Home Assistant (v2.0)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

The HDL Buspro integration allows you to control your HDL Buspro system directly from Home Assistant with **automatic setup via HDL Studio project backup export**.

---

## Features

- **🚀 Automatic Setup**: Upload or point to your HDL gateway backup JSON file (`XXX_Backup_.json` or `.busproj`) — all floors, rooms, lights, curtains, AC units, and switches are automatically imported and assigned to their respective Home Assistant Areas.
- **💡 Lighting**: Full support for standard On/Off switches, dimmable lights, and CCT lights with brightness & fade control.
- **🪟 Curtains & Blinds**: Support for roller shutters and Trietex curtains with position control and real-time state feedback.
- **❄️ Climate / AC**: Complete AC control (modes: Cool, Heat, Fan, Auto, Dry; fan speeds: Auto, High, Med, Low; swing; temperature setpoint).
- **🔌 Switches**: Generic relays and switches.
- **⚡ Local Push**: Operates entirely over local UDP with zero cloud dependency and real-time event updates.

---

## Installation & Setup

1. **Install via HACS**:
   - Under HACS -> Integrations, add this repository as a custom repository (Category: `Integration`).
   - Download "HDL Buspro" and restart Home Assistant.

2. **Configure via UI**:
   - Go to **Settings > Devices & Services > Add Integration** and search for **HDL Buspro**.
   - Provide the path to your HDL Gateway backup JSON file (e.g. `/config/Daim_Raza.json`) or paste its JSON content directly.
   - Confirm your gateway IP and Port (auto-detected from your file).
   - Click Submit — all entities and Areas are created automatically!

---

## Custom Services

You can send arbitrary commands or trigger scenes from Home Assistant automations:

#### 1. Activating a scene:
```yaml
service: buspro.activate_scene
data:
  address: [1, 74]
  scene_address: [3, 5]
```

#### 2. Sending an arbitrary message:
```yaml
service: buspro.send_message
data:
  address: [1, 74]
  operate_code: [4, 78]
  payload: [1, 100, 0, 3]
```

#### 3. Setting a universal switch:
```yaml
service: buspro.set_universal_switch
data:
  address: [1, 74]
  switch_number: 100
  status: 1
```
