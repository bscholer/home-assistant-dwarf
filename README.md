# DWARF 3 for Home Assistant

See your DWARF 3 in Home Assistant: SD card, capture progress, battery, temperatures, a camera, and controls for
automations. Start read-only in a minute, and add full control later if you want it.

## Get started

1. Install **DWARF 3 Smart Telescope** from the Home Assistant marketplace and restart Home Assistant.
2. Go to **Settings → Devices & services**. If your scope is on, it may already be listed as **Discovered**. If not,
   choose **Add integration → DWARF 3**.
3. Pick **Read-only** and enter the scope's IP address (look in your router's list of devices).

That's it. Read-only never touches the scope's one control connection, so the DWARFLAB app keeps working as normal.

## Want more? Full control

Battery, temperatures, the camera, and buttons like **Prepare** and **Close barrel** need a small helper called the
relay, because the scope only shares those with whatever holds its one control connection. It takes about two minutes:

1. Add this repository to the Home Assistant app store, install the **DWARF 3 relay** app, enter your scope's IP address,
   and press **Start**.
2. Open the DWARF 3 integration, press **⋮ → Reconfigure**, and choose **Full control**. It finds the relay by itself.
3. In the DWARFLAB app, enter your Home Assistant's IP address as the scope.

Your entities and dashboards stay exactly as they were. You only gain more of them.

| | Read-only | Full control |
|---|:-:|:-:|
| Scope online, SD card free and used | ✔ | ✔ |
| Capture sessions on the card | ✔ | ✔ |
| Works with the DWARFLAB app | ✔ | ✔ (through the relay) |
| Battery, temperatures, tracking | | ✔ |
| Capture progress, "capture finished" event | | ✔ |
| Wide camera | | ✔ |
| Buttons and services (goto, capture, darks, move, point) | | ✔ |

Without Home Assistant apps (Container or Core installs), run the relay yourself:
`docker run -d --network host -e DWARF3_HOST=<scope ip> -e DWARF3_AUTH=off -v dwarf3:/data ghcr.io/bscholer/dwarf3-control`,
then choose **Full control** and enter that machine's address.

## If something looks wrong

| You see | Try |
|---|---|
| "Nothing answered" when adding | The scope must be awake, on your Wi-Fi, and the address must be right. |
| The scope's address changed | **⋮ → Reconfigure** and enter the new one. A fixed address in your router avoids this. |
| Wide camera is blank | Press **Prepare** first. The scope only streams video after that. |
| Calibrate fails | It needs a dark sky with stars, so it fails in daylight. |
| Battery shows "unknown" | It appears about a minute after the scope connects to the relay. |
| The DWARFLAB app can't find the scope | With the relay, enter your Home Assistant's IP address in the app, not the scope's. |

Something else? **⋮ → Download diagnostics** on the device, then open an issue. Diagnostics hide your address and never
include what the scope reports about your Wi-Fi.

## Entities

- **Read-only:** scope online, SD card free, used and size, capture sessions.
- **Full control adds:** capture state (idle, running, done, failed), capture progress, frames captured and failed, battery, body
  and sensor temperatures, tracking, dark counts, relay version, **Capture finished** event, wide camera, and buttons for
  Prepare, Calibrate, Close barrel and Stop capture.

## Services (full control)

All take a DWARF 3 device as the target.

- `dwarf3.goto`: `name`, `ra_hours`, `dec_degrees` (J2000). The relay refuses a target within 30 degrees of the Sun.
- `dwarf3.start_capture`: `frames`, `exposure` (15, 30, 60), `gain`, `filter` (vis, astro, duo).
- `dwarf3.start_dark`: `frames`, `exposure`, `wide`. Close the barrel first.
- `dwarf3.move`: `angle`, `length` (0 to 1), `seconds` (up to 5).
- `dwarf3.point`: `pitch` (0 to 175, 172.5 is straight up) and optional `rotation`.
- `dwarf3.delete_session`: `session`. Cannot be undone, and is refused while a capture runs.

## Notes

- Anyone on your home network can control the scope through the relay, as they can without it. The relay app has an option to
  require an access token if you share your network.
- The relay's status refreshes every 30 s (read-only: 60 s). Change it under **Configure**.
- The tele camera is not offered: a frame can take over a minute.
- The brand images in `custom_components/dwarf3/brand/` belong to DWARFLAB, and this project is not affiliated with them.
  The MIT license covers the code.

MIT, see `LICENSE`.
