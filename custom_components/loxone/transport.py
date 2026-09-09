"""Per-signal source arbitration; no name-based equivalence assumptions."""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET


def logger_inventory(xml, port):
    root = ET.fromstring(xml)
    loggers = {e.get("U") for e in root.iter("C") if e.get("Type") == "Logger"
               and e.get("Address", "").startswith("/dev/udp/")
               and e.get("Address", "").endswith("/" + str(port))}
    seconds = {e.get("U", "").lower() for e in root.iter("C") if e.get("Type") == "Second"}
    signals = set()
    for e in root.iter("LoggerMailer"):
        on, off = e.get("On", ""), e.get("Off", "")
        if e.get("RefLogger") in loggers and on == off and ";<v" in on:
            signals.add(on.split(";", 1)[0].lower())
    return signals, next(iter(seconds & signals), None)


class SignalRouter:
    """Heartbeat loss selects fallback, while unchanged signals stay healthy."""
    def __init__(self, emit, clock=time.monotonic):
        self.emit, self.clock = emit, clock
        self.udp_signals = set()
        self.heartbeat = None
        self.heartbeat_at = None
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
        self.udp_signals, self.heartbeat = logger_inventory(xml, port)
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
        return self.heartbeat_at is not None and self.clock() - self.heartbeat_at < 5

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
            if source == "poll":
                self.polled_at[key] = now
                # An in-flight HTTP reply must not undo a newer push event.
                if snapshot is not None and self.revision.get(key, 0) != snapshot.get(key, 0):
                    continue
            if source == "ws":
                self.ws_at[key] = now
                self.ws_values[key] = value
                if key in self.udp_signals and self.udp_healthy:
                    continue
            self.revision[key] = self.revision.get(key, 0) + 1
            self.seen_at[key] = now
            self.sources[key] = source
            if key not in self.last or self.last[key] != value:
                self.last[key] = value
                accepted[original] = value
        if accepted:
            self.emit(accepted)

    def due(self, keys):
        # WS may have updated while UDP had priority. Recover that snapshot
        # without waiting for another change on an otherwise quiet signal.
        if self.websocket_connected and not self.udp_healthy:
            fallback = {key: value for key, value in self.ws_values.items()
                        if self.sources.get(key) == "udp"}
            if fallback:
                self.receive("ws", fallback)
        now = self.clock()
        eligible = [key for key in keys if now - self.polled_at.get(key.lower(), -1e9) >= (
            300 if self.last.get(key.lower()) is not None and (
                (key.lower() in self.udp_signals and self.udp_healthy)
                or (self.websocket_connected and key.lower() in self.ws_at)) else 30)]
        return sorted(eligible, key=lambda key: self.attempted_at.get(key.lower(), -1e9))

    def attempted(self, key):
        self.attempted_at[key.lower()] = self.clock()

    def seed(self, values):
        self.last.update({key.lower(): value for key, value in values.items()})
        self.seen_at.update({key.lower(): self.clock() for key in values})

    def expire(self, keys):
        """Do not display a frozen value as current after all usable paths fail."""
        missing = {}
        now = self.clock()
        for original in keys:
            key = original.lower()
            if key in self.udp_signals and self.udp_healthy:
                continue
            if self.websocket_connected and key in self.ws_at:
                continue
            if self.last.get(key) is not None and now - self.seen_at.get(key, -1e9) >= 90:
                self.last[key] = None
                self.sources[key] = "unavailable"
                missing[original] = None
        if missing:
            self.emit(missing)

    def diagnostics(self):
        from collections import Counter
        return {"heartbeat_configured": self.heartbeat is not None,
                "udp_healthy": self.udp_healthy,
                "configured_udp_signals": len(self.udp_signals),
                "websocket_aliases": sum(map(len, self.aliases.values())),
                "sources": dict(Counter(self.sources.values()))}
