"""Door contact polarity with the real HA runtime; skipped without HA.

Oliver's door contact "Haustuere" carries the Loxone texts 0 = Offen, 1 = Geschlossen.
Its name earns the door class, where HA shows on as open, so value 1 must read "off".
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
    from custom_components.loxone import binary_sensor


@unittest.skipUnless(HAS_HA, "Run with the installed Home Assistant Python runtime")
class ContactPolarityHATest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="loxone_contact_test_")
        self.hass = HomeAssistant(self.directory.name)

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    def contact(self, name, text):
        entity = binary_sensor.LoxoneDigitalSensor(
            name=name, uuidAction="00000000-0000-0000-0000000000000001", type="InfoOnlyDigital",
            details={"text": text}, states={"active": "00000000-0000-0000-0000000000000001"}, room="", cat="")
        entity.hass = self.hass
        return entity

    async def test_closed_text_on_value_one_shows_door_as_closed(self):
        entity = self.contact("Haustuere", {"off": "Offen", "on": "Geschlossen"})
        self.assertEqual(entity.device_class, binary_sensor.BinarySensorDeviceClass.DOOR)
        entity.async_schedule_update_ha_state = lambda: None
        await entity.event_handler(NS(data={"00000000-0000-0000-0000000000000001": 1.0}))
        self.assertFalse(entity.is_on)
        await entity.event_handler(NS(data={"00000000-0000-0000-0000000000000001": 0.0}))
        self.assertTrue(entity.is_on)

    async def test_default_texts_keep_the_plain_polarity(self):
        entity = self.contact("Haustuere", {"off": "Aus", "on": "Ein"})
        entity.async_schedule_update_ha_state = lambda: None
        await entity.event_handler(NS(data={"00000000-0000-0000-0000000000000001": 1.0}))
        self.assertTrue(entity.is_on)
