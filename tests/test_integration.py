import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.dwarf.const import CONF_TOKEN, DOMAIN

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
    mock.get(f"{BASE}/api/files", json={"entries": []})


async def setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=USER, unique_id="relay.test:9902")
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return entry


async def test_config_flow_creates_entry(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    mock_relay(aioclient_mock)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "relay"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {**USER, "mode": "relay"}


async def test_config_flow_unreachable(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    aioclient_mock.get(f"{BASE}/api/capabilities", exc=TimeoutError)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "relay"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["errors"] == {"base": "cannot_connect"}


async def test_config_flow_bad_token(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    mock_relay(aioclient_mock, move_code=401)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "relay"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["errors"] == {"base": "invalid_auth"}


async def test_config_flow_refuses_other_major_version(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    aioclient_mock.get(f"{BASE}/api/capabilities", json={**CAPS, "spec_version": "1.0"})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "relay"})
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
    aioclient_mock.get(f"{BASE}/api/capabilities", exc=TimeoutError)
    entry = await setup(hass)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_rejected_token_starts_reauth(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    aioclient_mock.get(f"{BASE}/api/capabilities", json=CAPS)
    aioclient_mock.get(f"{BASE}/api/status", json={"detail": "no", "code": "unauthorized"}, status=401)
    entry = await setup(hass)
    assert entry.state is ConfigEntryState.LOADED, "the entities exist, and the first read asks for a new token"
    assert any(hass.config_entries.flow.async_progress_by_handler(DOMAIN))


async def test_entities_exist_at_once_while_the_first_read_is_slow(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, monkeypatch
):
    import asyncio

    from custom_components.dwarf.api import RelayClient

    gate = asyncio.Event()

    async def slow_status(self):
        await gate.wait()
        return STATUS

    mock_relay(aioclient_mock)
    monkeypatch.setattr(RelayClient, "status", slow_status)
    entry = MockConfigEntry(domain=DOMAIN, data=USER, unique_id="relay.test:9902")
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()  # setup is done; the first read is still running in the background

    assert entry.state is ConfigEntryState.LOADED
    for entity in ("sensor.dwarf_3_battery", "sensor.dwarf_3_capture_state", "binary_sensor.dwarf_3_connectivity"):
        assert hass.states.get(entity).state == "unknown", entity + " should be unknown, not unavailable"
    assert hass.states.get("camera.dwarf_3_wide_camera").state != "unavailable"

    gate.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("sensor.dwarf_3_battery").state == "87"
    assert hass.states.get("sensor.dwarf_3_capture_sessions").state == "3"


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
    await hass.async_block_till_done(wait_background_tasks=True)
    first = hass.states.get(event_id)
    assert first.attributes["event_type"] == "capture_done"
    assert first.attributes["captured"] == 20 and first.attributes["session"] == "DWARF_RAW_x"

    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(event_id).state == first.state, "same job, no second event"

    failed = {**STATUS, "job": {**STATUS["job"], "id": "cd34", "state": "failed", "error": "scope left"}}
    aioclient_mock.clear_requests()
    mock_relay(aioclient_mock, status=failed)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)
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


SCOPE = "http://scope.test:8082"
DEVICE_INFO = {
    "code": 0,
    "data": {
        "sdCardInfo": {"hasSdcard": True, "availableSize": 31.0, "totalSize": 64.0},
        "wifiPassword": "hunter2",  # the real reply has this in clear text, and it must never leave the integration
    },
}
SESSIONS = [
    "DWARF_RAW_TELE_IC 1396_EXP_30_GAIN_60_2026-11-14-18-36-13-703",
    "DWARF_RAW_TELE_M 31_EXP_15_GAIN_60_2026-11-05-22-57-32-526",
]


async def setup_direct(hass: HomeAssistant, monkeypatch) -> MockConfigEntry:
    from custom_components.dwarf.direct import ScopeDirectClient

    monkeypatch.setattr(ScopeDirectClient, "list_sessions_blocking", lambda self: SESSIONS)
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: "scope.test", "mode": "direct"}, unique_id="direct:scope.test"
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return entry


async def test_direct_config_flow(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    aioclient_mock.post(f"{SCOPE}/deviceInfo", json=DEVICE_INFO)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "direct"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "scope.test"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: "scope.test", "mode": "direct"}


async def test_direct_config_flow_errors(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    aioclient_mock.post(f"{SCOPE}/deviceInfo", exc=TimeoutError)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "direct"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "scope.test"})
    assert result["errors"] == {"base": "cannot_connect"}

    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{SCOPE}/deviceInfo", json={"hello": "router"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "scope.test"})
    assert result["errors"] == {"base": "not_a_scope"}


async def test_direct_mode_has_only_what_the_scope_gives_out(hass: HomeAssistant, aioclient_mock, monkeypatch):
    aioclient_mock.post(f"{SCOPE}/deviceInfo", json=DEVICE_INFO)
    entry = await setup_direct(hass, monkeypatch)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("binary_sensor.dwarf_3_connectivity").state == "on"
    assert hass.states.get("sensor.dwarf_3_sd_card_free").state == "31.0"
    assert hass.states.get("sensor.dwarf_3_sd_card_used").state == "51.6"
    sessions = hass.states.get("sensor.dwarf_3_capture_sessions")
    assert sessions.state == "2"
    assert sessions.attributes["sessions"] == SESSIONS
    for entity in ("sensor.dwarf_3_battery", "button.dwarf_3_close_barrel",
                   "binary_sensor.dwarf_3_tracking", "event.dwarf_3_capture_finished"):
        assert hass.states.get(entity) is None, entity + " needs the control connection"


