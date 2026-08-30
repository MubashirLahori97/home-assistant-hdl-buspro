from .control import _SingleChannelControl
from .device import Device
from ..helpers.enums import OperateCode


class Cover(Device):
    def __init__(self, buspro, device_address, channel_number, name=""):
        super().__init__(buspro, device_address, name)
        self._buspro = buspro
        self._device_address = device_address
        self._channel = channel_number
        self._current_position = 0  # 0 = closed, 100 = open
        self._is_open = False
        
        self.register_telegram_received_cb(self._telegram_received_cb)
        self._call_read_current_status_of_channels(run_from_init=True)

    def _telegram_received_cb(self, telegram):
        if telegram.operate_code == OperateCode.SingleChannelControlResponse:
            channel = telegram.payload[0]
            position = telegram.payload[2]
            if channel == self._channel:
                self._current_position = position
                self._is_open = self._current_position > 0
                self._call_device_updated()

        elif telegram.operate_code == OperateCode.ReadStatusOfChannelsResponse:
            if self._channel <= telegram.payload[0]:
                self._current_position = telegram.payload[self._channel]
                self._is_open = self._current_position > 0
                self._call_device_updated()

        elif telegram.operate_code == OperateCode.SceneControlResponse:
            self._call_read_current_status_of_channels()

    @property
    def current_position(self):
        return self._current_position

    @property
    def is_open(self):
        return self._is_open

    @property
    def is_closed(self):
        return self._current_position == 0

    @property
    def device_identifier(self):
        return f"{self._device_address}-{self._channel}-cover"

    async def set_position(self, position):
        self._current_position = position
        self._is_open = self._current_position > 0

        scc = _SingleChannelControl(self._buspro)
        scc.subnet_id, scc.device_id = self._device_address
        scc.channel_number = self._channel
        scc.channel_level = position
        scc.running_time_minutes = 0
        scc.running_time_seconds = 0
        await scc.send()

    async def open_cover(self):
        await self.set_position(100)

    async def close_cover(self):
        await self.set_position(0)

    async def stop_cover(self):
        await self.set_position(self._current_position)
