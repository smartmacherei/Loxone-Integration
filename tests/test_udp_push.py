"""Tests fuer den UDP-Push-Kanal (custom_components/loxone/udp_push.py).

Laufen ohne Home Assistant: das Modul wird direkt aus der Datei geladen, damit der
Paket-Import von custom_components.loxone (der HA braucht) nicht angestossen wird.

    py -3 -m pytest tests/ -q
"""
from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import socket

import pytest

_MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "loxone" / "udp_push.py"
_spec = importlib.util.spec_from_file_location("udp_push", _MODULE_PATH)
udp_push = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(udp_push)

# Echte Datagramme vom Demo-Koffer, 05.09.2026 (Miniserver Gen 2, FW 17.1.6.30)
REAL_DIGITAL_ON = b"2026-09-05 16:05:59;HA UDP;V1-OutputRefLM-UDP;1\r\n"
REAL_TERMINAL_ANALOG = b"2026-09-05 16:23:12;HA UDP;18f7cbc0-017a-4c94-ffffa13734b4be2f;40\r\n"
REAL_TERMINAL_DIGITAL = b"2026-09-05 16:23:11;HA UDP;18f7cc6d-0257-8e27-ffff4488d265440f;0\r\n"
UUID_A = "18f7cbc0-017a-4c94-ffffa13734b4be2f"
UUID_B = "18f7cc6d-0257-8e27-ffff4488d265440f"


class TestParseValue:
    def test_plain_numbers(self):
        assert udp_push.parse_value("1") == 1.0
        assert udp_push.parse_value("0") == 0.0
        assert udp_push.parse_value("40.00") == 40.0
        assert udp_push.parse_value("-3.5") == -3.5

    def test_unit_and_decimal_comma_are_tolerated(self):
        assert udp_push.parse_value("25.5°") == 25.5
        assert udp_push.parse_value("25,5") == 25.5
        assert udp_push.parse_value(" 4Lx") == 4.0

    def test_non_numeric_is_none(self):
        assert udp_push.parse_value("<v.i>") is None
        assert udp_push.parse_value("") is None
        assert udp_push.parse_value(None) is None
        assert udp_push.parse_value("Ein") is None


class TestParseDatagram:
    def test_real_terminal_line(self):
        assert udp_push.parse_datagram(REAL_TERMINAL_ANALOG) == {UUID_A: 40.0}
        assert udp_push.parse_datagram(REAL_TERMINAL_DIGITAL) == {UUID_B: 0.0}

    def test_line_without_uuid_is_ignored(self):
        # Meldungstext ohne UUID (so sahen die ersten Testobjekte aus)
        assert udp_push.parse_datagram(REAL_DIGITAL_ON) == {}

    def test_multiple_lines_and_garbage(self):
        data = REAL_TERMINAL_ANALOG + b"kein;sinn\r\n" + REAL_TERMINAL_DIGITAL + b"\xff\xfe\r\n"
        assert udp_push.parse_datagram(data) == {UUID_A: 40.0, UUID_B: 0.0}

    def test_uuid_without_timestamp_or_title(self):
        # Logger mit ExcludeTimestamp oder anderer Textform: UUID darf vorne stehen
        assert udp_push.parse_datagram(f"{UUID_A};12.5".encode()) == {UUID_A: 12.5}

    def test_rfc_uuid_is_not_a_loxone_uuid(self):
        # 36 Zeichen (8-4-4-4-12) sind keine Loxone-UUID - Falle 9 aus dem Skill
        assert udp_push.parse_datagram(b"x;12345678-1234-1234-1234-123456789abc;1\r\n") == {}

    def test_value_missing_after_uuid(self):
        assert udp_push.parse_datagram(f"x;{UUID_A}".encode()) == {}
        assert udp_push.parse_datagram(f"x;{UUID_A};<v.i>".encode()) == {}


