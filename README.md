# MCZ Maestro for Home Assistant

Local Home Assistant integration for MCZ pellet stoves using the Maestro
WebSocket protocol directly. It does not require MaestroGateway or MQTT.

> [!WARNING]
> This is an independent community integration, not an official MCZ product.
> A pellet stove is a combustion appliance: keep the physical controls and the
> manufacturer's safety systems available, and validate behavior on your exact
> stove model before relying on automations.

## Features

- Local polling over the Maestro WebSocket connection.
- Climate entity for power and target temperature.
- Dynamic/automatic and manual operating modes.
- Manual P1–P5 power selection when Dynamic mode is disabled.
- Front and ducted fan controls based on model capabilities.
- Stove state, temperatures, alarms, maintenance and operating counters.
- Ambient-probe fault handling, including Maestro sentinel values.
- Model parameters loaded from the stove before controls are exposed.
- Serialized commands with delayed confirmation and no automatic command replay.

Eco and silent mode entities are disabled by default until they have been
validated on the exact stove model.

## Safety behavior

The integration fails closed when the latest complete state is stale, invalid,
in alarm or in diagnostic mode. It also:

- requires a valid ambient probe before ignition;
- validates fan and power combinations using the stove's model parameters;
- rejects manual P1–P5 commands while Dynamic mode is active;
- permits Dynamic/manual changes only while off or at stable P1–P5;
- blocks power and mode changes during transitional states;
- sends every write once, then confirms it with read-only polling for up to
  20 seconds.

## Installation

### HACS custom repository

1. In HACS, open **Integrations**.
2. Add this repository as a custom repository of type **Integration**.
3. Install **MCZ Maestro** and restart Home Assistant.

### Manual installation

Copy `custom_components/mcz_maestro` into your Home Assistant configuration:

```text
<config>/custom_components/mcz_maestro
```

Restart Home Assistant after copying the files.

## Configuration

In Home Assistant, select **Settings → Devices & services → Add integration**,
search for **MCZ Maestro**, then enter the local host and port of the Maestro
module. The default direct-Wi-Fi endpoint is `192.168.120.1:81`.

In Direct mode, only one controller should be connected to the local Maestro
WebSocket. Stop MaestroGateway before enabling direct control. In Relay mode,
HA and Android are separate clients of the same local Socket.IO relay.

## Choose one connection mode — same Home Assistant entities

**Direct Maestro (default / legacy):** connect to the stove's WebSocket
(usually `192.168.120.1:81`). Existing entries without a connection mode
continue to work exactly as before.

**MCZ Cloud Local:** connect to the owner's Socket.IO relay
(`http://<relay-host>:9000`, for example `192.168.1.252:9000`). The
integration joins the relay as one `Android-App` client using the MCZ
serial number and MAC address from the **local HA configuration form**.
The relay retains exclusive ownership of its connection to the stove.

For an **existing installation**, open **Settings → Devices & services →
MCZ Maestro → three-dot menu → Reconfigure**, select `MCZ Cloud Local`,
then enter the relay host, port, serial number and MAC address exactly as
stored in the relay's private identity file. The form checks real
`RecuperoParametri` and `RecuperoInfo` responses **without sending any
write** before switching. To undo, Reconfigure → `Direct` and restore the
original host/port. **Do not remove and re-add the integration.**

The mode switch reloads the *same config entry* and preserves its unique ID.
All `climate.poele_mcz_maestro_stove`, sensors, selects, switches, dashboards,
timers and existing automations keep their entity IDs. There is **one active
transport at a time**; HA does not try both or fail over automatically.

The relay must have `MCZ_WRITES_ENABLED=true` to allow control; an empty
write response or rejected command must never be assumed successful.
The adapter waits for an ACK from the stove forwarded by the relay, then the
existing HA coordinator confirms the new state with fresh reads (no retries
of the write). The relay itself enforces a one-second global write interval
and may refuse writes during transient/unsafe stove states.

**Security:** the relay client is intentionally LAN/VPN-only, does not use
public MCZ infrastructure, and expects the full MCZ identity. Enter that
identity in Home Assistant only; never share it in issues, logs, commits or
screenshots. The relay has no strong per-client authentication: keep its port
restricted to your trusted network. The UI alone is not a security boundary.

**Migration safety:** review and back up the HA integration configuration,
make the first switch while the stove is in a stable state, read the
connection sensor and other values, and only then use Android/HA controls.
A failed validation leaves the old connection unchanged. Restoring Direct
uses the existing local WebSocket code. None of this requires new dashboards
or modifying automations.

## Operating modes

- **Dynamic on**: the stove manages P1–P5 automatically to approach the target
  temperature; manual power writes are rejected.
- **Dynamic off**: the user may select P1–P5 directly.

Changing between Dynamic and manual mode is supported while the stove is off or
at a stable P1–P5 state. It remains blocked during ignition, stabilization,
shutdown, cooldown, alarms and diagnostics.

## Compatibility

Developed and validated with Home Assistant 2026.7.x on an MCZ Dynamic air
stove. Other Maestro models may expose different fan or temperature parameters;
the integration reads these capabilities and refuses inconsistent models.

## License

MIT
