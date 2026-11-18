from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.dwarf3.const import CONF_TOKEN, DOMAIN

BASE = "http://relay.test:9902"
CAPS = {
    "spec_version": "0.1",
    "service": {"name": "dwarf3-relay", "version": "0.3.0"},
    "capabilities": ["status", "goto", "capture"],
}
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
    "sd_total_gb": 64,
    "tele_darks": 18,
    "wide_darks": 3,
    "tracking_state": 1,
    "goto_state": 0,
    "calibration_state": 0,
    "capture_state": 1,
}
USER = {CONF_HOST: "relay.test", CONF_PORT: 9902, CONF_TOKEN: "secret"}


def mock_relay(mock: AiohttpClientMocker, status=STATUS, status_code=200, move_code=422):
    mock.get(f"{BASE}/api/capabilities", json=CAPS)
    mock.get(f"{BASE}/api/status", json=status, status=status_code)
    mock.post(f"{BASE}/api/move", json={"detail": "x", "code": "invalid_request"}, status=move_code)
    mock.get(f"{BASE}/api/sessions", json={"sessions": ["DWARF_RAW_a", "DWARF_RAW_b", "DWARF_RAW_c"]})


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


async def test_new_sensors(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    mock_relay(aioclient_mock)
    await setup(hass)
    state = hass.states.get
    assert state("sensor.dwarf_3_capture_progress").state == "35.0"
    assert state("sensor.dwarf_3_sd_card_used").state == "13.3"  # 55.5 GB free of 64
    assert state("sensor.dwarf_3_tele_darks").state == "18"
    assert state("sensor.dwarf_3_wide_darks").state == "3"
    assert state("sensor.dwarf_3_capture_sessions").state == "3"
    assert state("sensor.dwarf_3_relay_version").state == "0.3.0"
    assert state("binary_sensor.dwarf_3_tracking").state == "on"


async def test_new_sensors_stay_unknown_on_an_older_relay(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    older = {k: v for k, v in STATUS.items() if k not in ("tracking_state", "sd_total_gb", "tele_darks")}
    aioclient_mock.get(f"{BASE}/api/capabilities", json={**CAPS, "service": {"name": "dwarf3-relay"}})
    mock_relay(aioclient_mock, status=older)
    await setup(hass)
    assert hass.states.get("binary_sensor.dwarf_3_tracking").state == "unknown"
    assert hass.states.get("sensor.dwarf_3_sd_card_used").state == "unknown"
    assert hass.states.get("sensor.dwarf_3_relay_version").state == "unknown"


async def test_capture_finished_event_fires_once_per_job(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    mock_relay(aioclient_mock)
    entry = await setup(hass)
    event_id = "event.dwarf_3_capture_finished"
    assert hass.states.get(event_id).state == "unknown", "a running job is not a finish"

    done = {**STATUS, "job": {**STATUS["job"], "state": "done", "captured": 20}}
    aioclient_mock.clear_requests()
    mock_relay(aioclient_mock, status=done)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    first = hass.states.get(event_id)
    assert first.attributes["event_type"] == "capture_done"
    assert first.attributes["captured"] == 20 and first.attributes["session"] == "DWARF_RAW_x"

    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(event_id).state == first.state, "same job, no second event"

    failed = {**STATUS, "job": {**STATUS["job"], "id": "cd34", "state": "failed", "error": "scope left"}}
    aioclient_mock.clear_requests()
    mock_relay(aioclient_mock, status=failed)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(event_id).attributes["event_type"] == "capture_failed"


async def test_job_finished_before_startup_does_not_fire(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    finished = {**STATUS, "job": {**STATUS["job"], "state": "done"}}
    mock_relay(aioclient_mock, status=finished)
    await setup(hass)
    assert hass.states.get("event.dwarf_3_capture_finished").state == "unknown"


async def _call_service(hass, aioclient_mock, service, path, data):
    aioclient_mock.post(f"{BASE}{path}", json={"message": "ok"})  # first, so it wins over mock_relay's own
    mock_relay(aioclient_mock)
    entry = await setup(hass)
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    await hass.services.async_call(DOMAIN, service, {"device_id": device.id, **data}, blocking=True)
    return [c for c in aioclient_mock.mock_calls if c[1].path == path and c[0] == "POST"][0][2]


async def test_start_dark_service(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    body = await _call_service(hass, aioclient_mock, "start_dark", "/api/dark", {"frames": 10, "wide": True})
    assert body == {"frames": 10, "exposure": "15", "wide": True}


async def test_move_service(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    body = await _call_service(hass, aioclient_mock, "move", "/api/move", {"angle": 90, "seconds": 2})
    assert body == {"angle": 90.0, "length": 0.3, "seconds": 2.0}


async def test_point_service(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    body = await _call_service(hass, aioclient_mock, "point", "/api/point", {"pitch": 172.5})
    assert body == {"pitch": 172.5, "rotation": None}


async def test_delete_session_service_and_its_guard(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    import pytest
    import voluptuous as vol

    body = await _call_service(
        hass, aioclient_mock, "delete_session", "/api/sessions/delete", {"session": "DWARF_RAW_TELE_IC 1396_EXP_30"}
    )
    assert body == {"session": "DWARF_RAW_TELE_IC 1396_EXP_30"}, "real names have spaces"
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN, "delete_session", {"device_id": "x", "session": "DWARF_RAW_../etc"}, blocking=True
        )
