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


def test_unload_hooks_return_nothing():
    """HA treats a truthy return value of an unload hook as a coroutine and
    fails the unload with "a coroutine was expected" (seen at 1.6.x reload)."""
    import ast
    import builtins
    from unittest.mock import MagicMock

    source = (Path(__file__).resolve().parents[1] / "custom_components/loxone/__init__.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    checked = 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "async_on_unload" and node.args):
            continue
        hook = node.args[0]
        if isinstance(hook, ast.Lambda):
            names = {n.id: MagicMock(name=n.id) for n in ast.walk(hook.body)
                     if isinstance(n, ast.Name) and not hasattr(builtins, n.id)}
            result = eval(compile(ast.Expression(body=hook.body), "<lambda>", "eval"), names)
            assert result is None, f"line {hook.lineno}: unload lambda returns {result!r}"
            checked += 1
        elif isinstance(hook, ast.Name) and hook.id in functions:
            returns = [r for r in ast.walk(functions[hook.id]) if isinstance(r, ast.Return) and r.value is not None]
            assert not returns, f"{hook.id} returns a value from an unload hook"
            checked += 1
    assert checked >= 2
