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

# Energy Flow Monitor, documented in the Structure File (section EnergyFlowMonitor):
# Ppwr/Gpwr/Spwr and actual0..N in the unit of details.actualFormat, CO2 in kg/kWh,
# Pre/Pri as price per kWh (no currency in the structure). The other states
# (selfConsumption, storageChargeFromProduction, their totals, jLocked) are not
# documented and stay raw values.
EFM_POWER = {"Ppwr": "Production power", "Gpwr": "Grid power", "Spwr": "Storage power"}
EFM_OTHER = {"CO2": ("CO2 factor", "%.3f kg/kWh"), "Pre": ("Export price", "%.3f"), "Pri": ("Import price", "%.3f")}
EFM_ACTUAL = re.compile(r"actual\d+")


def _efm_nodes(nodes):
    for node in nodes if isinstance(nodes, list) else []:
        if isinstance(node, dict):
            yield node
            yield from _efm_nodes(node.get("nodes"))


def efm_values(control):
    """Documented EFM states as ``[{"state", "uuid", "name", "format"}]``.

    ``actualN`` is named after the node whose ``actualEfmState`` points at it.
    Without ``actualFormat`` the power states stay raw: their unit would be a guess.
    """
    details = control.get("details") or {}
    name = control.get("name") or control.get("type", "EFM")
    power_format = details.get("actualFormat")
    titles = {}
    for node in _efm_nodes(details.get("nodes")):
        ref, title = node.get("actualEfmState"), node.get("title")
        if isinstance(ref, str) and isinstance(title, str) and title:
            titles.setdefault(ref.lower(), title)
    values = []
    for key, uuid in (control.get("states") or {}).items():
        if not isinstance(uuid, str) or not UUID.fullmatch(uuid):
            continue
        if power_format and key in EFM_POWER:
            values.append({"state": key, "uuid": uuid, "name": f"{name} {EFM_POWER[key]}", "format": power_format})
        elif power_format and EFM_ACTUAL.fullmatch(key):
            title = titles.get(uuid.lower()) or titles.get(key.lower()) or key
            values.append({"state": key, "uuid": uuid, "name": f"{name} {title}", "format": power_format})
        elif key in EFM_OTHER:
            label, value_format = EFM_OTHER[key]
            values.append({"state": key, "uuid": uuid, "name": f"{name} {label}", "format": value_format})
    return values


def in_shading_category(config, control):
    """Loxone marks shading categories with type "shading", whatever their name.

    Old gate blocks (Torsteuerung V1) often drive blinds; their category is the
    only hint in the structure file.
    """
    category = config.get("cats", {}).get(control.get("cat"))
    return isinstance(category, dict) and category.get("type") == "shading"


def state_inventory(config):
    """Expose named existing WS states, never guess their write commands/units."""
    seen = {value.lower() for control in config.get("controls", {}).values()
            if control.get("type") in NATIVE_TYPES or control.get("auto_discovered")
            for value in [control.get("uuidAction"), *control.get("states", {}).values()]
            if isinstance(value, str) and UUID.fullmatch(value)}
    # EFM states with a documented unit are real sensors (sensor.efm_sensors).
    seen |= {value["uuid"].lower() for control in config.get("controls", {}).values()
             if control.get("type") == "EFM" for value in efm_values(control)}
    for control in config.get("controls", {}).values():
        if control.get("auto_discovered") or control.get("type") in NATIVE_TYPES:
            continue
        for name, uuid in control.get("states", {}).items():
            if not isinstance(uuid, str) or not UUID.fullmatch(uuid) or uuid.lower() in seen:
                continue
            seen.add(uuid.lower())
            yield {"uuidAction": uuid, "name": f"{control.get('name', control['type'])}: {name}",
                   "parent_id": control.get("uuidAction"), "parent_name": control.get("name", control["type"]),
                   "control_type": control["type"],
                   "room": control.get("room", ""), "cat": control.get("cat", ""),
                   "state_key": name, "type": "RawControlState"}
