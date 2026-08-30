import asyncio
from .device import Device
from ..helpers.enums import OperateCode
from ..core.telegram import Telegram


class AC(Device):
    """HDL Buspro AC device."""

    # Fan speed constants
    FAN_AUTO = 0
    FAN_HIGH = 1
    FAN_MEDIUM = 2
    FAN_LOW = 3

    # Mode constants
    MODE_COOLING = 0
    MODE_HEATING = 1
    MODE_FAN = 2
    MODE_AUTO = 3
    MODE_DEHUMIDIFY = 4

    def __init__(self, buspro, device_address, channel_number, name=""):
        super().__init__(buspro, device_address, name)
        self._buspro = buspro
        self._device_address = device_address
        self._channel_number = channel_number
        self._is_on = False
        self._temperature = None
        self._target_temperature = None
        self._fan_speed = self.FAN_AUTO
        self._mode = self.MODE_COOLING
        self._swing = False
        self._temperature_type = 0  # Celsius

        self.register_telegram_received_cb(self._telegram_received_cb)
        
        # Query initial status after short delay
        asyncio.ensure_future(self._read_ac_status(), loop=self._buspro.loop)

    async def _read_ac_status(self):
        await asyncio.sleep(3)
        telegram = Telegram()
        telegram.target_address = self._device_address
        telegram.operate_code = OperateCode.ReadAcCurrentStatus
        telegram.payload = [self._channel_number]
        await self._send_telegram(telegram)

    @property
    def is_on(self):
        return self._is_on

    @property
    def temperature(self):
        """Current room temperature."""
        return self._temperature

    @property
    def target_temperature(self):
        return self._target_temperature

    @property
    def fan_speed(self):
        return self._fan_speed

    @property
    def mode(self):
        return self._mode

    @property
    def swing(self):
        return self._swing

    @property
    def device_identifier(self):
        return f"{self._device_address}-{self._channel_number}-ac"

    def _telegram_received_cb(self, telegram):
        if telegram.operate_code == OperateCode.ReadAcCurrentStatusResponse:
            if len(telegram.payload) >= 8 and telegram.payload[0] == self._channel_number:
                self._temperature_type = telegram.payload[1]
                self._temperature = telegram.payload[2]
                self._is_on = telegram.payload[3] == 1
                self._target_temperature = telegram.payload[4]
                self._fan_speed = telegram.payload[5]
                self._mode = telegram.payload[6]
                self._swing = telegram.payload[7] == 1
                self._call_device_updated()

        elif telegram.operate_code == OperateCode.ControlAcStatusResponse:
            if len(telegram.payload) >= 1 and telegram.payload[0] == self._channel_number:
                asyncio.ensure_future(self._read_ac_status(), loop=self._buspro.loop)

    async def _send_control(self):
        """Send current state as a control command."""
        telegram = Telegram()
        telegram.target_address = self._device_address
        telegram.operate_code = OperateCode.ControlAcStatus
        telegram.payload = [
            self._channel_number,
            1 if self._is_on else 0,
            self._target_temperature or 24,
            self._fan_speed,
            self._mode,
            1 if self._swing else 0,
            self._temperature_type,
        ]
        await self._send_telegram(telegram)

    async def set_on(self):
        self._is_on = True
        await self._send_control()

    async def set_off(self):
        self._is_on = False
        await self._send_control()

    async def set_target_temperature(self, temperature):
        self._target_temperature = int(temperature)
        await self._send_control()

    async def set_fan_speed(self, fan_speed):
        self._fan_speed = fan_speed
        await self._send_control()

    async def set_mode(self, mode):
        self._mode = mode
        await self._send_control()

    async def set_swing(self, swing):
        self._swing = swing
        await self._send_control()
