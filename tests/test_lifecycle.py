"""A fired one-shot event must not be removed twice during HA reload."""
import asyncio
import importlib
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest
import websockets.exceptions

from test_udp_install import PACKAGE, module

lifecycle = module("lifecycle")
errors = importlib.import_module(PACKAGE + ".pyloxone_api.exceptions")


def ended(coroutine_or_none, hass=None):
    """Run a listener task to its end and report the reactions to it."""
    hass = hass or NS(data={})
    reloads, forgotten = [], []

    async def run():
        if coroutine_or_none is None:
            task = asyncio.create_task(asyncio.sleep(10))
            await asyncio.sleep(0)
            task.cancel()
        else:
            task = asyncio.create_task(coroutine_or_none)
        await asyncio.gather(task, return_exceptions=True)
        lifecycle.listener_ended(hass, "entry", task, reloads.append, lambda: forgotten.append(True))

    asyncio.run(run())
    return reloads, forgotten


async def fail(error):
    raise error


async def finish():
    return None


@pytest.mark.parametrize("error", [RuntimeError("boom"), KeyError("value"), ValueError("frame"),
                                   websockets.exceptions.ConnectionClosedError(None, None)])
def test_unexpected_listener_error_reloads_instead_of_freezing(error):
    # Issue #17: an error outside the four known classes left every entity frozen.
    assert ended(fail(error)) == ([1.0], [])


def test_known_connection_losses_reload_after_one_second():
    for error in (errors.LoxoneConnectionError("lost"), errors.LoxoneOutOfServiceException(),
                  errors.LoxoneConnectionClosedOk(), websockets.exceptions.ConnectionClosedOK(None, None)):
        assert ended(fail(error)) == ([1.0], [])


def test_unload_cancel_and_regular_close_do_not_reload():
    assert ended(None) == ([], [])
    assert ended(finish()) == ([], [])


def test_token_retry_delay_doubles_up_to_five_minutes():
    assert [lifecycle.token_retry_delay(n) for n in range(1, 12)] == [
        1, 2, 4, 8, 16, 32, 64, 128, 256, 300, 300]


def test_repeated_token_rejection_backs_off_until_a_connection_is_accepted():
    # Basic auth works, the token is refused: every reload would download structure and program again.
    hass = NS(data={})
    assert ended(fail(errors.LoxoneTokenError("rejected")), hass) == ([1], [True])
    assert ended(fail(errors.LoxoneTokenError("rejected")), hass) == ([2], [True])
    assert ended(fail(errors.LoxoneTokenError("rejected")), hass) == ([4], [True])
    lifecycle.token_accepted(hass, "entry", NS(authentication_state="rejected"))
    assert ended(fail(errors.LoxoneTokenError("rejected")), hass) == ([8], [True])
    lifecycle.token_accepted(hass, "entry", NS(authentication_state="accepted"))
    assert ended(fail(errors.LoxoneTokenError("rejected")), hass) == ([1], [True])
    # Another Miniserver keeps its own count.
    assert ended(fail(errors.LoxoneTokenError("rejected")), NS(data=hass.data)) == ([2], [True])


class Api:
    def __init__(self, token):
        self.token, self.closed = token, False

    def get_token_dict(self):
        return self.token

    async def close(self):
        self.closed = True


def stop(token, data):
    updates = []
    entry = NS(data=data)
    hass = NS(config_entries=NS(async_update_entry=lambda e, **kwargs: updates.append(kwargs)))
    api = Api(token)
    asyncio.run(lifecycle.save_token_and_close(hass, entry, api))
    return updates, api.closed


def test_stop_without_token_still_closes_the_connection():
    assert stop({}, {"token": "old"}) == ([], True)


def test_stop_keeps_the_token_and_other_data():
    token = {"token": "t", "hash_alg": "SHA256", "valid_until": 42, "unsecure_password": False}
    assert stop(token, {"other": 1}) == (
        [{"data": {"other": 1, "token": "t", "hash_alg": "SHA256", "valid_until": 42}}], True)


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
