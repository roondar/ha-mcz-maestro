# MCZ Maestro for Home Assistant

Home Assistant integration for MCZ pellet stoves with **one selectable connection**: native Maestro WebSocket or the local Socket.IO relay [roondar/mcz-cloud-local](https://github.com/roondar/mcz-cloud-local). No MQTT, bridge or additional HA entity is required.

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

Only one HA transport is active at a time. The relay can continue serving the
MCZ Android app in parallel with Home Assistant.

### Switch an existing installation without losing entities

1. Update the integration from HACS **only after the PR is merged and deployment approved**.
2. Go to **Settings → Devices & services → MCZ Maestro → Configure**.
3. Select **Cloud local — MCZ Socket.IO relay**.
4. Enter the relay host (default `192.168.1.252`) and port (`9000`).
5. Enter the stove **serial number** and **MAC address** in the password fields
   (exactly the same formatting as the relay's private identity file).
   Leave these fields blank on later visits to keep the existing values.
6. Submit. Home Assistant unloads the old client, loads only the selected
   transport and verifies `RecuperoParametri` + `RecuperoInfo` during setup.
   If setup fails, the entry reports an error; **no command is sent**.
7. Check the connection entity and the existing Chauffage, Réglages and
   Diagnostic views. Test a simple temperature change only with human approval.

**Existing version 0.2.6 entries default to Direct**, retaining their original
`host`, `port`, config-entry unique ID, device identifiers and entity IDs.
Both sets of connection settings are kept separately in the entry options.
The cloud identity is stored only in Home Assistant's config entry options,
not in YAML, Git, diagnostics or logs. Treat HA backups as confidential.

**Rollback:** In the same Configure dialog, choose **Direct** and use the
saved stove host and port. If the integration does not load, revert HACS to
the previous version and restart HA (the original `data.host` / `data.port`
are never migrated or deleted). Do not remove/re-add the integration.

The Options Flow validates field formats without opening a second connection.
The actual connection/read test runs on the exclusive entry reload. A failed
connection is never followed by an automatic write retry.

Only one controller should be connected to the **native** Maestro WebSocket.
Stop MaestroGateway before connecting directly. The local relay's guarded
write policy remains authoritative for Cloud mode.

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
