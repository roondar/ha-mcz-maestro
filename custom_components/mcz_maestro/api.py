"""Asynchronous local WebSocket client for MCZ Maestro stoves."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import logging
from typing import Any

from aiohttp import ClientError, ClientSession, ClientWebSocketResponse, WSMsgType

from .const import (
    COMMAND_MIN_INTERVAL_SECONDS,
    REQUEST_TIMEOUT,
    TEMPERATURE_STATUS_DISCONNECTED,
    TEMPERATURE_STATUS_FAULT,
    TEMPERATURE_STATUS_OK,
    TEMPERATURE_STATUS_THERMOSTAT_OFF,
    TEMPERATURE_STATUS_THERMOSTAT_ON,
)

_LOGGER = logging.getLogger(__name__)


class MaestroError(Exception):
    """Base exception for MCZ Maestro communication errors."""


class MaestroConnectionError(MaestroError):
    """Raised when the stove cannot be reached."""


class MaestroProtocolError(MaestroError):
    """Raised when the stove returns an invalid information frame."""


@dataclass(slots=True)
class MaestroData:
    """Decoded data from one RecuperoInfo response."""

    values: dict[str, Any]
    raw: dict[str, int]
    temperature_statuses: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MaestroParameters:
    """Safety-relevant values from one RecuperoParametri response."""

    raw: tuple[int, ...]
    target_temperature_min: float
    target_temperature_max: float
    target_temperature_step: float
    power_min: int
    power_max: int
    fan_coefficient: int
    fan_present: tuple[bool, bool, bool]
    fan_enabled: tuple[bool, bool, bool]
    fan_min: tuple[int, int, int]
    fan_max: tuple[int, int, int]
    fan_supports_auto: tuple[bool, bool, bool]
    fan_supports_off: tuple[bool, bool, bool]


# Indexes include the leading message type at index zero.
_INFO_FIELDS: dict[int, tuple[str, str]] = {
    1: ("stove_state", "int"),
    2: ("fan_front", "int"),
    3: ("fan_ducted_1", "int"),
    4: ("fan_ducted_2", "int"),
    5: ("fume_temperature", "int"),
    6: ("ambient_temperature", "temperature"),
    7: ("puffer_temperature", "temperature"),
    8: ("boiler_temperature", "temperature"),
    9: ("ntc3_temperature", "temperature"),
    19: ("modbus_address", "int"),
    20: ("active_mode", "int"),
    22: ("control_mode", "int"),
    23: ("eco_mode", "int"),
    24: ("silent_mode", "int"),
    26: ("target_temperature", "temperature"),
    28: ("motherboard_temperature", "temperature"),
    29: ("power_level", "int"),
    30: ("firmware_version", "int"),
    31: ("database_id", "int"),
    37: ("total_operating_seconds", "int"),
    43: ("hours_to_service", "int"),
    45: ("number_of_ignitions", "int"),
    47: ("pellet_sensor", "int"),
    59: ("return_temperature", "temperature"),
}


def decode_temperature(raw_value: int) -> tuple[float | None, str]:
    """Decode one Maestro half-degree temperature and its sentinel values."""
    if raw_value == 250:
        return None, TEMPERATURE_STATUS_THERMOSTAT_OFF
    if raw_value == 251:
        return None, TEMPERATURE_STATUS_THERMOSTAT_ON
    if raw_value == 252:
        return None, TEMPERATURE_STATUS_FAULT
    if raw_value == 255:
        return None, TEMPERATURE_STATUS_DISCONNECTED
    if 200 <= raw_value <= 240:
        return -(raw_value / 2 - 100), TEMPERATURE_STATUS_OK
    return raw_value / 2, TEMPERATURE_STATUS_OK


def decode_info_message(message: str) -> MaestroData:
    """Decode a `01|...` RecuperoInfo frame."""
    parts = message.strip().split("|")
    if not parts or parts[0].upper() != "01":
        raise MaestroProtocolError("La réponse n'est pas une trame RecuperoInfo")
    if len(parts) <= max(_INFO_FIELDS):
        raise MaestroProtocolError(
            f"Trame RecuperoInfo incomplète ({len(parts) - 1} champs)"
        )

    values: dict[str, Any] = {}
    raw: dict[str, int] = {}
    temperature_statuses: dict[str, str] = {}

    for index, (key, value_type) in _INFO_FIELDS.items():
        try:
            raw_value = int(parts[index], 16)
        except (ValueError, IndexError) as err:
            raise MaestroProtocolError(
                f"Valeur hexadécimale invalide au champ {index}"
            ) from err

        raw[key] = raw_value
        if value_type == "temperature":
            decoded, status = decode_temperature(raw_value)
            values[key] = decoded
            temperature_statuses[key] = status
        else:
            values[key] = raw_value

    values["total_operating_hours"] = round(
        values["total_operating_seconds"] / 3600, 1
    )
    return MaestroData(values, raw, temperature_statuses)


def decode_parameters_message(message: str) -> MaestroParameters:
    """Decode a `00|<hex>` RecuperoParametri frame."""
    if not message.startswith("00|"):
        raise MaestroProtocolError("La réponse n'est pas une trame RecuperoParametri")
    payload = message[3:].strip().replace("|", "")
    try:
        raw = tuple(bytes.fromhex(payload))
    except ValueError as err:
        raise MaestroProtocolError("Trame RecuperoParametri hexadécimale invalide") from err
    if len(raw) < 40:
        raise MaestroProtocolError(
            f"Trame RecuperoParametri incomplète ({len(raw)} octets)"
        )

    target_min = raw[2]
    target_max = raw[3]
    power_min = raw[6]
    power_max = raw[7]
    fan_coefficient = raw[26]
    if not 0 < target_min < target_max <= 50:
        raise MaestroProtocolError(
            f"Plage de consigne incohérente ({target_min}–{target_max} °C)"
        )
    if fan_coefficient <= 0:
        raise MaestroProtocolError("Coefficient de ventilation invalide")

    if not 1 <= power_min <= power_max <= 5:
        raise MaestroProtocolError(
            f"Plage de puissance incohérente (P{power_min}–P{power_max})"
        )

    fan_groups = (8, 14, 20)
    fan_present = tuple(raw[index] == 1 for index in fan_groups)
    fan_enabled = tuple(raw[index + 1] == 1 for index in fan_groups)
    fan_min = tuple(raw[index + 2] for index in fan_groups)
    fan_max = tuple(raw[index + 3] for index in fan_groups)
    fan_supports_auto = tuple(raw[index + 4] == 1 for index in fan_groups)
    fan_supports_off = tuple(raw[index + 5] == 1 for index in fan_groups)
    for index, present in enumerate(fan_present):
        if not present:
            continue
        if not 0 <= fan_min[index] <= fan_max[index] <= 5:
            raise MaestroProtocolError(
                f"Plage du ventilateur {index + 1} incohérente"
            )

    return MaestroParameters(
        raw=raw,
        target_temperature_min=float(target_min),
        target_temperature_max=float(target_max),
        # The half-degree capability depends on a separate firmware frame.
        # Use the universally supported integer step until that frame is validated.
        target_temperature_step=1.0,
        power_min=power_min,
        power_max=power_max,
        fan_coefficient=fan_coefficient,
        fan_present=fan_present,
        fan_enabled=fan_enabled,
        fan_min=fan_min,
        fan_max=fan_max,
        fan_supports_auto=fan_supports_auto,
        fan_supports_off=fan_supports_off,
    )


class MaestroClient:
    """Serialize reads and writes over a persistent local WebSocket."""

    def __init__(self, session: ClientSession, host: str, port: int) -> None:
        self._session = session
        self._host = host
        self._port = port
        self._websocket: ClientWebSocketResponse | None = None
        self._io_lock = asyncio.Lock()
        self._last_command_at = 0.0
        self._connection_generation = 0

    @property
    def url(self) -> str:
        """Return the local WebSocket URL."""
        return f"ws://{self._host}:{self._port}/"

    @property
    def connected(self) -> bool:
        """Return whether a usable WebSocket is open."""
        return self._websocket is not None and not self._websocket.closed

    @property
    def connection_generation(self) -> int:
        """Increment whenever a new WebSocket is established."""
        return self._connection_generation

    async def _async_connect(self) -> ClientWebSocketResponse:
        if self.connected:
            assert self._websocket is not None
            return self._websocket

        await self._async_close_unlocked()
        try:
            self._websocket = await self._session.ws_connect(
                self.url,
                heartbeat=10,
                autoclose=True,
                autoping=True,
            )
            self._connection_generation += 1
        except (ClientError, OSError, asyncio.TimeoutError) as err:
            raise MaestroConnectionError(
                f"Connexion impossible à {self.url}"
            ) from err
        _LOGGER.debug("Connected to MCZ Maestro at %s", self.url)
        return self._websocket

    async def async_request_info(self) -> MaestroData:
        """Request and decode the current stove information frame."""
        async with self._io_lock:
            try:
                websocket = await self._async_connect()
                await websocket.send_str("C|RecuperoInfo")
                async with asyncio.timeout(REQUEST_TIMEOUT):
                    while True:
                        response = await websocket.receive()
                        if response.type is WSMsgType.TEXT:
                            text = str(response.data)
                            if text.startswith("01|"):
                                return decode_info_message(text)
                            if text.startswith(("P|", "PING|")):
                                await websocket.send_str("P|PONG")
                                continue
                            _LOGGER.debug("Ignored Maestro frame: %s", text[:32])
                            continue
                        if response.type in {
                            WSMsgType.CLOSE,
                            WSMsgType.CLOSED,
                            WSMsgType.CLOSING,
                            WSMsgType.ERROR,
                        }:
                            raise MaestroConnectionError(
                                "Le WebSocket Maestro a été fermé"
                            )
            except (ClientError, OSError, asyncio.TimeoutError, MaestroError):
                await self._async_close_unlocked()
                raise

    async def async_request_parameters(self) -> MaestroParameters:
        """Request and decode the stove model parameters used for safety."""
        async with self._io_lock:
            try:
                websocket = await self._async_connect()
                await websocket.send_str("C|RecuperoParametri")
                async with asyncio.timeout(REQUEST_TIMEOUT):
                    while True:
                        response = await websocket.receive()
                        if response.type is WSMsgType.TEXT:
                            text = str(response.data)
                            if text.startswith("00|"):
                                return decode_parameters_message(text)
                            if text.startswith(("P|", "PING|")):
                                await websocket.send_str("P|PONG")
                                continue
                            _LOGGER.debug("Ignored Maestro frame: %s", text[:32])
                            continue
                        if response.type in {
                            WSMsgType.CLOSE,
                            WSMsgType.CLOSED,
                            WSMsgType.CLOSING,
                            WSMsgType.ERROR,
                        }:
                            raise MaestroConnectionError(
                                "Le WebSocket Maestro a été fermé"
                            )
            except (ClientError, OSError, asyncio.TimeoutError, MaestroError):
                await self._async_close_unlocked()
                raise

    async def async_write_parameter(self, cell: int, value: int) -> None:
        """Write one integer parameter to the stove."""
        async with self._io_lock:
            try:
                websocket = await self._async_connect()
                await self._async_rate_limit_command()
                await websocket.send_str(f"C|WriteParametri|{cell}|{value}")
                self._last_command_at = asyncio.get_running_loop().time()
            except (ClientError, OSError, asyncio.TimeoutError) as err:
                await self._async_close_unlocked()
                raise MaestroConnectionError(
                    f"Échec d'écriture du paramètre {cell}"
                ) from err

    async def async_set_datetime(self, value: datetime | None = None) -> None:
        """Synchronize the stove date and time."""
        value = value or datetime.now()
        async with self._io_lock:
            try:
                websocket = await self._async_connect()
                await self._async_rate_limit_command()
                await websocket.send_str(
                    f"C|SalvaDataOra|{value.strftime('%d%m%Y%H%M')}"
                )
                self._last_command_at = asyncio.get_running_loop().time()
            except (ClientError, OSError, asyncio.TimeoutError) as err:
                await self._async_close_unlocked()
                raise MaestroConnectionError(
                    "Échec de synchronisation de l'heure"
                ) from err

    async def _async_rate_limit_command(self) -> None:
        """Prevent command bursts even when several HA services run together."""
        elapsed = asyncio.get_running_loop().time() - self._last_command_at
        if elapsed < COMMAND_MIN_INTERVAL_SECONDS:
            await asyncio.sleep(COMMAND_MIN_INTERVAL_SECONDS - elapsed)

    async def async_close(self) -> None:
        """Close the WebSocket connection."""
        async with self._io_lock:
            await self._async_close_unlocked()

    async def _async_close_unlocked(self) -> None:
        websocket = self._websocket
        self._websocket = None
        if websocket is not None and not websocket.closed:
            await websocket.close()
