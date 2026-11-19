import pytest

from custom_components.dwarf3.config_flow import Dwarf3ConfigFlow


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def card_www(tmp_path, monkeypatch):
    """The card is copied into www; keep that out of the shared test config folder."""
    from custom_components.dwarf3 import card

    www = tmp_path / "www"
    monkeypatch.setattr(card, "_www", lambda hass: www)
    return www


@pytest.fixture(autouse=True)
def no_local_relay(monkeypatch):
    """By default no relay is found on this Home Assistant, and nothing touches the real network."""

    async def none(self):
        return None

    monkeypatch.setattr(Dwarf3ConfigFlow, "_local_ip", none)


@pytest.fixture
def local_ip(monkeypatch):
    def set_ip(ip: str | None) -> None:
        async def fake(self):
            return ip

        monkeypatch.setattr(Dwarf3ConfigFlow, "_local_ip", fake)

    return set_ip


class FakeSupervisor:
    """Just enough of the Supervisor client for the relay app install."""

    def __init__(self, *, installed=False, options=None, state="stopped", repos=(), fail_on=None, gate=None):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        from aiohasupervisor import SupervisorError, SupervisorNotFoundError
        from aiohasupervisor.models import AddonState

        self.installed = installed
        self.options = dict(options or {"scope_host": "", "auth": False})
        self.state = AddonState(state)
        self.calls: list[tuple] = []
        self.on_start = None

        def record(name, result=None, error=None):
            async def call(*args, **kwargs):
                self.calls.append((name, args, kwargs))
                if error is not None and fail_on == name:
                    raise error
                return result

            return call

        async def addon_info(slug):
            self.calls.append(("addon_info", (slug,), {}))
            if not self.installed:
                raise SupervisorNotFoundError("not installed")
            return SimpleNamespace(options=self.options, state=self.state)

        async def install(slug, *a, **k):
            self.calls.append(("install_addon", (slug,), {}))
            if gate is not None:
                await gate.wait()  # a slow install: the flow shows a progress screen meanwhile
            if fail_on == "install_addon":
                raise SupervisorError("No space left on device")
            self.installed = True

        async def set_options(slug, options):
            self.calls.append(("set_addon_options", (slug,), {"config": options.config}))
            self.options = dict(options.config)

        async def start(slug):
            self.calls.append(("start_addon", (slug,), {}))
            if self.on_start:
                self.on_start()  # the app "comes up": the test makes the relay answer

        repo_objects = [SimpleNamespace(source=r) for r in repos]
        self.store = SimpleNamespace(
            repositories_list=record("repositories_list", repo_objects),
            add_repository=record("add_repository"),
            reload=record("reload"),
            install_addon=install,
        )
        self.addons = SimpleNamespace(
            addon_info=addon_info,
            set_addon_options=set_options,
            start_addon=start,
            restart_addon=record("restart_addon"),
        )
        del AsyncMock

    def names(self):
        return [c[0] for c in self.calls]


@pytest.fixture
def supervisor(monkeypatch):
    """Pretend this Home Assistant has a Supervisor. Returns a function that installs a fake one."""
    from custom_components.dwarf3 import app_setup

    monkeypatch.setattr(app_setup, "READY_WAIT_S", 0)
    monkeypatch.setattr(app_setup, "READY_TRIES", 3)

    def install(**kwargs):
        fake = FakeSupervisor(**kwargs)
        monkeypatch.setattr(app_setup, "has_supervisor", lambda hass: True)
        monkeypatch.setattr(app_setup, "supervisor_client", lambda hass: fake)
        return fake

    return install


@pytest.fixture(autouse=True)
def no_live_listener(monkeypatch):
    """The live stream is a task that never ends, so most tests run without it. tests/test_live.py opts in."""

    async def idle(coordinator):
        return None

    monkeypatch.setattr("custom_components.dwarf3.follow_relay", idle)
