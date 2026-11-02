import asyncio

from .device import Device
from ..core.telegram import Telegram
from ..helpers.enums import OperateCode


class HvacModule(Device):
    """HDL HVAC module (M/HVAC, MPED, MAC, IR AC) on the 0x193A AC commands.

    Status and control share one 13-byte layout:
    [0] AC number, [1] temperature type, [2] current temperature,
    [3..6] cool / heat / auto / dry setpoints, [7] mode << 4 | fan speed,
    [8] on/off, [9] setup mode, [10] setup fan speed, [11] setup temperature,
    [12] swing enabled << 4 | swing active.

    It exposes the same interface as AC so the climate entity is shared.
    """

    FAN_AUTO = 0
    FAN_HIGH = 1
    FAN_MEDIUM = 2
    FAN_LOW = 3

    MODE_COOLING = 0
    MODE_HEATING = 1
    MODE_FAN = 2
    MODE_AUTO = 3
    MODE_DEHUMIDIFY = 4

    # Mode -> index of its setpoint in the payload (fan mode uses [11]).
    _SETPOINT_INDEX = {0: 3, 1: 4, 3: 5, 4: 6}

    def __init__(self, buspro, device_address, ac_number=1, name=""):
        super().__init__(buspro, device_address, name)
        self._buspro = buspro
        self._device_address = device_address
        self._ac_number = ac_number
        self._state = None

        self.register_telegram_received_cb(self._telegram_received_cb)
        asyncio.ensure_future(self._read_status(delay=3), loop=self._buspro.loop)

    async def _read_status(self, delay=0):
        if delay:
            await asyncio.sleep(delay)
        telegram = Telegram()
        telegram.target_address = self._device_address
        telegram.operate_code = OperateCode.ReadHvacStatus
        telegram.payload = [self._ac_number]
        await self._send_telegram(telegram)

    def _telegram_received_cb(self, telegram):
        if telegram.operate_code not in (
            OperateCode.ReadHvacStatusResponse,
            OperateCode.ControlHvacStatusResponse,
        ):
            return
        if tuple(telegram.source_address) != tuple(self._device_address):
            return
        payload = telegram.payload or []
        if len(payload) < 13 or payload[0] != self._ac_number:
            return
        self._state = list(payload[:13])
        self._call_device_updated()

    def _default_state(self):
        return [self._ac_number, 0, 0, 24, 24, 24, 24, 0, 0, 0, 0, 24, 0]

    @property
    def is_on(self):
        return bool(self._state and self._state[8])

    @property
    def temperature(self):
        return self._state[2] if self._state else None

    @property
    def mode(self):
        return self._state[9] if self._state else self.MODE_COOLING

    @property
    def fan_speed(self):
        return self._state[10] if self._state else self.FAN_AUTO

    @property
    def target_temperature(self):
        if not self._state:
            return None
        return self._state[self._SETPOINT_INDEX.get(self.mode, 11)]

    @property
    def swing(self):
        return bool(self._state and self._state[12] & 0x0F)

    @property
    def device_identifier(self):
        return f"{self._device_address}-{self._ac_number}-hvac"

    async def _send(self, **changes):
        state = list(self._state or self._default_state())
        if "on" in changes:
            state[8] = 1 if changes["on"] else 0
        if "mode" in changes:
            state[9] = changes["mode"]
        if "fan_speed" in changes:
            state[10] = changes["fan_speed"]
        if "temperature" in changes:
            temperature = int(changes["temperature"])
            state[self._SETPOINT_INDEX.get(state[9], 11)] = temperature
            state[11] = temperature
        if "swing" in changes:
            enabled = (state[12] >> 4) or 1
            state[12] = (enabled << 4) | (1 if changes["swing"] else 0)
        state[0] = self._ac_number
        state[7] = (state[9] << 4) | (state[10] & 0x0F)
        self._state = state

        telegram = Telegram()
        telegram.target_address = self._device_address
        telegram.operate_code = OperateCode.ControlHvacStatus
        telegram.payload = state
        await self._send_telegram(telegram)

    async def set_on(self):
        await self._send(on=True)

    async def set_off(self):
        await self._send(on=False)

    async def set_target_temperature(self, temperature):
        await self._send(temperature=temperature)

    async def set_fan_speed(self, fan_speed):
        await self._send(fan_speed=fan_speed)

    async def set_mode(self, mode):
        await self._send(mode=mode)

    async def set_swing(self, swing):
        await self._send(swing=swing)
