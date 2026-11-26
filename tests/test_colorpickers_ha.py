"""Colour-picker commands with the real HA runtime; skipped without HA."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

HAS_HA = importlib.util.find_spec("homeassistant") is not None
if HAS_HA:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from homeassistant.core import Event, HomeAssistant, callback
    from custom_components.loxone import helpers
    from custom_components.loxone.const import SENDDOMAIN
    from custom_components.loxone.lights.colorpickers import (
        LumiTech,
        RGBColorPicker,
        TunableWhiteLight,
    )


@unittest.skipUnless(HAS_HA, "Run with the installed Home Assistant Python runtime")
class ColorPickerCommandsHATest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="loxone_colorpicker_test_")
        self.hass = HomeAssistant(self.directory.name)
        helpers.device_registry.clear()
        self.commands = []
        self.counter = 0

        @callback
        def capture(event):
            self.commands.append(event.data)

        self.unsubscribe = self.hass.bus.async_listen(SENDDOMAIN, capture)

    async def asyncTearDown(self):
        self.unsubscribe()
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    def entity(self, light_type):
        self.counter += 1
        entity = light_type(
            uuidAction=f"colorpicker-action-{self.counter}",
            name="Test light",
            type="ColorPickerV2",
            room="Test room",
            states={"color": f"colorpicker-state-{self.counter}"},
            async_add_devices=lambda entities: None,
            lightcontroller_id=f"controller-{self.counter}",
        )
        entity.hass = self.hass
        entity.entity_id = f"light.colorpicker_{self.counter}"
        # Exercise the real state handler without registering an entity platform.
        entity.async_schedule_update_ha_state = Mock()
        return entity

    def variants(self):
        for light_type in (RGBColorPicker, LumiTech):
            yield light_type, "hsv", (120, 50)
            yield light_type, "temp", (3000,)
        yield TunableWhiteLight, "temp", (3000,)

    async def state(self, entity, kind, values, brightness):
        numbers = (*values, brightness) if kind == "hsv" else (brightness, *values)
        color = f"{kind}({','.join(str(value) for value in numbers)})"
        await entity.event_handler(Event("test_loxone_state", {entity._color_uuid: color}))
        self.assertEqual(entity.is_on, brightness > 0)

    async def command(self, entity, **kwargs):
        self.commands.clear()
        await entity.async_turn_on(**kwargs)
        await self.hass.async_block_till_done()
        self.assertEqual(len(self.commands), 1)
        self.assertEqual(self.commands[0]["uuid"], entity.uuidAction)
        return self.commands[0]["value"]

    def assert_color(self, command, kind, expected):
        self.assertTrue(command.startswith(f"{kind}("), command)
        self.assertTrue(command.endswith(")"), command)
        actual = tuple(float(value) for value in command[len(kind) + 1:-1].split(","))
        self.assertEqual(len(actual), len(expected))
        for value, wanted in zip(actual, expected):
            self.assertAlmostEqual(value, wanted, places=6)

    async def test_hs_and_brightness_from_off(self):
        for light_type in (RGBColorPicker, LumiTech):
            with self.subTest(light=light_type.__name__):
                entity = self.entity(light_type)
                await self.state(entity, "hsv", (120, 50), 0)
                value = await self.command(entity, hs_color=(120, 100), brightness=200)
                self.assert_color(value, "hsv", (120, 100, 78.431372549))

    async def test_temperature_and_brightness_from_off(self):
        for light_type, kind, values in self.variants():
            with self.subTest(light=light_type.__name__, previous_mode=kind):
                entity = self.entity(light_type)
                await self.state(entity, kind, values, 0)
                value = await self.command(entity, color_temp_kelvin=4000, brightness=128)
                self.assert_color(value, "temp", (50.196078431, 4000))

    async def test_plain_turn_on_restores_latest_nonzero_brightness(self):
        for light_type, kind, values in self.variants():
            with self.subTest(light=light_type.__name__, mode=kind):
                entity = self.entity(light_type)
                await self.state(entity, kind, values, 20)
                await self.state(entity, kind, values, 40)
                await self.state(entity, kind, values, 0)
                await self.state(entity, kind, values, 0)
                value = await self.command(entity)
                expected = (*values, 40) if kind == "hsv" else (40, *values)
                self.assert_color(value, kind, expected)

    async def test_plain_turn_on_defaults_to_full_brightness_after_initial_off(self):
        for light_type, kind, values in self.variants():
            with self.subTest(light=light_type.__name__, mode=kind):
                entity = self.entity(light_type)
                await self.state(entity, kind, values, 0)
                value = await self.command(entity)
                expected = (*values, 100) if kind == "hsv" else (100, *values)
                self.assert_color(value, kind, expected)

    async def test_color_only_restores_brightness_after_off(self):
        for light_type, kind, values in self.variants():
            with self.subTest(light=light_type.__name__, mode=kind):
                entity = self.entity(light_type)
                await self.state(entity, kind, values, 40)
                await self.state(entity, kind, values, 0)
                if kind == "hsv":
                    value = await self.command(entity, hs_color=(120, 100))
                    self.assert_color(value, "hsv", (120, 100, 40))
                else:
                    value = await self.command(entity, color_temp_kelvin=4000)
                    self.assert_color(value, "temp", (40, 4000))

    async def test_color_only_defaults_to_full_brightness_after_initial_off(self):
        for light_type, kind, values in self.variants():
            with self.subTest(light=light_type.__name__, mode=kind):
                entity = self.entity(light_type)
                await self.state(entity, kind, values, 0)
                if kind == "hsv":
                    value = await self.command(entity, hs_color=(120, 100))
                    self.assert_color(value, "hsv", (120, 100, 100))
                else:
                    value = await self.command(entity, color_temp_kelvin=4000)
                    self.assert_color(value, "temp", (100, 4000))

    async def test_explicit_zero_with_color_is_preserved(self):
        for light_type, kind, values in self.variants():
            with self.subTest(light=light_type.__name__, mode=kind):
                entity = self.entity(light_type)
                await self.state(entity, kind, values, 40)
                await self.state(entity, kind, values, 0)
                if kind == "hsv":
                    value = await self.command(entity, hs_color=(120, 100), brightness=0)
                    self.assert_color(value, "hsv", (120, 100, 0))
                else:
                    value = await self.command(entity, color_temp_kelvin=4000, brightness=0)
                    self.assert_color(value, "temp", (0, 4000))

    async def test_brightness_only_preserves_color_mode_and_zero(self):
        for light_type, kind, values in self.variants():
            for brightness, percent in ((128, 50.196078431), (0, 0)):
                with self.subTest(light=light_type.__name__, mode=kind, brightness=brightness):
                    entity = self.entity(light_type)
                    await self.state(entity, kind, values, 40)
                    await self.state(entity, kind, values, 0)
                    value = await self.command(entity, brightness=brightness)
                    expected = (*values, percent) if kind == "hsv" else (percent, *values)
                    self.assert_color(value, kind, expected)

    async def test_last_brightness_is_kept_per_entity(self):
        for light_type, kind, values in self.variants():
            with self.subTest(light=light_type.__name__, mode=kind):
                known = self.entity(light_type)
                unknown = self.entity(light_type)
                await self.state(known, kind, values, 40)
                await self.state(known, kind, values, 0)
                await self.state(unknown, kind, values, 0)
                for entity, percent in ((known, 40), (unknown, 100)):
                    value = await self.command(entity)
                    expected = (*values, percent) if kind == "hsv" else (percent, *values)
                    self.assert_color(value, kind, expected)

    async def test_plain_turn_on_without_color_state_uses_supported_command(self):
        for light_type in (RGBColorPicker, LumiTech, TunableWhiteLight):
            with self.subTest(light=light_type.__name__):
                value = await self.command(self.entity(light_type))
                self.assertEqual(value, "setBrightness/100.0")