async def test_direct_mode_survives_a_scope_that_is_off(hass: HomeAssistant, aioclient_mock, monkeypatch):
    aioclient_mock.post(f"{SCOPE}/deviceInfo", exc=TimeoutError)
    entry = await setup_direct(hass, monkeypatch)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("binary_sensor.dwarf_3_connectivity").state == "off"
    assert hass.states.get("sensor.dwarf_3_sd_card_free").state == "unknown"


async def test_direct_mode_never_opens_the_control_connection(hass: HomeAssistant, aioclient_mock, monkeypatch):
    aioclient_mock.post(f"{SCOPE}/deviceInfo", json=DEVICE_INFO)
    await setup_direct(hass, monkeypatch)
    assert {(c[0], c[1].port) for c in aioclient_mock.mock_calls} == {("POST", 8082)}


async def test_direct_mode_services_are_refused(hass: HomeAssistant, aioclient_mock, monkeypatch):
    import pytest
    from homeassistant.exceptions import ServiceValidationError

    aioclient_mock.post(f"{SCOPE}/deviceInfo", json=DEVICE_INFO)
    entry = await setup_direct(hass, monkeypatch)
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    with pytest.raises(ServiceValidationError, match="read-only"):
        await hass.services.async_call(
            DOMAIN,
            "goto",
            {"device_id": device.id, "name": "M42", "ra_hours": 5.5, "dec_degrees": -5.4},
            blocking=True,
        )


async def test_diagnostics_hide_the_wifi_password(hass: HomeAssistant, aioclient_mock, monkeypatch):
    from custom_components.dwarf.diagnostics import async_get_config_entry_diagnostics

    aioclient_mock.post(f"{SCOPE}/deviceInfo", json=DEVICE_INFO)
    entry = await setup_direct(hass, monkeypatch)
    out = await async_get_config_entry_diagnostics(hass, entry)
    text = str(out)
    assert "hunter2" not in text and "scope.test" not in text
    assert "9c:b8:b4" not in text.lower(), "the MAC identifies the scope too"
    assert "wifiPassword" in out["device_info_keys"], "key names help us learn the format, values never leave"


def test_sessions_are_ordered_by_the_time_in_the_name():
    from custom_components.dwarf.direct import session_order

    ordered = sorted(SESSIONS, key=session_order)
    assert ordered[-1].startswith("DWARF_RAW_TELE_IC 1396"), "Nov 14 is newer than Nov 5, whatever the target name"


# ---- the first-run experience

async def test_relay_on_this_home_assistant_is_found_and_added_in_one_click(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, local_ip
):
    local_ip("relay.test")
    mock_relay(aioclient_mock)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "relay"})
    assert result["step_id"] == "relay_found", "no form to fill in"
    assert result["description_placeholders"] == {"host": "relay.test"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: "relay.test", CONF_PORT: 9902, CONF_TOKEN: None, "mode": "relay"}


async def test_no_relay_found_shows_a_form_with_this_home_assistants_address(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, local_ip
):
    local_ip("relay.test")
    aioclient_mock.get(f"{BASE}/api/capabilities", exc=TimeoutError)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "relay"})
    assert result["step_id"] == "relay_manual" and result["type"] is FlowResultType.FORM
    assert [k for k in result["data_schema"].schema if k == CONF_HOST][0].default() == "relay.test"


async def test_relay_that_wants_a_token_asks_for_it(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, local_ip):
    local_ip("relay.test")
    mock_relay(aioclient_mock, move_code=401)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "relay"})
    assert result["step_id"] == "relay_manual", "falls back to the form, which has a token field"


async def _discovered(hass, aioclient_mock):
    from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

    aioclient_mock.post(f"{SCOPE}/deviceInfo", json=DEVICE_INFO)
    info = DhcpServiceInfo(ip="scope.test", hostname="dwarf", macaddress="9cb8b457d0ec")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "dhcp"}, data=info)
    assert result["type"] is FlowResultType.MENU and result["step_id"] == "discovery_confirm"
    assert result["description_placeholders"] == {"host": "scope.test"}
    assert set(result["menu_options"]) == {"discovery_readonly", "discovery_full"}
    return result


async def test_a_scope_found_on_the_network_can_be_added_read_only(hass: HomeAssistant, aioclient_mock):
    result = await _discovered(hass, aioclient_mock)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "discovery_readonly"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: "scope.test", "mode": "direct", "mac": "9c:b8:b4:57:d0:ec"}
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.unique_id == "direct:9c:b8:b4:57:d0:ec", "identity is the MAC, not the address"


async def test_a_found_scope_can_go_straight_to_full_control_with_the_relay_installed(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, local_ip, supervisor
):
    fake = supervisor()
    local_ip("relay.test")
    aioclient_mock.get(f"{BASE}/api/capabilities", exc=TimeoutError)
    result = await _discovered(hass, aioclient_mock)

    def app_comes_up():
        aioclient_mock.clear_requests()
        mock_relay(aioclient_mock)

    fake.on_start = app_comes_up
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "discovery_full"})
    result = await _finish_progress(hass, result)
    assert result["type"] is FlowResultType.CREATE_ENTRY, "no questions: the scope's address is already known"
    assert result["data"] == {CONF_HOST: "relay.test", CONF_PORT: 9902, CONF_TOKEN: None, "mode": "relay"}
    config = [c for c in fake.calls if c[0] == "set_addon_options"][0][2]["config"]
    assert config["scope_host"] == "scope.test"


async def test_a_found_scope_uses_a_relay_that_is_already_running(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, local_ip, supervisor
):
    fake = supervisor()
    local_ip("relay.test")
    mock_relay(aioclient_mock)
    result = await _discovered(hass, aioclient_mock)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "discovery_full"})
    assert result["type"] is FlowResultType.CREATE_ENTRY and result["data"]["mode"] == "relay"
    assert fake.calls == [], "nothing to install"