class TestProtocol:
    def _proto(self, known=None, dedupe=True):
        received = []
        proto = udp_push.LoxoneUdpPushProtocol(received.append, known=known, dedupe=dedupe)
        return proto, received

    def test_forwards_values_and_counts(self):
        proto, received = self._proto()
        proto.datagram_received(REAL_TERMINAL_ANALOG, ("192.168.0.186", 55555))
        assert received == [{UUID_A: 40.0}]
        assert proto.packets == 1 and proto.values == 1 and proto.last_received is not None

    def test_deduplicates_unchanged_values(self):
        # Ein rauschender 0-10-V-Eingang schickt "40" im Sekundentakt - nur der erste zaehlt
        proto, received = self._proto()
        for _ in range(3):
            proto.datagram_received(REAL_TERMINAL_ANALOG, None)
        proto.datagram_received(REAL_TERMINAL_ANALOG.replace(b";40", b";41"), None)
        assert received == [{UUID_A: 40.0}, {UUID_A: 41.0}]
        assert proto.dropped_duplicate == 2

    def test_dedupe_can_be_disabled_and_forgotten(self):
        proto, received = self._proto(dedupe=False)
        proto.datagram_received(REAL_TERMINAL_ANALOG, None)
        proto.datagram_received(REAL_TERMINAL_ANALOG, None)
        assert len(received) == 2
        proto2, received2 = self._proto()
        proto2.datagram_received(REAL_TERMINAL_ANALOG, None)
        proto2.forget(UUID_A)
        proto2.datagram_received(REAL_TERMINAL_ANALOG, None)
        assert len(received2) == 2

    def test_known_filter_drops_foreign_uuids(self):
        proto, received = self._proto(known={UUID_B})
        proto.datagram_received(REAL_TERMINAL_ANALOG + REAL_TERMINAL_DIGITAL, None)
        assert received == [{UUID_B: 0.0}]
        assert proto.dropped_unknown == 1

    def test_known_filter_is_case_insensitive(self):
        proto, received = self._proto(known={UUID_A.upper()})
        proto.datagram_received(REAL_TERMINAL_ANALOG, None)
        assert received == [{UUID_A: 40.0}]

    def test_callback_exception_does_not_kill_channel(self):
        calls = []

        def boom(values):
            calls.append(values)
            raise RuntimeError("Empfaenger kaputt")

        proto = udp_push.LoxoneUdpPushProtocol(boom)
        proto.datagram_received(REAL_TERMINAL_ANALOG, None)
        proto.datagram_received(REAL_TERMINAL_DIGITAL, None)
        assert len(calls) == 2

    def test_empty_datagram_triggers_no_callback(self):
        proto, received = self._proto()
        proto.datagram_received(b"", None)
        proto.datagram_received(REAL_DIGITAL_ON, None)
        assert received == [] and proto.packets == 2


def _free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_end_to_end_over_real_socket():
    """Datagramm ueber einen echten Socket an den Empfaenger schicken."""

    async def run():
        loop = asyncio.get_running_loop()
        port = _free_udp_port()
        got = loop.create_future()
        transport, protocol = await udp_push.async_start_udp_push(
            loop, port, lambda values: got.done() or got.set_result(values), known=[UUID_A], host="127.0.0.1"
        )
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.sendto(REAL_TERMINAL_ANALOG, ("127.0.0.1", port))
            return await asyncio.wait_for(got, 3), protocol
        finally:
            transport.close()

    values, protocol = asyncio.run(run())
    assert values == {UUID_A: 40.0}
    assert protocol.packets == 1


def test_port_in_use_raises_oserror():
    async def run():
        loop = asyncio.get_running_loop()
        port = _free_udp_port()
        t1, _ = await udp_push.async_start_udp_push(loop, port, lambda v: None, host="127.0.0.1")
        try:
            with pytest.raises(OSError):
                await udp_push.async_start_udp_push(loop, port, lambda v: None, host="127.0.0.1")
        finally:
            t1.close()

    asyncio.run(run())
