"""Weg 3 value rules: which entities export what, and which number goes out."""
from types import SimpleNamespace as NS

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
