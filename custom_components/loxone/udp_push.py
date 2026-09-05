"""UDP-Push-Kanal fuer Klemmen ohne Visu-Haekchen.

Der Miniserver pusht ueber den WebSocket ausschliesslich Bausteine mit Visu-Haekchen. Fuer
alle anderen Klemmen gibt es genau einen Echtzeitweg: ein Logger-Objekt mit UDP-Adresse
(``/dev/udp/<HA-IP>/<Port>``) und je Klemme eine Logger-Referenz (``OutputRefLM``) im
Miniserver-Programm. Eingerichtet wird das mit dem Skript ``ha_udp_logger.py`` aus dem
Loxone-Config-Skill; die Zuweisung direkt an der Klemme wertet der Miniserver nicht aus.

Der Miniserver schickt dann bei jeder Aenderung ein Datagramm (ein Textzeile, CRLF)::

    2026-09-05 16:23:12;HA UDP;18f7cbc0-017a-4c94-ffffa13734b4be2f;40.00
    <Zeitstempel>;<Titel des Logger-Objekts>;<Klemmen-UUID>;<Wert>

Gemessen am Demo-Koffer (Miniserver Gen 2, 05.09.2026): das Paket kommt 12-20 ms nach der
Aenderung, Impulse ab 20 ms Laenge vollstaendig (Ein und Aus), bei 10 ms geht ein Teil verloren
(SPS-Zyklus). Analoge Eingaenge melden auch Rauschen unterhalb der Anzeigeaufloesung - ein
unbelegter 0-10-V-Eingang lieferte rund ein Paket je Sekunde mit unveraendertem Text. Gleiche
Werte werden deshalb hier verworfen, bevor sie den Event-Bus erreichen.

Dieses Modul haengt bewusst nicht an Home Assistant: reine asyncio-Datagram-Verarbeitung, damit
Parser und Protokoll ohne HA-Installation testbar sind (tests/test_udp_push.py).
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Callable, Iterable

_LOGGER = logging.getLogger(__name__)

# Loxone-UUIDs haben 35 Zeichen (8-4-4-16), nicht 36 wie RFC-UUIDs.
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{16}$")
_NUMBER_RE = re.compile(r"^\s*([-+]?\d+(?:[.,]\d+)?)")

ValuesCallback = Callable[[dict[str, float]], None]


def parse_value(raw: str) -> float | None:
    """'40.00' -> 40.0, '1' -> 1.0, '25,5°' -> 25.5, '<v.i>' / '' -> None.

    Der Logger rendert ``<v>`` ohne Einheit; trotzdem tolerant gegen angehaengte Einheiten und
    Dezimalkomma, weil der Meldungstext im Programm frei editierbar ist.
    """
    m = _NUMBER_RE.match(raw or "")
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


def parse_datagram(data: bytes) -> dict[str, float]:
    """Alle ``<uuid>;<wert>``-Paare eines Datagramms.

    Zeitstempel und Logger-Titel stehen davor, muessen aber nicht: gesucht wird das erste Feld,
    das wie eine Loxone-UUID aussieht, der Wert ist das Feld dahinter. Zeilen ohne UUID oder
    ohne Zahl werden ignoriert - der Empfaenger darf an einem fremden Logger-Text nicht sterben.
    """
    out: dict[str, float] = {}
    text = data.decode("utf-8", errors="replace")
    for line in text.splitlines():
        fields = [f.strip() for f in line.split(";")]
        for i, field in enumerate(fields[:-1]):
            if _UUID_RE.match(field):
                value = parse_value(fields[i + 1])
                if value is not None:
                    out[field] = value
                break
    return out


class LoxoneUdpPushProtocol(asyncio.DatagramProtocol):
    """Nimmt Logger-Datagramme an und reicht neue Werte als ``{uuid: wert}`` weiter.

    ``known``: nur diese UUIDs durchlassen (typisch: alle Controls der Strukturdatei samt den
    auto-entdeckten Klemmen). Ohne Filter kaeme jeder fremde Logger-Text als Event durch.
    """

    def __init__(self, callback: ValuesCallback, known: Iterable[str] | None = None,
                 dedupe: bool = True) -> None:
        self._callback = callback
        self._known = {u.lower() for u in known} if known is not None else None
        self._dedupe = dedupe
        self._last: dict[str, float] = {}
        self.transport: asyncio.DatagramTransport | None = None
        # Zaehler fuer Diagnose/Systemzustand
        self.packets = 0
        self.values = 0
        self.dropped_unknown = 0
        self.dropped_duplicate = 0
        self.last_received: float | None = None

    def connection_made(self, transport) -> None:  # type: ignore[override]
        self.transport = transport

    def datagram_received(self, data: bytes, addr) -> None:
        self.packets += 1
        self.last_received = time.time()
        fresh: dict[str, float] = {}
        for uuid, value in parse_datagram(data).items():
            if self._known is not None and uuid.lower() not in self._known:
                self.dropped_unknown += 1
                continue
            if self._dedupe and self._last.get(uuid) == value:
                self.dropped_duplicate += 1
                continue
            self._last[uuid] = value
            fresh[uuid] = value
        if fresh:
            self.values += len(fresh)
            try:
                self._callback(fresh)
            except Exception:  # noqa: BLE001 - ein defekter Empfaenger darf den Kanal nicht stoppen
                _LOGGER.exception("UDP-Push: Callback fehlgeschlagen")

    def error_received(self, exc: Exception) -> None:
        _LOGGER.debug("UDP-Push: Socket-Fehler %s", exc)

    def forget(self, uuid: str) -> None:
        """Letzten Wert vergessen, damit der naechste gleiche Wert wieder durchkommt."""
        self._last.pop(uuid, None)


async def async_start_udp_push(loop: asyncio.AbstractEventLoop, port: int, callback: ValuesCallback,
                               known: Iterable[str] | None = None, host: str = "0.0.0.0"):
    """UDP-Empfaenger oeffnen. Liefert (transport, protocol); ``transport.close()`` beendet ihn.

    Bindet an alle Adressen, damit auch Broadcast-Ziele im Logger (``192.168.0.255`` oder
    ``255.255.255.255``) ankommen - der Miniserver muss die HA-Adresse dann nicht kennen.
    """
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: LoxoneUdpPushProtocol(callback, known), local_addr=(host, port)
    )
    return transport, protocol
