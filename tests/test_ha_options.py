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
