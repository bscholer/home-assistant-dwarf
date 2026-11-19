"""The relay app's start script: how the options become the relay's environment."""

import importlib.util
import urllib.request
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("relay_run", Path(__file__).parents[1] / "dwarf3_relay" / "run.py")
run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run)

NO_SITE = lambda environ: None  # noqa: E731
HOME = ("44.5", "-120.5", "UTC")  # what Home Assistant would say. Not anyone's real site.


def plan(options, tmp_path, fetch=NO_SITE, environ=None):
    return run.plan(options, environ or {}, data_dir=tmp_path, fetch_site=fetch)


def test_the_scope_address_is_required(tmp_path):
    with pytest.raises(SystemExit, match="Telescope IP address"):
        plan({"scope_host": " "}, tmp_path)


def test_defaults_need_no_token(tmp_path):
    env, _ = plan({"scope_host": "192.0.2.10"}, tmp_path)
    assert env["DWARF3_HOST"] == "192.0.2.10"
    assert env["DWARF3_AUTH"] == "off"
    assert "DWARF3_API_TOKEN" not in env
    assert not (tmp_path / "api-token").exists()


def test_your_own_token_is_used(tmp_path):
    env, messages = plan({"scope_host": "x", "auth": True, "api_token": " abc "}, tmp_path)
    assert (env["DWARF3_AUTH"], env["DWARF3_API_TOKEN"]) == ("on", "abc")
    assert not any("token is" in m for m in messages), "no need to print a token you chose"


def test_a_made_token_is_printed_and_kept(tmp_path):
    env, messages = plan({"scope_host": "x", "auth": True}, tmp_path)
    token = env["DWARF3_API_TOKEN"]
    assert len(token) >= 32 and f"Your access token is: {token}" in messages
    assert (tmp_path / "api-token").stat().st_mode & 0o777 == 0o600
    again, _ = plan({"scope_host": "x", "auth": True}, tmp_path)
    assert again["DWARF3_API_TOKEN"] == token, "the same token after a restart"


def test_location_comes_from_home_assistant_when_empty(tmp_path):
    env, _ = plan({"scope_host": "x"}, tmp_path, fetch=lambda environ: HOME)
    assert (env["DWARF3_LAT"], env["DWARF3_LON"], env["DWARF3_TZ"]) == HOME
    assert env["DWARF3_UTC_OFFSET"] == "0.0"


def test_your_own_location_wins(tmp_path):
    options = {"scope_host": "x", "latitude": "10", "longitude": "20", "timezone": "UTC"}
    env, _ = plan(options, tmp_path, fetch=lambda environ: pytest.fail("should not ask Home Assistant"))
    assert (env["DWARF3_LAT"], env["DWARF3_LON"]) == ("10", "20")


def test_half_a_location_falls_back_to_home_assistant(tmp_path):
    env, _ = plan({"scope_host": "x", "latitude": "10"}, tmp_path, fetch=lambda environ: HOME)
    assert env["DWARF3_LAT"] == "44.5"


def test_no_location_anywhere_says_so_and_guesses_nothing(tmp_path):
    env, messages = plan({"scope_host": "x"}, tmp_path)
    assert "DWARF3_LAT" not in env
    assert any("Prepare button will not work" in m for m in messages)


def test_the_supervisor_lookup_survives_a_failure(monkeypatch):
    assert run.home_assistant_site({}) is None, "no supervisor token"

    def boom(*args, **kwargs):
        raise OSError("no route")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert run.home_assistant_site({"SUPERVISOR_TOKEN": "t"}) is None
