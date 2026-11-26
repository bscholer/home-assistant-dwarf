"""DWARF mini and DWARF II: best effort from what the relay and dwarf_python_api know. Not run on hardware."""

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.dwarf.const import DOMAIN, model_from_device_info

from .test_integration import BASE, DEVICE_INFO, SCOPE, mock_relay, setup, setup_direct

MINI_CAPS = {
    "spec_version": "0.2",
    "service": {"name": "dwarf-relay", "model": "DWARF mini", "version": "0.6.0"},
    "capabilities": ["status", "goto", "capture", "pointing", "darks"],
    "capture": {"filters": ["astro", "duo"], "exposures": ["10", "15", "30", "60", "120", "180"], "wide_darks": True},
}


@pytest.mark.parametrize(
    "info, model",
    [
        ({"deviceId": 1}, "DWARF II"),
        ({"deviceId": 2}, "DWARF 3"),
        ({"deviceId": 4}, "DWARF mini"),
        ({"deviceName": "DWARF_mini_1A2B3C"}, "DWARF mini"),
        ({"deviceName": "DWARF3_3AD246"}, "DWARF 3"),
        ({}, None),
    ],
)
def test_model_from_device_info(info, model):
    assert model_from_device_info(info) == model


def _online(hass):
    return next(s for s in hass.states.async_all("binary_sensor") if s.attributes.get("device_class") == "connectivity")


def _device(hass, entry):
    return dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})


async def test_a_mini_behind_the_relay(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    aioclient_mock.get(f"{BASE}/api/capabilities", json=MINI_CAPS)  # registered first, so it answers
    mock_relay(aioclient_mock)
    entry = await setup(hass)

    assert _device(hass, entry).model == "DWARF mini"
    online = _online(hass)
    assert online.entity_id.startswith("binary_sensor.dwarf_mini_"), "a new install is named after its model"
    assert online.attributes["model"] == "DWARF mini"
    assert online.attributes["filters"] == ["astro", "duo"] and online.attributes["exposures"][-1] == "180"

    point_up = "button.dwarf_mini_point_straight_up"
    assert hass.states.get(point_up)
    with pytest.raises(HomeAssistantError, match="not known for the DWARF mini"):
        await hass.services.async_call("button", "press", {"entity_id": point_up}, blocking=True)


async def test_an_older_relay_keeps_the_dwarf_3_choices(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    mock_relay(aioclient_mock)
    entry = await setup(hass)
    assert _device(hass, entry).model == "DWARF 3"
    online = _online(hass)
    assert online.attributes["filters"] == ["vis", "astro", "duo"]
    assert online.attributes["exposures"] == ["15", "30", "60"]


async def test_read_only_mode_learns_the_model_from_the_scope(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, monkeypatch
):
    aioclient_mock.post(f"{SCOPE}/deviceInfo", json={**DEVICE_INFO, "data": {**DEVICE_INFO["data"], "deviceId": 1}})
    entry = await setup_direct(hass, monkeypatch)
    assert _device(hass, entry).model == "DWARF II"
    assert entry.runtime_data.client.model == "DWARF II"


def test_read_only_mode_finds_the_album_folder_of_each_model():
    import ftplib

    from custom_components.dwarf.direct import ScopeDirectClient

    class FTP:
        def __init__(self, folders):
            self.folders, self.visited = folders, []

        def cwd(self, path):
            self.visited.append(path)
            if path not in self.folders and path != "/":
                raise ftplib.error_perm("550 no such folder")

    client = ScopeDirectClient(None, "scope.test")
    assert client._root(FTP(set())) == "/Astronomy", "a DWARF 3 needs no look"

    client.set_model("DWARF II")
    ftp = FTP({"/Astronomy"})
    assert client._root(ftp) == "/Astronomy", "falls back when /DWARF_II/Astronomy is missing"
    assert ftp.visited[0] == "/DWARF_II/Astronomy"

    client.set_model("DWARF mini")
    assert client._root(FTP({"/DWARF_mini/Astronomy"})) == "/DWARF_mini/Astronomy"
