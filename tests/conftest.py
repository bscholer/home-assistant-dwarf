import pytest

from custom_components.dwarf3.config_flow import Dwarf3ConfigFlow


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


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
