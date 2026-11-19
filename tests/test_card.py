from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.dwarf3.card import CARD_URL, async_remove_card, async_setup_card


async def _resources(hass: HomeAssistant):
    assert await async_setup_component(hass, "http", {})
    assert await async_setup_component(hass, "lovelace", {})
    resources = hass.data["lovelace"].resources
    if not resources.loaded:
        await resources.async_load()
        resources.loaded = True
    return resources


def _ours(resources):
    return [r for r in resources.async_items() if r["url"].split("?")[0] == CARD_URL]


async def test_card_is_added_once(hass: HomeAssistant):
    resources = await _resources(hass)
    await async_setup_card(hass)
    await async_setup_card(hass)
    ours = _ours(resources)
    assert len(ours) == 1
    assert ours[0]["type"] == "module"
    assert "?v=" in ours[0]["url"]


async def test_old_version_is_replaced_and_duplicates_removed(hass: HomeAssistant):
    resources = await _resources(hass)
    await resources.async_create_item({"res_type": "module", "url": f"{CARD_URL}?v=old"})
    await resources.async_create_item({"res_type": "module", "url": f"{CARD_URL}?v=older"})
    await resources.async_create_item({"res_type": "module", "url": "/local/other-card.js"})
    await async_setup_card(hass)
    ours = _ours(resources)
    assert len(ours) == 1
    assert not ours[0]["url"].endswith("v=old")
    assert any(r["url"] == "/local/other-card.js" for r in resources.async_items())


async def test_card_is_removed(hass: HomeAssistant):
    resources = await _resources(hass)
    await async_setup_card(hass)
    await async_remove_card(hass)
    assert _ours(resources) == []
