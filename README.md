# HDL Buspro Home Assistant Integration
HDL Buspro integration for Home Assistant
Home Assistant integration for HDL Smart Bus / Buspro
Control HDL Buspro lights, curtains, climate, and switches from Home Assistant

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
- Fade control (supports the `transition` option on turn on / turn off)
- Real-time state updates

> Note: CCT (tunable white) lights in an HDL Studio import come in as dimmable
> lights with brightness only, because the export names one channel per light.

**Tunable-white and RGB / RGBW lights.** HDL has no colour command: each colour
is its own dimmer or LED-driver channel. Use **Configure → Add Tunable-White / RGB
Light** to combine the channels of one light:

- Tunable white: two channels, warm then cool. Home Assistant gets colour
  temperature (default range 2700 K – 6500 K, adjustable) and brightness.
- RGB: three channels (red, green, blue). RGBW: four (red, green, blue, white).

The light sets all of its channels together and rebuilds its state from the
channels' status replies, so changes made from a panel show up too.

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

Three climate types can be added from **Configure → Add device**:

- **Climate (AC)**: AC modules that use the `0xE0EA` / `0xE0EC` AC commands (the type the HDL Studio import creates).
- **Climate (HVAC module, with swing)**: HDL HVAC modules (M/HVAC, MPED, MAC, IR AC emitters) on the `0x193A` AC control command. Covers mode, fan speed, per-mode setpoints and swing. Enter the AC number as the channel.
- **Climate (Floor heating)**: DLP / heating-module floor heating, with Normal / Day / Night / Away as presets.

---

### 🔌 Switches & Fans

Support for generic HDL Buspro relay and switch devices.

Fans can be added from **Configure → Add device**:

- **Fan (Relay channel)**: on/off.
- **Fan (Dimmer / 0-10V channel)**: the channel level is the fan speed in percent.

---

### 🔘 Panel Buttons, Scenes & Sequences

**Panel button events.** HDL panels do not send a "button pressed" message;
each button sends the command it is programmed with to its target. Add a panel
with **Configure → Add device → Panel button events** (or **Scan the bus**), and the
integration turns every command the panel sends into an `event` entity update
and a `buspro_panel_button` event:

| Event type | When | Extra data |
|---|---|---|
| `channel_on` / `channel_off` | the button switches or dims a channel | `target_address`, `channel`, `level` |
| `scene` | the button runs a scene | `target_address`, `area`, `scene` |
| `sequence` | the button runs a sequence | `target_address`, `area`, `sequence` |
| `universal_switch_on` / `_off` | the button sets a universal switch | `target_address`, `switch` |

A button programmed with several targets produces one event per target.

```yaml
automation:
  - triggers:
      - trigger: event
        event_type: buspro_panel_button
        event_data:
          panel_address: [1, 25]
          type: universal_switch_on
          switch: 7
    actions:
      - action: light.turn_on
        target:
          entity_id: light.tuya_lamp
```

**Scene and sequence buttons.** **Configure → Add Scene or Sequence Button**
creates a `button` entity that runs a scene or sequence stored in an HDL module
(module address, area number, scene/sequence number, as in HDL Buspro Setup Tool).

---

### 🔁 Control Non-HDL Devices from HDL Panels (HDL Bridge)

Use an HDL panel button to control a device that is **not** HDL, such as a Tuya
light, a Zigbee plug or a script, and have the button's LED show its real state.

Home Assistant answers on the bus as a **virtual HDL device** at an address no
real module uses. A panel button pointed at that address reaches Home
Assistant, which drives the chosen entity and replies like a real module.

1. **Configure → Control a Non-HDL Device from an HDL Panel.**
2. Pick the entity, what the button sends, and the virtual address:
   - **Universal switch**: on/off.
   - **Relay channel**: on/off.
   - **Dimmer channel**: level 0–100 sets brightness (light), position (cover) or speed (fan).

   The virtual address must not be used by a real module; the form refuses addresses
   it has seen on the bus. Device IDs 200–254 are usually free.
3. In **HDL Buspro Setup Tool**, program the panel button to target that address
   with the same universal switch or channel number.

What happens:

- Button press → Home Assistant turns the entity on/off or sets its level, and
  sends the reply a real module would send.
- Panels that ask for the status of the virtual address get the entity's current state.
- When the entity changes outside HDL (Tuya app, voice assistant, automation),
  Home Assistant announces the new state on the bus so panel LEDs follow.

Limits:

- It only works while Home Assistant is running.
- Cloud-based Tuya devices react with cloud delay; local Tuya integrations are faster.

If you only need a button to trigger something (no LED feedback), a
**panel button event** with an automation is simpler.

---

### 🌡️ Sensors & Wall Panels

Sensor support for HDL sensor modules and wall panels with built-in sensors:

