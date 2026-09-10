"""Real HA flow/registry tests, also runnable standalone inside an HA container.

Uses a temporary HA instance, synthetic rooms and fake HTTP; never touches the
running HA instance, Miniserver configuration or installed integration.
"""
import asyncio
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

HAS_HA = importlib.util.find_spec("homeassistant") is not None
if HAS_HA:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from homeassistant.core import HomeAssistant
    from homeassistant.config_entries import ConfigEntry, ConfigEntries
    from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er
    from custom_components.loxone import config_flow as flow
    from custom_components.loxone.area_mapping import AreaMapping


@unittest.skipUnless(HAS_HA, "Run with the installed Home Assistant Python runtime")
class AreaMappingHATest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="loxone_room_mapping_test_")
        self.hass = HomeAssistant(self.directory.name)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        dr.async_setup(self.hass)
        await asyncio.gather(ar.async_load(self.hass), dr.async_load(self.hass), er.async_load(self.hass))
        self.office = ar.async_get(self.hass).async_create("Existing office")
        self.kitchen = ar.async_get(self.hass).async_create("Existing kitchen")
        self.options = {"host": "offline.invalid", "port": 80, "username": "test", "password": "FAKE_SECRET"}
        self.rooms = {"room-1": "Loxone office", "room-2": "Loxone kitchen"}
        self.entry = ConfigEntry(version=3, minor_version=1, domain="loxone", title="Test",
                                 data={}, options=self.options, source="user", unique_id=None,
                                 discovery_keys={}, subentries_data=[])
        self.hass.config_entries._entries[self.entry.entry_id] = self.entry

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    def new_flow(self):
        handler = flow.LoxoneFlowHandler()
        handler.hass = self.hass
        return handler

    async def test_room_fetch_accepts_https_and_url_hosts(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.json = AsyncMock(return_value={"rooms": {"r": {"name": "Room"}}})
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=response)
        context.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.get.return_value = context
        for host, port, expected in (("server.invalid", 443, "https://server.invalid/data/LoxAPP3.json"),
                                     ("https://server.invalid", 443, "https://server.invalid/data/LoxAPP3.json"),
                                     ("server.invalid", 80, "http://server.invalid/data/LoxAPP3.json")):
            with patch("homeassistant.helpers.aiohttp_client.async_get_clientsession", return_value=session):
                result = await flow.async_load_rooms(self.hass, {**self.options, "host": host, "port": port})
            self.assertEqual(str(session.get.call_args.args[0]), expected)
            self.assertEqual(result, {"r": "Room"})

    async def test_setup_mapping_step_and_stable_saved_ids(self):
        handler = self.new_flow()
        with patch.object(flow, "async_load_rooms", AsyncMock(return_value=self.rooms)):
            result = await handler.async_step_user({**self.options, "edit_room_mapping": True})
        self.assertEqual(result["step_id"], "room_mapping")
        result = await handler.async_step_room_mapping({"room": "room-1", "area": self.office.id})
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["options"]["room_area_mapping"], {"room-1": self.office.id})
        self.assertNotIn("room", result["options"])
        self.assertNotIn("edit_room_mapping", result["options"])

    async def test_skipping_does_not_connect_or_change_existing_options(self):
        handler = self.new_flow()
        with patch.object(flow, "async_load_rooms", AsyncMock(side_effect=AssertionError("unexpected network"))):
            result = await handler.async_step_user(self.options)
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["options"]["password"], "FAKE_SECRET")

    async def test_options_mapping_can_be_changed_and_removed(self):
        self.hass.config_entries.async_update_entry(self.entry, options={**self.options, "room_area_mapping": {"room-1": self.office.id}})
        handler = flow.LoxoneFlowHandler.async_get_options_flow(self.entry)
        handler.hass = self.hass
        with patch.object(flow, "async_load_rooms", AsyncMock(return_value=self.rooms)):
            await handler.async_step_init({**self.options, "edit_room_mapping": True})
        result = await handler.async_step_room_mapping({"room": "room-1", "area": self.kitchen.id, "map_another": True})
        self.assertEqual(result["step_id"], "room_mapping")
        result = await handler.async_step_room_mapping({"room": "room-1", "remove_mapping": True})
        self.assertEqual(result["data"]["room_area_mapping"], {})
        self.assertEqual(result["data"]["password"], "FAKE_SECRET")

    async def test_invalid_area_or_missing_room_stays_in_form(self):
        handler = self.new_flow()
        with patch.object(flow, "async_load_rooms", AsyncMock(return_value=self.rooms)):
            await handler.async_step_user({**self.options, "edit_room_mapping": True})
        for data in ({"room": "room-1", "area": "deleted"}, {"room": "unknown", "area": self.office.id}):
            result = await handler.async_step_room_mapping(data)
            self.assertEqual(result["type"], "form")
            self.assertTrue(result["errors"])

    async def test_fetch_error_is_safe_and_can_be_skipped(self):
        handler = self.new_flow()
        with patch.object(flow, "async_load_rooms", AsyncMock(side_effect=TimeoutError("FAKE_SECRET"))):
            result = await handler.async_step_user({**self.options, "edit_room_mapping": True})
        self.assertEqual(result["errors"], {"base": "room_fetch_failed"})
        self.assertNotIn("FAKE_SECRET", str(result["errors"]))
        result = await handler.async_step_user({**self.options, "edit_room_mapping": False})
        self.assertEqual(result["type"], "create_entry")

    async def test_actual_registries_persist_mapping_and_protect_user_edit(self):
        from types import SimpleNamespace as NS
        entry = NS(entry_id=self.entry.entry_id, options={"room_area_mapping": {"room-1": self.office.id}}, async_on_unload=lambda f: None)
        manager = AreaMapping(self.hass, entry, {"controls": {"control": {"room": "room-1"}}})
        await manager.start()
        devices, entities = dr.async_get(self.hass), er.async_get(self.hass)
        device = devices.async_get_or_create(config_entry_id=self.entry.entry_id, identifiers={("loxone", "device")})
        entity = entities.async_get_or_create("light", "loxone", "control", config_entry=self.entry, device_id=device.id)
        await manager.apply()
        self.assertEqual(devices.async_get(device.id).area_id, self.office.id)
        manager.close()
        reloaded = AreaMapping(self.hass, entry, {"controls": {"control": {"room": "room-1"}}})
        await reloaded.start()
        reloaded.mapping = {"room-1": self.kitchen.id}
        await reloaded.apply()
        self.assertEqual(devices.async_get(device.id).area_id, self.kitchen.id)
        devices.async_update_device(device.id, area_id=None)
        await reloaded.apply()
        self.assertIsNone(devices.async_get(device.id).area_id)
        reloaded.close()

    async def test_light_and_button_do_not_create_duplicate_original_area(self):
        from types import SimpleNamespace as NS
        from custom_components.loxone.lights.lightcontroller import LoxoneLightControllerV2
        from custom_components.loxone.button import LoxoneButton
        entry = NS(entry_id=self.entry.entry_id, options={"room_area_mapping": {"room-1": self.office.id}})
        manager = AreaMapping(self.hass, entry, {"controls": {"control": {"room": "room-1"}}})
        self.hass.data["loxone_area_mapping"] = {entry.entry_id: manager}
        for cls in (LoxoneLightControllerV2, LoxoneButton):
            entity = cls(uuidAction="control", name="Test", room="Loxone office", type="Pushbutton", states={}, async_add_devices=lambda *args: None)
            entity.hass = self.hass
            entity.platform = NS(config_entry=entry)
            self.assertIsNone(entity.device_info.get("suggested_area"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
