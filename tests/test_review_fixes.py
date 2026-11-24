"""Things a reviewer would check: one reload, the card coming back, discovery following an address, no collisions."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.dwarf3.card import CARD_URL, LOCAL_CARD_URL
from custom_components.dwarf3.const import CONF_TOKEN, DOMAIN

from .test_card import _ours, _resources
from .test_integration import DEVICE_INFO, SCOPE, USER, mock_relay, setup, setup_direct

MAC = "9c:b8:b4:57:d0:ec"


def _dhcp(ip: str) -> DhcpServiceInfo:
    return DhcpServiceInfo(ip=ip, hostname="dwarf", macaddress=MAC.replace(":", ""))


async def test_a_scope_added_by_hand_learns_its_mac_and_follows_a_new_address(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, monkeypatch
):
    aioclient_mock.post(f"{SCOPE}/deviceInfo", json=DEVICE_INFO)
    aioclient_mock.post("http://new.test:8082/deviceInfo", json=DEVICE_INFO)
    entry = await setup_direct(hass, monkeypatch)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "dhcp"}, data=_dhcp("scope.test"))
    assert (result["type"], result["reason"]) == (FlowResultType.ABORT, "already_configured")
    assert entry.data["mac"] == MAC and entry.unique_id == f"direct:{MAC}", "the MAC is learned at the same address"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1

    # The DHCP lease changed: the same scope turns up at another address.
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "dhcp"}, data=_dhcp("new.test"))
    assert (result["type"], result["reason"]) == (FlowResultType.ABORT, "already_configured")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.data[CONF_HOST] == "new.test"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_a_found_scope_is_not_added_twice_by_hand(hass: HomeAssistant, aioclient_mock, monkeypatch):
    aioclient_mock.post(f"{SCOPE}/deviceInfo", json=DEVICE_INFO)
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: "scope.test", "mode": "direct", "mac": MAC}, unique_id=f"direct:{MAC}"
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "direct"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "scope.test"})
    assert (result["type"], result["reason"]) == (FlowResultType.ABORT, "already_configured")


async def test_reconfigure_cannot_take_another_entrys_address(hass: HomeAssistant, aioclient_mock):
    mock_relay(aioclient_mock)
    other = {CONF_HOST: "other.test", CONF_PORT: 9902, CONF_TOKEN: "x", "mode": "relay"}
    MockConfigEntry(domain=DOMAIN, data=other, unique_id="other.test:9902").add_to_hass(hass)
    mine = MockConfigEntry(domain=DOMAIN, data={**USER, "mode": "relay"}, unique_id="relay.test:9902")
    mine.add_to_hass(hass)
    aioclient_mock.get("http://other.test:9902/api/capabilities", json={
        "spec_version": "0.1", "service": {"name": "r"}, "capabilities": ["status"]})
    aioclient_mock.get("http://other.test:9902/api/status", json={})
    aioclient_mock.post("http://other.test:9902/api/move", json={"detail": "x", "code": "invalid_request"}, status=422)
    result = await mine.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "relay"})
    taken = {CONF_HOST: "other.test", CONF_PORT: 9902, CONF_TOKEN: "x"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], taken)
    assert (result["type"], result["reason"]) == (FlowResultType.ABORT, "already_configured")
    assert mine.unique_id == "relay.test:9902"


async def test_changing_options_reloads_once(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    mock_relay(aioclient_mock)
    entry = await setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    asked = lambda: sum(1 for m, u, *_ in aioclient_mock.mock_calls if str(u).endswith("/api/capabilities"))  # noqa: E731
    before = asked()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"scan_interval": 45})
    await hass.async_block_till_done(wait_background_tasks=True)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert asked() - before == 1, "one setup after the change, not two"


async def test_the_card_is_back_when_a_scope_is_added_again(hass: HomeAssistant, aioclient_mock):
    resources = await _resources(hass)
    mock_relay(aioclient_mock)
    entry = await setup(hass)
    assert len(_ours(resources)) == 1
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert _ours(resources) == [], "taken away with the last scope"
    await setup(hass)
    assert len(_ours(resources)) == 1, "and back without a restart"
    assert CARD_URL and LOCAL_CARD_URL
