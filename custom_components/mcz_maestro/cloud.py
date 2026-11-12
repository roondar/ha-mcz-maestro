"""Socket.IO client for the existing MCZ local cloud relay.

This module changes transport only. The Maestro coordinator remains responsible
for validation, serialization of HA commands and confirmation after writes.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import socketio

from .api import (
    MaestroConnectionError,
    MaestroData,
    MaestroParameters,
    MaestroProtocolError,
    decode_info_message,
    decode_parameters_message,
)
from .const import COMMAND_MIN_INTERVAL_SECONDS, REQUEST_TIMEOUT


class MaestroCloudClient:
    """One session to mcz-cloud-local, with one in-flight request at a time."""

    def __init__(
        self, host: str, port: int, serial_number: str, mac_address: str
    ) -> None:
        self._host = host
        self._port = port
        self._identity = {
            "serialNumber": serial_number,
            "macAddress": mac_address,
        }
        # Python Socket.IO 5 uses Engine.IO 4, which the local Socket.IO 4
        # server supports alongside the Android application's Engine.IO 3.
        self._socket = socketio.AsyncClient(
            reconnection=False,
            logger=False,
            engineio_logger=False,
            request_timeout=REQUEST_TIMEOUT,
        )
        self._socket.on("rispondo", self._on_response)
        self._socket.on("disconnect", self._on_disconnect)
        self._io_lock = asyncio.Lock()
        self._pending: asyncio.Future[str] | None = None
        self._connection_generation = 0
        self._last_command_at = 0.0

    @property
    def url(self) -> str:
        """Return the relay URL without credentials."""
        return f"http://{self._host}:{self._port}"

    @property
    def connected(self) -> bool:
        """Return whether the Socket.IO session is connected."""
        return self._socket.connected

    @property
    def connection_generation(self) -> int:
        """Change on every new transport session."""
        return self._connection_generation

    async def _async_connect(self) -> None:
        if self.connected:
            return
        try:
            # WebSocket is supported by the relay; no extra HTTP polling.
            await self._socket.connect(
                self.url, transports=["websocket"], wait_timeout=REQUEST_TIMEOUT
            )
            await self._socket.emit(
                "join", {**self._identity, "type": "Android-App"}
            )
        except Exception as err:
            await self._async_disconnect_unlocked()
            raise MaestroConnectionError("Connexion au relais MCZ impossible") from err
        self._connection_generation += 1

    async def _on_response(self, payload: object) -> None:
        """Only accept the relay's response for this Socket.IO namespace SID."""
        if not isinstance(payload, dict):
            return
        future = self._pending
        if future is None or future.done():
            return
        if payload.get("socketChiamata") != self._socket.get_sid("/"):
            return
        frame = payload.get("stringaRicevuta")
        if isinstance(frame, str):
            future.set_result(frame)

    async def _on_disconnect(self) -> None:
        """Cancel an outstanding request instead of replaying it."""
        future = self._pending
        if future is not None and not future.done():
            future.set_exception(MaestroConnectionError("Relais MCZ déconnecté"))

    async def _async_exchange(
        self, call_type: int, command: str, *, write: bool = False,
        expected_generation: int | None = None,
    ) -> str:
        """Send one allowed relay request and wait for its correlated response."""
        async with self._io_lock:
            if write:
                if not self.connected or (
                    expected_generation is not None
                    and self.connection_generation != expected_generation
                ):
                    raise MaestroConnectionError(
                        "Commande refusée : connexion MCZ modifiée, actualiser l'état"
                    )
            else:
                await self._async_connect()
            if write:
                elapsed = (
                    asyncio.get_running_loop().time() - self._last_command_at
                )
                if elapsed < COMMAND_MIN_INTERVAL_SECONDS:
                    await asyncio.sleep(COMMAND_MIN_INTERVAL_SECONDS - elapsed)
                if not self.connected or (
                    expected_generation is not None
                    and self.connection_generation != expected_generation
                ):
                    raise MaestroConnectionError(
                        "Commande refusée : connexion MCZ modifiée, actualiser l'état"
                    )

            loop = asyncio.get_running_loop()
            future: asyncio.Future[str] = loop.create_future()
            self._pending = future
            try:
                await self._socket.emit(
                    "chiedo",
                    {
                        **self._identity,
                        "tipoChiamata": call_type,
                        "richiesta": command,
                    },
                )
                if write:
                    # A timeout does NOT authorize an automatic retry.
                    self._last_command_at = loop.time()
                return await asyncio.wait_for(future, timeout=REQUEST_TIMEOUT)
            except asyncio.CancelledError:
                await self._async_disconnect_unlocked()
                raise
            except Exception as err:
                # A late response on the same SID must not satisfy a later
                # request. Drop the session and start with a fresh SID next time.
                await self._async_disconnect_unlocked()
                raise MaestroConnectionError(
                    "Commande MCZ sans réponse valide (aucun rejeu)"
                ) from err
            finally:
                self._pending = None

    async def async_request_parameters(self) -> MaestroParameters:
        """Fetch model safety parameters without changing stove state."""
        frame = await self._async_exchange(0, "RecuperoParametri")
        try:
            return decode_parameters_message(frame)
        except MaestroProtocolError:
            await self.async_close()
            raise

    async def async_request_info(self) -> MaestroData:
        """Fetch the decoded state from the shared decoder."""
        frame = await self._async_exchange(1, "C|RecuperoInfo")
        try:
            return decode_info_message(frame)
        except MaestroProtocolError:
            await self.async_close()
            raise

    async def async_write_parameter(
        self, cell: int, value: int, *, expected_generation: int | None = None
    ) -> None:
        """Send one write; the coordinator confirms its application by reading."""
        await self._async_exchange(
            1, f"C|WriteParametri|{cell}|{value}", write=True,
            expected_generation=expected_generation,
        )

    async def async_set_datetime(
        self, value: datetime | None = None, *, expected_generation: int | None = None
    ) -> None:
        """Synchronize time only when the coordinator permits the operation."""
        value = value or datetime.now()
        await self._async_exchange(
            1, f"C|SalvaDataOra|{value.strftime('%d%m%Y%H%M')}", write=True,
            expected_generation=expected_generation,
        )

    async def async_close(self) -> None:
        """Close this transport before HA instantiates a different one."""
        async with self._io_lock:
            await self._async_disconnect_unlocked()

    async def _async_disconnect_unlocked(self) -> None:
        if self._socket.connected:
            await self._socket.disconnect()
