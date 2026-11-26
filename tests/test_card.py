from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.dwarf.card import CARD_URL, LOCAL_CARD_URL, async_remove_card, async_setup_card


async def _resources(hass: HomeAssistant):
    assert await async_setup_component(hass, "http", {})
    assert await async_setup_component(hass, "lovelace", {})
    resources = hass.data["lovelace"].resources
    if not resources.loaded:
        await resources.async_load()
        resources.loaded = True
    return resources


def _ours(resources):
    return [r for r in resources.async_items() if r["url"].split("?")[0] in (CARD_URL, LOCAL_CARD_URL)]


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


def test_card_fonts_ship_with_the_card():
    from custom_components.dwarf.card import FRONTEND_DIR

    for weight in (400, 500, 600, 700):
        assert (FRONTEND_DIR / "fonts" / f"barlow-{weight}.woff2").stat().st_size > 1000
    assert (FRONTEND_DIR / "fonts" / "OFL.txt").exists()


async def test_card_is_copied_to_www_and_served_from_local(hass: HomeAssistant, card_www: Path):
    www = card_www
    www.mkdir()
    resources = await _resources(hass)
    await async_setup_card(hass)
    assert (www / "dwarf" / "dwarf-card.js").exists()
    assert (www / "dwarf" / "fonts" / "barlow-500.woff2").exists()
    assert _ours(resources)[0]["url"].startswith(f"{LOCAL_CARD_URL}?v=")
    await async_remove_card(hass)
    assert not (www / "dwarf").exists()


async def test_without_www_at_startup_the_card_uses_its_own_route(hass: HomeAssistant, card_www: Path):
    resources = await _resources(hass)
    assert not card_www.exists()
    await async_setup_card(hass)
    assert _ours(resources)[0]["url"].startswith(f"{CARD_URL}?v=")
    # Copied anyway, so /local serves it after the next restart.
    assert (card_www / "dwarf" / "dwarf-card.js").exists()


async def test_a_card_from_before_the_rename_is_replaced(hass, card_www):
    """0.8 and older called the integration dwarf3. Its dashboard resource and www copy must not linger."""
    old = card_www / "dwarf3"
    old.mkdir(parents=True)
    (old / "dwarf3-card.js").write_text("// the old card")
    from custom_components.dwarf import card

    assert card._is_ours("/local/dwarf3/dwarf3-card.js?v=abc")
    assert card._is_ours("/dwarf3_frontend/dwarf3-card.js")
    assert not card._is_ours("/local/somebody-else/card.js")
    await hass.async_add_executor_job(card._install, card_www)
    assert not old.exists()
    assert (card_www / "dwarf" / "dwarf-card.js").exists()
