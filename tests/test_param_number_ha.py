"""Block parameter numbers with the real HA runtime; skipped without HA."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

HAS_HA = importlib.util.find_spec("homeassistant") is not None
if HAS_HA:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from homeassistant.core import HomeAssistant
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers.dispatcher import async_dispatcher_send
    from homeassistant.helpers.entity import EntityCategory
    from custom_components.loxone import helpers
    from custom_components.loxone.param_number import SIGNAL_PARAMETERS, BlockParameterNumber

PARAM = {"unique_id": "20fd118e-02ad-b702-00ffcd7c89c3e057", "block": "20fd118e-02ad-b7da-ffffa13734b4be2f",
         "block_type": "AutoJalousie", "block_title": "Beschattung Buero", "visu": False, "room": "room-1",
         "key": "TimeEnd", "label": "Opening duration", "unit": "s",
         "limits": {"min": 0.0, "default": 75.0}, "value": 75.0, "ha_wired": False}
LOXCONFIG = {"rooms": {"room-1": {"name": "Buero"}}}


@unittest.skipUnless(HAS_HA, "Run with the installed Home Assistant Python runtime")
class BlockParameterNumberHATest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="loxone_param_test_")
        self.hass = HomeAssistant(self.directory.name)
        helpers.device_registry.clear()  # devices are cached per block across tests

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    def entity(self, **changes):
        entity = BlockParameterNumber("entry", LOXCONFIG, {**PARAM, **changes})
        entity.hass = self.hass
        entity.entity_id = "number.beschattung_buero_opening_duration"
        entity.writes = []
        entity.async_write_ha_state = lambda: entity.writes.append(entity.native_value)
        return entity

    async def test_configuration_entity_on_the_block_device(self):
        entity = self.entity()
        assert entity.entity_category is EntityCategory.CONFIG
        assert entity.entity_registry_enabled_default is False
        assert entity.device_info["identifiers"] == {("loxone", PARAM["block"])}
        assert entity.device_info["suggested_area"] == "Buero"
        assert (entity.native_value, entity.native_min_value) == (75.0, 0.0)

    async def test_visu_block_keeps_its_control_device(self):
        loxconfig = {"controls": {PARAM["block"]: {"name": "Jalousie Buero", "type": "Jalousie", "room": "r2"}},
                     "rooms": {"r2": {"name": "Buero 2"}}}
        info = BlockParameterNumber("entry", loxconfig, PARAM).device_info
        assert (info["name"], info["model"], info["suggested_area"]) == ("Jalousie Buero", "Jalousie", "Buero 2")

    async def test_unwired_parameter_follows_the_program_and_refuses_changes(self):
        entity = self.entity()
        await entity.async_added_to_hass()
        for values in ({PARAM["unique_id"]: 90.0}, {PARAM["unique_id"]: 90.0}, {}):
            async_dispatcher_send(self.hass, SIGNAL_PARAMETERS.format("entry"), values)
            await self.hass.async_block_till_done()
        assert entity.writes == [90.0, None]
        with self.assertRaises(HomeAssistantError):
            await entity.async_set_native_value(80.0)

    async def test_wired_parameter_is_held_by_ha(self):
        entity = self.entity(ha_wired=True)

        async def last():  # the bare test instance has no restore-state registry
            return type("Last", (), {"native_value": 70.0})()
        entity.async_get_last_number_data = last
        await entity.async_added_to_hass()
        assert entity.native_value == 70.0  # HA's last value survives an HA restart
        async_dispatcher_send(self.hass, SIGNAL_PARAMETERS.format("entry"), {PARAM["unique_id"]: 10.0})
        await self.hass.async_block_till_done()
        await entity.async_set_native_value(80.0)
        assert entity.writes == [80.0]  # the program value does not overwrite HA's
        assert entity.extra_state_attributes["controlled_by_ha"] is True
