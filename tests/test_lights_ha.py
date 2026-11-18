"""Dimmer, light controller and colour picker state handling with the real HA runtime; skipped without HA.

Structure File 17.0: a dimmer's min is its lowest on-level, off is position 0. activeMoods, moodList
and additionalMoods are JSON; colour states are hsv(h,s,v) or temp(brightness,kelvin) text.
"""
import importlib.util
import json
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
    from custom_components.loxone.lights.colorpickers import RGBColorPicker, TunableWhiteLight
    from custom_components.loxone.lights.dimmer import LoxoneDimmer
    from custom_components.loxone.lights.lightcontroller import LoxoneLightControllerV2

DIMMER = {name: f"00000000-0000-0000-00000000000000{index}" for index, name in enumerate(
    ("position", "min", "max", "step"), 61)}
MASTER = {name: f"00000000-0000-0000-00000000000000{index}" for index, name in enumerate(
    ("position", "min", "max", "step"), 71)}
MOODS = {name: f"00000000-0000-0000-00000000000000{index}" for index, name in enumerate(
    ("activeMoods", "moodList", "additionalMoods"), 81)}
COLOR = "00000000-0000-0000-0000000000000091"
PROBE = "loxone_eval_probe"
INJECTED = f"__import__('sys').modules.__setitem__('{PROBE}', 1)"


class LightHATestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="loxone_light_test_")
        self.hass = HomeAssistant(self.directory.name)
        self.sent = []
        self.hass.bus.async_listen(SENDDOMAIN, callback(lambda event: self.sent.append(event.data["value"])))
        sys.modules.pop(PROBE, None)

    async def asyncTearDown(self):
        sys.modules.pop(PROBE, None)
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    def added(self, entity):
        entity.hass = self.hass
        entity.schedule_update_ha_state = entity.async_schedule_update_ha_state = lambda *args: None
        return entity

    def controller(self, sub_controls=None):
        return self.added(LoxoneLightControllerV2(
            name="Wohnen", uuidAction="00000000-0000-0000-0000000000000080", type="LightControllerV2",
            room="", cat="", states=MOODS, subControls=sub_controls or {}, async_add_devices=None))


@unittest.skipUnless(HAS_HA, "Run with the installed Home Assistant Python runtime")
class DimmerMinimumHATest(LightHATestCase):
    async def test_dimmer_at_its_minimum_is_on(self):
        dimmer = self.added(LoxoneDimmer(name="Spots", uuidAction="00000000-0000-0000-0000000000000060",
                                         type="Dimmer", room="", cat="", states=DIMMER, async_add_devices=None))
        await dimmer.event_handler(NS(data={DIMMER["min"]: 20.0, DIMMER["max"]: 100.0, DIMMER["position"]: 20.0}))
        self.assertTrue(dimmer.is_on)
        self.assertGreater(dimmer.brightness, 0)
        await dimmer.event_handler(NS(data={DIMMER["position"]: 0.0}))
        self.assertFalse(dimmer.is_on)

    async def test_master_dimmer_at_its_minimum_has_brightness(self):
        controller = self.controller({"x/masterValue": {"name": "Master", "type": "Dimmer",
                                                        "uuidAction": "x/masterValue", "states": MASTER}})
        await controller.event_handler(NS(data={MASTER["min"]: 20.0, MASTER["max"]: 100.0, MASTER["position"]: 20.0}))
        self.assertGreater(controller.brightness, 0)


@unittest.skipUnless(HAS_HA, "Run with the installed Home Assistant Python runtime")
class MoodsHATest(LightHATestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.entity = self.controller()

    async def moods(self, moods):
        await self.entity.event_handler(NS(data={MOODS["moodList"]: json.dumps(moods)}))

    async def test_mood_name_with_a_comma_is_one_mood(self):
        await self.moods([{"name": "Hell, warm", "id": 1}, {"name": "Aus", "id": 778}])
        self.sent.clear()
        await self.entity.async_turn_on(effect="Hell, warm")
        await self.hass.async_block_till_done()
        self.assertEqual(self.sent, ["changeTo/1"])

    async def test_mood_list_with_json_booleans_keeps_the_names(self):
        await self.moods([{"name": "Abend", "id": 1, "static": False, "t5": True},
                          {"name": "truefalse", "id": 2, "static": True, "t5": False}])
        self.assertEqual(self.entity.effect_list, ["Abend", "truefalse"])

    async def test_active_and_additional_moods_are_read(self):
        await self.moods([{"name": "Abend", "id": 1}])
        await self.entity.event_handler(NS(data={MOODS["activeMoods"]: "[1]", MOODS["additionalMoods"]: "[2, 3]"}))
        self.assertEqual(self.entity.effect, "Abend")
        self.assertIs(self.entity.is_on, True)

    async def test_injected_mood_state_is_not_executed(self):
        await self.entity.event_handler(NS(data={MOODS["activeMoods"]: "[1]"}))
        for state in MOODS.values():
            await self.entity.event_handler(NS(data={state: INJECTED}))
        self.assertNotIn(PROBE, sys.modules)
        self.assertEqual(self.entity._active_moods, [1])


@unittest.skipUnless(HAS_HA, "Run with the installed Home Assistant Python runtime")
class ColorStateHATest(LightHATestCase):
    def picker(self, cls):
        return self.added(cls(name="Farbe", uuidAction="00000000-0000-0000-0000000000000090", type="ColorPickerV2",
                              room="", cat="", states={"color": COLOR}, async_add_devices=None))

    async def test_hsv_and_temp_states_are_read(self):
        rgb = self.picker(RGBColorPicker)
        await rgb.event_handler(NS(data={COLOR: "hsv(10,20,30)"}))
        self.assertEqual((rgb.hs_color, rgb.brightness), ((10, 20), 76.5))
        await rgb.event_handler(NS(data={COLOR: "temp(50,3000)"}))
        self.assertEqual((rgb.color_temp_kelvin, rgb.brightness), (3000, 128))
        white = self.picker(TunableWhiteLight)
        await white.event_handler(NS(data={COLOR: "temp(50,3000)"}))
        self.assertEqual((white.color_temp_kelvin, white.brightness), (3000, 128))

    async def test_injected_colour_state_is_not_executed(self):
        rgb = self.picker(RGBColorPicker)
        await rgb.event_handler(NS(data={COLOR: "hsv(10,20,30)"}))
        await rgb.event_handler(NS(data={COLOR: f"hsv({INJECTED},0,0)"}))
        await rgb.event_handler(NS(data={COLOR: f"temp({INJECTED},0)"}))
        self.assertNotIn(PROBE, sys.modules)
        self.assertEqual((rgb.hs_color, rgb.brightness), ((10, 20), 76.5))
        white = self.picker(TunableWhiteLight)
        await white.event_handler(NS(data={COLOR: "temp(50,3000)"}))
        await white.event_handler(NS(data={COLOR: f"temp({INJECTED},0)"}))
        self.assertNotIn(PROBE, sys.modules)
        self.assertEqual((white.color_temp_kelvin, white.brightness), (3000, 128))
