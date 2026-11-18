# DWARF 3 for Home Assistant

Status, control, and a wide-camera snapshot for a DWARF 3 smart telescope, through the
[dwarf3 relay](https://github.com/bscholer/dwarf3-control).

This repo holds two things:

- `custom_components/dwarf3/`, the integration. Install it with HACS (custom repository, category Integration).
- `dwarf3_relay/`, an add-on that runs the relay. Add this repo's URL under **Settings → Add-ons → Add-on Store → Repositories**.
  On a Home Assistant install without add-ons, run the relay image yourself (`ghcr.io/bscholer/dwarf3-control`, host network)
  and skip the add-on.

The integration talks to the relay over its HTTP API and shares no code with it. It reads `/api/capabilities` and refuses a
relay whose spec major version it does not know.

## Why a relay

The scope accepts one control client. The relay holds that connection and lets the DWARFLAB app, Home Assistant, and tools
such as astrolab share it. The relay must be on the scope's Wi-Fi network and reachable from Home Assistant.

## Setup

1. Install and start the add-on, with `scope_host` set to the scope's IP. Read the API token in the add-on log, or set your own.
2. Enter the Home Assistant host's IP in the DWARFLAB app as the scope.
3. Add the **DWARF 3 Smart Telescope** integration with the host, port 9902, and the token.

## Entities

| Kind | Entities |
|---|---|
| Sensor | Capture state (idle, running, done, failed), frames captured, battery, body temperature, SD card free |
| Sensor, diagnostic | Frames failed, tele and wide sensor temperature, pitch and rotation (off by default) |
| Binary sensor | Scope reachable, DWARFLAB app connected, capturing from another client |
| Button | Close barrel, stop capture, prepare, calibrate |
| Camera | Wide camera snapshot |

Capture state carries `frames`, `captured`, `failed`, `session`, and `error` as attributes.

## Services

- `dwarf3.goto`: `name`, `ra_hours`, `dec_degrees` (J2000). The relay refuses a target within 30 degrees of the Sun.
- `dwarf3.start_capture`: `frames`, `exposure` (15, 30, 60), `gain`, `filter` (vis, astro, duo).

Both take a DWARF 3 device as the target.

## Auth

The relay requires a bearer token for everything but status. If the token is wrong the integration starts a reauth flow.
With `auth` off on the relay, leave the token empty.

## Limits

- Status is polled (30 s by default, set in the integration options). The relay has no event stream yet.
- Only one controller at a time works. Starting a capture from Home Assistant while another client holds the scope
  returns an error, and the *capturing from another client* sensor turns on.
- The tele camera is not offered. A tele frame waits for a keyframe and can take over a minute.
- The `prepare` button needs `latitude`, `longitude` and `timezone` in the add-on options. Nothing is guessed.
