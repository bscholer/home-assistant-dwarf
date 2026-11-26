# DWARF relay

Your DWARF 3 only talks to one thing at a time. This app holds that connection and shares it, so the
DWARFLAB app and Home Assistant work together.

## Set up

1. Enter your scope's IP address under **Configuration**. Press **Save**, then **Start**.
2. In Home Assistant, add the **DWARF 3** integration and choose **Full control**. It finds this app by itself.
3. In the DWARFLAB app, enter this Home Assistant's IP address as the scope.

## Good to know

- **Prepare** uses your Home Assistant's location. To observe from somewhere else, fill in the optional
  latitude, longitude and time zone.
- Anyone on your home network can control the scope through the relay, as they can without it. Turn on
  **Require an access token** if you share your network. The token appears in the **Log** tab.
- The scope's IP address can change. Give it a fixed address in your router so you only enter it once.
