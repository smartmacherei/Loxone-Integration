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

OPERATING_MODE = "00000000-0000-0000-0000000000000011"


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
            states={"operatingMode": OPERATING_MODE}, **{CONF_HVAC_AUTO_MODE: 0})
        self.entity.schedule_update_ha_state = lambda *args, **kwargs: None

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    def shown(self, operating_mode):
        self.entity._stateAttribValues[OPERATING_MODE] = operating_mode
        return self.entity.hvac_mode

    async def send(self, hvac_mode):
        self.sent.clear()
        self.entity.set_hvac_mode(hvac_mode)
        await self.hass.async_block_till_done()
        return self.sent

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
