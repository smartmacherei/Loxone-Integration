"""Room controllers and AC control with the real HA runtime; skipped without HA.

IRoomControllerV2 operatingMode (Loxone Structure File 17.0): 0 automatic heating and cooling,
1 automatic heating only, 2 automatic cooling only, 3/4/5 the same as manual modes, -1 off. The
Loxone app offers Auto, Heizen, Kühlen and Aus, which are 0, 1, 2 and -1 (issue #16).

IRoomController mode: 0 automatic (no period active), 1/2 automatic currently heating/cooling,
3/4 automatic heating/cooling, 5/6 manual heating/cooling; only 0 and 3-6 can be selected.
serviceMode 1 switches heating and cooling off.
"""
from concurrent.futures import ThreadPoolExecutor
import importlib
import importlib.util
import inspect
from pathlib import Path
import sys
import tempfile
import unittest

HAS_HA = importlib.util.find_spec("homeassistant") is not None
if HAS_HA:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from homeassistant.components.climate import HVACMode
    from homeassistant.core import HomeAssistant, callback
    from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
    from custom_components.loxone.climate import (LoxoneAcControl, LoxoneRoomController,
                                                  LoxoneRoomControllerV2)
    from custom_components.loxone.const import CONF_HVAC_AUTO_MODE, SENDDOMAIN

STATES = {name: f"00000000-0000-0000-00000000000000{index}" for index, name in enumerate(
    ("operatingMode", "activeMode", "tempTarget", "comfortTemperature", "comfortTemperatureCool",
     "comfortTemperatureOffset", "tempActual", "prepareState"), 11)}
IRC_STATES = {name: f"00000000-0000-0000-00000000000000{index}" for index, name in enumerate(
    ("mode", "serviceMode", "currHeatTempIx", "currCoolTempIx", "tempTarget", "tempActual"), 31)}
AC_STATES = {name: f"00000000-0000-0000-00000000000000{index}" for index, name in enumerate(
    ("status", "mode", "temperature", "targetTemperature", "fan", "fanspeeds", "ventMode",
     "airflows", "minTemp", "maxTemp"), 51)}


class ClimateHATestCase(unittest.IsolatedAsyncioTestCase):
    states = STATES

    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="loxone_climate_test_")
        self.hass = HomeAssistant(self.directory.name)
        self.sent = []
        self.hass.bus.async_listen(SENDDOMAIN, callback(lambda event: self.sent.append(event.data["value"])))
        self.entity = self.create()
        self.entity.schedule_update_ha_state = lambda *args, **kwargs: None

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    def state(self, **values):
        for name, value in values.items():
            self.entity._stateAttribValues[self.states[name]] = value

    async def sent_by(self, action):
        self.sent.clear()
        if inspect.isawaitable(result := action()):
            await result
        await self.hass.async_block_till_done()
        return self.sent

    async def send(self, hvac_mode):
        return await self.sent_by(lambda: self.entity.set_hvac_mode(hvac_mode))


