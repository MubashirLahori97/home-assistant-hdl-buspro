''' pybuspro version 1.0.0  '''

import asyncio
import logging
import weakref

from .helpers.enums import *
from .transport.network_interface import NetworkInterface


# ip, port = gateway_address
# subnet_id, device_id, channel = device_address


class StateUpdater:
    def __init__(self, buspro, sleep=10):
        self.buspro = buspro
        self.run_forever = True
        self.run_task = None
        self.sleep = sleep

    async def start(self):
        self.run_task = self.buspro.loop.create_task(self.run())

    async def run(self):
        await asyncio.sleep(0)
        self.buspro.logger.info("Starting StateUpdater with {} seconds interval".format(self.sleep))

        while True:
            await asyncio.sleep(self.sleep)
            await self.buspro.sync()


class Buspro:

    def __init__(self, gateway_address_send_receive, loop_=None, header_ip=None, gateway_ip_filter=False):
        self.loop = loop_ or asyncio.get_event_loop()
        self.state_updater = None
        self.started = False
        self.network_interface = None
        self.logger = logging.getLogger("buspro.log")
        self.telegram_logger = logging.getLogger("buspro.telegram")

        self.callback_all_messages = None
        self._all_messages_cbs = []
        self._telegram_received_cbs = []
        self._pending_requests = []
        # Every Device created on this bus (weak, so throwaway ones vanish).
        self.devices = weakref.WeakSet()

        self.gateway_address_send_receive = gateway_address_send_receive
        # Local IP written into the header of frames we send.
        self.header_ip = header_ip
        # When set, frames that do not come from the gateway's IP are dropped.
        self.gateway_ip_filter = gateway_ip_filter

    def __del__(self):
        if self.started:
            try:
                task = self.loop.create_task(self.stop())
                self.loop.run_until_complete(task)
            except RuntimeError as exp:
                self.logger.warning("Could not close loop, reason: {}".format(exp))

    # noinspection PyUnusedLocal
    async def start(self, state_updater=False):  # , daemon_mode=False):
        self.network_interface = NetworkInterface(
            self, self.gateway_address_send_receive, header_ip=self.header_ip)
        self.network_interface.register_callback(self._callback_all_messages)
        await self.network_interface.start()

        if state_updater:
            self.state_updater = StateUpdater(self)
            await self.state_updater.start()

        '''
        if daemon_mode:
            await self._loop_until_sigint()
        '''

        self.started = True

        # await asyncio.sleep(5)
        # await self.network_interface.send_message(b'\0x01')

    async def stop(self):
        await self._stop_network_interface()
        self.started = False

    def _callback_all_messages(self, telegram):
        if telegram is None:
            return

        if self.gateway_ip_filter and telegram.udp_address is not None:
            gateway_ip = self.gateway_address_send_receive[0][0]
            if telegram.udp_address[0] != gateway_ip:
                return

        self.telegram_logger.debug(telegram)

        self._resolve_pending_requests(telegram)

        if self.callback_all_messages is not None:
            self.callback_all_messages(telegram)

        for all_messages_cb in list(self._all_messages_cbs):
            try:
                all_messages_cb(telegram)
            except Exception:
                self.logger.exception("Error in bus message listener")

        for telegram_received_cb in self._telegram_received_cbs:
            device_address = telegram_received_cb['device_address']

            # Sender callback kun for oppgitt kanal
            if device_address == telegram.target_address or device_address == telegram.source_address:
                if telegram.operate_code is not OperateCode.TIME_IF_FROM_LOGIC_OR_SECURITY:
                    postfix = telegram_received_cb['postfix']
                    if postfix is not None:
                        telegram_received_cb['callback'](telegram, postfix)
                    else:
                        telegram_received_cb['callback'](telegram)

    def _resolve_pending_requests(self, telegram):
        for pending in list(self._pending_requests):
            if pending['future'].done():
                continue
            if telegram.operate_code_raw != pending['response_code']:
                continue
            source = pending['source_address']
            if source is not None and tuple(telegram.source_address) != tuple(source):
                continue
            if pending['collect'] is not None:
                pending['collect'].append(telegram)
            else:
                pending['future'].set_result(telegram)

    async def _stop_network_interface(self):
        if self.network_interface is not None:
            await self.network_interface.stop()
            self.network_interface = None

    def register_telegram_received_all_messages_cb(self, telegram_received_cb):
        """Add a listener that receives every decoded bus message."""
        self._all_messages_cbs.append(telegram_received_cb)

    def unregister_telegram_received_all_messages_cb(self, telegram_received_cb):
        if telegram_received_cb in self._all_messages_cbs:
            self._all_messages_cbs.remove(telegram_received_cb)

    async def send_telegram(self, telegram):
        if self.network_interface is None:
            self.logger.info("Could not send message. Not connected.")
            return
        await self.network_interface.send_telegram(telegram)

    async def request(self, telegram, response_code, timeout=1.0, retries=2, source_address=None):
        """Send a telegram and wait for the reply with the given operate code.

        response_code is the two raw bytes of the expected reply. The reply
        must come from source_address (default: the telegram's target).
        Returns the reply telegram, or None when nothing answered.
        """
        if source_address is None:
            source_address = telegram.target_address
        for _ in range(retries + 1):
            pending = {
                'future': self.loop.create_future(),
                'response_code': bytes(response_code),
                'source_address': source_address,
                'collect': None,
            }
            self._pending_requests.append(pending)
            try:
                await self.send_telegram(telegram)
                return await asyncio.wait_for(pending['future'], timeout)
            except asyncio.TimeoutError:
                continue
            finally:
                self._pending_requests.remove(pending)
        return None

    async def collect(self, telegram, response_code, duration=3.0):
        """Send a telegram (usually a broadcast) and gather every reply with
        the given operate code that arrives within duration seconds."""
        replies = []
        pending = {
            'future': self.loop.create_future(),
            'response_code': bytes(response_code),
            'source_address': None,
            'collect': replies,
        }
        self._pending_requests.append(pending)
        try:
            await self.send_telegram(telegram)
            await asyncio.sleep(duration)
        finally:
            self._pending_requests.remove(pending)
            pending['future'].cancel()
        return replies

    def register_telegram_received_device_cb(self, telegram_received_cb, device_address, postfix=None):
        self._telegram_received_cbs.append({
            'callback': telegram_received_cb,
            'device_address': device_address,
            'postfix': postfix})

    def unregister_telegram_received_device_cb(self, telegram_received_cb, device_address, postfix=None):
        self._telegram_received_cbs.remove({
            'callback': telegram_received_cb,
            'device_address': device_address,
            'postfix': postfix})

    @staticmethod
    async def sync():
        # await self.callback("LOG: Sync() triggered from StateUpdater")
        # print("LOG: Sync() triggered from StateUpdater")
        raise NotImplementedError