- **Temperature, illuminance, motion and dry contacts** from HDL sensor modules (including the 8-in-1 / 12-in-1 and Sensors-in-One modules; the Sensors-in-One status reply also provides **humidity** and lux).
- **Wall panels** — the DLP family, **Enviro** (HDL-MPTLC43), **Granite Display** (HDL-MPTL4C) and the **Tile** climate/multifunction panels expose their built-in **temperature** sensor. Panels that carry a humidity sensor (Granite Display, Tile climate panels) also expose **humidity**.
- Panel temperature is read with the panel's channel-addressed temperature command and from its temperature broadcasts, including the fractional (float) value — panel readings are *not* offset-corrected like the sensor modules.

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

The AC and floor-heating pages of these panels drive the AC / floor-heating modules on the bus; control those from the module's climate entity, as before.

---

### ⚡ Local Communication

The integration communicates directly with the HDL Buspro system over the local network.

- No cloud service required
- Local UDP communication
- Real-time event updates
- Low-latency control
- Works without an external HDL cloud service

---

### 🔎 Discovery

- **Gateway search**: when you set up the integration without a project file,
  it searches the network for HDL gateways and fills in the first one found.
- **Bus scan**: **Configure → Scan the Bus for Modules** asks every module for
  its name and type and lists the new ones. Ticked modules are added:
  - Relay channels become lights or switches (your choice), named from the channel names stored in the modules.
  - Dimmer channels become dimmable lights.
  - Panels get button events and a temperature sensor.
  - 12-in-1, 8-in-1 and Sensors-in-One modules get their sensors.
  - Dry-contact modules get one binary sensor per input.

  Modules of an unknown type are listed but add nothing; add them manually.

---

### ⚙️ Settings, Availability & Diagnostics

**Configure → Settings**:

| Setting | What it does |
|---|---|
| Only accept messages from the gateway's IP | Drops UDP frames from any other sender. Leave off on sites with several gateways. |
| Check modules are online every N seconds | Sends HDL's "is device online" command (`0xF065`) to every configured module. Entities of a module that does not answer become *unavailable*. 0 turns it off. |
| Bus monitor | Fires a `buspro_telegram` event for every message on the bus: source, target, device type, operate code and payload. Useful for finding out what a button sends, or the layout of an unsupported module's replies. Watch it in **Developer tools → Events**. |
| Enable experimental features | Turns on the raw read sensor below. |

**Diagnostics**: **Settings → Devices & services → HDL Buspro → ⋮ → Download diagnostics**
gives the gateway settings, configured devices, bridged entities, the modules
seen on the bus with their device type and last-seen time, and the firmware
version of each configured module that is talking on the bus.

---

### 🧪 Experimental: Raw Read Sensors (Energy Meters)

> **Not tested on real hardware.** Turn on *Enable experimental features* in
> Settings to use it.

HDL's command list names power-meter reads (voltage `0xD902`, power factor
`0xD904`, current `0xD908`, power `0xD90A`, energy `0xD91A`), but no public
source documents the layout of their replies. Instead of guessing, the
**raw read sensor** polls any read command and decodes the bytes you tell it to:

1. Turn on the **bus monitor**, then send the read command with
   `buspro.send_message` and note the reply's payload in Developer tools → Events.
2. **Configure → Add Raw Read Sensor**: pick a power-meter preset, which fills in the command, unit and sensor type. Then set:
   - which reply byte the value starts at
   - its length
   - its byte order and sign
   - a scale, for example `0.1`
3. The *energy* preset creates a `total_increasing` kWh sensor, which can be added to the Energy dashboard.

Every reading also shows the raw reply as the `raw_payload` attribute. If you
work out a meter's layout, please open an issue so it can become a supported
device type.

Security modules (SEC250K) and Z-Audio / SD audio are not supported: their
command layouts are not publicly documented either.

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
| Tunable-white / RGB / RGBW channel groups | Light (colour temperature / colour) |
| Switch / Relay | Switch |
| Fan on a relay or dimmer / 0-10V channel | Fan |
| Curtain / Blind | Cover |
| AC / HVAC / floor heating | Climate |
| Panel buttons | Event |
| Scenes and sequences | Button |
| Power meters (experimental raw read) | Sensor |
| Sensors (temperature, humidity, illuminance, motion, dry contact) | Sensor / Binary Sensor |
| Wall panels (DLP, Enviro, Granite Display, Tile) built-in sensors | Sensor (temperature, humidity) |

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
```

- `address`: HDL device address as `[subnet_id, device_id]`.
- `scene_address`: scene address as `[subnet_id, scene_number]`.

---

## Send a Raw Message

Service:

```yaml
service: buspro.send_message
data:
  address: [1, 74]
  operate_code: 49
  payload: [1]
```

- `address`: HDL device address as `[subnet_id, device_id]`.
- `operate_code`: HDL Buspro operate code (integer).
- `payload`: payload bytes as a list of integers.

---

## Set a Universal Switch

Service:

```yaml
service: buspro.set_universal_switch
data:
  address: [1, 74]
  switch_number: 9
  status: 1
```

- `address`: HDL device address as `[subnet_id, device_id]`.
- `switch_number`: universal switch number (integer).
- `status`: `1` for on, `0` for off.
