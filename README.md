# KEBA P40 Custom Integration for Home Assistant

This custom integration uses the local KEBA P40 REST API. Connection data is
entered through the Home Assistant user interface; no API password needs to be
stored in `configuration.yaml` or `secrets.yaml`.

> [!IMPORTANT]
> This is an independent community project, not an official KEBA or Home
> Assistant integration. It is published as a working foundation without a
> support commitment. Pull requests are not accepted; forks and independent
> further development are explicitly welcome.

## Repository layout

- `custom_components/keba_p40/`: HACS-compatible Home Assistant integration
- `python_tool/keba_phase_toggle.py`: Standalone API and phase-toggle test tool
- `api_docs/keba-openapi.json`: KEBA REST API OpenAPI specification
- `examples/`: Legacy YAML configuration examples

The source code is available under the [MIT License](LICENSE). See
[CONTRIBUTING.md](CONTRIBUTING.md) for the fork-oriented contribution policy.
The vendor-generated OpenAPI file is provided separately as a reference; see
[api_docs/README.md](api_docs/README.md) before redistributing it.

Maintainer: [Ich-h4lt](https://github.com/Ich-h4lt)

### Standalone Python tool

The test tool requires Python 3 and `requests`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r python_tool/requirements.txt
python3 python_tool/keba_phase_toggle.py --help
```

If `--password` is omitted, the tool reads `KEBA_PASSWORD` or prompts for the
password without displaying it. Passing the password directly may store it in
the shell history.

## Features

- Setup through **Settings > Devices & services**
- Automatic JWT authentication and renewal
- Automatic wallbox selection when only one wallbox exists
- Wallbox selection during setup when several wallboxes exist
- Wallbox state
- Connected phases reported by the wallbox
- Measured active charging phases
- Offered current
- Active power
- Total energy suitable for the Home Assistant energy dashboard
- Per-phase current and voltage
- Temperature
- Session state, error code and hardware maximum current
- Vehicle connected binary sensor
- Maximum asymmetric phase current
- Adjustable `max_available_current`
- Target charging power control with automatic phase/current selection
- Buttons for switching to the next higher or lower charging profile
- Buttons for starting and stopping charging
- Charging cards with a comment, picked from the cards the wallbox knows or
  entered by hand
- One **Start charging (comment)** button per charging card
- **Session charging card** sensor showing which card the current or last
  session uses
- Actions for starting charging with or without a card ID
- Service for selecting an exact supported charging power in kW
- Service for selecting a profile by summed charging current
- Selectable one-phase or three-phase operation

The integration does not write `max_asymmetrical_phase_current`, because the
documented REST v2 API only supports reading this value.

## Wallbox prerequisites

Photovoltaic-optimized charging must be enabled for the wallbox using the
official KEBA app. In the photovoltaic charging settings:

- Enable phase switching.
- Set the communication channel for phase switching to **CPM Direct Control**.

These settings allow the integration to use the KEBA API for switching between
one-phase and three-phase operation. If phase switching is disabled or another
communication channel is selected, the phase control entity may be rejected by
the wallbox.

For the stepped charging scheme below,
`max_asymmetrical_phase_current` should be configured manually on the wallbox
to **16 A**. The REST v2 API used by this integration can read this value but
cannot change it.

Be aware that `max_available_current` is applied differently depending on the
active phase mode:

- With one-phase charging, `max_available_current` limits the current on that
  single phase.
- With three-phase charging, `max_available_current` applies to each phase. A
  setting of 10 A therefore permits up to 10 A per phase, or 30 A in total
  across all three phases.

The configured `max_asymmetrical_phase_current` can impose an additional limit
when charging on a single phase. Select both values with the electrical
installation, grid operator requirements and wallbox configuration in mind.

### Charging power reference

With `max_asymmetrical_phase_current` set to 16 A, charging power can be
controlled granularly from approximately 1.4 kW to 3.7 kW using one phase.
Switching to three phases at 6 A continues at approximately 4.2 kW and allows
scaling up to 22 kW, depending on your grid connection and electrical
installation.

The **Target charging power** select offers fixed profiles in 1 A increments.
Each option sets `max_available_current` and switches between one and three
phases as required. Arbitrary intermediate values cannot be selected.

The wallbox applies phase and current changes asynchronously. The final state
is normally reflected in Home Assistant after 20 to 30 seconds. Reducing the polling interval does
not speed up the switching process inside the wallbox.

The REST API does not expose the current phase-toggle state. The integration
therefore stores the last successfully requested phase target and uses it for
the phase select, charging profiles and increase/decrease buttons. Changes made
outside this integration cannot be detected while the wallbox is idle.

During charging, **Measured active phases** counts phases carrying more than
0.5 A. This sensor is unavailable while no phase carries charging current.
**Connected phases** only describes the physical wallbox connection and does
not indicate the phase-toggle state.

| | 1-phase range | ... | Phase switch | ... | Typical 11 kW | ... | 3-phase maximum |
|---|---:|---:|---:|---:|---:|---:|---:|
| Phases | 1 | ... | 3 | ... | 3 | ... | 3 |
| Current per phase (`max_available_current`) | 6–16 A | ... | 6 A | ... | 16 A | ... | 32 A |
| Summed phase current (service target) | 6–16 A | ... | 18 A | ... | 48 A | ... | 96 A |
| Approx. power | 1.4–3.7 kW | ... | 4.2 kW | ... | 11.1 kW | ... | 22.2 kW |

The summed phase current is used only as a convenient service target. For
example, 48 A means 16 A on each of three phases, not 48 A on one conductor.

### Charging power targets

For automations, use `keba_p40.set_charging_power_target` with a float value in
kW. Only the exact values listed below are accepted. Available targets depend
on the maximum current supported by the wallbox. A 32 A wallbox exposes:

<details>
<summary>One-phase profiles</summary>

- `1.4` → 1 phase, 6 A
- `1.6` → 1 phase, 7 A
- `1.8` → 1 phase, 8 A
- `2.1` → 1 phase, 9 A
- `2.3` → 1 phase, 10 A
- `2.5` → 1 phase, 11 A
- `2.8` → 1 phase, 12 A
- `3.0` → 1 phase, 13 A
- `3.2` → 1 phase, 14 A
- `3.5` → 1 phase, 15 A
- `3.7` → 1 phase, 16 A

</details>

<details>
<summary>Three-phase profiles</summary>

- `4.2` → 3 phases, 6 A per phase
- `4.8` → 3 phases, 7 A per phase
- `5.5` → 3 phases, 8 A per phase
- `6.2` → 3 phases, 9 A per phase
- `6.9` → 3 phases, 10 A per phase
- `7.6` → 3 phases, 11 A per phase
- `8.3` → 3 phases, 12 A per phase
- `9.0` → 3 phases, 13 A per phase
- `9.7` → 3 phases, 14 A per phase
- `10.4` → 3 phases, 15 A per phase
- `11.1` → 3 phases, 16 A per phase
- `11.8` → 3 phases, 17 A per phase
- `12.5` → 3 phases, 18 A per phase
- `13.2` → 3 phases, 19 A per phase
- `13.9` → 3 phases, 20 A per phase
- `14.5` → 3 phases, 21 A per phase
- `15.2` → 3 phases, 22 A per phase
- `15.9` → 3 phases, 23 A per phase
- `16.6` → 3 phases, 24 A per phase
- `17.3` → 3 phases, 25 A per phase
- `18.0` → 3 phases, 26 A per phase
- `18.7` → 3 phases, 27 A per phase
- `19.4` → 3 phases, 28 A per phase
- `20.1` → 3 phases, 29 A per phase
- `20.8` → 3 phases, 30 A per phase
- `21.5` → 3 phases, 31 A per phase
- `22.2` → 3 phases, 32 A per phase

</details>

### Charging current target

For automations that work with current rather than profile names, use
`keba_p40.set_charging_current_target`. Its integer value represents the
summed target current:

- `6` through `16` select the matching one-phase profile.
- `18` selects three phases at 6 A (`3 × 6 A`).
- Further three-phase steps are `21`, `24`, `27`, and so on, up to three times
  the wallbox maximum current.

Values such as `17`, `19`, or `20` are rejected because they do not correspond
to one of the fixed profiles.

### Switching between adjacent profiles

The integration provides two button entities for moving through the same
ordered profile list:

- **Increase charging power** switches to the next higher profile.
- **Decrease charging power** switches to the next lower profile.

The buttons adjust `max_available_current` and switch phases automatically.
This also covers the transition between `3.7 kW (1-phase, 16 A)` and
`4.2 kW (3-phase, 6 A)`.

The decrease button is unavailable at the minimum profile
`1.4 kW (1-phase, 6 A)`. The increase button is unavailable at the maximum
profile supported by the wallbox.

```yaml
actions:
  - action: button.press
    target:
      entity_id: button.keba_p40_increase_charging_power

  - action: button.press
    target:
      entity_id: button.keba_p40_decrease_charging_power
```

The API calls used by this integration have been tested with wallbox firmware
version **1.4.4 and newer**. Older versions may expose different endpoints or
behavior and are currently untested.

## OCPP and network note

During testing with a DKV integration using GreenFlux (`greenflux.com`), the
OCPP connection was unstable while the wallbox had both its cellular
connection and normal network access enabled.

In that environment, the connection became stable after placing the wallbox in
a restricted DMZ network. The wallbox received an IP address and subnet mask
through DHCP, but no default gateway and no DNS server. This kept the wallbox
reachable by Home Assistant on the local network while preventing the Ethernet
connection from interfering with its cellular OCPP connection.

Access from Home Assistant to this isolated DMZ was provided through source NAT
(SNAT). From the wallbox perspective, API requests therefore originated from
an address inside its local DMZ subnet, so no default gateway was required for
the response traffic.

This is an environment-specific workaround rather than a general KEBA, DKV or
GreenFlux recommendation. Network behavior can depend on the wallbox firmware,
OCPP provider and local routing setup. Ensure that Home Assistant can route to
the isolated wallbox network before applying this configuration.

## Installation

The integration requires Home Assistant 2025.4 or newer.

### HACS

Until this repository is included in the default HACS catalog, add it as a
custom repository:

1. Open **HACS > Integrations**.
2. Open the menu and select **Custom repositories**.
3. Add
   `https://github.com/Ich-h4lt/keba-p40-home-assistant`
   with category **Integration**.
4. Search for **KEBA P40** and install it.
5. Restart Home Assistant.

After the restart, continue with the configuration steps below.

### Manual installation

Copy the integration directory:

```text
custom_components/keba_p40
```

to your Home Assistant configuration:

```text
/config/custom_components/keba_p40
```

The resulting structure must look like this:

```text
/config/custom_components/keba_p40/
  __init__.py
  api.py
  binary_sensor.py
  button.py
  cards.py
  charging.py
  config_flow.py
  const.py
  coordinator.py
  entity.py
  manifest.json
  number.py
  select.py
  sensor.py
  services.py
  services.yaml
  strings.json
  translations/de.json
  translations/en.json
```

Restart Home Assistant after copying the files.

## Configuration

1. Open **Settings > Devices & services**.
2. Select **Add integration**.
3. Search for **KEBA P40**.
4. Enter the wallbox IP address, REST API port and password.
5. Keep port `8443` unless the KEBA configuration uses another port.
6. Leave SSL verification disabled for the default self-signed certificate.

If several wallboxes are managed by the device, a second dialog asks which
serial number should be added.

Connection settings can later be changed under the integration's
**Configure** dialog. The options include:

- IP address or hostname
- REST API port
- Password
- SSL certificate verification
- Polling interval from 5 to 300 seconds

Each poll reads the wallbox status and the load management one after another
over the same HTTPS connection. The default interval is 5 seconds.

> **Choose the interval clearly below or clearly above 10 seconds.** The
> wallbox hard-closes an idle HTTPS connection after about 10 seconds with a
> TCP reset. With an interval below that (for example 5 seconds) one connection
> stays open and no TLS handshake is needed per poll. With a much longer
> interval (for example 30 seconds or more) every poll opens a new connection,
> but only rarely. Values around 10 to 15 seconds are the worst case: the
> connection is reset right before it would be reused.

If authentication fails, Home Assistant starts a reauthentication flow and
asks for the current password.

## Charging cards

On wallboxes that require authorization, for example a DKV edition that
authorizes sessions through OCPP, a session is only billed to a card if the
start command names the card's RFID ID. **Start charging** always starts
without a card.

To start with a card, add it as a charging card:

1. Open **Settings > Devices & services > KEBA P40**.
2. Select **Add charging card**.
3. Choose a card the wallbox already knows, or enter the card ID. Known cards
   come from the wallbox token list and its last 50 sessions. Their IDs are
   shortened, for example `04…F6`, and shown with the date of their last use.
4. Enter a comment, for example `DKV`.

Each card gets its own button, for example **Start charging (DKV)**. Pressing
it starts charging authorized by that card:

```yaml
actions:
  - action: button.press
    target:
      entity_id: button.keba_p40_start_charging_dkv
```

Cards can be renamed or deleted on the integration page. Deleting a card also
removes its button.

The card ID is stored only in the integration configuration, like the
password. It is not part of entity IDs, unique IDs, states, attributes or log
messages, and the integration shows it only shortened. Automations use the
card's button and never need the ID.

The **Session charging card** sensor shows which card the current or last
session uses: the card's comment, **No card**, or **Unknown card** with a
shortened `card_hint` attribute. The integration reads the session list only
at startup, when a session starts or ends, and while a new session is not yet
listed, at most every 30 seconds.

## Entities

The integration creates normal Home Assistant entities. The controls can
be changed directly from a dashboard or used in automations:

- `number.*maximum_available_current`
- `select.*target_charging_power`
- `select.*phases`
- `button.*increase_charging_power`
- `button.*decrease_charging_power`
- `button.*start_charging`
- `button.*start_charging_<comment>`, one per charging card
- `button.*stop_charging`

Example automation actions:

```yaml
actions:
  - action: keba_p40.set_charging_power_target
    target:
      entity_id: select.keba_p40_target_charging_power
    data:
      power: 4.2

  - action: keba_p40.set_charging_current_target
    target:
      entity_id: select.keba_p40_target_charging_power
    data:
      current: 18

  - action: number.set_value
    target:
      entity_id: number.keba_p40_maximum_available_current
    data:
      value: 10

  - action: select.select_option
    target:
      entity_id: select.keba_p40_phases
    data:
      option: "1"

  - action: button.press
    target:
      entity_id: button.keba_p40_increase_charging_power

  - action: button.press
    target:
      entity_id: button.keba_p40_decrease_charging_power

  - action: button.press
    target:
      entity_id: button.keba_p40_start_charging

  - action: button.press
    target:
      entity_id: button.keba_p40_stop_charging

  - action: keba_p40.start_charging
    data:
      config_entry_id: 01JABCDEFGHJKMNPQRSTVWXYZ0

  - action: keba_p40.start_charging_with_token
    data:
      config_entry_id: 01JABCDEFGHJKMNPQRSTVWXYZ0
      token_id: A2D80F8E
```

Actual entity IDs depend on the wallbox name and may differ from this example.
In the action editor, `config_entry_id` is selected from a list of configured
wallboxes.

`keba_p40.start_charging` always starts without a card.
`keba_p40.start_charging_with_token` passes the card ID directly, so the ID
appears in the automation and its traces. Prefer the button of a configured
charging card.

## Dashboard

After adding the integration, open:

**Settings > Devices & services > KEBA P40 > Devices > your wallbox**

The device page lists all entities created by the integration. Open an entity
and select the settings icon to see or change its exact entity ID.

Typical entities are:

| Information or control | Entity domain | Example entity ID |
|---|---|---|
| Wallbox state | `sensor` | `sensor.keba_p40_status` |
| Connected phases | `sensor` | `sensor.keba_p40_connected_phases` |
| Measured active phases | `sensor` | `sensor.keba_p40_measured_active_phases` |
| Offered current | `sensor` | `sensor.keba_p40_offered_current` |
| Active power | `sensor` | `sensor.keba_p40_active_power` |
| Total energy | `sensor` | `sensor.keba_p40_total_energy` |
| Current L1/L2/L3 | `sensor` | `sensor.keba_p40_current_l1` |
| Voltage L1/L2/L3 | `sensor` | `sensor.keba_p40_voltage_l1` |
| Temperature | `sensor` | `sensor.keba_p40_temperature` |
| Vehicle connected | `binary_sensor` | `binary_sensor.keba_p40_vehicle_connected` |
| Session active | `binary_sensor` | `binary_sensor.keba_p40_session_active` |
| Maximum asymmetric phase current | `sensor` | `sensor.keba_p40_maximum_asymmetric_phase_current` |
| Hardware maximum current | `sensor` | `sensor.keba_p40_hardware_maximum_current` |
| Error code | `sensor` | `sensor.keba_p40_error_code` |
| Maximum available current | `number` | `number.keba_p40_maximum_available_current` |
| Target charging power | `select` | `select.keba_p40_target_charging_power` |
| Active phase selection | `select` | `select.keba_p40_phases` |
| Increase charging power | `button` | `button.keba_p40_increase_charging_power` |
| Decrease charging power | `button` | `button.keba_p40_decrease_charging_power` |
| Start charging | `button` | `button.keba_p40_start_charging` |
| Start charging with a card | `button` | `button.keba_p40_start_charging_dkv` |
| Stop charging | `button` | `button.keba_p40_stop_charging` |
| Session charging card | `sensor` | `sensor.keba_p40_session_charging_card` |

Entity IDs are generated from the device and entity names. Always confirm the
actual IDs on the device page before using the examples below.

Each entity uses the stable internal unique ID format:

```text
keba_p40_{serialNumber}_{key}
```

For example:

```text
keba_p40_12345678_total_active_power
```

Card buttons use the internal ID of the charging card instead of the card ID:
`keba_p40_{serialNumber}_start_charging_card_{cardEntryId}`.

### Entities card

Add a manual card to a dashboard and replace the entity IDs where required:

```yaml
type: entities
title: KEBA P40
entities:
  - entity: sensor.keba_p40_status
    name: Status
  - entity: binary_sensor.keba_p40_vehicle_connected
    name: Vehicle connected
  - entity: sensor.keba_p40_connected_phases
    name: Connected phases
  - entity: sensor.keba_p40_measured_active_phases
    name: Measured active phases
  - entity: sensor.keba_p40_offered_current
    name: Offered current
  - entity: sensor.keba_p40_active_power
    name: Active power
  - entity: sensor.keba_p40_total_energy
    name: Total energy
  - entity: sensor.keba_p40_current_l1
    name: Current L1
  - entity: sensor.keba_p40_current_l2
    name: Current L2
  - entity: sensor.keba_p40_current_l3
    name: Current L3
  - entity: sensor.keba_p40_voltage_l1
    name: Voltage L1
  - entity: sensor.keba_p40_voltage_l2
    name: Voltage L2
  - entity: sensor.keba_p40_voltage_l3
    name: Voltage L3
  - entity: sensor.keba_p40_temperature
    name: Temperature
  - entity: binary_sensor.keba_p40_session_active
    name: Session active
  - entity: sensor.keba_p40_error_code
    name: Error code
  - entity: sensor.keba_p40_maximum_asymmetric_phase_current
    name: Maximum asymmetric phase current
  - entity: sensor.keba_p40_hardware_maximum_current
    name: Hardware maximum current
  - entity: select.keba_p40_target_charging_power
    name: Target charging power
  - entity: number.keba_p40_maximum_available_current
    name: Maximum available current
  - entity: select.keba_p40_phases
    name: Phases
  - entity: button.keba_p40_decrease_charging_power
    name: Decrease charging power
  - entity: button.keba_p40_increase_charging_power
    name: Increase charging power
  - entity: button.keba_p40_start_charging
    name: Start charging
  - entity: button.keba_p40_stop_charging
    name: Stop charging
```

### Power graph

The active power sensor has the Home Assistant `power` device class and can be
displayed in a graph:

```yaml
type: history-graph
title: KEBA charging power
hours_to_show: 12
entities:
  - entity: sensor.keba_p40_active_power
    name: Active power
```

The total energy sensor uses the `total_increasing` state class and kWh as its
unit, so it can be selected as an energy source in the Home Assistant energy
dashboard.

The offered current and active power values are updated using the polling
interval configured in the integration options.

## Security

The KEBA certificate is normally self-signed. When SSL verification is
disabled, keep the API reachable only from a trusted local network.
