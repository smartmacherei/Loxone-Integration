"""Weg 3 value rules: which entities export what, and which number goes out."""
from types import SimpleNamespace as NS

import pytest

from test_udp_install import module

values = module("ha_values")


def state(value, **attributes):
    return NS(state=value, attributes=attributes)


def test_numeric_boolean_and_enum_states_export_one_value():
    number, = values.entries_for("sensor.pool", state("23.5", friendly_name="Pool"))
    assert number == {"key": "sensor.pool", "entity_id": "sensor.pool", "attribute": None, "title": "Pool", "digital": False}
    assert values.value_of(number, state("23.5")) == 23.5
    digital, = values.entries_for("binary_sensor.tor", state("off", friendly_name="Tor"))
    assert digital["digital"] and values.value_of(digital, state("on")) == 1.0
    assert values.value_of(digital, state("off")) == 0.0
    enum, = values.entries_for("select.modus", state("eco", options=["eco", "comfort"]))
    assert enum["title"] == "select.modus" and values.value_of(enum, state("comfort", options=["eco", "comfort"])) == 1.0
    assert values.value_of(enum, state("boost", options=["eco", "comfort"])) is None


def test_unknown_states_export_but_send_nothing_and_text_is_unsupported():
    entry, = values.entries_for("sensor.later", state("unavailable"))
    assert values.value_of(entry, state("unavailable")) is None and values.value_of(entry, None) is None
    assert values.entries_for("sensor.later", None) == [entry]
    assert values.entries_for("sensor.text", state("Hello")) is None
    # Not known yet at button time: the domain decides analog or digital.
    assert values.entries_for("sensor.later", None)[0]["digital"] is False
    assert values.entries_for("binary_sensor.tor", None)[0]["digital"] is True
    assert values.entries_for("switch.pumpe", state("unavailable"))[0]["digital"] is True


def test_climate_exports_mode_temperatures_and_action():
    thermostat = state("heat", friendly_name="Thermostat 1", hvac_modes=["off", "heat", "cool"],
                       current_temperature=34, temperature=23.0, hvac_action="idle")
    entries = values.entries_for("climate.thermostat_1", thermostat, "de")
    assert [(e["key"], e["title"]) for e in entries] == [
        ("climate.thermostat_1", "Thermostat 1"),
        ("climate.thermostat_1.current_temperature", "Thermostat 1 Ist-Temperatur"),
        ("climate.thermostat_1.temperature", "Thermostat 1 Solltemperatur"),
        ("climate.thermostat_1.hvac_action", "Thermostat 1 Aktion")]
    assert [values.value_of(e, thermostat) for e in entries] == [1.0, 34.0, 23.0, 4.0]
    english = values.entries_for("climate.thermostat_1", thermostat, "en")
    assert english[1]["title"] == "Thermostat 1 current temperature"
    assert values.value_of(entries[0], state("auto", hvac_modes=["off", "heat"])) is None


def test_numbers_are_formatted_with_a_dot_and_without_noise():
    assert [values.format_number(v) for v in (23.0, 34.55, 1000000.5, -0.0, 0.1 + 0.2)] == [
        "23", "34.55", "1000000.5", "0", "0.3"]
    assert values.program_entries(values.entries_for("sensor.pool", state("1", friendly_name="Pool"))) == [
        {"key": "sensor.pool", "title": "Pool", "digital": False}]


class Socket:
    def __init__(self):
        self.sent = []

    def sendto(self, data, address):
        self.sent.append(data.decode())


def sender(entries, current=None):
    states = current or {}
    send = values.HaValuesSender(NS(states=NS(get=states.get)), entries, "ms.invalid", 55556)
    send.socket = Socket()
    send.address = ("192.0.2.1", 55556)  # resolved at start
    return send


def event(entity_id, old, new):
    return NS(data={"entity_id": entity_id, "old_state": old, "new_state": new})


DIGITAL = {"key": "input_boolean.klingel", "entity_id": "input_boolean.klingel", "attribute": None, "title": "Klingel", "digital": True}
ANALOG = {"key": "sensor.pool", "entity_id": "sensor.pool", "attribute": None, "title": "Pool", "digital": False}


def test_digital_value_follows_every_change_as_one_or_zero():
    # Its analog command holds the value: Loxone shows "on" for as long as HA does.
    on, off = state("on"), state("off")
    current = {"input_boolean.klingel": on}
    send = sender([DIGITAL], current)
    send._changed(event("input_boolean.klingel", off, on))
    current["input_boolean.klingel"] = off  # HA has moved on by the time the next event arrives
    send._changed(event("input_boolean.klingel", on, off))
    assert send.socket.sent == ["input_boolean.klingel=1", "input_boolean.klingel=0"]


