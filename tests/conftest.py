"""Shared fixtures: a fake UDP link that records sent frames and injects replies."""
from unittest.mock import patch

import pytest

from custom_components.buspro.const import DOMAIN
from custom_components.buspro.pybuspro.core.telegram import Telegram
from custom_components.buspro.pybuspro.helpers.telegram_helper import TelegramHelper

pytest_plugins = ["pytest_homeassistant_custom_component"]

GATEWAY = ("192.168.1.250", 6000)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/ in every test."""
    yield


@pytest.fixture
def expected_lingering_tasks():
    """pybuspro devices schedule a delayed first status read on creation."""
    return True


@pytest.fixture
def expected_lingering_timers():
    return True


def build_frame(source, target, operate_code, payload, source_type=None):
    """Build a raw UDP frame as an HDL gateway would send it."""
    telegram = Telegram()
    telegram.source_address = source
    telegram.target_address = target
    telegram.operate_code = operate_code
    telegram.payload = list(payload)
    if source_type is not None:
        telegram.source_device_type = source_type
    return bytes(TelegramHelper().build_send_buffer(telegram))


def decode_frame(frame):
    return TelegramHelper().build_telegram_from_udp_data(bytes(frame), GATEWAY)


class FakeBus:
    """Captures frames the integration sends; lets tests inject frames."""

    def __init__(self):
        self.sent = []
        self.clients = []
        self.responder = None

    def telegrams(self):
        return [decode_frame(frame) for frame in self.sent]

    def inject(self, frame, address=GATEWAY):
        for client in list(self.clients):
            client.callback(frame, address)


@pytest.fixture
def fake_bus():
    bus = FakeBus()

    async def fake_start(self):
        bus.clients.append(self)

    async def fake_stop(self):
        if self in bus.clients:
            bus.clients.remove(self)

    async def fake_send(self, message):
        bus.sent.append(bytes(message))
        if bus.responder is not None:
            reply = bus.responder(decode_frame(message))
            if reply is not None:
                self.buspro.loop.call_soon(bus.inject, reply)

    with patch("custom_components.buspro.pybuspro.transport.udp_client.UDPClient.start", fake_start), \
         patch("custom_components.buspro.pybuspro.transport.udp_client.UDPClient.stop", fake_stop), \
         patch("custom_components.buspro.pybuspro.transport.udp_client.UDPClient.send_message", fake_send), \
         patch("custom_components.buspro._local_ip_towards", return_value=(192, 168, 1, 20)):
        yield bus


async def setup_entry(hass, devices=None, bridges=None, options=None):
    """Create and set up a config entry with the given devices."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    data = {
        "host": GATEWAY[0],
        "port": GATEWAY[1],
        "devices": devices or [],
        "areas": [],
        "floors": [],
        "scenes": [],
        "gateway": {"ip": GATEWAY[0], "port": GATEWAY[1]},
    }
    if bridges is not None:
        data["bridges"] = bridges
    entry = MockConfigEntry(domain=DOMAIN, version=2, data=data, options=options or {},
                            unique_id=f"buspro_{GATEWAY[0]}_{GATEWAY[1]}")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