async def test_full_control_without_a_supervisor_asks_for_the_relays_address(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, local_ip
):
    local_ip("relay.test")
    aioclient_mock.get(f"{BASE}/api/capabilities", exc=TimeoutError)
    result = await _discovered(hass, aioclient_mock)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "discovery_full"})
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "relay_manual"


async def test_other_gear_in_the_mac_range_is_ignored(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

    aioclient_mock.post(f"{SCOPE}/deviceInfo", json={"hello": "a light bulb"})
    info = DhcpServiceInfo(ip="scope.test", hostname="bulb", macaddress="9cb8b4000001")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "dhcp"}, data=info)
    assert (result["type"], result["reason"]) == (FlowResultType.ABORT, "not_a_scope")


async def test_discovery_stays_quiet_once_something_is_set_up(hass: HomeAssistant, aioclient_mock, monkeypatch):
    from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

    aioclient_mock.post(f"{SCOPE}/deviceInfo", json=DEVICE_INFO)
    await setup_direct(hass, monkeypatch)
    info = DhcpServiceInfo(ip="scope.test", hostname="dwarf", macaddress="9cb8b457d0ec")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "dhcp"}, data=info)
    assert (result["type"], result["reason"]) == (FlowResultType.ABORT, "already_configured")


async def test_switching_from_read_only_to_the_relay_keeps_entity_ids(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, monkeypatch, local_ip
):
    from homeassistant.helpers import entity_registry as er

    aioclient_mock.post(f"{SCOPE}/deviceInfo", json=DEVICE_INFO)
    entry = await setup_direct(hass, monkeypatch)
    registry = er.async_get(hass)
    shared = ["sensor.dwarf_3_sd_card_free", "sensor.dwarf_3_sd_card_used", "sensor.dwarf_3_capture_sessions",
              "binary_sensor.dwarf_3_connectivity"]
    before = {e: registry.async_get(e).unique_id for e in shared}
    assert hass.states.get("sensor.dwarf_3_battery") is None

    local_ip("relay.test")
    mock_relay(aioclient_mock)
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "relay"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert (result["type"], result["reason"]) == (FlowResultType.ABORT, "reconfigure_successful")
    await hass.async_block_till_done(wait_background_tasks=True)

    entry = hass.config_entries.async_get_entry(entry.entry_id)
    assert entry.state is ConfigEntryState.LOADED and entry.data["mode"] == "relay"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1, "the same entry, not a second one"
    assert {e: registry.async_get(e).unique_id for e in shared} == before, "same entities"
    assert hass.states.get("sensor.dwarf_3_battery").state == "87", "and the relay's extras arrive"
    assert hass.states.get("sensor.dwarf_3_capture_sessions").state == "3", "now read through the relay"


async def test_switching_back_to_read_only_keeps_entity_ids(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, monkeypatch
):
    from homeassistant.helpers import entity_registry as er

    from custom_components.dwarf.direct import ScopeDirectClient

    mock_relay(aioclient_mock)
    aioclient_mock.post(f"{SCOPE}/deviceInfo", json=DEVICE_INFO)
    monkeypatch.setattr(ScopeDirectClient, "list_sessions_blocking", lambda self: SESSIONS)
    entry = await setup(hass)
    registry = er.async_get(hass)
    before = registry.async_get("sensor.dwarf_3_sd_card_free").unique_id

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "direct"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "scope.test"})
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done(wait_background_tasks=True)

    entry = hass.config_entries.async_get_entry(entry.entry_id)
    assert entry.state is ConfigEntryState.LOADED and entry.data["mode"] == "direct"
    assert registry.async_get("sensor.dwarf_3_sd_card_free").unique_id == before
    assert hass.states.get("sensor.dwarf_3_sd_card_free").state == "31.0"


async def test_changing_the_scope_address(hass: HomeAssistant, aioclient_mock, monkeypatch):
    aioclient_mock.post(f"{SCOPE}/deviceInfo", json=DEVICE_INFO)
    aioclient_mock.post("http://new.test:8082/deviceInfo", json=DEVICE_INFO)
    entry = await setup_direct(hass, monkeypatch)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "direct"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "new.test"})
    assert result["reason"] == "reconfigure_successful"
    assert hass.config_entries.async_get_entry(entry.entry_id).data[CONF_HOST] == "new.test"


# ---- installing the relay app from the flow

async def _to_the_install_menu(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "relay"})
    assert result["type"] is FlowResultType.MENU and result["step_id"] == "relay"
    return result


async def _finish_progress(hass, result):
    """A slow install shows a progress screen first. A fast one (as in these tests) finishes in one call."""
    if result["type"] is FlowResultType.SHOW_PROGRESS:
        await hass.async_block_till_done(wait_background_tasks=True)
        result = await hass.config_entries.flow.async_configure(result["flow_id"])
    return result


async def test_flow_installs_and_sets_up_the_relay_app(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, local_ip, supervisor
):
    from custom_components.dwarf.app_setup import APP_REPOSITORY, APP_SLUG

    fake = supervisor()
    local_ip("relay.test")
    aioclient_mock.get(f"{BASE}/api/capabilities", exc=TimeoutError)
    aioclient_mock.post(f"{SCOPE}/deviceInfo", json=DEVICE_INFO)
    result = await _to_the_install_menu(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "relay_install"})
    assert result["step_id"] == "relay_install" and result["type"] is FlowResultType.FORM, "asks only for the scope"

    aioclient_mock.clear_requests()  # the app is "running" by the time the flow looks
    mock_relay(aioclient_mock)
    aioclient_mock.post(f"{SCOPE}/deviceInfo", json=DEVICE_INFO)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "scope.test"})
    result = await _finish_progress(hass, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: "relay.test", CONF_PORT: 9902, CONF_TOKEN: None, "mode": "relay"}
    assert fake.names() == [
        "repositories_list", "add_repository", "reload", "addon_info", "install_addon", "addon_info",
        "set_addon_options", "start_addon",
    ]
    assert fake.calls[1][2] == {} and fake.calls[1][1][0].repository == APP_REPOSITORY
    config = [c for c in fake.calls if c[0] == "set_addon_options"][0][2]["config"]
    assert config["scope_host"] == "scope.test" and config["auth"] is False
    assert [c for c in fake.calls if c[0] == "start_addon"][0][1] == (APP_SLUG,)


