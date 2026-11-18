"""Shared lookup maps of several Miniservers and the device cache; HA-free."""
import importlib.util
import sys
import types

import pytest

from test_udp_install import module


@pytest.fixture
def helpers(monkeypatch):
    if importlib.util.find_spec("homeassistant") is None:
        const = types.ModuleType("homeassistant.const")
        const.Platform = types.SimpleNamespace(**{name: name.lower() for name in (
            "SENSOR", "BINARY_SENSOR", "SWITCH", "COVER", "FAN", "LIGHT", "CLIMATE", "ALARM_CONTROL_PANEL",
            "MEDIA_PLAYER", "NUMBER", "TEXT", "BUTTON", "SELECT", "SCENE", "EVENT")})
        monkeypatch.setitem(sys.modules, "homeassistant", types.ModuleType("homeassistant"))
        monkeypatch.setitem(sys.modules, "homeassistant.const", const)
    return module("helpers")


def test_two_miniservers_keep_their_initial_values_and_unload_their_own(helpers):
    # Entry B finishing setup must not replace A's values before A's platforms read them.
    helpers.publish("A", helpers.initial_values, {"a1": 1.0, "a2": 2.0})
    helpers.publish("B", helpers.initial_values, {"b1": 3.0})
    from importlib import import_module
    platform_view = import_module(helpers.__name__).initial_values  # what sensor.py reads
    assert platform_view == {"a1": 1.0, "a2": 2.0, "b1": 3.0}
    helpers.release("A")
    assert platform_view == {"b1": 3.0}
    helpers.release("B")
    assert platform_view == {}


def test_renamed_device_gets_its_new_name_after_a_reload(helpers):
    helpers.publish("A", helpers.device_map, {"ctl": ("dev", "Dimmer Kueche")})
    first = helpers.get_or_create_device("ctl/AI1", "Kanal 1", "Dimmer", "Kueche")
    # Controls of one physical device share the first DeviceInfo during a setup.
    assert helpers.get_or_create_device("ctl", "Kanal 2", "Switch", "Bad") is first
    assert first["name"] == "Dimmer Kueche" and first["model"] == "Dimmer"
    unmapped = helpers.get_or_create_device("lc", "Lichtsteuerung", "LightControllerV2", "Bad")
    helpers.release("A")
    helpers.publish("A", helpers.device_map, {"ctl": ("dev", "Dimmer Essen")})
    assert helpers.get_or_create_device("ctl", "Kanal 1", "Dimmer", "Kueche")["name"] == "Dimmer Essen"
    assert unmapped["name"] == "Lichtsteuerung"
    assert helpers.get_or_create_device("lc", "Licht Bad", "LightControllerV2", "Bad")["name"] == "Licht Bad"
    helpers.release("A")
