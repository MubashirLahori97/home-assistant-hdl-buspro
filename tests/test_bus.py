"""Bus groundwork: frames, listeners, request/collect."""
import asyncio

from custom_components.buspro.pybuspro.buspro import Buspro
from custom_components.buspro.pybuspro.helpers.enums import OperateCode
from custom_components.buspro.pybuspro.core.telegram import Telegram
from custom_components.buspro.pybuspro.helpers.telegram_helper import TelegramHelper

from .conftest import GATEWAY, build_frame, decode_frame


def test_frame_round_trip_keeps_raw_codes():
    frame = build_frame((1, 20), (1, 74), OperateCode.SingleChannelControl, [3, 100, 0, 2])
    telegram = decode_frame(frame)
    assert telegram.source_address == (1, 20)
    assert telegram.target_address == (1, 74)
    assert telegram.operate_code == OperateCode.SingleChannelControl
    assert telegram.operate_code_raw == b"\x00\x31"
    assert telegram.payload == [3, 100, 0, 2]


def test_unknown_operate_code_keeps_raw_bytes():
    class Raw:
        value = b"\xD9\x0B"
    frame = build_frame((1, 30), (1, 254), Raw(), [1, 2, 3])
    telegram = decode_frame(frame)
    assert telegram.operate_code is None
    assert telegram.operate_code_raw == b"\xD9\x0B"
    assert telegram.payload == [1, 2, 3]


def test_header_ip_is_configurable():
    telegram = Telegram()
    telegram.target_address = (1, 1)
    telegram.operate_code = OperateCode.ReadStatusOfChannels
    frame = TelegramHelper((10, 0, 0, 5)).build_send_buffer(telegram)
    assert list(frame[:4]) == [10, 0, 0, 5]


def test_bad_crc_is_dropped():
    frame = bytearray(build_frame((1, 20), (1, 74), OperateCode.SceneControl, [1, 2]))
    frame[-1] ^= 0xFF
    assert TelegramHelper().build_telegram_from_udp_data(bytes(frame), GATEWAY) is None


async def test_listeners_request_and_collect(hass, fake_bus):
    hdl = Buspro((GATEWAY, ("", 6000)), hass.loop)
    await hdl.start()

    heard = []
    hdl.register_telegram_received_all_messages_cb(heard.append)
    second = []
    hdl.register_telegram_received_all_messages_cb(second.append)

    # A None telegram (bad frame) must not crash listeners.
    hdl._callback_all_messages(None)

    def responder(sent):
        if sent.operate_code == OperateCode.IsDeviceOnline:
            return build_frame(sent.target_address, (200, 200),
                               OperateCode.IsDeviceOnlineResponse, [0xF8])
        return None

    fake_bus.responder = responder
    request = Telegram()
    request.target_address = (1, 74)
    request.operate_code = OperateCode.IsDeviceOnline
    reply = await hdl.request(request, OperateCode.IsDeviceOnlineResponse.value, timeout=0.5)
    assert reply is not None and reply.source_address == (1, 74)
    assert len(heard) == 1 and len(second) == 1

    fake_bus.responder = None
    request.target_address = (1, 99)
    assert await hdl.request(request, OperateCode.IsDeviceOnlineResponse.value,
                             timeout=0.05, retries=1) is None
    assert len(fake_bus.sent) == 3  # 1 answered + 2 tries unanswered

    def remark_responder(sent):
        return None

    fake_bus.responder = remark_responder
    scan = Telegram()
    scan.target_address = (255, 255)
    scan.operate_code = OperateCode.ReadDeviceRemark

    async def answer_later():
        await asyncio.sleep(0.01)
        for device_id in (5, 6):
            fake_bus.inject(build_frame((1, device_id), (200, 200),
                                        OperateCode.ReadDeviceRemarkResponse, list(b"Hall\x00")))

    hass.loop.create_task(answer_later())
    replies = await hdl.collect(scan, OperateCode.ReadDeviceRemarkResponse.value, duration=0.1)
    assert sorted(r.source_address for r in replies) == [(1, 5), (1, 6)]

    hdl.unregister_telegram_received_all_messages_cb(heard.append)
    await hdl.stop()


async def test_gateway_ip_filter(hass, fake_bus):
    hdl = Buspro((GATEWAY, ("", 6000)), hass.loop, gateway_ip_filter=True)
    await hdl.start()
    heard = []
    hdl.register_telegram_received_all_messages_cb(heard.append)
    frame = build_frame((1, 2), (1, 3), OperateCode.SceneControl, [1, 1])
    fake_bus.inject(frame, ("192.168.1.99", 6000))
    fake_bus.inject(frame, GATEWAY)
    assert len(heard) == 1
    await hdl.stop()
