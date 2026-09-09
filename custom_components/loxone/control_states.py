"""Lossless state inventory for controls without a native HA implementation."""
import re

NATIVE_TYPES = {
    "Alarm", "InfoOnlyDigital", "PresenceDetector", "SmokeAlarm", "IRoomControllerV2",
    "IRoomController", "AcControl", "Pushbutton", "Jalousie", "Gate", "Window",
    "Ventilation", "Dimmer", "EIBDimmer", "LightControllerV2", "AudioZoneV2", "Slider",
    "Radio", "InfoOnlyAnalog", "TextInput", "Meter", "Switch", "TimedSwitch", "Intercom",
    "RawTerminal",
}
UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{16}$")


def state_inventory(config):
    """Expose named existing WS states, never guess their write commands/units."""
    seen = {value.lower() for control in config.get("controls", {}).values()
            if control.get("type") in NATIVE_TYPES or control.get("auto_discovered")
            for value in [control.get("uuidAction"), *control.get("states", {}).values()]
            if isinstance(value, str) and UUID.fullmatch(value)}
    for control in config.get("controls", {}).values():
        if control.get("auto_discovered") or control.get("type") in NATIVE_TYPES:
            continue
        for name, uuid in control.get("states", {}).items():
            if not isinstance(uuid, str) or not UUID.fullmatch(uuid) or uuid.lower() in seen:
                continue
            seen.add(uuid.lower())
            yield {"uuidAction": uuid, "name": f"{control.get('name', control['type'])}: {name}",
                   "parent_id": control.get("uuidAction"), "control_type": control["type"],
                   "room": control.get("room", ""), "cat": control.get("cat", ""),
                   "state_key": name, "type": "RawControlState"}
