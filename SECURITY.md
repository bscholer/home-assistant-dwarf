# Security

## Reporting a problem

Please do not open a public issue for a security problem. Use
[private vulnerability reporting](https://github.com/bscholer/home-assistant-dwarf/security/advisories/new)
on this repository instead. This is a one-person hobby project, so expect a reply within about a week, and a fix
as soon as I can make one.

Useful things to include: the version of the integration and the relay app, whether you use Read-only or Full control,
and the steps to reproduce.

## What to know about how this works

- **The relay has no login by default.** In Full control, anyone on your network who can reach the relay can control the
  scope, as they can reach the scope itself without it. If you share your network (guests, IoT VLAN, a shared house),
  turn on the relay app's `auth` option and set an `api_token`.
- **Keep the scope and relay off the internet.** Do not forward their ports or expose them through a public reverse proxy.
- **Read-only mode** only reads from the scope. It sends no commands.
- **Diagnostics** hide your scope's address and leave out what it reports about your Wi-Fi. Check anything else you paste
  into an issue yourself.
- The integration copies its dashboard card into `config/www/dwarf` and registers it as a dashboard resource.

## Supported versions

Only the latest release gets fixes.
