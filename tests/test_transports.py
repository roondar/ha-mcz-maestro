"""Protocol-level tests: local fake Socket.IO relay, never a real stove."""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import types
from unittest.mock import patch

import pytest
import pytest_asyncio
import socketio
from aiohttp import WSMsgType, WSMessage, web

# Load transport modules without importing Home Assistant's package initializer.
# The CI unit-test environment intentionally has no access to HA or the stove.
ROOT = Path(__file__).resolve().parents[1]
for name, directory in (
    ("custom_components", ROOT / "custom_components"),
    ("custom_components.mcz_maestro", ROOT / "custom_components" / "mcz_maestro"),
):
    if name not in sys.modules:
        package = types.ModuleType(name)
        package.__path__ = [str(directory)]
        sys.modules[name] = package

from custom_components.mcz_maestro.api import (  # noqa: E402
    MaestroClient,
    MaestroConnectionError,
    MaestroProtocolError,
)
from custom_components.mcz_maestro.cloud import MaestroCloudClient  # noqa: E402


IDENTITY = {"serialNumber": "TEST_SERIAL", "macAddress": "aabbccddeeff"}


def parameters_frame() -> str:
    """A coherent mock model frame, not a capture from the real appliance."""
    raw = bytearray(40)
    raw[2], raw[3], raw[6], raw[7], raw[26] = 5, 35, 1, 5, 2
    for offset in (8, 14, 20):
        raw[offset : offset + 6] = bytes((1, 1, 1, 5, 1, 1))
    return "00|" + raw.hex().upper()


def info_frame() -> str:
    """A coherent mock state frame, with enough fields for the shared parser."""
    values = ["00"] * 64
    values[0] = "01"
    values[1] = "00"
    values[2:5] = ["02", "02", "02"]
    values[6] = "28"
    values[26] = "28"
    values[29] = "01"
    return "|".join(values)


class FakeRelay:
    """Small protocol-equivalent server, with per-SID routing and no stove."""

    def __init__(self) -> None:
        self.sio = socketio.AsyncServer(async_mode="aiohttp")
        self.app = web.Application()
        self.sio.attach(self.app)
        self.accepted: set[str] = set()
        self.requests: list[tuple[str, str]] = []
        self.writes: list[str] = []
        self.no_reply = False
        self.wrong_sid_first = False
        self.invalid_info = False

        @self.sio.on("join")
        async def join(sid, payload):
            if (
                isinstance(payload, dict)
                and all(payload.get(k) == v for k, v in IDENTITY.items())
                and payload.get("type") == "Android-App"
            ):
                self.accepted.add(sid)

        @self.sio.on("chiedo")
        async def chiedo(sid, payload):
            if sid not in self.accepted:
                return
            if not all(payload.get(k) == v for k, v in IDENTITY.items()):
                return
            command = payload.get("richiesta")
            call = payload.get("tipoChiamata")
            self.requests.append((sid, command))
            if command == "RecuperoParametri" and call == 0:
                frame = parameters_frame()
            elif command == "C|RecuperoInfo" and call == 1:
                frame = "01|bad" if self.invalid_info else info_frame()
            elif (
                call == 1
                and (command.startswith("C|WriteParametri|")
                     or command.startswith("C|SalvaDataOra|"))
            ):
                self.writes.append(command)
                frame = "ACK"
            else:
                return
            if self.no_reply:
                return
            if self.wrong_sid_first:
                await self.sio.emit(
                    "rispondo",
                    {"socketChiamata": "obsolete-SID", "stringaRicevuta": "bad"},
                    to=sid,
                )
            await self.sio.emit(
                "rispondo",
                {"socketChiamata": sid, "stringaRicevuta": frame},
                to=sid,
            )

        @self.sio.event
        async def disconnect(sid):
            self.accepted.discard(sid)

    async def start(self) -> None:
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await self.site.start()
        self.port = self.site._server.sockets[0].getsockname()[1]

    async def close(self) -> None:
        await self.runner.cleanup()

    def client(self, **identity) -> MaestroCloudClient:
        return MaestroCloudClient(
            "127.0.0.1", self.port,
            identity.get("serialNumber", IDENTITY["serialNumber"]),
            identity.get("macAddress", IDENTITY["macAddress"]),
        )


@pytest_asyncio.fixture
async def relay():
    instance = FakeRelay()
    await instance.start()
    try:
        yield instance
    finally:
        await instance.close()


