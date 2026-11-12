"""Hermetic tests for the MCZ Cloud Local transport (no real stove or HA)."""

from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


# Load only the pure protocol modules, not the Home Assistant integration's
# __init__.py, so these tests can run on a small GitHub Actions runner.
ROOT = Path(__file__).resolve().parents[1]
parent = types.ModuleType("custom_components")
parent.__path__ = [str(ROOT / "custom_components")]
sys.modules.setdefault("custom_components", parent)
package = types.ModuleType("custom_components.mcz_maestro")
package.__path__ = [str(ROOT / "custom_components" / "mcz_maestro")]
sys.modules.setdefault("custom_components.mcz_maestro", package)

relay_api = importlib.import_module("custom_components.mcz_maestro.relay_api")
api = importlib.import_module("custom_components.mcz_maestro.api")


def parameters() -> str:
    raw = bytearray(40)
    raw[2], raw[3], raw[6], raw[7], raw[26] = 5, 35, 1, 5, 4
    for start in (8, 14, 20):
        raw[start : start + 6] = bytes((1, 1, 1, 5, 1, 1))
    return "00|" + raw.hex()


def info() -> str:
    values = ["00"] * 60
    values[0] = "01"
    values[6], values[22], values[26], values[29] = "26", "01", "28", "01"
    return "|".join(values)


class FakeSocket:
    def __init__(self, replies=None, wrong_sid=False):
        self.connected = False
        self.handlers = {}
        self.messages = []
        self.replies = replies or {}
        self.wrong_sid = wrong_sid

    def on(self, name):
        def register(callback):
            self.handlers[name] = callback
            return callback

        return register

    def event(self, callback):
        self.handlers[callback.__name__] = callback
        return callback

    def get_sid(self, namespace):
        assert namespace == "/"
        return "fake-namespace-sid"

    async def connect(self, url, *, transports, wait_timeout):
        assert url == "http://192.168.1.252:9000"
        assert transports == ["websocket"]
        assert wait_timeout == 5
        self.connected = True

    async def emit(self, event, payload):
        self.messages.append((event, payload))
        if event != "chiedo":
            return
        response = self.replies.get(payload["richiesta"])
        if response is not None:
            await self.handlers["rispondo"](
                {
                    "socketChiamata": (
                        "invalid" if self.wrong_sid else self.get_sid("/")
                    ),
                    "stringaRicevuta": response,
                }
            )

    async def disconnect(self):
        if self.connected:
            self.connected = False
            await self.handlers["disconnect"]()


class TestRelayClient(unittest.IsolatedAsyncioTestCase):
    def make_client(self):
        return relay_api.MaestroRelayClient(
            "192.168.1.252", 9000, "SIM-NO-SECRETS", "02:00:00:00:00:01"
        )

    async def test_reads_and_single_acknowledged_write(self):
        sock = FakeSocket(
            {
                "RecuperoParametri": parameters(),
                "C|RecuperoInfo": info(),
                "C|WriteParametri|42|40": "ACK",
            }
        )
        with patch.object(relay_api.socketio, "AsyncClient", return_value=sock):
            client = self.make_client()
            try:
                params = await client.async_request_parameters()
                self.assertEqual(params.target_temperature_max, 35)
                self.assertEqual(params.target_temperature_step, 0.5)
                state = await client.async_request_info()
                self.assertEqual(state.values["target_temperature"], 20.0)
                self.assertEqual(client.connection_generation, 1)
                await client.async_write_parameter(42, 40)
                self.assertEqual(
                    [name for name, _ in sock.messages],
                    ["join", "chiedo", "chiedo", "chiedo"],
                )
                self.assertEqual(
                    sock.messages[0][1]["type"], "Android-App"
                )
                self.assertEqual(
                    [payload["richiesta"] for name, payload in sock.messages
                     if name == "chiedo"],
                    ["RecuperoParametri", "C|RecuperoInfo",
                     "C|WriteParametri|42|40"],
                )
            finally:
                await client.async_close()
                self.assertFalse(client.connected)

    async def test_timeout_does_not_replay_a_write(self):
        sock = FakeSocket({
            "RecuperoParametri": parameters(),
            "C|RecuperoInfo": info(),
        })
        with (
            patch.object(relay_api.socketio, "AsyncClient", return_value=sock),
            patch.object(relay_api, "REQUEST_TIMEOUT", 0.02),
        ):
            client = self.make_client()
            try:
                with self.assertRaises(api.MaestroConnectionError):
                    await client.async_write_parameter(42, 40)
                self.assertEqual(
                    sum(
                        name == "chiedo" and payload["richiesta"]
                        == "C|WriteParametri|42|40"
                        for name, payload in sock.messages
                    ),
                    1,
                )
            finally:
                await client.async_close()

    async def test_wrong_sid_fails_closed(self):
        sock = FakeSocket(
            {"C|RecuperoInfo": info()}, wrong_sid=True
        )
        with patch.object(relay_api.socketio, "AsyncClient", return_value=sock):
            client = self.make_client()
            try:
                with self.assertRaises(api.MaestroProtocolError):
                    await client.async_request_info()
            finally:
                await client.async_close()

    async def test_direct_protocol_parsers_reused_by_relay(self):
        self.assertEqual(api.decode_info_message(info()).values["stove_state"], 0)
        self.assertEqual(
            api.decode_parameters_message(parameters()).fan_present,
            (True, True, True),
        )


if __name__ == "__main__":
    unittest.main()
