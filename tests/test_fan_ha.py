"""Ventilation commands with the real HA runtime; skipped without HA.

Structure File 17.0: setTimer/{interval}/{speed}/{modeId}/{timerProfileIdx} with modeId from
details.modes and -1 for a manual timer; setTimer/0 stops the timer and returns to automatic.
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
    from custom_components.loxone.fan import LoxoneVentilation

STATES = {"speed": "00000000-0000-0000-0000000000000051", "mode": "00000000-0000-0000-0000000000000052"}
MODES = [{"name": "Waermetauscher", "id": 2}, {"name": "Abluft", "id": 1}]


@unittest.skipUnless(HAS_HA, "Run with the installed Home Assistant Python runtime")
class VentilationHATest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="loxone_fan_test_")
        self.hass = HomeAssistant(self.directory.name)
        self.sent = []
        self.hass.bus.async_listen(SENDDOMAIN, callback(lambda event: self.sent.append(event.data["value"])))
        self.entity = LoxoneVentilation(
            name="Lueftung", uuidAction="00000000-0000-0000-0000000000000050", type="ventilation",
            room="", cat="", details={"modes": MODES}, states=STATES)
        self.entity.hass = self.hass
        self.entity.schedule_update_ha_state = self.entity.async_schedule_update_ha_state = lambda *args: None

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    async def state(self, speed, mode):
        await self.entity.event_handler(NS(data={STATES["speed"]: speed, STATES["mode"]: mode}))

    async def sent_by(self, call):
        self.sent.clear()
        await call
        await self.hass.async_block_till_done()
        return self.sent

    async def test_presets_are_the_configured_modes(self):
        await self.state(40.0, 1.0)
        assert self.entity.preset_modes == ["Waermetauscher", "Abluft"]
        assert self.entity.preset_mode == "Abluft"

    async def test_speed_change_keeps_the_current_mode(self):
        await self.state(40.0, 2.0)
        assert await self.sent_by(self.entity.async_set_percentage(70)) == ["setTimer/3600/70/2/-1"]

    async def test_preset_keeps_the_current_speed(self):
        await self.state(40.0, 2.0)
        assert await self.sent_by(self.entity.async_set_preset_mode("Abluft")) == ["setTimer/3600/40/1/-1"]

    async def test_turn_on_with_speed_and_preset_sends_one_timer(self):
        await self.state(0.0, 2.0)
        assert await self.sent_by(self.entity.async_turn_on(percentage=60, preset_mode="Abluft")) == [
            "setTimer/3600/60/1/-1"]

    async def test_turn_on_with_preset_from_off_runs_the_fan(self):
        await self.state(0.0, 2.0)
        assert await self.sent_by(self.entity.async_turn_on(preset_mode="Abluft")) == ["setTimer/3600/30/1/-1"]

    async def test_plain_turn_on_returns_to_automatic(self):
        await self.state(0.0, 2.0)
        assert await self.sent_by(self.entity.async_turn_on()) == ["setTimer/0"]

    async def test_turn_off_stops_the_fan(self):
        await self.state(40.0, 2.0)
        assert await self.sent_by(self.entity.async_turn_off()) == ["setTimer/3600/0/2/-1"]