@pytest.mark.asyncio
async def test_cloud_reads_and_connection_generation(relay):
    client = relay.client()
    try:
        assert not client.connected
        params = await client.async_request_parameters()
        data = await client.async_request_info()
        assert params.target_temperature_max == 35
        assert data.values["ambient_temperature"] == 20.0
        assert client.connected
        assert client.connection_generation == 1
        assert [command for _, command in relay.requests] == [
            "RecuperoParametri", "C|RecuperoInfo"
        ]
    finally:
        await client.async_close()


@pytest.mark.asyncio
async def test_write_awaits_ack_and_never_replays(relay):
    client = relay.client()
    try:
        await client.async_request_parameters()
        await client.async_request_info()
        await client.async_write_parameter(42, 40)
        assert relay.writes == ["C|WriteParametri|42|40"]
        relay.no_reply = True
        with patch("custom_components.mcz_maestro.cloud.REQUEST_TIMEOUT", 0.15):
            with pytest.raises(MaestroConnectionError):
                await client.async_write_parameter(34, 40)
        assert relay.writes.count("C|WriteParametri|34|40") == 1
        await asyncio.sleep(0.2)
        assert relay.writes.count("C|WriteParametri|34|40") == 1
    finally:
        await client.async_close()


@pytest.mark.asyncio
async def test_invalid_join_cannot_read(relay):
    client = relay.client(serialNumber="NOT_THE_STOVE")
    try:
        with patch("custom_components.mcz_maestro.cloud.REQUEST_TIMEOUT", 0.15):
            with pytest.raises(MaestroConnectionError):
                await client.async_request_parameters()
        assert relay.requests == []
    finally:
        await client.async_close()


@pytest.mark.asyncio
async def test_bad_response_is_not_accepted(relay):
    client = relay.client()
    relay.invalid_info = True
    try:
        with pytest.raises(MaestroProtocolError):
            await client.async_request_info()
        assert not client.connected
    finally:
        await client.async_close()


@pytest.mark.asyncio
async def test_wrong_sid_does_not_complete_request(relay):
    client = relay.client()
    relay.wrong_sid_first = True
    try:
        assert (await client.async_request_info()).values["stove_state"] == 0
    finally:
        await client.async_close()


@pytest.mark.asyncio
async def test_disconnect_then_manual_read_reconnects(relay):
    client = relay.client()
    try:
        await client.async_request_info()
        sid = next(iter(relay.accepted))
        await relay.sio.disconnect(sid)
        await asyncio.sleep(0.1)
        await client.async_request_info()
        assert client.connection_generation == 2
    finally:
        await client.async_close()


@pytest.mark.asyncio
async def test_simulated_android_and_ha_are_independent(relay):
    ha = relay.client()
    android = socketio.AsyncClient(reconnection=False)
    responses = asyncio.Queue()

    @android.on("rispondo")
    async def received(payload):
        await responses.put(payload)

    try:
        await ha.async_request_parameters()
        await android.connect(
            f"http://127.0.0.1:{relay.port}", transports=["websocket"]
        )
        await android.emit("join", {**IDENTITY, "type": "Android-App"})
        await android.emit(
            "chiedo",
            {**IDENTITY, "tipoChiamata": 1, "richiesta": "C|RecuperoInfo"},
        )
        result = await asyncio.wait_for(responses.get(), timeout=2)
        assert result["socketChiamata"] == android.get_sid("/")
        assert (await ha.async_request_info()).values["stove_state"] == 0
        assert len({sid for sid, _ in relay.requests}) == 2
    finally:
        if android.connected:
            await android.disconnect()
        await ha.async_close()


class FakeWebSocket:
    """Tiny legacy WebSocket fixture for read-only regression coverage."""

    def __init__(self) -> None:
        self.closed = False
        self.sent = []

    async def send_str(self, message):
        self.sent.append(message)

    async def receive(self):
        return WSMessage(WSMsgType.TEXT, info_frame(), "")

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_legacy_direct_read_unchanged():
    class Session:
        async def ws_connect(self, *args, **kwargs):
            return socket

    socket = FakeWebSocket()
    client = MaestroClient(Session(), "192.168.120.1", 81)
    try:
        assert (await client.async_request_info()).values["stove_state"] == 0
        assert socket.sent == ["C|RecuperoInfo"]
        assert client.url == "ws://192.168.120.1:81/"
    finally:
        await client.async_close()


def test_entity_identity_remains_entry_based():
    """The transport options must never become part of HA entity identifiers."""
    component = ROOT / "custom_components" / "mcz_maestro"
    entity = (component / "entity.py").read_text()
    assert 'self._attr_unique_id = f"{entry.unique_id}_{entity_key}"' in entity
    assert 'identifiers={(DOMAIN, self._entry.unique_id or self._entry.entry_id)}' in entity
    assert "entry.data[CONF_HOST]" in (component / "__init__.py").read_text()
