"""TimedSwitch turn_on with the real HA runtime; skipped without HA.

Structure File 17.0: pulse starts the countdown from off. A stairwell switch (isStairwayLs) restarts a
running countdown on pulse; a comfort switch turns off on pulse. on keeps the output on permanently.
"""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace as NS

HAS_HA = importlib.util.find_spec("homeassistant") is not None
if HAS_HA:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from homeassistant.core import HomeAssistant, callback
    from custom_components.loxone.const import SENDDOMAIN
    from custom_components.loxone.switch import LoxoneTimedSwitch

DELAY = "00000000-0000-0000-0000000000000031"
STATES = {"deactivationDelay": DELAY, "deactivationDelayTotal": "00000000-0000-0000-0000000000000032"}


@unittest.skipUnless(HAS_HA, "Run with the installed Home Assistant Python runtime")
class TimedSwitchTurnOnHATest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="loxone_switch_test_")
        self.hass = HomeAssistant(self.directory.name)
        self.sent = []
        self.hass.bus.async_listen(SENDDOMAIN, callback(lambda event: self.sent.append(event.data["value"])))

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    async def sent_on_turn_on(self, stairway, delay=None):
        entity = LoxoneTimedSwitch(
            name="Licht", uuidAction="00000000-0000-0000-0000000000000030", type="TimedSwitch",
            room="", cat="", details={"isStairwayLs": stairway}, states=STATES)
        entity.hass = self.hass
        entity.schedule_update_ha_state = entity.async_schedule_update_ha_state = lambda *args: None
        if delay is not None:
            await entity.event_handler(NS(data={DELAY: delay}))
        self.sent.clear()
        await self.hass.async_add_executor_job(entity.turn_on)
        await self.hass.async_block_till_done()
        return self.sent

    async def test_comfort_switch_that_is_on_stays_on(self):
        assert await self.sent_on_turn_on(False, 120.0) == ["on"]
        assert await self.sent_on_turn_on(False, -1.0) == ["on"]

    async def test_comfort_switch_with_unknown_state_is_switched_on(self):
        assert await self.sent_on_turn_on(False) == ["on"]

    async def test_comfort_switch_that_is_off_starts_its_countdown(self):
        assert await self.sent_on_turn_on(False, 0.0) == ["pulse"]

    async def test_stairwell_switch_starts_or_restarts_its_countdown(self):
        assert await self.sent_on_turn_on(True, 0.0) == ["pulse"]
        assert await self.sent_on_turn_on(True, 120.0) == ["pulse"]
        assert await self.sent_on_turn_on(True, -1.0) == ["pulse"]