@unittest.skipUnless(HAS_HA, "Run with the installed Home Assistant Python runtime")
class RoomControllerV2ModesHATest(ClimateHATestCase):
    def create(self, **details):
        return LoxoneRoomControllerV2(
            hass=self.hass, name="Wohnzimmer", uuidAction="00000000-0000-0000-0000000000000010",
            type="IRoomControllerV2", room="", cat="", details={"timerModes": [], **details},
            states=STATES, **{CONF_HVAC_AUTO_MODE: 0})

    def shown(self, operating_mode):
        self.state(operatingMode=operating_mode)
        return self.entity.hvac_mode

    async def test_app_modes_show_as_the_same_hvac_mode(self):
        assert [self.shown(mode) for mode in (0, 1, 2, -1)] == [
            HVACMode.AUTO, HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF]

    async def test_manual_modes_show_whether_they_heat_or_cool(self):
        assert [self.shown(mode) for mode in (3, 4, 5)] == [HVACMode.HEAT_COOL, HVACMode.HEAT, HVACMode.COOL]

    async def test_heat_and_cool_select_the_automatic_modes_of_the_app(self):
        assert await self.send(HVACMode.HEAT) == ["setOperatingMode/1"]
        assert await self.send(HVACMode.COOL) == ["setOperatingMode/2"]
        assert await self.send(HVACMode.AUTO) == ["setOperatingMode/0"]
        assert await self.send(HVACMode.OFF) == ["setOperatingMode/-1"]

    async def test_every_offered_mode_reads_back_as_itself(self):
        for hvac_mode in self.entity.hvac_modes:
            command, = await self.send(hvac_mode)
            assert self.shown(int(command.rsplit("/", 1)[1])) == hvac_mode

    async def test_turn_on_selects_automatic_and_turn_off_selects_off(self):
        # HA's fallback turn_on picks HEAT_COOL from hvac_modes, the manual mode 3.
        self.state(operatingMode=-1)
        assert await self.sent_by(self.entity.async_turn_on) == ["setOperatingMode/0"]
        assert await self.sent_by(self.entity.async_turn_off) == ["setOperatingMode/-1"]

    async def test_temperature_in_a_manual_mode_is_the_manual_temperature(self):
        self.state(operatingMode=5, tempTarget=24)
        assert await self.sent_by(lambda: self.entity.set_temperature(temperature=23)) == ["setManualTemperature/23"]

    async def sent_temperature(self, temperature, **states):
        self.state(**states)
        command, = await self.sent_by(lambda: self.entity.set_temperature(temperature=temperature))
        name, value = command.rsplit("/", 1)
        return name, float(value)

    async def test_temperature_while_cooling_automatically_shifts_the_offset_from_the_current_target(self):
        # The Miniserver takes setComfortModeTemp as the new comfortTemperatureOffset (PyLoxone
        # issue #544). While cooling, the target follows comfortTemperatureCool, not comfortTemperature.
        assert await self.sent_temperature(23, operatingMode=2, activeMode=1, comfortTemperature=21,
                                           comfortTemperatureCool=24, comfortTemperatureOffset=0,
                                           tempTarget=24) == ("setComfortModeTemp", -1)

    async def test_temperature_while_off_or_protecting_sets_the_comfort_temperature(self):
        # Off (-1, activeMode 4) and building protection (activeMode 2) hold a protection target.
        # An offset taken from it would store e.g. +16 K (22 °C requested, 6 °C frost protection).
        for operating_mode, active_mode in ((-1, 4), (0, 2)):
            assert await self.sent_temperature(22, operatingMode=operating_mode, activeMode=active_mode,
                                               comfortTemperature=21, comfortTemperatureOffset=0,
                                               tempTarget=6) == ("setComfortModeTemp", 1)

    async def test_temperature_before_the_states_arrive_is_refused_with_a_clear_error(self):
        for states in ({}, dict(operatingMode=0, activeMode=1), dict(operatingMode=0, activeMode=2)):
            self.entity._stateAttribValues.clear()
            self.state(**states)
            with self.assertRaisesRegex(HomeAssistantError, "not been received"):
                await self.sent_by(lambda: self.entity.set_temperature(temperature=22))
            assert self.sent == []

    async def test_temperatures_reach_home_assistant(self):
        self.state(tempActual=21.5, tempTarget=22)
        attributes = self.entity.state_attributes
        assert (attributes["current_temperature"], attributes["temperature"]) == (21.5, 22)

    async def test_fahrenheit_format_converts_the_temperatures(self):
        self.entity = self.create(format="%.1f°F")
        self.state(tempActual=77, tempTarget=68)
        attributes = self.entity.state_attributes
        assert (attributes["current_temperature"], attributes["temperature"]) == (25, 20)


