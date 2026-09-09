"""Ventilation measurements belong to their HA sensor platforms."""


def ventilation_states(config, binary=False):
    for control in config.get("controls", {}).values():
        if control.get("type") != "Ventilation":
            continue
        details, states = control.get("details", {}), control.get("states", {})
        fields = (("presence", "Presence", "hasPresence", None),) if binary else (
            ("humidityIndoor", "Humidity", "hasIndoorHumidity", "%.1f%%"),
            ("airQualityIndoor", "Air Quality", "hasAirQuality", "%.1f ppm"),
            ("temperatureOutdoor", "Outdoor Temperature", None, "%.1f °C"),
        )
        for key, label, flag, format_ in fields:
            if key not in states or (flag and not details.get(flag)):
                continue
            state = states[key]
            yield {"uuidAction": state, "parent_id": control["uuidAction"],
                   "name": f"{control['name']} - {label}",
                   "room": control.get("room", ""), "cat": control.get("cat", ""),
                   "type": "presence" if binary else "analog",
                   "states": {"active": state} if binary else {"value": state},
                   "details": {} if binary else {"format": format_}}
