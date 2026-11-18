"""TextInput state with the real HA runtime; skipped without HA.

Structure File 17.0: the text arrives on states.text, not on the control's uuidAction.
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
    from homeassistant.core import HomeAssistant
    from custom_components.loxone.text import LoxoneText

ACTION = "00000000-0000-0000-0000000000000040"
TEXT = "00000000-0000-0000-0000000000000041"


@unittest.skipUnless(HAS_HA, "Run with the installed Home Assistant Python runtime")
class TextInputHATest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="loxone_text_test_")
        self.hass = HomeAssistant(self.directory.name)
        self.entity = LoxoneText(name="Notiz", uuidAction=ACTION, type="TextInput", room="", cat="",
                                 details={}, states={"text": TEXT})
        self.entity.hass = self.hass
        self.entity.schedule_update_ha_state = self.entity.async_schedule_update_ha_state = lambda *args: None

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    async def test_text_state_is_shown(self):
        await self.entity.event_handler(NS(data={TEXT: "Muell rausbringen"}))
        self.assertEqual(self.entity.native_value, "Muell rausbringen")
        self.assertEqual(self.entity.state, "Muell rausbringen")

    async def test_value_on_the_action_uuid_is_not_the_text(self):
        await self.entity.event_handler(NS(data={TEXT: "alt", ACTION: 0.0}))
        self.assertEqual(self.entity.native_value, "alt")

    async def test_text_longer_than_a_state_is_cut_to_fit(self):
        await self.entity.event_handler(NS(data={TEXT: "x" * 300}))
        self.assertEqual(self.entity.state, "x" * 255)