async def test_switching_a_read_only_entry_to_an_installed_relay_asks_nothing(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, monkeypatch, local_ip, supervisor
):
    fake = supervisor()
    aioclient_mock.post(f"{SCOPE}/deviceInfo", json=DEVICE_INFO)
    entry = await setup_direct(hass, monkeypatch)
    local_ip("relay.test")
    aioclient_mock.get(f"{BASE}/api/capabilities", exc=TimeoutError)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "relay"})
    assert result["step_id"] == "relay", "no relay yet, so offer to install one"
    aioclient_mock.clear_requests()
    mock_relay(aioclient_mock)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "relay_install"})
    result = await _finish_progress(hass, result)

    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reconfigure_successful"
    config = [c for c in fake.calls if c[0] == "set_addon_options"][0][2]["config"]
    assert config["scope_host"] == "scope.test", "the scope's address came from the read-only entry"
    updated = hass.config_entries.async_get_entry(entry.entry_id)
    assert updated.data["mode"] == "relay" and updated.entry_id == entry.entry_id


async def test_an_address_the_user_already_entered_in_the_app_is_kept(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, local_ip, supervisor
):
    fake = supervisor(installed=True, options={"scope_host": "10.0.0.9", "auth": False}, repos=[
        "https://github.com/bscholer/home-assistant-dwarf3/"])
    local_ip("relay.test")
    aioclient_mock.get(f"{BASE}/api/capabilities", exc=TimeoutError)
    aioclient_mock.post(f"{SCOPE}/deviceInfo", json=DEVICE_INFO)
    result = await _to_the_install_menu(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "relay_install"})
    aioclient_mock.clear_requests()
    mock_relay(aioclient_mock)
    aioclient_mock.post(f"{SCOPE}/deviceInfo", json=DEVICE_INFO)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "scope.test"})
    result = await _finish_progress(hass, result)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert fake.names() == ["repositories_list", "addon_info", "start_addon"], "repo known, nothing to install or set"
    assert [c for c in fake.calls if c[0] == "start_addon"][0][1] == ("bbc0cf72_dwarf3_relay",), (
        "an install from the repository's old name keeps its app"
    )


def test_app_slugs_follow_the_supervisor_hash():
    from custom_components.dwarf.app_setup import APP_SLUG, LEGACY_APP_SLUG

    assert LEGACY_APP_SLUG == "bbc0cf72_dwarf3_relay", "the slug existing installs have"
    assert APP_SLUG == "a51b3b4f_dwarf3_relay"


async def test_install_failure_explains_and_offers_the_manual_way(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, local_ip, supervisor
):
    supervisor(fail_on="install_addon")
    local_ip("relay.test")
    aioclient_mock.get(f"{BASE}/api/capabilities", exc=TimeoutError)
    aioclient_mock.post(f"{SCOPE}/deviceInfo", json=DEVICE_INFO)
    result = await _to_the_install_menu(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "relay_install"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "scope.test"})
    result = await _finish_progress(hass, result)
    assert result["type"] is FlowResultType.MENU and result["step_id"] == "relay_install_failed"
    assert "No space left on device" in result["description_placeholders"]["error"]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "relay_manual"})
    assert result["step_id"] == "relay_manual"


async def test_an_app_that_never_answers_is_reported(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, local_ip, supervisor
):
    supervisor()
    local_ip("relay.test")
    aioclient_mock.get(f"{BASE}/api/capabilities", exc=TimeoutError)
    aioclient_mock.post(f"{SCOPE}/deviceInfo", json=DEVICE_INFO)
    result = await _to_the_install_menu(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "relay_install"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "scope.test"})
    result = await _finish_progress(hass, result)
    assert result["step_id"] == "relay_install_failed"
    assert "not answering" in result["description_placeholders"]["error"]


async def test_a_bad_scope_address_is_caught_before_installing_anything(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, local_ip, supervisor
):
    fake = supervisor()
    local_ip("relay.test")
    aioclient_mock.get(f"{BASE}/api/capabilities", exc=TimeoutError)
    aioclient_mock.post(f"{SCOPE}/deviceInfo", exc=TimeoutError)
    result = await _to_the_install_menu(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "relay_install"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "scope.test"})
    assert result["step_id"] == "relay_install" and result["errors"] == {"base": "cannot_connect"}
    assert fake.calls == []


