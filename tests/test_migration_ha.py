"""Config entry migration with the real HA runtime; skipped without HA.

Uses a temporary HA instance and registry; never touches a running installation.
"""
import asyncio
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

HAS_HA = importlib.util.find_spec("homeassistant") is not None
if HAS_HA:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from homeassistant.core import HomeAssistant
    from homeassistant.config_entries import ConfigEntry, ConfigEntries
    from homeassistant.helpers import device_registry as dr, entity_registry as er
    from custom_components import loxone


@unittest.skipUnless(HAS_HA, "Run with the installed Home Assistant Python runtime")
class MigrationHATest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="loxone_migration_test_")
        self.hass = HomeAssistant(self.directory.name)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        dr.async_setup(self.hass)
        await asyncio.gather(dr.async_load(self.hass), er.async_load(self.hass))
        options = {"host": "offline.invalid", "port": 80, "username": "test", "password": "FAKE_SECRET",
                   "generate_scenes": True, "generate_scenes_delay": 3, "auto_discovery": True}
        self.entry = ConfigEntry(version=3, minor_version=1, domain="loxone", title="Test",
                                 data={}, options=options, source="user", unique_id=None,
                                 discovery_keys={}, subentries_data=[])
        self.hass.config_entries._entries[self.entry.entry_id] = self.entry

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    async def test_scene_records_and_options_are_removed(self):
        registry = er.async_get(self.hass)
        scene = registry.async_get_or_create("scene", "loxone", "controller-1", config_entry=self.entry)
        light = registry.async_get_or_create("light", "loxone", "controller", config_entry=self.entry)
        foreign = registry.async_get_or_create("scene", "other", "keep")
        self.assertTrue(await loxone.async_migrate_entry(self.hass, self.entry))
        self.assertEqual(self.entry.version, 4)
        self.assertNotIn("generate_scenes", self.entry.options)
        self.assertNotIn("generate_scenes_delay", self.entry.options)
        self.assertEqual(self.entry.options["auto_discovery"], True)
        self.assertIsNone(registry.async_get(scene.entity_id))
        self.assertIsNotNone(registry.async_get(light.entity_id))
        self.assertIsNotNone(registry.async_get(foreign.entity_id))

    async def test_current_version_is_left_alone(self):
        self.hass.config_entries.async_update_entry(self.entry, version=4)
        self.assertTrue(await loxone.async_migrate_entry(self.hass, self.entry))
        self.assertEqual(self.entry.version, 4)
        self.assertIn("generate_scenes", self.entry.options)
