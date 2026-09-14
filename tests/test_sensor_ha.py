"""Analog sensor values from the Miniserver with the real HA runtime; skipped without HA.

Loxone delivers NaN for analog terminals without a value (e.g. a battery state
that is not reported). HA rejects NaN for a numeric sensor, so the entity must
report it as unavailable instead of raising on every state update.
"""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

HAS_HA = importlib.util.find_spec("homeassistant") is not None
if HAS_HA:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from homeassistant.core import HomeAssistant
    from custom_components.loxone import sensor


@unittest.skipUnless(HAS_HA, "Run with the installed Home Assistant Python runtime")
class AnalogSensorHATest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="loxone_sensor_test_")
        self.hass = HomeAssistant(self.directory.name)
        self.entity = sensor.LoxoneSensor(
            name="Halle Battery State", uuidAction="00000000-0000-0000-0000000000000001",
            type="analog", details={"format": "%.1f"}, states={}, room="", cat="")
        self.entity.hass = self.hass
        self.entity.entity_id = "sensor.halle_battery_state"

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    async def test_nan_is_unavailable_instead_of_raising(self):
        self.entity._attr_native_value = float("nan")
        self.assertFalse(self.entity.available)
        self.assertIsNone(self.entity.state)

    async def test_number_stays_available(self):
        self.entity._attr_native_value = 87.0
        self.assertTrue(self.entity.available)
        self.assertEqual(self.entity.state, 87.0)

    async def test_missing_value_is_unavailable(self):
        self.assertFalse(self.entity.available)