def test_digital_value_is_also_sent_after_restart_and_on_attribute_changes():
    on = state("on", brightness=10)
    send = sender([DIGITAL], {"input_boolean.klingel": on})
    send._changed(event("input_boolean.klingel", state("unavailable"), on))        # HA or integration restart
    send._changed(event("input_boolean.klingel", state("on", brightness=5), on))   # attribute only
    assert send.socket.sent == ["input_boolean.klingel=1", "input_boolean.klingel=1"]


def test_resend_after_start_timer_or_program_change_includes_digital_values():
    # A Miniserver restart loses the value; the resend restores the state within 5 minutes.
    send = sender([DIGITAL, ANALOG], {"input_boolean.klingel": state("on"), "sensor.pool": state("23.5")})
    send.send_all()
    assert send.socket.sent == ["input_boolean.klingel=1", "sensor.pool=23.5"]


def test_analog_values_still_follow_every_change_including_attributes():
    send = sender([ANALOG], {"sensor.pool": state("23.5")})
    send._changed(event("sensor.pool", state("23.5", unit="C"), state("23.5")))
    assert send.socket.sent == ["sensor.pool=23.5"]


class Resolver:
    """getaddrinfo stand-in: records each lookup and the thread it ran on."""
    def __init__(self, failures=0):
        self.lookups, self.failures = [], failures

    def __call__(self, host, port, family=0, type=0, proto=0, flags=0):
        import socket
        import threading
        self.lookups.append((host, port, threading.get_ident()))
        if self.failures:
            self.failures -= 1
            raise socket.gaierror(11001, "getaddrinfo failed")
        return [(socket.AF_INET, socket.SOCK_DGRAM, 17, "", ("192.0.2.7", port))]


class AddressedSocket:
    def __init__(self, *args):
        self.sent = []

    def setblocking(self, flag):
        pass

    def sendto(self, data, address):
        self.sent.append((data.decode(), address))

    def close(self):
        pass


def started(monkeypatch, host, resolver, steps):
    """Start a sender against ``host`` with HA's event helpers stubbed; run ``steps`` on the loop."""
    import asyncio
    import socket
    import sys
    import threading
    import types
    event = types.ModuleType("homeassistant.helpers.event")
    event.async_track_state_change_event = lambda hass, ids, action: (lambda: None)
    event.async_track_time_interval = lambda hass, action, interval: (lambda: None)
    for name, mod in {"homeassistant": types.ModuleType("homeassistant"),
                      "homeassistant.helpers": types.ModuleType("homeassistant.helpers"),
                      "homeassistant.helpers.event": event}.items():
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setattr(socket, "getaddrinfo", resolver)
    monkeypatch.setattr(values, "socket", NS(socket=AddressedSocket, AF_INET=socket.AF_INET, SOCK_DGRAM=socket.SOCK_DGRAM))

    async def run():
        loop = asyncio.get_running_loop()
        hass = NS(loop=loop, async_create_task=loop.create_task, states=NS(get={"sensor.pool": state("23.5")}.get))
        send = values.HaValuesSender(hass, [ANALOG], host, 55556)

        async def settle():
            while pending := [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]:
                await asyncio.gather(*pending)
        send.start()
        await settle()
        for step in steps:
            step(send)
            await settle()
        return send.socket.sent, threading.get_ident()

    return asyncio.run(run())


@pytest.mark.parametrize("host", ["miniserver.fritz.box", "https://miniserver.fritz.box:8443/path"])
def test_host_is_resolved_once_off_the_loop_not_per_datagram(monkeypatch, host):
    # sendto with a name looked it up synchronously in the event loop for every datagram;
    # the https form kept by host_option made every send fail silently.
    resolver = Resolver()
    change = event("sensor.pool", state("23"), state("23.5"))
    sent, loop_thread = started(monkeypatch, host, resolver, [lambda s: s._changed(change)] * 3)
    assert [(h, p) for h, p, _ in resolver.lookups] == [("miniserver.fritz.box", 55556)]
    assert resolver.lookups[0][2] != loop_thread
    assert sent == [("sensor.pool=23.5", ("192.0.2.7", 55556))] * 4


def test_failed_lookup_logs_once_and_retries_with_the_resend(monkeypatch, caplog):
    resolver = Resolver(failures=2)
    tick = lambda s: s._tick(None)
    with caplog.at_level("DEBUG"):
        sent, _ = started(monkeypatch, "miniserver.fritz.box", resolver, [tick, tick])
    assert len(resolver.lookups) == 3
    assert len([r for r in caplog.records if r.levelname == "WARNING"]) == 1
    assert sent == [("sensor.pool=23.5", ("192.0.2.7", 55556))]
