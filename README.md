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
| 🔎 **Discovery** | Finds the gateway on your network and scans the bus for modules, with their names. |
| 💡 **Lighting** | On/off, dimmable, tunable-white and RGB / RGBW lights; fade (`transition`); live state. |
| 🪟 **Curtains & blinds** | Open, close, stop, position, live position feedback. |
| ❄️ **Climate** | AC and HVAC modules (mode, setpoint, fan speed, swing) and floor heating with presets. |
| 🔌 **Switches & fans** | HDL relay channels; fans on relay or dimmer / 0-10V channels. |
| 🌡️ **Sensors & wall panels** | Temperature, humidity, illuminance, motion and dry contacts from sensor modules and DLP / Enviro / Granite / Tile panels. |
| 🔘 **Panel buttons & scenes** | Panel button presses as events for automations; scene and sequence buttons. |
| 🔁 **HDL Bridge** | Use an HDL panel button to control non-HDL devices (Tuya, Zigbee, scripts…), with the button LED following their state. |
| 🩺 **Diagnostics** | Online check, bus monitor and a diagnostics download. |
| 🛠️ **Actions** | Run scenes, set universal switches, send raw HDL messages. |
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
   - leave both fields empty. The integration searches your network for HDL gateways and fills in the first one it finds; check the IP and port, then add devices afterwards. **Scan the bus** is the quickest way.

Floors and areas are created **once**, when you complete an import. They are not recreated on restart. Areas you already have with the same name are left alone. You can move entities between areas freely; the integration won't move them back.

### Adding or updating devices later

Open the integration's **Configure** menu:

