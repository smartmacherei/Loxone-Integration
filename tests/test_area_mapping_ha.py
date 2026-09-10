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

    async def test_meter_shared_device_info_does_not_set_read_only_property(self):
        from custom_components.loxone.sensor import LoxoneMeterSensor
        info = {"identifiers": {("loxone", "parent-meter")}, "name": "Meter"}
        sensor = LoxoneMeterSensor(device_info=info, parent_id="parent-meter", uuidAction="meter-value",
                                  type="analog", room="Room", cat="", name="Meter Actual",
                                  details={"format": "%.1f kWh"})
        self.assertEqual(sensor.name, "Meter Actual")
        self.assertEqual(sensor.device_info, info)

    async def test_caught_platform_failure_is_partial_then_recovers(self):
        from custom_components.loxone import startup_trace as trace
        async def broken(hass, entry):
            raise AttributeError("PRIVATE_PROJECT")
        broken.__module__ = "custom_components.loxone.sensor"
        broken = trace.tracked_platform(broken)
        async def setup(hass, entry):
            trace.advance(hass, entry, "entity_platforms")
            try: await broken(hass, entry)
            except AttributeError: pass  # HA catches platform failures internally.
            return True
        await trace.tracked_setup(self.hass, self.entry, setup)
        result = await trace.diagnostics(self.hass, self.entry)
        self.assertEqual(result["state"], "partial")
        self.assertEqual(result["failed_platforms"], ["sensor"])
        self.assertNotIn("PRIVATE_PROJECT", str(result))
        async def recovered(hass, entry): return True
        recovered.__module__ = "custom_components.loxone.sensor"
        await trace.tracked_platform(recovered)(self.hass, self.entry)
        result = await trace.diagnostics(self.hass, self.entry)
        self.assertEqual(result["state"], "completed")
        self.assertNotIn("error_code", result)

    async def test_room_mapping_defaults_on_but_can_be_skipped(self):
        for schema in (flow.DATA_SCHEMA_SETUP, flow.DATA_SCHEMA_OPTIONS):
            self.assertTrue(schema(self.options)["edit_room_mapping"])
            self.assertFalse(schema({**self.options, "edit_room_mapping": False})["edit_room_mapping"])

    async def test_customer_registry_iterator_does_not_crash_constructor(self):
        from types import SimpleNamespace as NS
        class EntryIterator(dict):
            def __iter__(self): return iter(self.values())
        registry = NS(devices=EntryIterator({"device": NS(id="device", config_entries=set())}))
        with patch.object(dr, "async_get", return_value=registry):
            manager = AreaMapping(self.hass, self.entry, {"controls": {}})
        self.assertEqual(manager.initial_devices, {"device"})

    async def test_startup_failure_is_safe_persistent_and_cleared_on_recovery(self):
        from custom_components.loxone import startup_trace as trace
        async def broken(hass, entry):
            trace.advance(hass, entry, "area_mapping")
            raise TypeError("PASSWORD_AND_PRIVATE_PROJECT")
        with self.assertRaises(TypeError):
            await trace.tracked_setup(self.hass, self.entry, broken)
        self.hass.data.pop(trace.KEY)
        stored = await trace.diagnostics(self.hass, self.entry)
        self.assertEqual(stored["error_code"], "AREA_MAPPING_FAILED")
        self.assertTrue(stored["historical"])
        self.assertNotIn("PASSWORD_AND_PRIVATE_PROJECT", str(stored))
        await trace.tracked_setup(self.hass, self.entry, AsyncMock(return_value=True))
        recovered = await trace.diagnostics(self.hass, self.entry)
        self.assertEqual(recovered["state"], "completed")
        self.assertNotIn("error_code", recovered)

    async def test_connection_check_persists_without_provisioning(self):
        from custom_components.loxone import connection_diagnostics as diag
        result = {"state": "completed", "checks": {}, "completed_at": "2026-09-10T00:00:00Z"}
        with patch.object(diag, "probe", return_value=result), patch.object(diag.persistent_notification, "async_create") as notification:
            await diag.run_check(self.hass, self.entry)
        self.assertTrue(notification.called)
        self.hass.data.pop(diag.KEY)
        stored = await diag.diagnostics(self.hass, self.entry)
        self.assertEqual(stored["last_explicit_check"]["state"], "completed")
        self.assertEqual(stored["current"]["udp_receive_state"], "listener_missing")

    async def test_connection_action_is_available_without_loaded_miniserver(self):
        from custom_components.loxone import async_setup
        from custom_components.loxone import connection_diagnostics as diag
        with patch.object(diag, "run_check", AsyncMock()) as check:
            await async_setup(self.hass, {})
            await self.hass.services.async_call("loxone", "check_connection", {"entry_id": self.entry.entry_id}, blocking=True)
        check.assert_awaited_once_with(self.hass, self.entry)

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
        result = await handler.async_step_room_mapping({"Loxone: Loxone office": self.office.id, "Loxone: Loxone kitchen": self.kitchen.id})
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["options"]["room_area_mapping"], {"room-1": self.office.id, "room-2": self.kitchen.id})
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
        result = await handler.async_step_room_mapping({"Loxone: Loxone kitchen": self.kitchen.id})
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["room_area_mapping"], {"room-2": self.kitchen.id})
        self.assertEqual(result["data"]["password"], "FAKE_SECRET")

    async def test_list_contains_named_area_pickers_and_existing_selections(self):
        from types import SimpleNamespace as NS
        handler = NS(parent_handler=NS(hass=self.hass),
                     flow_state={"rooms": {"r1": "Office", "r2": "Office", "r3": "Kitchen"}},
                     options={"room_area_mapping": {"r1": self.office.id, "r3": "deleted-area"}})
        schema = await flow.mapping_form(handler)
        fields = {str(marker): (marker, selector) for marker, selector in schema.schema.items()}
        self.assertEqual(len(fields), 3)
        self.assertEqual(await flow.mapping_suggestions(handler), {"Loxone: Office (r1)": self.office.id})
        self.assertTrue(all("area" in selector.serialize()["selector"] for _, selector in fields.values()))
        self.assertEqual(schema({}), {})  # Clearing must not reinsert saved defaults.
        result = await flow.validate_mapping(handler, {"Loxone: Office (r1)": None, "Loxone: Office (r2)": ""})
        self.assertEqual(result, {"room_area_mapping": {}})

    async def test_empty_list_clears_all_saved_mappings(self):
        self.hass.config_entries.async_update_entry(self.entry, options={**self.options, "room_area_mapping": {"room-1": self.office.id}})
        handler = flow.LoxoneFlowHandler.async_get_options_flow(self.entry)
        handler.hass = self.hass
        with patch.object(flow, "async_load_rooms", AsyncMock(return_value=self.rooms)):
            await handler.async_step_init({**self.options, "edit_room_mapping": True})
        result = await handler.async_step_room_mapping({})
        self.assertEqual(result["data"]["room_area_mapping"], {})

    async def test_validation_retry_does_not_restore_cleared_room(self):
        self.hass.config_entries.async_update_entry(self.entry, options={**self.options, "room_area_mapping": {"room-1": self.office.id}})
        handler = flow.LoxoneFlowHandler.async_get_options_flow(self.entry)
        handler.hass = self.hass
        with patch.object(flow, "async_load_rooms", AsyncMock(return_value=self.rooms)):
            first = await handler.async_step_init({**self.options, "edit_room_mapping": True})
        initial = next(k for k in first["data_schema"].schema if str(k) == "Loxone: Loxone office")
        self.assertEqual(initial.description["suggested_value"], self.office.id)
        result = await handler.async_step_room_mapping({"Loxone: Loxone kitchen": "deleted-area"})
        self.assertEqual(result["type"], "form")
        cleared = next(k for k in result["data_schema"].schema if str(k) == "Loxone: Loxone office")
        self.assertNotIn("suggested_value", cleared.description or {})

    async def test_invalid_area_or_missing_room_stays_in_form(self):
        handler = self.new_flow()
        with patch.object(flow, "async_load_rooms", AsyncMock(return_value=self.rooms)):
            await handler.async_step_user({**self.options, "edit_room_mapping": True})
        for data in ({"Loxone: Loxone office": "deleted"}, {"unknown": self.office.id}):
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
