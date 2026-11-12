"""Socket.IO client for the optional local MCZ cloud relay.

This transport speaks the Android-App protocol. The existing direct Maestro
WebSocket transport remains unchanged. No extra HA entities or services.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import logging

from aiohttp import ClientError
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

_LOGGER = logging.getLogger(__name__)


class MaestroRelayClient:
    """One serialized Android-App session on the trusted local relay."""

    def __init__(
        self, host: str, port: int, serial_number: str, mac_address: str
    ) -> None:
        self._host = host
        self._port = port
        self._identity = {
            "serialNumber": serial_number,
            "macAddress": mac_address,
        }
        self._io_lock = asyncio.Lock()
        self._socket: socketio.AsyncClient | None = None
        self._pending: asyncio.Future[str] | None = None
        self._connection_generation = 0
        self._last_command_at = 0.0

    @property
    def connected(self) -> bool:
        """Return whether the Socket.IO namespace is connected."""
        return self._socket is not None and self._socket.connected

    @property
    def connection_generation(self) -> int:
        """New generation after each connected Socket.IO session."""
        return self._connection_generation

    async def _async_connect(self) -> socketio.AsyncClient:
        if self.connected:
            assert self._socket is not None
            return self._socket

        await self._async_close_unlocked()
        sio = socketio.AsyncClient(reconnection=False, logger=False, engineio_logger=False)
        self._socket = sio

        @sio.on("rispondo")
        async def on_response(payload: object) -> None:
            pending = self._pending
            if self._socket is not sio or pending is None or pending.done():
                return
            # The relay restores the original Socket.IO namespace SID.
            if (
                not isinstance(payload, dict)
                or payload.get("socketChiamata") != sio.get_sid("/")
                or not isinstance(payload.get("stringaRicevuta"), str)
            ):
                pending.set_exception(MaestroProtocolError("Réponse du relais invalide"))
                return
            pending.set_result(payload["stringaRicevuta"])

        @sio.event
        async def disconnect(*_args: object) -> None:
            pending = self._pending
            if self._socket is sio and pending is not None and not pending.done():
                pending.set_exception(MaestroConnectionError("Relais MCZ déconnecté"))

        try:
            await sio.connect(
                f"http://{self._host}:{self._port}",
                transports=["websocket"],
                wait_timeout=5,
            )
            # The relay requires this identity, which is stored only in the
            # Home Assistant config entry and never printed to logs.
            await sio.emit("join", {**self._identity, "type": "Android-App"})
        except (OSError, ClientError, asyncio.TimeoutError, socketio.exceptions.ConnectionError) as err:
            await self._async_close_unlocked()
            raise MaestroConnectionError("Connexion au relais MCZ impossible") from err
        self._connection_generation += 1
        _LOGGER.debug("Connected to MCZ local relay")
        return sio

    async def _async_exchange(
        self, tipo_chiamata: int, richiesta: str, *, write: bool = False
    ) -> str:
        """Send once, wait for the matching relay response, never replay."""
        async with self._io_lock:
            sio = await self._async_connect()
            if write:
                loop = asyncio.get_running_loop()
                remaining = (
                    COMMAND_MIN_INTERVAL_SECONDS
                    - (loop.time() - self._last_command_at)
                )
                if remaining > 0:
                    await asyncio.sleep(remaining)

            future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
            self._pending = future
            try:
                if write:
                    self._last_command_at = asyncio.get_running_loop().time()
                await sio.emit(
                    "chiedo",
                    {
                        **self._identity,
                        "tipoChiamata": tipo_chiamata,
                        "richiesta": richiesta,
                    },
                )
                return await asyncio.wait_for(future, REQUEST_TIMEOUT)
            except (asyncio.TimeoutError, OSError, ClientError, socketio.exceptions.ConnectionError) as err:
                await self._async_close_unlocked()
                # This may include a relay refusal. Never resend a write.
                raise MaestroConnectionError(
                    "Aucune réponse du relais MCZ ; vérifier l'état avant de réessayer"
                ) from err
            except MaestroProtocolError:
                await self._async_close_unlocked()
                raise
            finally:
                if self._pending is future:
                    self._pending = None

    async def async_request_parameters(self) -> MaestroParameters:
        """Read the real module's model parameters through the relay."""
        return decode_parameters_message(
            await self._async_exchange(0, "RecuperoParametri")
        )

    async def async_request_info(self) -> MaestroData:
        """Read a fresh full stove state through the relay."""
        return decode_info_message(
            await self._async_exchange(1, "C|RecuperoInfo")
        )

    async def async_write_parameter(self, cell: int, value: int) -> None:
        """Write one parameter; wait for the module response, not only emit."""
        reply = await self._async_exchange(
            1, f"C|WriteParametri|{cell}|{value}", write=True
        )
        if not reply:
            raise MaestroProtocolError("Accusé d'écriture vide")
        # The coordinator independently confirms the value with a fresh read.

    async def async_set_datetime(self, value: datetime | None = None) -> None:
        """Synchronize the stove clock, only after coordinator validation."""
        stamp = (value or datetime.now()).strftime("%d%m%Y%H%M")
        reply = await self._async_exchange(
            1, f"C|SalvaDataOra|{stamp}", write=True
        )
        if not reply:
            raise MaestroProtocolError("Accusé d'écriture vide")

    async def async_close(self) -> None:
        async with self._io_lock:
            await self._async_close_unlocked()

    async def _async_close_unlocked(self) -> None:
        sio = self._socket
        self._socket = None
        if sio is not None:
            try:
                await sio.disconnect()
            except (OSError, ClientError, socketio.exceptions.ConnectionError):
                pass
