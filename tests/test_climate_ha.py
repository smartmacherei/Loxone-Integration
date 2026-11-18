"""Room controller (IRoomControllerV2) operating modes with the real HA runtime; skipped without HA.

operatingMode (Loxone Structure File 17.0): 0 automatic heating and cooling, 1 automatic heating
only, 2 automatic cooling only, 3/4/5 the same as manual modes, -1 off. The Loxone app offers
Auto, Heizen, Kühlen and Aus, which are 0, 1, 2 and -1 (issue #16).
"""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

HAS_HA = importlib.util.find_spec("homeassistant") is not None
if HAS_HA:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from homeassistant.components.climate import HVACMode
    from homeassistant.core import HomeAssistant, callback
    from custom_components.loxone.climate import LoxoneRoomControllerV2
    from custom_components.loxone.const import CONF_HVAC_AUTO_MODE, SENDDOMAIN

STATES = {name: f"00000000-0000-0000-00000000000000{index}" for index, name in enumerate(
    ("operatingMode", "activeMode", "tempTarget", "comfortTemperature", "comfortTemperatureCool",
     "comfortTemperatureOffset"), 11)}


@unittest.skipUnless(HAS_HA, "Run with the installed Home Assistant Python runtime")
class RoomControllerV2ModesHATest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="loxone_climate_test_")
        self.hass = HomeAssistant(self.directory.name)
        self.sent = []
        self.hass.bus.async_listen(SENDDOMAIN, callback(lambda event: self.sent.append(event.data["value"])))
        self.entity = LoxoneRoomControllerV2(
            hass=self.hass, name="Wohnzimmer", uuidAction="00000000-0000-0000-0000000000000010",
            type="IRoomControllerV2", room="", cat="", details={"timerModes": []},
            states=STATES, **{CONF_HVAC_AUTO_MODE: 0})
        self.entity.schedule_update_ha_state = lambda *args, **kwargs: None

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    def state(self, **values):
        for name, value in values.items():
            self.entity._stateAttribValues[STATES[name]] = value

    def shown(self, operating_mode):
        self.state(operatingMode=operating_mode)
        return self.entity.hvac_mode

    async def sent_by(self, action):
        self.sent.clear()
        action()
        await self.hass.async_block_till_done()
        return self.sent

    async def send(self, hvac_mode):
        return await self.sent_by(lambda: self.entity.set_hvac_mode(hvac_mode))

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