async def test_a_slow_install_shows_progress_then_finishes(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, local_ip, supervisor
):
    import asyncio

    gate = asyncio.Event()
    supervisor(gate=gate)
    local_ip("relay.test")
    aioclient_mock.get(f"{BASE}/api/capabilities", exc=TimeoutError)
    aioclient_mock.post(f"{SCOPE}/deviceInfo", json=DEVICE_INFO)
    result = await _to_the_install_menu(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "relay_install"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "scope.test"})
    assert result["type"] is FlowResultType.SHOW_PROGRESS and result["progress_action"] == "install_app"

    aioclient_mock.clear_requests()
    mock_relay(aioclient_mock)
    gate.set()
    result = await _finish_progress(hass, result)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_services_accept_an_entity_as_the_target(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    aioclient_mock.post(f"{BASE}/api/move", json={"message": "moved"})  # first, so it wins over mock_relay's own
    mock_relay(aioclient_mock)
    await setup(hass)
    # the service target picker offers this integration's entities, and any of them picks the device
    await hass.services.async_call(
        DOMAIN, "move", {"entity_id": "sensor.dwarf_3_battery", "angle": 90}, blocking=True
    )
    posts = [c for c in aioclient_mock.mock_calls if c[0] == "POST" and c[1].path == "/api/move" and c[2].get("angle")]
    assert posts and posts[0][2]["angle"] == 90.0


# ---- the "needs prepare" hint

def _unprepared(**extra):
    return {**STATUS, "pitch": None, "rotation": None, "job": None, **extra}


async def test_needs_prepare_is_on_until_the_scope_reports_its_motors(hass: HomeAssistant, aioclient_mock):
    mock_relay(aioclient_mock, status=_unprepared())
    await setup(hass)
    state = hass.states.get("binary_sensor.dwarf_3_needs_prepare")
    assert state.state == "on"
    assert "Press Prepare" in state.attributes["hint"]


async def test_needs_prepare_is_off_once_prepared(hass: HomeAssistant, aioclient_mock):
    mock_relay(aioclient_mock)  # STATUS has a pitch and rotation
    await setup(hass)
    state = hass.states.get("binary_sensor.dwarf_3_needs_prepare")
    assert state.state == "off" and "hint" not in state.attributes


async def test_pressing_prepare_clears_the_hint(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.post(f"{BASE}/api/prepare", json={"message": "ready, pointing up"})
    mock_relay(aioclient_mock, status=_unprepared())
    entry = await setup(hass)
    assert hass.states.get("binary_sensor.dwarf_3_needs_prepare").state == "on"

    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{BASE}/api/prepare", json={"message": "ready, pointing up"})
    mock_relay(aioclient_mock)  # now it reports positions
    await hass.services.async_call("button", "press", {"entity_id": "button.dwarf_3_prepare"}, blocking=True)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("binary_sensor.dwarf_3_needs_prepare").state == "off"
    assert entry.runtime_data.data["pitch"] == 172.5


async def test_needs_prepare_is_unknown_when_the_scope_is_not_answering(hass: HomeAssistant, aioclient_mock):
    mock_relay(aioclient_mock, status={"detail": "off", "code": "scope_error"}, status_code=502)
    await setup(hass)
    assert hass.states.get("binary_sensor.dwarf_3_needs_prepare").state == "unknown"


async def test_a_running_capture_is_never_flagged(hass: HomeAssistant, aioclient_mock):
    mock_relay(aioclient_mock, status=_unprepared(job=STATUS["job"]))  # positions are cached or empty mid-capture
    await setup(hass)
    assert hass.states.get("binary_sensor.dwarf_3_needs_prepare").state == "off"


async def test_read_only_mode_has_no_prepare_hint(hass: HomeAssistant, aioclient_mock, monkeypatch):
    aioclient_mock.post(f"{SCOPE}/deviceInfo", json=DEVICE_INFO)
    await setup_direct(hass, monkeypatch)
    assert hass.states.get("binary_sensor.dwarf_3_needs_prepare") is None


# ---- pan/tilt-style controls

async def test_pitch_and_rotation_are_shown_in_degrees_by_default(hass: HomeAssistant, aioclient_mock):
    mock_relay(aioclient_mock)
    await setup(hass)
    pitch = hass.states.get("sensor.dwarf_3_pitch")
    assert (pitch.state, pitch.attributes["unit_of_measurement"]) == ("172.5", "°")
    assert hass.states.get("sensor.dwarf_3_rotation").state == "10.0"


@pytest.mark.parametrize(
    ("button", "angle"),
    [("nudge_right", 0), ("nudge_up", 90), ("nudge_left", 180), ("nudge_down", 270)],
)
async def test_nudge_buttons_send_a_short_joystick_move(hass: HomeAssistant, aioclient_mock, button, angle):
    aioclient_mock.post(f"{BASE}/api/move", json={"message": "moved"})  # first, so it wins over mock_relay's own
    mock_relay(aioclient_mock)
    await setup(hass)
    await hass.services.async_call("button", "press", {"entity_id": f"button.dwarf_3_{button}"}, blocking=True)
    moves = [c[2] for c in aioclient_mock.mock_calls if c[0] == "POST" and c[1].path == "/api/move"]
    sent = [m for m in moves if m.get("length")]  # not the token check, which sends length 0
    assert sent[-1] == {"angle": angle, "length": 0.3, "seconds": 1.0}


async def test_point_straight_up_sets_the_pitch_only(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.post(f"{BASE}/api/point", json={"message": "pointed"})
    mock_relay(aioclient_mock)
    await setup(hass)
    await hass.services.async_call("button", "press", {"entity_id": "button.dwarf_3_point_straight_up"}, blocking=True)
    sent = [c[2] for c in aioclient_mock.mock_calls if c[0] == "POST" and c[1].path == "/api/point"]
    assert sent == [{"pitch": 172.5, "rotation": None}]


async def test_there_are_no_pitch_or_rotation_sliders(hass: HomeAssistant, aioclient_mock):
    mock_relay(aioclient_mock)
    await setup(hass)
    assert not hass.states.async_entity_ids("number"), "a slider that moves motors is too easy to hit by accident"


# ---- the latest stack as an image

NEWEST = "DWARF_RAW_TELE_M 81_EXP_30_GAIN_60_2026-11-18-03-11-46-101"
OLDER = "DWARF_RAW_TELE_NGC 224_EXP_30_GAIN_60_2026-11-17-21-06-11-337"


def make_jpeg(width: int = 2400, height: int = 1200, shade: int = 90) -> bytes:
    import io

    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (width, height), (shade, shade, shade)).save(out, "JPEG")
    return out.getvalue()


def mock_stack(mock, jpeg: bytes, *, sessions=(OLDER, NEWEST)):
    """Register these before mock_relay, since the first matching mock wins."""
    import base64

    mock.get(f"{BASE}/api/sessions", json={"sessions": list(sessions)})
    mock.get(
        f"{BASE}/api/files",
        json={"entries": [{"name": "stacked.jpg", "size": len(jpeg), "dir": False},
                          {"name": "stacked_thumbnail.jpg", "size": 40000, "dir": False}]},
    )
    mock.get(
        f"{BASE}/api/files/chunk",
        json={"offset": 0, "size": len(jpeg), "data": base64.b64encode(jpeg).decode(), "eof": True},
    )


def stack_entity(hass):
    return hass.data["image"].get_entity("image.dwarf_3_latest_stack")


def calls(mock, path):
    return [c for c in mock.mock_calls if c[1].path == path]


async def test_the_newest_stack_is_an_image_entity(hass: HomeAssistant, aioclient_mock):
    import io

    from PIL import Image

    mock_stack(aioclient_mock, make_jpeg())
    mock_relay(aioclient_mock)
    await setup(hass)
    state = hass.states.get("image.dwarf_3_latest_stack")
    assert state.state != "unknown", "it has been updated"
    assert state.attributes["session"] == NEWEST and state.attributes["target"] == "M 81"
    assert (state.attributes["exposure_s"], state.attributes["gain"]) == (30, 60)
    assert state.attributes["started"] == "2026-11-18 03:11:46"
    image = Image.open(io.BytesIO(await stack_entity(hass).async_image()))
    assert (image.format, image.width) == ("JPEG", 1280), "downscaled for a display"
    assert [c[1].query["path"] for c in calls(aioclient_mock, "/api/files")] == [NEWEST], "looked at the newest only"


async def test_an_unchanged_stack_is_not_downloaded_again(hass: HomeAssistant, aioclient_mock):
    mock_stack(aioclient_mock, make_jpeg())
    mock_relay(aioclient_mock)
    entry = await setup(hass)
    assert len(calls(aioclient_mock, "/api/files/chunk")) == 1
    entry.runtime_data.stack.last_check -= 10_000  # long enough ago that a check is due
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(calls(aioclient_mock, "/api/files")) == 2, "checked the size"
    assert len(calls(aioclient_mock, "/api/files/chunk")) == 1, "but the file was the same"


async def test_while_capturing_a_changed_stack_is_picked_up_within_a_poll(hass: HomeAssistant, aioclient_mock):
    mock_stack(aioclient_mock, make_jpeg(height=1200))
    mock_relay(aioclient_mock)  # STATUS has a running job
    entry = await setup(hass)
    first = hass.states.get("image.dwarf_3_latest_stack").state

    aioclient_mock.clear_requests()
    mock_stack(aioclient_mock, make_jpeg(height=1500))  # the scope stacked another frame: a bigger file
    mock_relay(aioclient_mock)
    entry.runtime_data.stack.last_check -= 31  # a running capture is checked every 30 s
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(calls(aioclient_mock, "/api/files/chunk")) == 1, "downloaded again"
    assert hass.states.get("image.dwarf_3_latest_stack").state != first, "and the entity says it updated"


async def test_a_finished_capture_gets_one_last_look(hass: HomeAssistant, aioclient_mock):
    mock_stack(aioclient_mock, make_jpeg(height=1200))
    mock_relay(aioclient_mock)  # running
    entry = await setup(hass)

    aioclient_mock.clear_requests()
    done = {**STATUS, "capture_state": 0, "job": {**STATUS["job"], "state": "done"}}
    mock_stack(aioclient_mock, make_jpeg(height=1600))
    mock_relay(aioclient_mock, status=done)
    # the last check was moments ago, so only the running-to-done change can make another one due
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(calls(aioclient_mock, "/api/files/chunk")) == 1


async def test_an_idle_scope_is_checked_rarely(hass: HomeAssistant, aioclient_mock):
    done = {**STATUS, "capture_state": 0, "job": {**STATUS["job"], "state": "done"}}
    mock_stack(aioclient_mock, make_jpeg())
    mock_relay(aioclient_mock, status=done)
    entry = await setup(hass)
    aioclient_mock.mock_calls.clear()
    for _ in range(3):
        await entry.runtime_data.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert calls(aioclient_mock, "/api/files") == [], "no check within ten minutes of the last"


async def test_no_stack_yet_is_just_unknown(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(f"{BASE}/api/sessions", json={"sessions": []})
    mock_relay(aioclient_mock)
    entry = await setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("image.dwarf_3_latest_stack").state == "unknown"


async def test_a_scope_that_is_off_does_not_break_the_image(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(f"{BASE}/api/sessions", json={"detail": "off", "code": "scope_error"}, status=502)
    mock_relay(aioclient_mock)
    entry = await setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("image.dwarf_3_latest_stack").state == "unknown"


async def test_read_only_mode_has_the_stack_too(hass: HomeAssistant, aioclient_mock, monkeypatch):
    from custom_components.dwarf.direct import ScopeDirectClient

    jpeg = make_jpeg()
    monkeypatch.setattr(ScopeDirectClient, "fetch_stack_blocking", lambda self, known: (NEWEST, len(jpeg), jpeg))
    aioclient_mock.post(f"{SCOPE}/deviceInfo", json=DEVICE_INFO)
    await setup_direct(hass, monkeypatch)
    state = hass.states.get("image.dwarf_3_latest_stack")
    assert state.attributes["target"] == "M 81"


async def test_stack_entity_keeps_its_id_on_a_switch(hass: HomeAssistant, aioclient_mock, monkeypatch, local_ip):
    from homeassistant.helpers import entity_registry as er

    from custom_components.dwarf.direct import ScopeDirectClient

    jpeg = make_jpeg()
    monkeypatch.setattr(ScopeDirectClient, "fetch_stack_blocking", lambda self, known: (NEWEST, len(jpeg), jpeg))
    aioclient_mock.post(f"{SCOPE}/deviceInfo", json=DEVICE_INFO)
    entry = await setup_direct(hass, monkeypatch)
    before = er.async_get(hass).async_get("image.dwarf_3_latest_stack").unique_id

    local_ip("relay.test")
    mock_stack(aioclient_mock, jpeg)
    mock_relay(aioclient_mock)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "relay"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done(wait_background_tasks=True)
    assert er.async_get(hass).async_get("image.dwarf_3_latest_stack").unique_id == before


def test_session_names_are_described():
    from custom_components.dwarf.stack import describe

    assert describe(NEWEST) == {"session": NEWEST, "camera": "tele", "exposure_s": 30, "gain": 60,
                                "started": "2026-11-18 03:11:46", "target": "M 81"}
    no_target = describe("DWARF_RAW_TELE_EXP_15_GAIN_60_2026-11-05-22-57-32-526")
    assert "target" not in no_target and no_target["exposure_s"] == 15
    assert describe("something else") == {"session": "something else"}


def test_a_small_image_is_not_resized():
    import io

    from PIL import Image

    from custom_components.dwarf.stack import downscale

    assert Image.open(io.BytesIO(downscale(make_jpeg(800, 400)))).width == 800


# ---- browsing every stack in Home Assistant's Media

BROKEN = "DWARF_RAW_TELE_M 31_EXP_15_GAIN_60_2026-11-19-01-00-00-000"  # a session that never produced a stack
THUMB = b"\xff\xd8thumb"


def library(monkeypatch, *, newest_jpeg=None, thumbs=True):
    """The scope's album, as seen through the relay client. Returns a counter of the listings made."""
    from custom_components.dwarf.api import RelayClient

    jpeg = newest_jpeg or make_jpeg()
    stacks = {OLDER: make_jpeg(2000, 800), NEWEST: jpeg, BROKEN: None}
    counter = {"listings": []}

    async def sessions(self):
        return list(stacks)

    async def files(self, path):
        counter["listings"].append(path)
        have = stacks[path]
        entries = [] if have is None else [{"name": "stacked.jpg", "size": len(have), "dir": False}]
        if have is not None and thumbs:
            entries.append({"name": "stacked_thumbnail.jpg", "size": len(THUMB), "dir": False})
        return entries

    async def download(self, path, size):
        session, name = path.rsplit("/", 1)
        return stacks[session] if name == "stacked.jpg" else THUMB

    monkeypatch.setattr(RelayClient, "sessions", sessions)
    monkeypatch.setattr(RelayClient, "files", files)
    monkeypatch.setattr(RelayClient, "download", download)
    return counter


async def browse(hass, path=""):
    from homeassistant.components import media_source
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "media_source", {})
    await hass.async_block_till_done()  # integrations register their sources in background tasks
    return await media_source.async_browse_media(hass, f"media-source://dwarf{path}")


async def test_every_stack_shows_up_in_the_media_browser_newest_first(hass: HomeAssistant, aioclient_mock, monkeypatch):
    library(monkeypatch)
    mock_relay(aioclient_mock)
    entry = await setup(hass)
    root = await browse(hass)
    assert [c.title for c in root.children] == ["M 81, 30 s, 2026-11-18 03:11", "NGC 224, 30 s, 2026-11-17 21:06"]
    assert all(c.can_play and not c.can_expand and c.media_content_type == "image/jpeg" for c in root.children)
    assert root.children[0].media_content_id == f"media-source://dwarf/{entry.entry_id}/{NEWEST}"
    assert "authSig" in root.children[0].thumbnail, "thumbnails are signed, so the browser can load them"
    assert BROKEN not in str([c.title for c in root.children]), "only sessions that have a stack"


async def test_without_thumbnails_it_still_browses(hass: HomeAssistant, aioclient_mock, monkeypatch):
    library(monkeypatch, thumbs=False)
    mock_relay(aioclient_mock)
    await setup(hass)
    root = await browse(hass)
    assert len(root.children) == 2 and root.children[0].thumbnail is None


async def test_older_sessions_are_not_listed_twice(hass: HomeAssistant, aioclient_mock, monkeypatch):
    counter = library(monkeypatch)
    mock_relay(aioclient_mock)
    entry = await setup(hass)
    await browse(hass)
    counter["listings"].clear()
    entry.runtime_data.library._listed = float("-inf")  # the cached listing has expired
    await browse(hass)
    assert counter["listings"] == [BROKEN], "only the newest session can still change"


async def test_a_playable_address_serves_the_picture_and_is_signed(
    hass: HomeAssistant, aioclient_mock, monkeypatch, hass_client, hass_client_no_auth
):
    import io
    from datetime import timedelta

    from homeassistant.components import media_source
    from homeassistant.components.http.auth import async_sign_path
    from homeassistant.setup import async_setup_component
    from PIL import Image

    library(monkeypatch)
    mock_relay(aioclient_mock)
    entry = await setup(hass)
    assert await async_setup_component(hass, "media_source", {})
    await hass.async_block_till_done()  # integrations register their sources in background tasks
    play = await media_source.async_resolve_media(hass, f"media-source://dwarf/{entry.entry_id}/{NEWEST}", None)
    assert play.mime_type == "image/jpeg"

    response = await (await hass_client()).get(play.url)
    assert response.status == 200 and response.content_type == "image/jpeg"
    assert Image.open(io.BytesIO(await response.read())).width == 1280

    anonymous = await hass_client_no_auth()
    assert (await anonymous.get(play.url)).status == 401, "not without a signature"
    signed = async_sign_path(hass, play.url, timedelta(minutes=5))
    assert (await anonymous.get(signed)).status == 200, "with the signature Home Assistant adds, a display can fetch it"


async def test_the_thumbnail_is_served_as_it_is(hass: HomeAssistant, aioclient_mock, monkeypatch, hass_client):
    from custom_components.dwarf.media_source import stack_path

    library(monkeypatch)
    mock_relay(aioclient_mock)
    entry = await setup(hass)
    response = await (await hass_client()).get(stack_path(entry.entry_id, OLDER, thumbnail=True))
    assert (response.status, await response.read()) == (200, THUMB)


async def test_unknown_or_unsafe_addresses_are_not_found(hass: HomeAssistant, aioclient_mock, monkeypatch, hass_client):
    from custom_components.dwarf.media_source import stack_path

    library(monkeypatch)
    mock_relay(aioclient_mock)
    entry = await setup(hass)
    client = await hass_client()
    assert (await client.get(stack_path("nope", NEWEST))).status == 404
    assert (await client.get(stack_path(entry.entry_id, "something_else"))).status == 404
    traversal = await client.get(f"/api/dwarf/stack/{entry.entry_id}/DWARF_RAW_..%2F..%2Fetc")
    assert traversal.status in (400, 404), "refused, either by the web server or by us"
    assert (await client.get(stack_path(entry.entry_id, BROKEN))).status == 404, "a session with no stack"


async def test_resolving_an_unknown_stack_fails_cleanly(hass: HomeAssistant, aioclient_mock, monkeypatch):
    import pytest
    from homeassistant.components import media_source
    from homeassistant.components.media_source import Unresolvable
    from homeassistant.setup import async_setup_component

    library(monkeypatch)
    mock_relay(aioclient_mock)
    await setup(hass)
    assert await async_setup_component(hass, "media_source", {})
    await hass.async_block_till_done()  # integrations register their sources in background tasks
    with pytest.raises(Unresolvable):
        await media_source.async_resolve_media(hass, "media-source://dwarf/nope/DWARF_RAW_x", None)


async def test_read_only_mode_browses_over_ftp(hass: HomeAssistant, aioclient_mock, monkeypatch, hass_client):
    from custom_components.dwarf.direct import ScopeDirectClient

    jpeg = make_jpeg()
    monkeypatch.setattr(ScopeDirectClient, "fetch_stack_blocking", lambda self, known: (NEWEST, len(jpeg), jpeg))
    monkeypatch.setattr(
        ScopeDirectClient,
        "index_stacks_blocking",
        lambda self, known: {OLDER: {"stack": 10, "thumb": 5}, NEWEST: {"stack": len(jpeg), "thumb": None}},
    )
    monkeypatch.setattr(ScopeDirectClient, "read_file_blocking", lambda self, session, name: jpeg)
    aioclient_mock.post(f"{SCOPE}/deviceInfo", json=DEVICE_INFO)
    entry = await setup_direct(hass, monkeypatch)
    root = await browse(hass)
    assert [c.title for c in root.children][0].startswith("M 81")
    from custom_components.dwarf.media_source import stack_path

    assert (await (await hass_client()).get(stack_path(entry.entry_id, NEWEST))).status == 200


# ---- live video

def camera(hass, kind):
    return hass.data["camera"].get_entity(f"camera.dwarf_3_{kind}_camera")


async def test_both_cameras_stream_through_the_relay_in_full_control(hass: HomeAssistant, aioclient_mock):
    from homeassistant.components.camera import CameraEntityFeature

    mock_relay(aioclient_mock)
    await setup(hass)
    for kind, path in (("wide", "ch1"), ("tele", "ch0")):
        entity = camera(hass, kind)
        assert entity.supported_features & CameraEntityFeature.STREAM
        assert await entity.stream_source() == f"rtsp://relay.test:554/{path}/stream0", "the relay forwards port 554"
        assert entity.stream_options["rtsp_transport"] == "tcp"


async def test_read_only_mode_streams_from_the_scope_itself(hass: HomeAssistant, aioclient_mock, monkeypatch):
    aioclient_mock.post(f"{SCOPE}/deviceInfo", json=DEVICE_INFO)
    await setup_direct(hass, monkeypatch)
    assert await camera(hass, "wide").stream_source() == "rtsp://scope.test:554/ch1/stream0"
    assert await camera(hass, "tele").stream_source() == "rtsp://scope.test:554/ch0/stream0"
    assert await camera(hass, "wide").async_camera_image() is None, "no relay, so no still: the stream is the picture"


async def test_the_tele_camera_has_a_still_through_the_relay_too(hass: HomeAssistant, aioclient_mock):
    import base64

    aioclient_mock.get(f"{BASE}/api/frame", json={"data": base64.b64encode(b"\xff\xd8tele").decode()})
    mock_relay(aioclient_mock)
    await setup(hass)
    assert await camera(hass, "tele").async_camera_image() == b"\xff\xd8tele"
    asked = [c[1].query["camera"] for c in aioclient_mock.mock_calls if c[1].path == "/api/frame"]
    assert asked == ["tele"]


async def test_the_wide_camera_keeps_its_entity_id(hass: HomeAssistant, aioclient_mock):
    from homeassistant.helpers import entity_registry as er

    mock_relay(aioclient_mock)
    entry = await setup(hass)
    assert er.async_get(hass).async_get("camera.dwarf_3_wide_camera").unique_id == f"{entry.entry_id}_wide_camera"


async def test_a_refused_poll_keeps_the_last_reading(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, monkeypatch
):
    from custom_components.dwarf import coordinator as coordinator_module

    mock_relay(aioclient_mock)
    entry = await setup(hass)
    assert hass.states.get("sensor.dwarf_3_battery").state == "87"

    aioclient_mock.clear_requests()
    refused = {"detail": "no app connection to carry the command", "code": "busy"}
    mock_relay(aioclient_mock, status=refused, status_code=409)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.dwarf_3_battery").state == "87", "one refused poll is not an outage"

    monkeypatch.setattr(coordinator_module, "GRACE_S", 0)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.dwarf_3_battery").state == "unavailable", "a long outage still shows"
