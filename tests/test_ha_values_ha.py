"""Weg 3 with the real HA runtime: label lookup, sender, button flow; skipped without HA.

Uses a temporary HA instance and registries; never touches a running installation.
"""
import asyncio
import importlib.util
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from types import SimpleNamespace as NS

HAS_HA = importlib.util.find_spec("homeassistant") is not None
if HAS_HA:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from homeassistant.core import HomeAssistant
    from homeassistant.config_entries import ConfigEntry, ConfigEntries
    from homeassistant.helpers import device_registry as dr, entity_registry as er, label_registry as lr
    from custom_components.loxone import ha_values


@unittest.skipUnless(HAS_HA, "Run with the installed Home Assistant Python runtime")
class HaValuesHATest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="loxone_ha_values_test_")
        self.hass = HomeAssistant(self.directory.name)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        dr.async_setup(self.hass)
        await asyncio.gather(dr.async_load(self.hass), er.async_load(self.hass), lr.async_load(self.hass))
        self.receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.receiver.bind(("127.0.0.1", 0))
        self.receiver.settimeout(2)
        options = {"host": "127.0.0.1", "port": 80, "username": "test", "password": "FAKE_SECRET"}
        self.entry = ConfigEntry(version=4, minor_version=1, domain="loxone", title="Test",
                                 data={}, options=options, source="user", unique_id=None,
                                 discovery_keys={}, subentries_data=[])
        self.hass.config_entries._entries[self.entry.entry_id] = self.entry
        registry, labels = er.async_get(self.hass), lr.async_get(self.hass)
        label = labels.async_create("Loxone")
        for platform, unique in (("climate", "thermo"), ("sensor", "pool"), ("sensor", "text")):
            entity = registry.async_get_or_create(platform, "demo", unique)
            registry.async_update_entity(entity.entity_id, labels={label.label_id})
        self.hass.states.async_set("climate.demo_thermo", "heat", {"friendly_name": "Thermostat 1", "hvac_modes": ["off", "heat"],
                                                                   "current_temperature": 34, "temperature": 23, "hvac_action": "idle"})
        self.hass.states.async_set("sensor.demo_pool", "21.5", {"friendly_name": "Pool"})
        self.hass.states.async_set("sensor.demo_text", "Hello")

    async def asyncTearDown(self):
        self.receiver.close()
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    def received(self, count):
        packets = set()
        for _ in range(count):
            packets.add(self.receiver.recv(200).decode())
        return packets

    async def test_label_lookup_orders_values_and_reports_unsupported(self):
        entries, unsupported, beyond = ha_values.desired(self.hass, 3, "de")
        self.assertEqual([e["key"] for e in entries], ["climate.demo_thermo", "climate.demo_thermo.current_temperature",
                                                       "climate.demo_thermo.hvac_action"])
        self.assertEqual(unsupported, ["sensor.demo_text"])
        self.assertEqual(beyond, ["climate.demo_thermo.temperature", "sensor.demo_pool"])

    async def test_sender_pushes_changes_to_the_udp_port(self):
        entries, _, _ = ha_values.desired(self.hass, 500, "de")
        sender = ha_values.HaValuesSender(self.hass, entries, "127.0.0.1", self.receiver.getsockname()[1])
        sender.start()
        self.assertEqual(self.received(5), {"climate.demo_thermo=1", "climate.demo_thermo.current_temperature=34",
                                            "climate.demo_thermo.temperature=23", "climate.demo_thermo.hvac_action=4",
                                            "sensor.demo_pool=21.5"})
        self.hass.states.async_set("sensor.demo_pool", "22")
        await self.hass.async_block_till_done()
        self.assertEqual(self.received(1), {"sensor.demo_pool=22"})
        sender.stop()

    async def test_button_without_way_two_stores_wish_list_and_notifies(self):
        created = []
        from homeassistant.components import persistent_notification
        original = persistent_notification.async_create
        persistent_notification.async_create = lambda hass, message, **kw: created.append(message)
        try:
            await ha_values.async_apply(self.hass, self.entry)
        finally:
            persistent_notification.async_create = original
        self.assertEqual(len(created), 1)
        stored = self.hass.data[ha_values.KEY][self.entry.entry_id]
        self.assertEqual(len(stored["entries"]), 5)
        self.assertEqual(await ha_values._store(self.hass, self.entry.entry_id).async_load(), {"entries": stored["entries"]})
        stored["sender"].stop()
        # With the manager present the button hands over the wish list and forces a check.
        forced = []

        async def check(force=False):
            forced.append(force)
        manager = NS(ha_values=None, configured_callbacks=[], task=None, check=check)
        self.hass.data.setdefault("loxone_udp_setup", {})[self.entry.entry_id] = manager
        await ha_values.async_apply(self.hass, self.entry)
        await self.hass.async_block_till_done()
        self.assertEqual(forced, [True])
        self.assertEqual([e["key"] for e in manager.ha_values][:1], ["climate.demo_thermo"])
        self.assertEqual(set(manager.ha_values[0]), {"key", "title", "digital"})
        self.hass.data[ha_values.KEY][self.entry.entry_id]["sender"].stop()
