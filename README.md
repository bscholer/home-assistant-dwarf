# DWARF 3 for Home Assistant

See your DWARF 3 in Home Assistant: SD card, capture progress, battery, temperatures, a camera, and controls for
automations. Start read-only in a minute, and add full control later if you want it.

## Get started

1. Install **DWARF 3 Smart Telescope** from the Home Assistant marketplace and restart Home Assistant.
2. Go to **Settings → Devices & services**. If your scope is on, it may already be listed as **Discovered**: pick read-only, or full control to have the relay set up for you. If not,
   choose **Add integration → DWARF 3**.
3. Pick **Read-only** and enter the scope's IP address (look in your router's list of devices).

That's it. Read-only never touches the scope's one control connection, so the DWARFLAB app keeps working as normal.

## Want more? Full control

Battery, temperatures, the camera, and buttons like **Prepare** and **Close barrel** need a small helper called the
relay, because the scope only shares those with whatever holds its one control connection. It takes about a minute, and the
integration sets it up for you:

1. Open the DWARF 3 integration, press **⋮ → Reconfigure**, and choose **Full control**.
2. Choose **Install and set it up for me**. It adds the app repository, installs the **DWARF 3 relay** app, gives it your
   scope's address and starts it.
3. In the DWARFLAB app, enter your Home Assistant's IP address as the scope.
4. Each time you switch the scope on, press **Prepare** on the device. The camera, Calibrate, goto and capture only work after
   it. The **Needs prepare** sensor shows a problem until you have.

Your entities and dashboards stay exactly as they were. You only gain more of them. Picking **Full control** when you first add
the integration works the same way.

Prefer to do it by hand? Add `https://github.com/bscholer/home-assistant-dwarf3` to the Home Assistant app store, install **DWARF 3
relay**, enter your scope's IP address and start it. The integration finds it by itself.

| | Read-only | Full control |
|---|:-:|:-:|
| Scope online, SD card free and used | ✔ | ✔ |
| Capture sessions on the card | ✔ | ✔ |
| Latest stack image, and every stack in Media | ✔ | ✔ |
| Works with the DWARFLAB app | ✔ | ✔ (through the relay) |
| Battery, temperatures, tracking | | ✔ |
| Capture progress, "capture finished" event | | ✔ |
| Live wide and tele video | ✔ (plays while the app has the camera on) | ✔ |
| Buttons and services (goto, capture, darks, move, point) | | ✔ |

Without Home Assistant apps (Container or Core installs), run the relay yourself:
`docker run -d --network host -e DWARF3_HOST=<scope ip> -e DWARF3_AUTH=off -v dwarf3:/data ghcr.io/bscholer/dwarf3-control`,
then choose **Full control** and enter that machine's address.

## Dashboard card

The integration installs a **DWARF 3** card for you. Edit a dashboard, choose **Add card** and search for DWARF 3. It
has the live view with a joystick, a shutter button with capture settings, goto with a list of targets and their height in
your sky, a gallery of the stacks on the SD card, and the device controls. In a panel view it fills the screen: the controls sit beside the live view on a desktop or a landscape tablet, and below it
on a portrait tablet or a phone.

```yaml
type: custom:dwarf3-card
device_id: <optional, the first DWARF 3 is used when left out>
theme: auto  # or light, dark. auto follows Home Assistant
```

After an update, reload the page if the card looks old. The card uses the Barlow font (SIL Open Font License, in
`frontend/fonts`).

## If something looks wrong

| You see | Try |
|---|---|
| "Nothing answered" when adding | The scope must be awake, on your Wi-Fi, and the address must be right. |
| The scope's address changed | **⋮ → Reconfigure** and enter the new one. A fixed address in your router avoids this. |
| **Needs prepare** shows a problem, or the wide camera is blank | Press **Prepare**. The scope only reports its position and streams video after that. |
| Calibrate fails | It needs a dark sky with stars, so it fails in daylight. |
| Battery shows "unknown" | It appears about a minute after the scope connects to the relay. |
| The DWARFLAB app can't find the scope | With the relay, enter your Home Assistant's IP address in the app, not the scope's. |

Something else? **⋮ → Download diagnostics** on the device, then open an issue. Diagnostics hide your address and never
include what the scope reports about your Wi-Fi.

## Entities

- **Read-only:** scope online, SD card free, used and size, capture sessions.
- **Full control adds:** capture state (idle, running, done, failed), capture progress, frames captured and failed, battery, body
  and sensor temperatures, tracking, **Needs prepare**, dark counts, relay version, **Capture finished** event, wide and tele cameras (live video and stills), and buttons for
  Prepare, Calibrate, Close barrel and Stop capture.
- **Latest stack**, an image of the newest session's `stacked.jpg`, scaled to 1280 px wide. It refreshes every 30 s while a
  capture runs (if the scope rewrites the file as it stacks, it updates live) and every 10 minutes otherwise. Cast it to a smart
  display when a capture finishes:

  ```yaml
  triggers:
    - trigger: state
      entity_id: event.dwarf_3_capture_finished
  actions:
    - action: media_player.play_media
      target:
        entity_id: media_player.office_display
      data:
        media_content_type: image/jpeg
        media_content_id: media-source://image/image.dwarf_3_latest_stack
  ```
- **Media browser:** every session on the scope that has a stack is listed under **Media → DWARF 3**, newest first, with a
  thumbnail and a title like "M 81, 30 s, 2026-11-18 03:11" (the time is the scope's own clock). Play one on any display from there,
  or in an automation with `media-source://dwarf3/<entry id>/<session folder name>`. It works in read-only mode too.
- **Pitch and rotation** sensors, in degrees, like a PTZ camera's pan and tilt position. They are the scope's motor angles,
  not altitude and azimuth, because the mount is tilted. Pitch 172.5 is straight up and 0 is the closed barrel.
- **Nudge** buttons (right, up, left, down) turn the scope about 9 degrees, and **Point straight up** sets the pitch to 172.5.
  Close barrel is the park position. There are no pitch or rotation sliders, on purpose: they would be too easy to hit by
  accident. For an exact position use `dwarf3.point`.
- **Pitch and rotation** sensors, in degrees, like a PTZ camera's pan and tilt position. They are the scope's motor angles,
  not altitude and azimuth, because the mount is tilted. 172.5 pitch is straight up and 0 is the closed barrel.
- **Nudge** buttons (right, up, left, down) turn the scope about 9 degrees, and **Point straight up** sets the pitch to 172.5.
  Close barrel is the park position. There are no pitch or rotation sliders, on purpose: they would be too easy to hit by
  accident. For exact positions use `dwarf3.point`.

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
- Live video (wide and tele) is the scope's RTSP stream, played by Home Assistant. In full control it goes through the relay, which
  forwards port 554 (so the relay needs the host network, as the app does). In read-only mode it comes straight from the scope, and
  only plays while the DWARFLAB app has the camera running, since nothing here can Prepare. The scope only streams after **Prepare**.
  The tele stream waits for a keyframe, so it can take up to about 40 s to start.
- The brand images in `custom_components/dwarf3/brand/` belong to DWARFLAB, and this project is not affiliated with them.
  The MIT license covers the code.

MIT, see `LICENSE`.
