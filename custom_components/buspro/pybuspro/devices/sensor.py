import asyncio
import struct

# from ..helpers.generics import Generics
from .control import _ReadSensorStatus, _ReadStatusOfUniversalSwitch, _ReadStatusOfChannels, _ReadFloorHeatingStatus, \
    _ReadDryContactStatus, _ReadSensorsInOneStatus, _ReadTemperature, _GenericControl
from .device import Device
from ..helpers.enums import *

# Analog value type for relative humidity in ReadAnalogValue requests.
ANALOG_TYPE_HUMIDITY = 0x45


class Sensor(Device):
    def __init__(self, buspro, device_address, universal_switch_number=None, channel_number=None, device=None,
                 switch_number=None, name="", delay_read_current_state_seconds=0,
                 temperature_channel=1, read_humidity=False):
        super().__init__(buspro, device_address, name)

        self._buspro = buspro
        self._device_address = device_address
        self._universal_switch_number = universal_switch_number
        self._channel_number = channel_number
        self._name = name
        self._device = device
        self._switch_number = switch_number
        # Wall panels (device="panel": DLP family, Enviro, Granite Display,
        # Tile climate panels) report temperature per channel and can be
        # polled for humidity instead of temperature.
        self._temperature_channel = temperature_channel
        self._read_humidity = read_humidity

        self._current_temperature = None
        self._current_humidity = None
        self._temperature_precise = None
        self._temperature_from_panel = False
        self._brightness = None
        self._motion_sensor = None
        self._sonic = None
        self._dry_contact_1_status = None
        self._dry_contact_2_status = None
        self._universal_switch_status = OnOffStatus.OFF
        self._channel_status = 0
        self._switch_status = 0

        self.register_telegram_received_cb(self._telegram_received_cb)
        self._call_read_current_status_of_sensor(run_from_init=True)

    def _telegram_received_cb(self, telegram):
        if telegram.operate_code == OperateCode.ReadSensorStatusResponse:
            success_or_fail = telegram.payload[0]
            self._current_temperature = telegram.payload[1]
            brightness_high = telegram.payload[2]
            brightness_low = telegram.payload[3]
            self._motion_sensor = telegram.payload[4]
            self._sonic = telegram.payload[5]
            self._dry_contact_1_status = telegram.payload[6]
            self._dry_contact_2_status = telegram.payload[7]
            if success_or_fail == SuccessOrFailure.Success.value[0]:
                self._brightness = (brightness_high << 8) | brightness_low
                self._call_device_updated()

        elif telegram.operate_code == OperateCode.ReadSensorsInOneStatusResponse:
            self._current_temperature = telegram.payload[1]
            self._temperature_from_panel = False
            self._temperature_precise = None
            if len(telegram.payload) >= 4:
                self._brightness = (telegram.payload[2] << 8) | telegram.payload[3]
            if len(telegram.payload) >= 5:
                # 0xFF means no humidity sensor is fitted to the module.
                humidity = telegram.payload[4]
                self._current_humidity = None if humidity == 0xFF else humidity
            self._motion_sensor = telegram.payload[7]
            self._dry_contact_1_status = telegram.payload[8]
            self._dry_contact_2_status = telegram.payload[9]
            self._call_device_updated()

        elif telegram.operate_code == OperateCode.BroadcastSensorStatusResponse:
            self._current_temperature = telegram.payload[0]
            brightness_high = telegram.payload[1]
            brightness_low = telegram.payload[2]
            self._motion_sensor = telegram.payload[3]
            self._sonic = telegram.payload[4]
            self._dry_contact_1_status = telegram.payload[5]
            self._dry_contact_2_status = telegram.payload[6]
            self._brightness = (brightness_high << 8) | brightness_low
            self._call_device_updated()

        elif telegram.operate_code == OperateCode.BroadcastSensorStatusAutoResponse:
            self._current_temperature = telegram.payload[0]
            if self._device == "12in1":
                self._current_temperature = self._current_temperature - 20
            
            brightness_high = telegram.payload[1]
            brightness_low = telegram.payload[2]
            self._motion_sensor = telegram.payload[3]
            self._sonic = telegram.payload[4]
            self._dry_contact_1_status = telegram.payload[5]
            self._dry_contact_2_status = telegram.payload[6]
            self._brightness = (brightness_high << 8) | brightness_low
            self._call_device_updated()

        elif telegram.operate_code == OperateCode.ReadFloorHeatingStatusResponse:
            self._current_temperature = telegram.payload[1]
            self._call_device_updated()

        elif telegram.operate_code == OperateCode.BroadcastTemperatureResponse:
            # Panel temperature broadcast: [channel, whole degrees,
            # float32 little-endian degrees]. Panels report the real
            # value, not the +20 biased encoding of the sensor modules.
            if self._device == "panel" and telegram.payload \
                    and telegram.payload[0] != self._temperature_channel:
                pass
            elif self._store_panel_temperature(telegram.payload):
                self._call_device_updated()

        elif telegram.operate_code == OperateCode.ReadTemperatureResponse:
            # Answer to a channel-addressed panel temperature read; panels
            # reply on every channel they own, so only accept ours.
            if telegram.payload and telegram.payload[0] == self._temperature_channel:
                if self._store_panel_temperature(telegram.payload):
                    self._call_device_updated()

        elif telegram.operate_code == OperateCode.ReadAnalogValueResponse:
            # Generic analog value reply: payload[0] names the value type;
            # relative humidity (0x45) carries its value at payload[2].
            if len(telegram.payload) >= 3 \
                    and telegram.payload[0] == ANALOG_TYPE_HUMIDITY \
                    and 0 <= telegram.payload[2] <= 100:
                self._current_humidity = telegram.payload[2]
                self._call_device_updated()

        elif telegram.operate_code == OperateCode.ReadStatusOfUniversalSwitchResponse:
            switch_number = telegram.payload[0]
            universal_switch_status = telegram.payload[1]

            if switch_number == self._universal_switch_number:
                self._universal_switch_status = universal_switch_status
                self._call_device_updated()

        elif telegram.operate_code == OperateCode.BroadcastStatusOfUniversalSwitch:
            if self._universal_switch_number is not None and self._universal_switch_number <= telegram.payload[0]:
                self._universal_switch_status = telegram.payload[self._universal_switch_number]
                self._call_device_updated()

        elif telegram.operate_code == OperateCode.UniversalSwitchControlResponse:
            switch_number = telegram.payload[0]
            universal_switch_status = telegram.payload[1]

            if switch_number == self._universal_switch_number:
                self._universal_switch_status = universal_switch_status
                self._call_device_updated()

        elif telegram.operate_code == OperateCode.ReadStatusOfChannelsResponse:
            if self._channel_number <= telegram.payload[0]:
                self._channel_status = telegram.payload[self._channel_number]
                self._call_device_updated()

        elif telegram.operate_code == OperateCode.SingleChannelControlResponse:
            if self._channel_number == telegram.payload[0]:
                # if telegram.payload[1] == SuccessOrFailure.Success::
                self._channel_status = telegram.payload[2]
                self._call_device_updated()

        elif telegram.operate_code == OperateCode.ReadDryContactStatusResponse:
            if self._switch_number == telegram.payload[1]:
                self._switch_status = telegram.payload[2]
                self._call_device_updated()

    def _store_panel_temperature(self, payload):
        """Decode a panel temperature frame.

        Layout: [channel, signed whole degrees, float32 little-endian
        degrees]. Returns True when a value was stored.
        """
        if not payload or len(payload) < 2:
            return False
        whole = payload[1]
        if whole > 127:
            whole -= 256
        self._current_temperature = whole
        self._temperature_from_panel = True
        self._temperature_precise = None
        if len(payload) >= 6:
            try:
                precise = struct.unpack("<f", bytes(payload[2:6]))[0]
            except (struct.error, ValueError, TypeError):
                precise = None
            if precise is not None and -50 < precise < 100:
                self._temperature_precise = precise
        return True

    async def read_sensor_status(self):
        if self._universal_switch_number is not None:
            rsous = _ReadStatusOfUniversalSwitch(self._buspro)
            rsous.subnet_id, rsous.device_id = self._device_address
            rsous.switch_number = self._universal_switch_number
            await rsous.send()
        elif self._channel_number is not None:
            rsoc = _ReadStatusOfChannels(self._buspro)
            rsoc.subnet_id, rsoc.device_id = self._device_address
            await rsoc.send()
        elif self._device is not None and self._device == "panel" and self._read_humidity:
            rav = _GenericControl(self._buspro)
            rav.subnet_id, rav.device_id = self._device_address
            rav.operate_code = OperateCode.ReadAnalogValue
            rav.payload = [ANALOG_TYPE_HUMIDITY, 0]
            await rav.send()
        elif self._device is not None and self._device == "panel":
            rt = _ReadTemperature(self._buspro)
            rt.subnet_id, rt.device_id = self._device_address
            rt.channel_number = self._temperature_channel
            await rt.send()
        elif self._device is not None and self._device == "dlp":
            rfhs = _ReadFloorHeatingStatus(self._buspro)
            rfhs.subnet_id, rfhs.device_id = self._device_address
            await rfhs.send()
        elif self._device is not None and self._device == "dry_contact":
            rdcs = _ReadDryContactStatus(self._buspro)
            rdcs.subnet_id, rdcs.device_id = self._device_address
            rdcs.switch_number = self._switch_number
            await rdcs.send()
        elif self._device is not None and self._device == "sensors_in_one":
            rsios = _ReadSensorsInOneStatus(self._buspro)
            rsios.subnet_id, rsios.device_id = self._device_address
            await rsios.send()
        else:
            rss = _ReadSensorStatus(self._buspro)
            rss.subnet_id, rss.device_id = self._device_address
            await rss.send()

    @property
    def temperature(self):
        if self._current_temperature is None:
            return 0
        if self._temperature_precise is not None:
            return self._temperature_precise
        if self._temperature_from_panel:
            return self._current_temperature
        if self._device is not None and self._device == "dlp":
            return self._current_temperature
        if self._device is not None and self._device == "12in1":
            return self._current_temperature
        if self._device is not None and self._device == "panel":
            return self._current_temperature
        return self._current_temperature - 20

    @property
    def humidity(self):
        return self._current_humidity

    @property
    def brightness(self):
        if self._brightness is None:
            return 0
        return self._brightness

    @property
    def movement(self):
        if self._motion_sensor == 1 or self._sonic == 1:
            return True
        if self._motion_sensor == 0 and self._sonic == 0:
            return False

    @property
    def dry_contact_1_is_on(self):
        if self._dry_contact_1_status == 1:
            return True
        else:
            return False

    @property
    def dry_contact_2_is_on(self):
        if self._dry_contact_2_status == 1:
            return True
        else:
            return False

    @property
    def universal_switch_is_on(self):
        if self._universal_switch_status == 1:
            return True
        else:
            return False

    @property
    def single_channel_is_on(self):
        if self._channel_status > 0:
            return True
        else:
            return False

    @property
    def switch_status(self):
        if self._switch_status == 1:
            return True
        else:
            return False

    @property
    def device_identifier(self):
        return f"{self._device_address}-{self._universal_switch_number}-{self._channel_number}-{self._switch_number}"

    def _call_read_current_status_of_sensor(self, run_from_init=False):

        async def read_current_status_of_sensor():
            if run_from_init:
                await asyncio.sleep(5)
            await self.read_sensor_status()

        asyncio.ensure_future(read_current_status_of_sensor(), loop=self._buspro.loop)
