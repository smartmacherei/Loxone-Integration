"""
Helper functions

For more details about this component, please refer to the documentation at
https://home-assistant.io/components/loxone/
"""

import re

from .const import DOMAIN, cfmt

# Initialize a device registry
device_registry = {}

# control_uuid (lowercase) -> (device_uuid, device_name)
# Wird beim Setup aus dem Miniserver-Programm befuellt (topology.py) und ordnet
# jede Entity ihrem echten physischen Loxone-Geraet (TreeDevice) zu.
# Leer => Fallback auf das alte Verhalten (ein HA-Geraet pro Control).
device_map = {}

# control_uuid -> Initialwert (per HTTP geholt). Fuer auto-entdeckte Klemmen,
# deren Wert der Miniserver nicht ueber den WS-Stream pusht (z.B. Konfig-Analog).
initial_values = {}


def get_or_create_device(device_uuid, device_name, device_type, device_room):
    base = str(device_uuid).split("/")[0]  # SubControl-Suffix wie /AI1 abschneiden
    mapping = device_map.get(base.lower())
    if mapping:
        # Bekanntes physisches Geraet: alle zugehoerigen Controls teilen sich
        # EIN HA-Device mit dem echten Loxone-Geraetenamen.
        dev_key, mapped_name = mapping
        name = mapped_name or device_name
    else:
        # Unbekannt (z.B. Funktionsbaustein wie LightControllerV2) -> wie bisher
        # ein eigenes Geraet je Control.
        dev_key, name = base, device_name
    if dev_key not in device_registry:
        device_registry[dev_key] = {
            "identifiers": {(DOMAIN, dev_key)},
            "name": name,
            "manufacturer": "Loxone",
            "model": device_type,
            "suggested_area": device_room,
        }
    return device_registry[dev_key]


def map_range(value, in_min, in_max, out_min, out_max):
    if in_max == in_min:
        return out_min
    return out_min + (((value - in_min) / (in_max - in_min)) * (out_max - out_min))


def hass_to_lox(level):
    """Convert the given HASS light level (0-255) to Loxone (0.0-100.0)."""
    return (level * 100.0) / 255.0


def lox_to_hass(lox_val):
    """Convert the given Loxone (0.0-100.0) light level to HASS (0-255)."""
    return (lox_val / 100.0) * 255.0


def lox2lox_mapped(x, min_v, max_v):
    if x <= min_v:
        return 0
    if x >= max_v:
        return max_v
    return x


def lox2hass_mapped(x, min_v, max_v):
    if x <= min_v:
        return 0
    if x >= max_v:
        return lox_to_hass(max_v)
    return lox_to_hass(x)


# def to_hass_color_temp(temp: float):
#     """Linear interpolation between Loxone values from 2700 to 6500"""
#     return np.interp(temp, [2700, 6500], [500, 153])
#
#
# def to_loxone_color_temp(temp: float):
#     """Linear interpolation between HASS values from 153 to 500"""
#     return np.interp(temp, [153, 500], [6500, 2700])


def to_hass_color_temp(temp: float):
    """Linear interpolation between Loxone values from 2700 to 6500"""
    if temp <= 2700:
        return 500
    if temp >= 6500:
        return 153
    return 500 + (temp - 2700) * (153 - 500) / (6500 - 2700)


def to_loxone_color_temp(temp: float):
    """Linear interpolation between HASS values from 153 to 500"""
    if temp <= 153:
        return 6500
    if temp >= 500:
        return 2700
    return 6500 + (temp - 153) * (2700 - 6500) / (500 - 153)


def get_room_name_from_room_uuid(lox_config: dict, room_uuid: str):
    if "rooms" in lox_config:
        if room_uuid in lox_config["rooms"]:
            return lox_config["rooms"][room_uuid]["name"]

    return ""


def get_cat_name_from_cat_uuid(lox_config: dict, cat_uuid: str):
    if "cats" in lox_config:
        if cat_uuid in lox_config["cats"]:
            return lox_config["cats"][cat_uuid]["name"]
    return ""


def add_room_and_cat_to_value_values(loxconfig: dict, sensor: dict):
    sensor.update(
        {
            "room": get_room_name_from_room_uuid(loxconfig, sensor.get("room", "")),
            "cat": get_cat_name_from_cat_uuid(loxconfig, sensor.get("cat", "")),
        }
    )
    return sensor


def get_miniserver_type(t):
    if t == 0:
        return "Miniserver (Gen 1)"
    elif t == 1:
        return "Miniserver Go (Gen 1)"
    elif t == 2:
        return "Miniserver (Gen 2)"
    elif t == 3:
        return "Miniserver Go (Gen 2)"
    elif t == 4:
        return "Miniserver Compact"
    return "Unknown type"


def get_all(json_data, name):
    controls = []
    all_controls = json_data.get("controls", {})
    names = name if isinstance(name, list) else [name]
    for c in all_controls:
        if all_controls[c].get("type") in names:
            controls.append(all_controls[c])
    return controls


def clean_unit(lox_format):
    """Extract the unit string from a Loxone format specifier like '%.1f °C'."""
    search = re.search(cfmt, lox_format, flags=re.X)
    if search:
        unit = lox_format.replace(search.group(0).strip(), "").strip()
        if unit == "%%":
            unit = "%"
        return unit
    return lox_format
