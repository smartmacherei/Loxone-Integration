"""A fired one-shot event must not be removed twice during HA reload."""
import asyncio
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

spec = importlib.util.spec_from_file_location("lifecycle", Path(__file__).resolve().parents[1] / "custom_components/loxone/lifecycle.py")
lifecycle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lifecycle)


@pytest.mark.parametrize("fire_before_unload", [True, False])
def test_listener_cleanup_and_queued_events(monkeypatch, fire_before_unload):
    monkeypatch.setitem(sys.modules, "homeassistant.core", NS(callback=lambda fn: fn))
    callbacks, unload, removed, delivered = [], [], [], []
    def listen(event_type, handler):
        callbacks.append(handler)
        def cancel():
            assert not removed, "HA rejects removal of an already removed listener"
            removed.append(event_type)
        return cancel
    async def listener(event):
        delivered.append(event)
    async def run():
        tasks = []
        def create(coro):
            tasks.append(asyncio.create_task(coro))
        hass = NS(bus=NS(async_listen=listen), async_create_task=create)
        entry = NS(async_on_unload=unload.append)
        lifecycle.listen_once(hass, entry, "started", listener)
        if fire_before_unload:
            callbacks[0]("event")
            callbacks[0]("duplicate")
        unload[0]()
        unload[0]()
        callbacks[0]("queued after unload")
        if tasks:
            await asyncio.gather(*tasks)
    asyncio.run(run())
    assert removed == ["started"]
    assert delivered == (["event"] if fire_before_unload else [])