@unittest.skipUnless(HAS_HA, "Run with the installed Home Assistant Python runtime")
class RoomControllerModesHATest(ClimateHATestCase):
    states = IRC_STATES

    def create(self, **details):
        return LoxoneRoomController(
            hass=self.hass, name="Bad", uuidAction="00000000-0000-0000-0000000000000030",
            type="IRoomController", room="", cat="", details=details, states=IRC_STATES,
            **{CONF_HVAC_AUTO_MODE: 0})

    def shown(self, mode, service_mode=0):
        self.state(mode=mode, serviceMode=service_mode)
        return self.entity.hvac_mode

    def apply(self, commands):
        """What the Miniserver reports after the commands."""
        for command in commands:
            name, value = command.split("/")
            self.state(**{{"mode": "mode", "service": "serviceMode"}[name]: int(value)})

    async def test_modes_show_whether_the_controller_heats_or_cools(self):
        assert [self.shown(mode) for mode in range(7)] == [
            HVACMode.AUTO, HVACMode.AUTO, HVACMode.AUTO, HVACMode.HEAT, HVACMode.COOL,
            HVACMode.HEAT, HVACMode.COOL]

    async def test_heat_and_cool_select_automatic_heating_and_cooling(self):
        self.state(serviceMode=0)
        assert await self.send(HVACMode.AUTO) == ["mode/0"]
        assert await self.send(HVACMode.HEAT) == ["mode/3"]
        assert await self.send(HVACMode.COOL) == ["mode/4"]

    async def test_off_is_the_service_mode_heating_and_cooling_off(self):
        assert await self.send(HVACMode.OFF) == ["service/1"]
        assert self.shown(4, service_mode=1) == HVACMode.OFF
        assert await self.send(HVACMode.HEAT) == ["service/0", "mode/3"]

    async def test_every_offered_mode_reads_back_as_itself(self):
        self.state(mode=0, serviceMode=0)
        for hvac_mode in self.entity.hvac_modes:
            self.apply(await self.send(hvac_mode))
            assert self.entity.hvac_mode == hvac_mode

    async def test_restricted_controller_offers_only_its_modes(self):
        # details.restrictedToMode: 0 heating and cooling, 1 cooling only, 2 heating only.
        both = [HVACMode.OFF, HVACMode.AUTO, HVACMode.HEAT, HVACMode.COOL]
        for restricted, hidden in ((0, None), (1, HVACMode.HEAT), (2, HVACMode.COOL)):
            modes = self.create(restrictedToMode=restricted).hvac_modes
            assert modes == [mode for mode in both if mode != hidden], restricted

    async def test_heating_only_controller_is_not_switched_to_cooling(self):
        # mode/4 would switch a heating-only controller to automatic cooling.
        self.entity = self.create(restrictedToMode=2)
        self.entity.schedule_update_ha_state = lambda *args, **kwargs: None
        self.state(mode=3, serviceMode=0)
        for action in (self.entity.async_handle_set_hvac_mode_service, self.entity.set_hvac_mode):
            with self.assertRaises(ServiceValidationError):
                await self.sent_by(lambda: action(HVACMode.COOL))
            assert self.sent == []

    async def test_turn_on_leaves_off_without_changing_the_mode(self):
        self.state(mode=4, serviceMode=1)
        assert await self.sent_by(self.entity.async_turn_on) == ["service/0"]
        assert await self.sent_by(self.entity.async_turn_off) == ["service/1"]

    async def test_temperature_changes_the_temperature_in_use_heating_or_cooling(self):
        self.state(currHeatTempIx=1, currCoolTempIx=2)
        for mode, index in ((0, 1), (1, 1), (2, 2), (3, 1), (4, 2), (5, 1), (6, 2)):
            self.state(mode=mode)
            assert await self.sent_by(lambda: self.entity.set_temperature(temperature=23)) == [
                f"settemp/{index}/23"]

    async def test_temperatures_reach_home_assistant(self):
        self.state(tempActual=21.5, tempTarget=22)
        attributes = self.entity.state_attributes
        assert (attributes["current_temperature"], attributes["temperature"]) == (21.5, 22)

    async def test_fahrenheit_range_allows_fahrenheit_targets(self):
        # 7-35 taken as °F would refuse every sensible target.
        self.entity = self.create(format="%.1f°F")
        assert (round(self.entity.min_temp, 1), round(self.entity.max_temp, 1)) == (44.6, 95)


