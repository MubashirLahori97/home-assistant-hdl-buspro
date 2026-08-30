# HDL Buspro Home Assistant Integration

[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A Home Assistant integration for **HDL Buspro** systems, providing local control and monitoring of HDL devices directly from Home Assistant.

The integration is designed to simplify HDL Buspro setup by using an **HDL Studio project backup/export** to automatically discover and configure devices, rooms, and areas.

---

## ✨ Features

### 🚀 Automatic Setup

Import your HDL Buspro installation using an HDL Studio project backup/export.

The integration can use the project information to automatically discover and configure:

- Floors
- Rooms
- Areas
- Lights
- Curtains and blinds
- AC / climate units
- Switches
- Other supported HDL devices

This reduces the need to manually configure individual HDL devices in Home Assistant.

---

### 💡 Lighting

Support for HDL lighting devices, including:

- On/Off lights
- Dimmable lights
- Brightness control
- CCT lights
- Fade control
- Real-time state updates

---

### 🪟 Curtains & Blinds

Control supported HDL Buspro curtain and blind devices from Home Assistant.

Supported functionality includes:

- Open
- Close
- Stop
- Position control
- Real-time position/state feedback

---

### ❄️ Climate / AC

Control supported HDL Buspro HVAC/AC devices directly from Home Assistant.

Supported functionality includes:

- Cool
- Heat
- Fan
- Auto
- Dry
- Temperature setpoint
- Fan speed
- Auto
- High
- Medium
- Low
- Swing control

---

### 🔌 Switches

Support for generic HDL Buspro relay and switch devices.

---

### ⚡ Local Communication

The integration communicates directly with the HDL Buspro system over the local network.

- No cloud service required
- Local UDP communication
- Real-time event updates
- Low-latency control
- Works without an external HDL cloud service

---

## 📦 Installation

### HACS

After approval, the integration will be available in the HACS default repository and can be installed directly from:

**HACS → Integrations → HDL Buspro**

During development, you can install it as a custom repository:

1. Open **HACS**.
2. Go to **Integrations**.
3. Select the three-dot menu.
4. Select **Custom repositories**.
5. Add:

   `https://github.com/MubashirLahori97/home-assistant-hdl-buspro`

6. Select **Integration** as the category.
7. Click **Add**.
8. Install **HDL Buspro**.
9. Restart Home Assistant.

You can also use the [My Home Assistant HACS link](https://my.home-assistant.io/create-link/?redirect=hacs_repository&repository=MubashirLahori97%2Fhome-assistant-hdl-buspro) to add this repository.

### Requirements

- Home Assistant with access to the HDL Buspro IP gateway over UDP.
- An HDL Studio export or backup in JSON, CSV, or XLSX format for automatic setup. The file must be available to Home Assistant, for example under `/config`.
- The `openpyxl` dependency is installed automatically when XLSX parsing is used.

---

## ⚙️ Configuration

After installation:

1. Go to **Settings**.
2. Select **Devices & services**.
3. Click **Add Integration**.
4. Search for **HDL Buspro**.
5. Follow the configuration flow.

The integration can use an HDL Gateway project backup/export to automatically configure the installation.

Depending on the exported project, the configuration can include:

- Gateway information
- Floors
- Rooms
- Areas
- Devices
- Device addresses
- Device types

The gateway IP address and port can be obtained from the imported project information when available.

---

## 🏠 Home Assistant Entities

Supported HDL Buspro devices are exposed as native Home Assistant entities.

| HDL Device | Home Assistant Entity |
|---|---|
| Lighting | Light |
| Switch / Relay | Switch |
| Curtain / Blind | Cover |
| AC / HVAC | Climate |
| Sensors | Sensor / Binary Sensor |

The exact entities created depend on the devices present in the HDL Buspro project.

---

# 🛠️ Custom Services

The integration also provides services for advanced HDL Buspro control.

These services can be used from Home Assistant automations, scripts, and developer tools.

---

## Activate a Scene

Service:

```yaml
service: buspro.activate_scene
data:
  address: [1, 74]
  scene_address: [3, 5]
