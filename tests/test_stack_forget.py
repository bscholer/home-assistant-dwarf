from homeassistant.core import HomeAssistant

from custom_components.dwarf import stack
from custom_components.dwarf.stack import StackLibrary, StackTracker

OLD = "DWARF_RAW_TELE_M 31_EXP_30_GAIN_60_2026-11-17-21-05-28-280"
NEW = "DWARF_RAW_TELE_M 81_EXP_30_GAIN_60_2026-11-18-03-11-46-101"


class FakeSource:
    """Sessions with a stack each; the newest one is "latest"."""

    def __init__(self, sessions):
        self.sessions = list(sessions)

    async def fetch(self, known):
        if not self.sessions:
            return None
        session = max(self.sessions, key=stack.session_order)
        if known == (session, 1):
            return session, 1, None
        return session, 1, session.encode()

    async def index(self, known):
        return {name: {"stack": 1, "thumb": 1} for name in self.sessions}

    async def read(self, session, name):
        return session.encode()


async def test_deleting_the_latest_stack_shows_the_one_before(hass: HomeAssistant, monkeypatch):
    monkeypatch.setattr(stack, "downscale", lambda raw: raw)
    source = FakeSource([OLD, NEW])
    tracker = StackTracker(hass, source)
    changes = []
    tracker.add_listener(lambda: changes.append(tracker.session))
    await tracker.async_check()
    assert tracker.session == NEW

    source.sessions.remove(NEW)
    tracker.forget(NEW)
    assert tracker.session is None and tracker.jpeg is None, "never keep showing a deleted stack"
    assert tracker.due(running=False)
    await tracker.async_check()
    assert tracker.session == OLD
    assert changes == [NEW, None, OLD]


async def test_deleting_the_last_stack_leaves_nothing(hass: HomeAssistant, monkeypatch):
    monkeypatch.setattr(stack, "downscale", lambda raw: raw)
    source = FakeSource([NEW])
    tracker = StackTracker(hass, source)
    await tracker.async_check()
    source.sessions.clear()
    tracker.forget(NEW)
    await tracker.async_check()
    assert tracker.session is None and tracker.jpeg is None


async def test_forgetting_another_session_keeps_the_latest(hass: HomeAssistant, monkeypatch):
    monkeypatch.setattr(stack, "downscale", lambda raw: raw)
    tracker = StackTracker(hass, FakeSource([OLD, NEW]))
    await tracker.async_check()
    tracker.forget(OLD)
    assert tracker.session == NEW


async def test_library_drops_a_deleted_session_at_once(hass: HomeAssistant, monkeypatch):
    monkeypatch.setattr(stack, "downscale", lambda raw: raw)
    source = FakeSource([OLD, NEW])
    library = StackLibrary(hass, source)
    assert [name for name, _ in await library.async_sessions()] == [NEW, OLD]
    await library.async_image(NEW, thumbnail=True)
    source.sessions.remove(NEW)
    library.forget(NEW)
    assert [name for name, _ in await library.async_sessions()] == [OLD], "the listing is cached"
    assert all(key[0] != NEW for key in library._images)
