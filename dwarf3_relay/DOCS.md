# DWARF 3 relay

The relay keeps one connection to the scope and shares it. The scope accepts one control client, so
without the relay the DWARFLAB app and Home Assistant would lock each other out.

## Setup

1. Set `scope_host` to the scope's IP address.
2. Start the app. If you did not set `api_token`, it makes one and prints it in the app log.
3. In the DWARFLAB app, enter this Home Assistant host's IP as the scope. The app shows it as `DWARF3_RELAY1`.
4. Add the **DWARF 3 Smart Telescope** integration and give it this host, port 9902, and the token.

## Options

| Option | Meaning |
|---|---|
| `scope_host` | IP address of the scope. Required. |
| `api_token` | Access token for control. Use a long random string, such as the output of `openssl rand -hex 24`. Empty makes one and prints it to the log. |
| `auth` | Turn off to let any device on your network control the scope. |
| `latitude`, `longitude`, `timezone` | Your site, for the Prepare button. Empty means Prepare fails. Nothing is guessed. |

`timezone` is a name such as `America/Chicago`. The UTC offset is read once at start, so restart the app after a clock change.
