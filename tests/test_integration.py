from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.dwarf3.const import CONF_TOKEN, DOMAIN

BASE = "http://relay.test:9902"
CAPS = {"spec_version": "0.1", "service": {"name": "dwarf3-relay"}, "capabilities": ["status", "goto", "capture"]}
STATUS = {
    "app_connected": True,
    "busy_elsewhere": False,
    "job": {
        "id": "ab12", "state": "running", "frames": 20, "captured": 7, "failed": 1,
        "session": "DWARF_RAW_x", "error": None,
    },
    "rotation": 10.0,
    "pitch": 172.5,
    "sd_free_gb": 55.5,
    "battery_percent": 87,
    "device_temperature_c": 31,
    "tele_sensor_temperature_c": 41,
    "wide_sensor_temperature_c": 39,
    "scope_reachable": True,
}
USER = {CONF_HOST: "relay.test", CONF_PORT: 9902, CONF_TOKEN: "secret"}


def mock_relay(mock: AiohttpClientMocker, status=STATUS, status_code=200, move_code=422):
    mock.get(f"{BASE}/api/capabilities", json=CAPS)
    mock.get(f"{BASE}/api/status", json=status, status=status_code)
    mock.post(f"{BASE}/api/move", json={"detail": "x", "code": "invalid_request"}, status=move_code)


async def setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=USER, unique_id="relay.test:9902")
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow_creates_entry(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    mock_relay(aioclient_mock)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == USER


async def test_config_flow_unreachable(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    aioclient_mock.get(f"{BASE}/api/capabilities", exc=TimeoutError)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["errors"] == {"base": "cannot_connect"}


async def test_config_flow_bad_token(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    mock_relay(aioclient_mock, move_code=401)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["errors"] == {"base": "invalid_auth"}


async def test_config_flow_refuses_other_major_version(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    aioclient_mock.get(f"{BASE}/api/capabilities", json={**CAPS, "spec_version": "1.0"})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["errors"] == {"base": "unsupported_version"}


async def test_entities_show_status(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    mock_relay(aioclient_mock)
    entry = await setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.dwarf_3_battery").state == "87"
    assert hass.states.get("sensor.dwarf_3_capture_state").state == "running"
    assert hass.states.get("sensor.dwarf_3_capture_state").attributes["captured"] == 7
    assert hass.states.get("sensor.dwarf_3_frames_captured").state == "7"
    assert hass.states.get("sensor.dwarf_3_body_temperature").state == "31"
    assert hass.states.get("binary_sensor.dwarf_3_connectivity").state == "on"
    assert hass.states.get("binary_sensor.dwarf_3_capturing_from_another_client").state == "off"


async def test_scope_asleep_keeps_the_entry_loaded(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    mock_relay(aioclient_mock, status={"detail": "scope did not answer", "code": "scope_error"}, status_code=502)
    entry = await setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("binary_sensor.dwarf_3_connectivity").state == "off"
    assert hass.states.get("sensor.dwarf_3_battery").state == "unknown"


async def test_relay_down_makes_setup_retry(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    aioclient_mock.get(f"{BASE}/api/status", exc=TimeoutError)
    entry = await setup(hass)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_rejected_token_starts_reauth(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    aioclient_mock.get(f"{BASE}/api/status", json={"detail": "no", "code": "unauthorized"}, status=401)
    entry = await setup(hass)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert any(hass.config_entries.flow.async_progress_by_handler(DOMAIN))


async def test_button_posts_with_the_token(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    mock_relay(aioclient_mock)
    aioclient_mock.post(f"{BASE}/api/close_barrel", json={"message": "closed"})
    await setup(hass)
    await hass.services.async_call("button", "press", {"entity_id": "button.dwarf_3_close_barrel"}, blocking=True)
    call = [c for c in aioclient_mock.mock_calls if c[1].path == "/api/close_barrel"][0]
    assert call[3]["Authorization"] == "Bearer secret"


async def test_goto_service(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    mock_relay(aioclient_mock)
    aioclient_mock.post(f"{BASE}/api/goto", json={"message": "ok"})
    entry = await setup(hass)
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    await hass.services.async_call(
        DOMAIN, "goto", {"device_id": device.id, "name": "M42", "ra_hours": 5.59, "dec_degrees": -5.4}, blocking=True
    )
    call = [c for c in aioclient_mock.mock_calls if c[1].path == "/api/goto"][0]
    assert call[2] == {"name": "M42", "ra_hours": 5.59, "dec_degrees": -5.4}


async def test_unload(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    mock_relay(aioclient_mock)
    entry = await setup(hass)
    await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_wide_camera_returns_the_frame(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    import base64

    from homeassistant.components.camera import async_get_image

    mock_relay(aioclient_mock)
    aioclient_mock.get(f"{BASE}/api/frame", json={"data": base64.b64encode(b"\xff\xd8jpeg").decode()})
    await setup(hass)
    image = await async_get_image(hass, "camera.dwarf_3_wide_camera")
    assert image.content == b"\xff\xd8jpeg"
    call = [c for c in aioclient_mock.mock_calls if c[1].path == "/api/frame"][0]
    assert call[1].query["camera"] == "wide"


async def test_plain_text_error_from_the_relay_is_reported(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    import pytest
    from homeassistant.exceptions import HomeAssistantError

    mock_relay(aioclient_mock)
    aioclient_mock.post(f"{BASE}/api/prepare", text="Internal Server Error", status=500)
    await setup(hass)
    with pytest.raises(HomeAssistantError, match="Internal Server Error"):
        await hass.services.async_call("button", "press", {"entity_id": "button.dwarf_3_prepare"}, blocking=True)


async def test_camera_keeps_the_last_frame(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    import base64

    from homeassistant.components.camera import async_get_image

    mock_relay(aioclient_mock)
    aioclient_mock.get(f"{BASE}/api/frame", json={"data": base64.b64encode(b"first").decode()})
    await setup(hass)
    assert (await async_get_image(hass, "camera.dwarf_3_wide_camera")).content == b"first"
    frames = [c for c in aioclient_mock.mock_calls if c[1].path == "/api/frame"]
    assert (await async_get_image(hass, "camera.dwarf_3_wide_camera")).content == b"first"
    assert len([c for c in aioclient_mock.mock_calls if c[1].path == "/api/frame"]) == len(frames), "fresh: no refetch"

    camera = hass.data["camera"].get_entity("camera.dwarf_3_wide_camera")
    camera._image_time -= 100
    aioclient_mock.clear_requests()
    mock_relay(aioclient_mock)
    aioclient_mock.get(f"{BASE}/api/frame", json={"detail": "no frame", "code": "busy"}, status=409)
    assert (await async_get_image(hass, "camera.dwarf_3_wide_camera")).content == b"first", "stale beats an error"


async def test_camera_error_names_the_prepare_step(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    import pytest
    from homeassistant.components.camera import async_get_image
    from homeassistant.exceptions import HomeAssistantError

    mock_relay(aioclient_mock)
    aioclient_mock.get(f"{BASE}/api/frame", json={"detail": "Connection refused", "code": "busy"}, status=409)
    await setup(hass)
    with pytest.raises(HomeAssistantError, match="Prepare"):
        await async_get_image(hass, "camera.dwarf_3_wide_camera")
