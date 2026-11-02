# Changelog

## 2.2.0 (unreleased)

### Added
- **HDL Bridge:** control any Home Assistant entity (for example a Tuya light or a Zigbee plug) from an HDL panel button. Home Assistant answers as a virtual HDL device, and the panel's button LED follows the entity's state.
- **Panel button events:** `event` entities and a `buspro_panel_button` event for the commands a panel sends: channel, scene, sequence and universal switch.
- **Scene and sequence buttons** (`button` platform).
- **Tunable-white and RGB / RGBW lights** built from 2–4 dimmer channels.
- **HVAC module climate** on the `0x193A` AC commands, with swing.
- **Floor-heating climate** added from the options flow, with Normal / Day / Night / Away presets.
- **Fans** on relay (on/off) or dimmer / 0-10V (speed %) channels.
- **Gateway search** in the setup flow, and a **bus scan** that reads module names and types and adds the ticked modules.
- **Settings:**
  - gateway-IP filter
  - optional online check (`0xF065`) that marks unresponsive modules unavailable
  - bus monitor (`buspro_telegram` events)
  - experimental features
- **Diagnostics download:** configured devices, bridges, modules seen on the bus, and firmware versions.
- **Experimental raw read sensor:** polls any read command and decodes configured bytes, with power-meter presets. Off by default and not tested on real meters.
- Test suite (pytest) in CI.

### Changed
- The HDL header now carries this machine's IP instead of a fixed `192.168.1.15`.
- Decode errors and CRC failures go to the debug log instead of stdout.
- Several listeners can receive every bus message, and unknown operate codes keep their raw bytes.
- The options flow keeps its settings when devices are added. Before, every options step cleared the stored options.

## 2.1.1
- Pre-existing user areas are left alone on import (no floor change).
- Light transition works: the `TRANSITION` feature flag is set, and the value is rounded to whole seconds.
- `buspro.send_message` accepts a single integer operate code.