| Menu item | What it does |
|---|---|
| **Add Device or Sensor Manually** | Pick the type, then enter the address as subnet, device and channel (or switch / AC number). |
| **Add Scene or Sequence Button** | A button entity that runs a scene or sequence stored in a module. |
| **Add Tunable-White / RGB Light** | Combine 2–4 dimmer channels into one colour light. |
| **Control a Non-HDL Device from an HDL Panel** | Set up the [HDL Bridge](#-hdl-bridge-control-non-hdl-devices-from-hdl-panels). |
| **Remove Bridged Devices** | Remove HDL Bridge entries. |
| **Scan the Bus for Modules** | Find modules and add the ones you tick ([Discovery](#-discovery)). |
| **Import / Update from File** | Re-import an updated HDL Studio export. |
| **Settings** | Gateway-IP filter, online check, bus monitor, experimental features ([Settings](#%EF%B8%8F-settings-availability--diagnostics)). |

---

## 💡 Lighting

- On/off and dimmable lights, with brightness.
- **Fade**: the `transition` option on `light.turn_on` / `light.turn_off` sets the HDL running time in whole seconds.
- Live state from the bus, including changes made from panels.

**Tunable-white and RGB / RGBW lights.** HDL has no colour command: each colour is its own dimmer or LED-driver channel. Use **Configure → Add Tunable-White / RGB Light** to combine the channels of one light:

- **Tunable white:** two channels, warm then cool. You get colour temperature (default 2700–6500 K, adjustable) and brightness.
- **RGB:** three channels (red, green, blue). **RGBW:** four (red, green, blue, white).

The light sets all its channels together and rebuilds its state from their status replies, so changes made from a panel show up too.

> CCT lights in an HDL Studio import come in as dimmable lights with brightness only, because the export names one channel per light. Add them as a tunable-white light to get colour temperature.

## 🪟 Curtains & blinds

Open, close, stop and position, with live position feedback.

## ❄️ Climate

Three climate types, chosen in **Add Device or Sensor Manually**:

| Type | For | Features |
|---|---|---|
| **Climate (AC)** | AC modules on the `0xE0EA` / `0xE0EC` commands. This is the type the HDL Studio import creates. | Modes: off, cool, heat, fan only, auto, dry. Setpoint 16–32 °C. Fan: auto / high / medium / low. Swing. |
| **Climate (HVAC module, with swing)** | HDL HVAC modules (M/HVAC, MPED, MAC, IR AC emitters) on the `0x193A` AC command. Enter the AC number as the channel. | The same modes and fan speeds, a setpoint per mode, and swing. |
| **Climate (Floor heating)** | DLP / heating-module floor heating. | Heat / off, setpoint, Normal / Day / Night / Away as presets. |

## 🔌 Switches & fans

- Generic HDL relay channels as switches.
- **Fan (Relay channel):** on/off.
- **Fan (Dimmer / 0-10V channel):** the channel level is the fan speed in percent.

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

## 🔘 Panel buttons, scenes & sequences

**Panel button events.** HDL panels don't send a "button pressed" message; each button sends the command it is programmed with to its target. Add a panel with **Add Device or Sensor Manually → Panel button events** (or **Scan the bus**). Every command the panel sends then updates an `event` entity and fires a `buspro_panel_button` event:

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

**Scene and sequence buttons.** **Configure → Add Scene or Sequence Button** creates a `button` entity that runs a scene or sequence stored in an HDL module. Enter the module address and the area and scene / sequence numbers, as shown in HDL Buspro Setup Tool.

---

## 🔁 HDL Bridge: control non-HDL devices from HDL panels

Use an HDL panel button to control a device that is **not** HDL, such as a Tuya light, a Zigbee plug or a script, and have the button's LED show its real state.

Home Assistant answers on the bus as a **virtual HDL device** at an address no real module uses. A panel button pointed at that address reaches Home Assistant, which drives the chosen entity and replies like a real module.

1. **Configure → Control a Non-HDL Device from an HDL Panel.**
2. Pick the entity, what the button sends, and the virtual address:
   - **Universal switch:** on / off.
   - **Relay channel:** on / off.
   - **Dimmer channel:** level 0–100 sets brightness (light), position (cover) or speed (fan).

   The address must not be used by a real module; the form refuses addresses it has seen on the bus. Device IDs 200–254 are usually free.
3. In **HDL Buspro Setup Tool**, program the panel button to target that address with the same universal switch or channel number.

What happens:

- **Button press:** Home Assistant turns the entity on/off or sets its level, and sends the reply a real module would send.
- **Status requests:** panels that ask for the virtual device's status get the entity's current state.
- **Changes from elsewhere** (Tuya app, voice assistant, automation): Home Assistant announces the new state on the bus, so the panel LEDs follow.

Limits:

- It works only while Home Assistant is running.
- Cloud-based Tuya devices respond with cloud delay; local Tuya integrations are faster.

If you only need a button to trigger something, with no LED feedback, a panel button event plus an automation is simpler.

---

## 🔎 Discovery

- **Gateway search:** when you set up without a project file, the integration searches your network for HDL gateways and fills in the first one found.
- **Bus scan:** **Configure → Scan the Bus for Modules** asks every module for its name and type, and lists the new ones. The modules you tick are added as follows:

| Module | Added as |
|---|---|
| Relay | Lights or switches (your choice), named from the channel names stored in the module |
| Dimmer | Dimmable lights |
| Panel | Button events and a temperature sensor |
| 12-in-1, 8-in-1, Sensors-in-One | Their sensors |
| Dry contact | One binary sensor per input |

Modules of an unknown type are listed but add nothing; add them manually.

---

## ⚙️ Settings, availability & diagnostics

**Configure → Settings:**

| Setting | What it does |
|---|---|
| Only accept messages from the gateway's IP | Drops UDP frames from any other sender. Leave off on sites with several gateways. |
| Check modules are online every N seconds | Sends HDL's "is device online" command (`0xF065`) to every configured module. Entities of a module that doesn't answer become *unavailable*. 0 turns it off. |
| Bus monitor | Fires a `buspro_telegram` event for every message on the bus, with source, target, device type, operate code and payload. Useful for finding out what a button sends, or how an unsupported module's replies are laid out. Watch it in **Developer tools → Events**. |
| Enable experimental features | Turns on the raw read sensor below. |

**Diagnostics:** **Settings → Devices & services → HDL Buspro → ⋮ → Download diagnostics** gives you:

- the gateway settings
- configured devices and bridged entities
- modules seen on the bus, with their device type and last-seen time
- the firmware version of each configured module that is talking on the bus

---

## 🧪 Experimental: raw read sensors (energy meters)

> **Not tested on real hardware.** Turn on *Enable experimental features* in Settings to use it.

HDL's command list names power-meter reads (voltage `0xD902`, power factor `0xD904`, current `0xD908`, power `0xD90A`, energy `0xD91A`), but no public source documents how their replies are laid out. Rather than guess, the **raw read sensor** polls any read command and decodes the bytes you specify:

1. Turn on the **bus monitor**. Send the read command with `buspro.send_message`, and note the reply's payload in **Developer tools → Events**.
2. **Configure → Add Raw Read Sensor (experimental)**: pick a power-meter preset, which fills in the command, unit and sensor type. Then set:
   - the reply byte where the value starts
   - its length
   - its byte order and sign
   - a scale, such as `0.1`
3. The *energy* preset creates a `total_increasing` kWh sensor, which can be added to the Energy dashboard.

Each reading also shows the raw reply as the `raw_payload` attribute. If you work out a meter's layout, please open an issue so it can become a supported device type.

Security modules (SEC250K) and Z-Audio / SD audio are not supported: their command layouts aren't publicly documented either.

---

## 🏠 Entities

| HDL device | Home Assistant entity |
|---|---|
| Lighting (on/off, dimmable, tunable white, RGB / RGBW) | Light |
| Relay | Switch |
| Fan on a relay or dimmer / 0-10V channel | Fan |
| Curtain / blind | Cover |
| AC / HVAC / floor heating | Climate |
| Panel buttons | Event |
| Scenes and sequences | Button |
| Power meters (experimental raw read) | Sensor |
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

**Find out what a button or module sends.** Turn on the **bus monitor** in Settings and watch `buspro_telegram` in **Developer tools → Events**.

**Debug logging.** Add this to `configuration.yaml` and restart:

```yaml
logger:
  default: warning
  logs:
    custom_components.buspro: debug
    buspro.telegram: debug   # every message on the bus
```

**Report a problem.** Open an [issue](https://github.com/MubashirLahori97/home-assistant-hdl-buspro/issues) with your Home Assistant version, the device type and address, the debug log, and ideally the diagnostics download.

---

## 📄 License

[MIT](LICENSE)
