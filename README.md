# DWARF 3 for Home Assistant

Status, control, and a wide-camera snapshot for a DWARF 3 smart telescope, through the
[dwarf3 relay](https://github.com/bscholer/dwarf3-control).

This repo holds two things:

- `custom_components/dwarf3/`, the integration. Install it from the Home Assistant marketplace (add this repo as a custom repository, category Integration).
- `dwarf3_relay/`, an app that runs the relay. Add this repo's URL as a repository in the Home Assistant app store.
  On a Home Assistant install without apps, run the relay image yourself (`ghcr.io/bscholer/dwarf3-control`, host network)
  and skip the app.

The integration talks to the relay over its HTTP API and shares no code with it. It reads `/api/capabilities` and refuses a
relay whose spec major version it does not know.

## Two ways to connect

When you add the integration you choose one.

**Read-only, straight from the scope.** Nothing to install. You give the integration the scope's IP address and it reads what the
scope gives out over plain HTTP and FTP: whether it is reachable, the SD card free, used and size (size only if the scope reports it),
and the capture sessions. It never takes the scope's one control connection, so the DWARFLAB app keeps working. It cannot show battery,
temperatures or state, and it has no camera or controls, because the scope only sends those to the client that holds the control connection.

**Full control, through the relay.** The relay holds that one connection and lets the DWARFLAB app, Home Assistant, and tools such as
astrolab share it. It gives everything below. The relay must be on the scope's Wi-Fi network and reachable from Home Assistant.

You can add both. Only the relay mode gives the app a place to share the connection, so do not run the relay and read-only mode
expecting the app to see Home Assistant's stats: the relay's entities are the ones that carry battery and the rest.

## Setup, full control

1. Install and start the app, with `scope_host` set to the scope's IP. Read the API token in the app log, or set your own.
2. Enter the Home Assistant host's IP in the DWARFLAB app as the scope.
3. Add the **DWARF 3 Smart Telescope** integration, choose **Full control**, and give it the host, port 9902, and the token.

## Entities (full control)

| Kind | Entities |
|---|---|
| Sensor | Capture state (idle, running, done, failed), capture progress, frames captured, battery, body temperature, SD card free and used, capture sessions |
| Sensor, diagnostic | Frames failed, tele and wide sensor temperature, tele and wide dark counts, relay version, SD card size, pitch and rotation, goto and calibration state codes (the last four are off by default) |
| Binary sensor | Tracking, scope reachable, DWARFLAB app connected, capturing from another client |
| Event | Capture finished (`capture_done` or `capture_failed`, with the frame counts and session) |
| Button | Close barrel, stop capture, prepare, calibrate |
| Camera | Wide camera snapshot |

Capture state carries `frames`, `captured`, `failed`, `session`, and `error` as attributes. Tracking, SD card size, and the state
codes need relay 0.3.0 or later and read as unknown on an older relay. The goto and calibration codes are shown as the scope sends
them, and what each number means is not confirmed yet. Capture sessions is read every 10 minutes, because it reads the scope's album.

## Services

All take a DWARF 3 device as the target.

- `dwarf3.goto`: `name`, `ra_hours`, `dec_degrees` (J2000). The relay refuses a target within 30 degrees of the Sun.
- `dwarf3.start_capture`: `frames`, `exposure` (15, 30, 60), `gain`, `filter` (vis, astro, duo).
- `dwarf3.start_dark`: `frames`, `exposure`, `wide`. Close the barrel first.
- `dwarf3.move`: `angle`, `length` (0 to 1), `seconds` (up to 5). The joystick.
- `dwarf3.point`: `pitch` (0 to 175, 172.5 is straight up) and optional `rotation`.
- `dwarf3.delete_session`: `session`. Deletes a capture session from the SD card. It cannot be undone and is refused while a capture runs.

## Auth

The relay requires a bearer token for everything but status. If the token is wrong the integration starts a reauth flow.
With `auth` off on the relay, leave the token empty.

## Limits

- Status is polled (30 s by default, set in the integration options). The relay has no event stream yet.
- Only one controller at a time works. Starting a capture from Home Assistant while another client holds the scope
  returns an error, and the *capturing from another client* sensor turns on.
- The scope only streams video after **Prepare**, so the wide camera has no image before that. Frames can take 20 s or more, so the
  camera shows the last frame while a new one loads.
- **Calibrate** needs a dark sky with stars. In daylight it fails with a focus or plate-solve error from the scope.
- The tele camera is not offered. A tele frame waits for a keyframe and can take over a minute.
- The `prepare` button needs `latitude`, `longitude` and `timezone` in the app options. Nothing is guessed.

## Brand images

`custom_components/dwarf3/brand/` holds the icon and logo, which Home Assistant 2026.3 and later shows without anything in the
brands repository. They are derived from the DWARFLAB logo and belong to DWARFLAB. The MIT license covers the code, not those images.
This project is not affiliated with DWARFLAB.

## License

MIT, see `LICENSE`.

## Diagnostics

Download diagnostics from the device page. In read-only mode it lists the names of the fields the scope returns, never their values,
because the scope's `deviceInfo` reply includes the home Wi-Fi password in clear text. The integration reads only the SD card figures.
