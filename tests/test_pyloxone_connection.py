"""Websocket protocol robustness of the bundled pyloxone_api, without HA."""
import asyncio
import hashlib
import hmac
import importlib
import importlib.util
import json
import logging
import struct
import sys
import types
import uuid
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from Crypto.PublicKey import RSA

ROOT = Path(__file__).resolve().parents[1] / "custom_components/loxone/pyloxone_api"
PACKAGE = "pyloxone_api_under_test"


def _load():
    # The package imports aiohttp at module level; Windows test runs lack it.
    stub = "aiohttp" not in sys.modules and importlib.util.find_spec("aiohttp") is None
    if stub:
        aiohttp = types.ModuleType("aiohttp")
        aiohttp.ClientSession = type("ClientSession", (), {})
        sys.modules["aiohttp"] = aiohttp
    try:
        spec = importlib.util.spec_from_file_location(
            PACKAGE, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
        package = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = package
        spec.loader.exec_module(package)
        return importlib.import_module(PACKAGE + ".connection")
    finally:
        if stub:
            del sys.modules["aiohttp"]


lox = _load()
USER = "user"
STATE_UUID = "0f2f6a0b-01c3-4c5e-ffff504f94000000"


def make(**kwargs):
    return lox.LoxoneConnection("192.168.1.2", USER, "secret", port=80, **kwargs)


def header(msg_type, length, first=0x03):
    return struct.pack("<BBBBI", first, msg_type, 0, 0, length)


def value_state(value):
    body = uuid.UUID(STATE_UUID.replace("-", "")).bytes_le + struct.pack("<d", value)
    return [header(2, len(body)), body]


def ll(control, value, code=200):
    return json.dumps({"LL": {"control": control, "value": value, "Code": str(code)}})


def text_frame(text):
    body = text.encode() if isinstance(text, str) else text
    return [header(0, len(body)), body]


class FakeSocket:
    """Yields the given frames; stays open afterwards if ``block``."""

    def __init__(self, frames, block=False):
        self.frames = frames
        self.block = block
        self.state = NS(CLOSED=object())
        self.sent = []

    async def send(self, message):
        self.sent.append(message)

    async def _frames(self):
        for frame in self.frames:
            yield frame
        if self.block:
            await asyncio.Event().wait()

    def __aiter__(self):
        return self._frames()


async def settle():
    while tasks := asyncio.all_tasks() - {asyncio.current_task()}:
        await asyncio.gather(*tasks)


def queued(conn):
    commands = []
    while not conn._message_queue.empty():
        commands.append(conn._message_queue.get_nowait().command)
    return commands


BAD_FRAMES = {
    "type byte >= 8": [header(9, 4), b"abcd"],
    "8-byte frame without 0x03": [header(2, 5, first=0x10), b"12345"],
    "truncated TEXT": text_frame(b'{"LL": {"control": "jdev/sys/getjwt/HASH/user", "value": {"token": "SECRET"'),
}


@pytest.mark.parametrize("bad", BAD_FRAMES.values(), ids=BAD_FRAMES.keys())
def test_bad_frame_does_not_stop_later_state_updates(bad):
    received = []

    async def callback(message):
        received.append(message)

    async def run():
        conn = make()
        await conn._do_start_listening(callback, FakeSocket(bad + value_state(21.5)))
        await settle()

    asyncio.run(run())
    assert received == [{STATE_UUID: 21.5}]


def test_skipped_frame_is_logged_without_payload(caplog):
    caplog.set_level(logging.DEBUG)

    async def run():
        await make()._do_start_listening(None, FakeSocket(BAD_FRAMES["truncated TEXT"]))
        await settle()

    asyncio.run(run())
    assert "Skipping unparseable" in caplog.text
    assert "SECRET" not in caplog.text and "HASH" not in caplog.text


@pytest.mark.parametrize("frames", [
    [header(0, 5), b'{"LL": {"value": {"token": "SECRET"}}}'],  # length mismatch
    [b'{"LL": {"value": {"token": "SECRET"}}}'],  # no header before it
], ids=["length mismatch", "no header"])
def test_unhandled_frame_is_logged_without_payload(caplog, frames):
    caplog.set_level(logging.DEBUG)

    async def run():
        await make()._do_start_listening(None, FakeSocket(frames))
        await settle()

    asyncio.run(run())
    assert "Message not handled" in caplog.text
    assert "SECRET" not in caplog.text


def test_text_reply_with_raw_newline_in_string_is_delivered():
    received = []

    async def callback(message):
        received.append(message)

    async def run():
        reply = b'{"LL":{"control":"jdev/sps/io/x/a\nb","value":"a\nb","Code":"200"}}'
        await make()._do_start_listening(callback, FakeSocket(text_frame(reply)))
        await settle()

    asyncio.run(run())
    assert received == [{"control": "jdev/sps/io/x/a\nb", "value": "a\nb", "Code": 200}]


JWT = "jdev/sys/getjwt/abc/user/2/edfc5f9a-df3f-4cad-9dddcdc42c732b82/pyloxone_api"
TOKEN = {"token": "jwt", "validUntil": 999999999, "key": "6b6579", "tokenRights": 2}
REJECTED = {
    "getjwt 401": ll(JWT, "", 401),
    "getjwt 200 without token": ll(JWT, {**TOKEN, "token": ""}),
    "authwithtoken 400": ll("authwithtoken/abc/user", "", 400),
    "authwithtoken 403": ll("authwithtoken/abc/user", "", 403),
}


@pytest.mark.parametrize("reply", REJECTED.values(), ids=REJECTED.keys())
def test_rejected_authentication_requests_reconnect(reply):
    async def run():
        conn = make(token={"token": "stale", "valid_until": 999999999, "hash_alg": "SHA256"})
        await conn._websocket_event(lox.TextMessage(reply))
        return conn, queued(conn)

    conn, commands = asyncio.run(run())
    assert conn._reconnect_event.is_set()
    assert lox.CMD_ENABLE_UPDATES not in commands
    assert conn.authentication_state == "rejected"
    assert conn.get_token_dict()["token"] == ""


ACCEPTED = {
    "getjwt 200": ll(JWT, TOKEN),
    "authwithtoken 200": ll("authwithtoken/abc/user", {"validUntil": 999999999}),
}


@pytest.mark.parametrize("reply", ACCEPTED.values(), ids=ACCEPTED.keys())
def test_accepted_authentication_enables_updates(reply):
    async def run():
        conn = make(token={"token": "jwt", "valid_until": 999999999, "hash_alg": "SHA256"})
        await conn._websocket_event(lox.TextMessage(reply))
        return conn, queued(conn)

    conn, commands = asyncio.run(run())
    assert not conn._reconnect_event.is_set()
    assert commands == [lox.CMD_ENABLE_UPDATES]
    assert conn.authentication_state == "accepted"


def test_rejected_token_request_ends_listening_with_token_error():
    # LoxoneTokenError is what makes the integration drop the token and reload.
    async def run():
        conn = make()
        conn._session_key = b"session"
        conn.connection = FakeSocket(text_frame(ll(JWT, "", 401)), block=True)
        await asyncio.wait_for(conn.start_listening(), timeout=5)

    with pytest.raises(lox.LoxoneTokenError):
        asyncio.run(run())


def visusalt(ok=True):
    value = {"key": "41424344", "salt": "73616c74", "hashAlg": "SHA256"} if ok else ""
    return lox.TextMessage(ll(f"dev/sys/getvisusalt/{USER}", value, 200 if ok else 500))


def secured_targets(commands):
    return [c.split("/")[4] for c in commands if c.startswith("jdev/sps/ios/")]


def test_secured_commands_in_flight_get_one_salt_reply_each():
    async def run():
        conn = make()
        await conn.send_secured__websocket_command("uuid-a", "on", "1234")
        await conn.send_secured__websocket_command("uuid-b", "off", "1234")
        requests = queued(conn)
        await conn._websocket_event(visusalt())
        first = queued(conn)
        await conn._websocket_event(visusalt())
        return requests, first, queued(conn)

    requests, first, second = asyncio.run(run())
    assert requests == [f"jdev/sys/getvisusalt/{USER}"] * 2
    assert secured_targets(first) == ["uuid-a"]
    assert secured_targets(second) == ["uuid-b"]


def test_failed_salt_reply_drops_only_its_own_command():
    async def run():
        conn = make()
        await conn.send_secured__websocket_command("uuid-a", "on", "1234")
        await conn._websocket_event(visusalt(ok=False))
        await conn.send_secured__websocket_command("uuid-b", "off", "1234")
        await conn._websocket_event(visusalt())
        return queued(conn)

    assert secured_targets(asyncio.run(run())) == ["uuid-b"]


REDIRECTS = {
    "https with port": ("https://192-168-1-2.504f94000000.dyndns.loxonecloud.com:4443",
                        "wss://192-168-1-2.504f94000000.dyndns.loxonecloud.com:4443/ws/rfc6455"),
    "https default port": ("https://192-168-1-2.504f94000000.dyndns.loxonecloud.com",
                           "wss://192-168-1-2.504f94000000.dyndns.loxonecloud.com/ws/rfc6455"),
}


@pytest.mark.parametrize("redirect,expected", REDIRECTS.values(), ids=REDIRECTS.keys())
def test_remote_access_uses_scheme_and_port_of_redirect(monkeypatch, redirect, expected):
    pem = RSA.generate(1024).publickey().export_key().decode()
    api_key = "{'snr': '50:4F:94:00:00:00', 'version': '16.0.4.21', 'local': false}"
    bodies = {
        lox.CMD_GET_API_KEY: ll("dev/cfg/apiKey", api_key).encode(),
        lox.LOXAPPPATH: b'{"msInfo": {}, "controls": {}}',
        lox.CMD_GET_PUBLIC_KEY: ll("dev/sys/getPublicKey", pem).encode(),
    }

    class Http:
        def __init__(self, url, username, password, scheme, session):
            self.base_url = f"{scheme}://{url}"

            async def close():
                pass

            self.session = NS(close=close)

        async def get(self, endpoint, timeout=None):
            async def read():
                return bodies[endpoint]

            # aiohttp follows the cloud DNS redirect; url is the final location
            return NS(status=200, url=redirect + endpoint, content=NS(read=read))

    urls = []

    async def connect(url, **kwargs):
        urls.append(url)
        return "websocket"

    monkeypatch.setattr(lox, "LoxoneAsyncHttpClient", Http)
    monkeypatch.setattr(lox.wslib, "connect", connect)
    conn = lox.LoxoneConnection("dns.loxonecloud.com/504F94000000", USER, "secret", port=80)
    assert asyncio.run(conn.open()) == "websocket"
    assert urls == [expected]


@pytest.mark.parametrize("version,command", [([10, 1], "jdev/sys/refreshtoken"),
                                             ([12, 0], "jdev/sys/refreshjwt")])
def test_refresh_token_command_per_firmware(version, command):
    async def run():
        conn = make(token={"token": "jwt", "valid_until": 999999999, "hash_alg": "SHA1"})
        conn._key, conn._hash_alg, conn.miniserver_version = "6b6579", "SHA1", version
        await conn._refresh_token()
        return queued(conn)

    token_hash = hmac.new(bytes.fromhex("6b6579"), b"jwt", hashlib.sha1).hexdigest()
    assert asyncio.run(run()) == [f"{command}/{token_hash}/{USER}"]
