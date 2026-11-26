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


@unittest.skipUnless(HAS_HA, "Run with the installed Home Assistant Python runtime")
class EnergyFlowMonitorHATest(unittest.IsolatedAsyncioTestCase):
    """Issue #22: Energy Flow Monitor values carry unit, device class and state class."""

    def setUp(self):
        from custom_components.loxone import helpers
        from test_energy_flow import EFM
        helpers.device_registry.clear()
        self.cfg = {"controls": {EFM["uuidAction"]: EFM}, "rooms": {}, "cats": {}}

    def test_power_values_are_power_sensors_on_the_monitor_device(self):
        from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
        from test_energy_flow import uid
        entities = {e.unique_id: e for e in sensor.efm_sensors(self.cfg, None, None)}
        self.assertEqual(len(entities), 9)
        grid = entities[uid(3)]
        self.assertEqual(grid.name, "Energieflussmonitor Grid power")
        self.assertEqual(grid.native_unit_of_measurement, "kW")
        self.assertEqual(grid.device_class, SensorDeviceClass.POWER)
        self.assertEqual(grid.state_class, SensorStateClass.MEASUREMENT)
        self.assertEqual(grid.suggested_display_precision, 3)
        self.assertEqual(grid.device_info["name"], "Energieflussmonitor")
        self.assertEqual(entities[uid(10)].name, "Energieflussmonitor Netz")
        self.assertEqual(entities[uid(10)].device_class, SensorDeviceClass.POWER)
        co2 = entities[uid(5)]
        self.assertEqual(co2.native_unit_of_measurement, "kg/kWh")
        self.assertIsNone(co2.device_class)
        self.assertEqual(co2.state_class, SensorStateClass.MEASUREMENT)
        self.assertEqual(entities[uid(7)].state_class, SensorStateClass.MEASUREMENT)

    def test_remaining_raw_states_share_the_monitor_device(self):
        from custom_components.loxone.control_states import state_inventory
        from custom_components.loxone.raw_sensor import RawValueSensor
        raw = [RawValueSensor(**state) for state in state_inventory(self.cfg)]
        self.assertEqual({r.name for r in raw}, {"Energieflussmonitor: jLocked", "Energieflussmonitor: selfConsumption",
                                                 "Energieflussmonitor: totalSelfConsumption"})
        self.assertEqual({r.device_info["name"] for r in raw}, {"Energieflussmonitor"})

    def test_every_state_is_exactly_one_entity(self):
        from custom_components.loxone.control_states import state_inventory
        from test_energy_flow import EFM
        native = {e.unique_id for e in sensor.efm_sensors(self.cfg, None, None)}
        raw = {s["uuidAction"] for s in state_inventory(self.cfg)}
        self.assertFalse(native & raw)
        self.assertEqual(native | raw, set(EFM["states"].values()))

    def test_other_controls_name_their_device_after_the_control(self):
        from custom_components.loxone.control_states import state_inventory
        from custom_components.loxone.raw_sensor import RawValueSensor
        from test_energy_flow import uid
        cfg = {"controls": {uid(50): {"type": "Wallbox2", "name": "Wallbox", "uuidAction": uid(50),
                                      "states": {"active": uid(51), "power": uid(52)}}}}
        raw = [RawValueSensor(**state) for state in state_inventory(cfg)]
        self.assertEqual({r.device_info["name"] for r in raw}, {"Wallbox"})