@unittest.skipUnless(HAS_HA, "Run with the installed Home Assistant Python runtime")
class AcControlHATest(ClimateHATestCase):
    states = AC_STATES

    def create(self, states=AC_STATES, **details):
        return LoxoneAcControl(
            hass=self.hass, name="Klima", uuidAction="00000000-0000-0000-0000000000000050",
            type="AcControl", room="", cat="", details=details, states=states)

    async def test_off_only_powers_off_and_keeps_the_configured_mode(self):
        assert await self.send(HVACMode.OFF) == ["off"]

    async def test_modes_power_on_and_select_the_mode(self):
        assert await self.send(HVACMode.COOL) == ["on", "setMode/3"]
        assert await self.send(HVACMode.HEAT) == ["on", "setMode/2"]
        assert await self.send(HVACMode.AUTO) == ["on", "setMode/1"]

    async def test_turn_on_only_powers_on_and_turn_off_only_powers_off(self):
        # HA's fallback turn_on picks HEAT from hvac_modes.
        self.state(status=0, mode=3)
        assert await self.sent_by(self.entity.async_turn_on) == ["on"]
        assert await self.sent_by(self.entity.async_turn_off) == ["off"]

    async def test_temperature_unit_follows_the_format(self):
        for details, expected in (({"format": "%.1f°F"}, (25, 20)), ({"format": "%.1f°C"}, (77, 68)),
                                  ({"format": "%.1f"}, (77, 68)), ({}, (77, 68))):
            self.entity = self.create(**details)
            self.state(temperature=77, targetTemperature=68)
            attributes = self.entity.state_attributes
            assert (attributes["current_temperature"], attributes["temperature"]) == expected, details

    def limits(self):
        attributes = self.entity.capability_attributes
        return attributes["min_temp"], attributes["max_temp"]

    async def test_target_range_follows_the_limit_states(self):
        # minTemp/maxTemp since Config 15.3, in the Miniserver's unit.
        self.state(minTemp=16, maxTemp=30)
        assert self.limits() == (16, 30)
        self.entity = self.create(format="%.1f°F")
        self.state(minTemp=59, maxTemp=86)
        assert (self.entity.min_temp, self.entity.max_temp) == (59, 86)
        assert self.limits() == (15, 30)

    async def test_target_range_without_limit_states_is_the_home_assistant_default(self):
        # Before the states arrive, and on a Miniserver older than 15.3 without them.
        older = {name: uuid for name, uuid in AC_STATES.items() if name not in ("minTemp", "maxTemp")}
        for states in (AC_STATES, older):
            self.entity = self.create(states)
            self.state(temperature=21, targetTemperature=22)
            assert self.limits() == (7, 35)


@unittest.skipUnless(HAS_HA, "Run with the installed Home Assistant Python runtime")
class ClimateTemperatureApiHATest(unittest.TestCase):
    def test_no_deprecated_temperature_api_is_reported(self):
        # HA 2026.11 logs this at class creation; it stops working in 2027.11.
        name = "custom_components.loxone.climate"
        previous = sys.modules.pop(name)
        try:
            with self.assertNoLogs(name, "WARNING"), ThreadPoolExecutor(1) as executor:
                # A thread without a running hass, as when HA imports the platform.
                executor.submit(importlib.import_module, name).result()
        finally:
            sys.modules[name] = previous
            sys.modules["custom_components.loxone"].climate = previous
