"""Prevent ventilation measurements being registered as fans or sharing fan IDs."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("ventilation_states", Path(__file__).resolve().parents[1] / "custom_components/loxone/ventilation_states.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_ventilation_uses_state_ids_and_honors_available_measurements():
    config = {"controls": {"fan": {"type": "Ventilation", "uuidAction": "fan",
        "name": "Fan", "details": {"hasPresence": True, "hasIndoorHumidity": True},
        "states": {"presence": "p", "humidityIndoor": "h", "airQualityIndoor": "a", "temperatureOutdoor": "t"}}}}
    binary = list(module.ventilation_states(config, True))
    analog = list(module.ventilation_states(config))
    assert [x["uuidAction"] for x in binary] == ["p"]
    assert binary[0]["states"] == {"active": "p"}
    assert [x["uuidAction"] for x in analog] == ["h", "t"]
    assert all(x["parent_id"] == "fan" and x["uuidAction"] != "fan" for x in binary + analog)
