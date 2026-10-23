"""Old gate blocks (Torsteuerung V1) wired to blinds must show up as shading."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/loxone"
HAS_HA = importlib.util.find_spec("homeassistant") is not None

# Shape of a real structure file: six "Door" blocks driving Raffstores, category "Beschattung".
CONFIG = {
    "cats": {"cat-shade": {"name": "Beschattung", "type": "shading"},
             "cat-gate": {"name": "Tor", "type": "undefined"}},
    "rooms": {"room": {"name": "Wohnzimmer"}},
    "controls": {
        "raff": {"type": "Gate", "name": "Schiebetüre 1", "uuidAction": "raff", "room": "room",
                 "cat": "cat-shade", "states": {"position": "raff-pos", "active": "raff-active"},
                 "details": {"animation": 0}},
        "garage": {"type": "Gate", "name": "Garage", "uuidAction": "garage", "room": "room",
                   "cat": "cat-gate", "states": {"position": "garage-pos", "active": "garage-active"},
                   "details": {"animation": 0}},
    },
}


def control_states():
    spec = importlib.util.spec_from_file_location("control_states", ROOT / "control_states.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shading_category_is_recognized_by_type_not_name():
    module = control_states()
    assert module.in_shading_category(CONFIG, CONFIG["controls"]["raff"])
    assert not module.in_shading_category(CONFIG, CONFIG["controls"]["garage"])
    renamed = {**CONFIG, "cats": {"cat-shade": {"name": "Sonnenschutz", "type": "shading"}}}
    assert module.in_shading_category(renamed, CONFIG["controls"]["raff"])


def test_missing_or_unknown_category_is_not_shading():
    module = control_states()
    assert not module.in_shading_category(CONFIG, {"cat": "deleted"})
    assert not module.in_shading_category({}, CONFIG["controls"]["raff"])


@unittest.skipUnless(HAS_HA, "Run with the installed Home Assistant Python runtime")
class GateDeviceClassHATest(unittest.TestCase):
    def test_gate_in_shading_category_is_a_blind(self):
        sys.path.insert(0, str(ROOT.parents[1]))
        from homeassistant.components.cover import CoverDeviceClass
        from custom_components.loxone import cover
        from custom_components.loxone.helpers import add_room_and_cat_to_value_values

        def gate(key):
            control = CONFIG["controls"][key]
            return cover.LoxoneGate(hass=None, shading=cover.in_shading_category(CONFIG, control),
                                    **add_room_and_cat_to_value_values(CONFIG, control))

        self.assertEqual(gate("raff").device_class, CoverDeviceClass.BLIND)
        self.assertEqual(gate("garage").device_class, CoverDeviceClass.GARAGE)
