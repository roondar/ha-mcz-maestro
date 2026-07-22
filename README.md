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

Only one controller should be connected to the local Maestro WebSocket. Stop
MaestroGateway before enabling this integration.

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
