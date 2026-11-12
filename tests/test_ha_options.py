"""Options-flow compatibility with Home Assistant; no network or stove."""
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")
probatio = pytest.importorskip("probatio")

from homeassistant.data_entry_flow import FlowResultType  # noqa: E402
from custom_components.mcz_maestro.config_flow import MczMaestroOptionsFlow  # noqa: E402


@pytest.mark.asyncio
async def test_options_forms_and_round_trip_preserve_entry_identity():
    entry = SimpleNamespace(
        entry_id="existing", unique_id="192.168.120.1:81",
        data={"host": "192.168.120.1", "port": 81}, options={},
    )
    flow = MczMaestroOptionsFlow()
    flow.hass = SimpleNamespace(config_entries=SimpleNamespace(
        async_get_known_entry=lambda entry_id: entry
    ))
    flow.handler = entry.entry_id
    flow.flow_id = "test"
    initial = await flow.async_step_init()
    assert initial["type"] == FlowResultType.FORM
    assert isinstance(initial["data_schema"], probatio.Schema)
    cloud_form = await flow.async_step_init({"transport": "cloud"})
    assert isinstance(cloud_form["data_schema"], probatio.Schema)
    # Synthetically invalid inputs must raise the exception HA 2026.11 handles.
    with pytest.raises(probatio.Invalid):
        cloud_form["data_schema"]({"cloud_host": "test", "cloud_port": 70000})
    result = await flow.async_step_cloud({
        "cloud_host": "127.0.0.1", "cloud_port": 9000,
        "cloud_serial_number": "SYNTHETIC", "cloud_mac_address": "aabbccddeeff",
    })
    assert result["type"] == FlowResultType.CREATE_ENTRY
    entry.options = result["data"]
    direct_form = await flow.async_step_init({"transport": "direct"})
    assert isinstance(direct_form["data_schema"], probatio.Schema)
    result = await flow.async_step_direct({"direct_host": "192.168.120.1", "direct_port": 81})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["transport"] == "direct"
    assert entry.unique_id == "192.168.120.1:81"
    assert entry.data == {"host": "192.168.120.1", "port": 81}


@pytest.mark.asyncio
async def test_cloud_startup_retries_after_relay_becomes_available():
    """A failed initial read asks HA to retry; it never changes transport."""
    from unittest.mock import AsyncMock, patch

    from homeassistant.exceptions import ConfigEntryNotReady

    from custom_components.mcz_maestro import async_setup_entry
    from custom_components.mcz_maestro.api import MaestroConnectionError
    from custom_components.mcz_maestro.const import DOMAIN

    entry = SimpleNamespace(
        entry_id="existing",
        unique_id="192.168.120.1:81",
        data={"host": "192.168.120.1", "port": 81},
        options={
            "transport": "cloud",
            "cloud_host": "127.0.0.1",
            "cloud_port": 9000,
            "cloud_serial_number": "SYNTHETIC",
            "cloud_mac_address": "aabbccddeeff",
        },
    )
    forward = AsyncMock()
    hass = SimpleNamespace(
        data={},
        config_entries=SimpleNamespace(async_forward_entry_setups=forward),
    )
    unavailable = SimpleNamespace(
        async_request_parameters=AsyncMock(
            side_effect=MaestroConnectionError("relay offline")
        ),
        async_close=AsyncMock(),
    )
    recovered = SimpleNamespace(
        async_request_parameters=AsyncMock(return_value=object()),
        async_close=AsyncMock(),
    )
    coordinator = SimpleNamespace(async_config_entry_first_refresh=AsyncMock())

    with (
        patch(
            "custom_components.mcz_maestro.MaestroCloudClient",
            side_effect=[unavailable, recovered],
        ) as cloud_factory,
        patch(
            "custom_components.mcz_maestro.MaestroCoordinator",
            return_value=coordinator,
        ),
    ):
        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, entry)
        unavailable.async_close.assert_awaited_once()
        assert hass.data == {}
        forward.assert_not_awaited()

        # Simulate HA's next setup attempt after the relay is restored.
        assert await async_setup_entry(hass, entry) is True
        recovered.async_request_parameters.assert_awaited_once()
        coordinator.async_config_entry_first_refresh.assert_awaited_once()
        forward.assert_awaited_once()
        assert hass.data[DOMAIN][entry.entry_id] is coordinator
        assert cloud_factory.call_count == 2

    assert entry.unique_id == "192.168.120.1:81"
    assert entry.options["transport"] == "cloud"

def test_climate_uses_native_temperature_properties():
    """Climate values keep their semantics without HA's deprecated aliases."""
    from homeassistant.const import UnitOfTemperature
    from custom_components.mcz_maestro.climate import MaestroClimate

    assert MaestroClimate._attr_native_temperature_unit == UnitOfTemperature.CELSIUS
    assert "_attr_temperature_unit" not in MaestroClimate.__dict__
    assert "current_temperature" not in MaestroClimate.__dict__
    assert "target_temperature" not in MaestroClimate.__dict__

    fake = SimpleNamespace(coordinator=SimpleNamespace(data=SimpleNamespace(
        values={"ambient_temperature": 19.0, "target_temperature": 20.5}
    )))
    assert MaestroClimate.native_current_temperature.fget(fake) == 19.0
    assert MaestroClimate.native_target_temperature.fget(fake) == 20.5
