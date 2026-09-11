"""Per-signal source arbitration; no name-based equivalence assumptions."""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET


def _inventory(xml, port):
    root = ET.fromstring(xml)
    loggers = {e.get("U") for e in root.iter("C") if e.get("Type") == "Logger"
               and e.get("Address", "").startswith("/dev/udp/")
               and e.get("Address", "").endswith("/" + str(port))}
    seconds = {e.get("U", "").lower() for e in root.iter("C") if e.get("Type") == "Second"}
    # Gateway/Client: a logger sits under the LoxLIVE of the Miniserver that
    # sends it, and that Miniserver's heartbeat is keyed by the LoxLIVE UUID.
    lives, logger_live = set(), {}
    for live in root.iter("C"):
        if live.get("Type") == "LoxLIVE" and live.get("U"):
            lives.add(live.get("U").lower())
            for e in live.iter("C"):
                if e.get("U") in loggers:
                    logger_live[e.get("U")] = live.get("U").lower()
    signals, owners = set(), {}
    for e in root.iter("LoggerMailer"):
        on, off = e.get("On", ""), e.get("Off", "")
        if e.get("RefLogger") in loggers and on == off and ";<v" in on:
            key = on.split(";", 1)[0].lower()
            signals.add(key)
            if e.get("RefLogger") in logger_live:
                owners[key] = logger_live[e.get("RefLogger")]
    heartbeats = lives & signals
    return signals, next(iter(seconds & signals), None), owners, heartbeats


def logger_inventory(xml, port):
    signals, heartbeat, _, _ = _inventory(xml, port)
    return signals, heartbeat


class StateUpdate:
    """Changed signal values, delivered to entities through the HA dispatcher.

    ``data`` keeps the interface of the former ``loxone_event`` bus event, which
    is no longer fired: every value would otherwise be written to the recorder.
    """
    __slots__ = ("data",)

    def __init__(self, data):
        self.data = data


class SignalRouter:
    """Heartbeat loss selects fallback, while unchanged signals stay healthy."""
    def __init__(self, emit, clock=time.monotonic):
        self.emit, self.clock = emit, clock
        self.udp_signals = set()
        self.heartbeat = None
        self.heartbeat_at = None
        # Gateway/Client: one heartbeat per Miniserver, keyed by LoxLIVE UUID;
        # a signal is live only while the Miniserver that sends it is.
        self.heartbeats = set()
        self.heartbeat_seen = {}
        self.owners = {}
        self.ws_at = {}
        self.ws_values = {}
        self.polled_at = {}
        self.attempted_at = {}
        self.revision = {}
        self.last = {}
        self.sources = {}
        self.aliases = {}
        self.websocket_connected = False
        self.http_scales = {}
        self.seen_at = {}

    def configure(self, xml, port, config=None, terminals=()):
        self.udp_signals, self.heartbeat, self.owners, self.heartbeats = _inventory(xml, port)
        if config is not None:
            from .signal_bindings import SignalBindings
            bindings = SignalBindings(xml, config)
            self.aliases = bindings.websocket_aliases(terminals)
            self.http_scales = bindings.http_scales(terminals)

    def websocket_state(self, connected):
        self.websocket_connected = connected
        if not connected:
            self.ws_at.clear()
            self.ws_values.clear()

    @property
    def udp_healthy(self):
        now = self.clock()
        return ((self.heartbeat_at is not None and now - self.heartbeat_at < 5)
                or any(now - at < 5 for at in self.heartbeat_seen.values()))

    def udp_live(self, key):
        """UDP is trusted for ``key`` while the Miniserver sending it is alive."""
        live = self.owners.get(key)
        if live in self.heartbeats:
            at = self.heartbeat_seen.get(live)
            return at is not None and self.clock() - at < 5
        return self.udp_healthy

    def receive(self, source, values, snapshot=None):
        now, accepted = self.clock(), {}
        if source == "ws":
            self.websocket_connected = True
            expanded = dict(values)
            for key, value in values.items():
                for terminal in self.aliases.get(key.lower(), ()):
                    expanded.setdefault(terminal, value)
            values = expanded
        for original, value in values.items():
            key = original.lower()
            if source == "udp" and key == self.heartbeat:
                self.heartbeat_at = now
                continue
            if source == "udp" and key in self.heartbeats:
                self.heartbeat_seen[key] = now
                continue
            if source == "poll":
                self.polled_at[key] = now
                # An in-flight HTTP reply must not undo a newer push event.
                if snapshot is not None and self.revision.get(key, 0) != snapshot.get(key, 0):
                    continue
            if source == "ws":
                self.ws_at[key] = now
                self.ws_values[key] = value
                if key in self.udp_signals and self.udp_live(key):
                    continue
            self.revision[key] = self.revision.get(key, 0) + 1
            self.seen_at[key] = now
            self.sources[key] = source
            if key not in self.last or self.last[key] != value:
                self.last[key] = value
                accepted[original] = value
        if accepted:
            self.emit(accepted)

    def due(self, keys, limit=None):
        """Keys to poll now, least recently attempted first, at most ``limit``.

        The limit bounds the request load per cycle; the ordering rotates
        fairly through all keys so none is starved.
        """
        # WS may have updated while UDP had priority. Recover that snapshot
        # without waiting for another change on an otherwise quiet signal.
        if self.websocket_connected and not self.udp_healthy:
            fallback = {key: value for key, value in self.ws_values.items()
                        if self.sources.get(key) == "udp"}
            if fallback:
                self.receive("ws", fallback)
        now = self.clock()
        # A signal with a live push path (UDP heartbeat or open WebSocket) only
        # gets a half-hourly sanity read; the heartbeat reports path loss itself.
        eligible = [key for key in keys if now - self.polled_at.get(key.lower(), -1e9) >= (
            1800 if self.last.get(key.lower()) is not None and (
                (key.lower() in self.udp_signals and self.udp_live(key.lower()))
                or (self.websocket_connected and key.lower() in self.ws_at)) else 30)]
        ordered = sorted(eligible, key=lambda key: self.attempted_at.get(key.lower(), -1e9))
        return ordered[:limit] if limit else ordered

    def attempted(self, key):
        self.attempted_at[key.lower()] = self.clock()

    def seed(self, values):
        self.last.update({key.lower(): value for key, value in values.items()})
        self.seen_at.update({key.lower(): self.clock() for key in values})

    def expire(self, keys, max_age=90):
        """Do not display a frozen value as current after all usable paths fail.

        ``max_age`` grows with the poll rotation period so a value that is
        simply waiting for its turn is not declared unavailable.
        """
        missing = {}
        now = self.clock()
        for original in keys:
            key = original.lower()
            if key in self.udp_signals and self.udp_live(key):
                continue
            if self.websocket_connected and key in self.ws_at:
                continue
            if self.last.get(key) is not None and now - self.seen_at.get(key, -1e9) >= max_age:
                self.last[key] = None
                self.sources[key] = "unavailable"
                missing[original] = None
        if missing:
            self.emit(missing)

    def diagnostics(self):
        from collections import Counter
        now = self.clock()
        return {"heartbeat_configured": self.heartbeat is not None or bool(self.heartbeats),
                "udp_healthy": self.udp_healthy,
                "miniserver_heartbeats": {live: (live in self.heartbeat_seen and now - self.heartbeat_seen[live] < 5)
                                          for live in sorted(self.heartbeats)},
                "configured_udp_signals": len(self.udp_signals),
                "websocket_aliases": sum(map(len, self.aliases.values())),
                "sources": dict(Counter(self.sources.values()))}
