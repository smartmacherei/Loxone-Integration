"""Diagnostics support for Pyloxone."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data.get(DOMAIN, {}).get(config_entry.entry_id)
    manager = hass.data.get(DOMAIN + "_udp_setup", {}).get(config_entry.entry_id)
    receiver = hass.data.get(DOMAIN + "_udp", {}).get(config_entry.entry_id)
    router = hass.data.get(DOMAIN + "_transport", {}).get(config_entry.entry_id)
    area_mapping = hass.data.get(DOMAIN + "_area_mapping", {}).get(config_entry.entry_id)
    return {
        # Project/visualization data can include credentials and private content.
        # Setup diagnostics require status, not the unfiltered project document.
        "coordinator_available": coordinator is not None,
        "area_mapping": {
            "configured_rooms": len(area_mapping.mapping),
            "managed_devices": len(area_mapping.owned.get("devices", {})),
            "managed_entities": len(area_mapping.owned.get("entities", {})),
            "manual_device_overrides": len(area_mapping.owned.get("overridden_devices", [])),
            "manual_entity_overrides": len(area_mapping.owned.get("overridden_entities", [])),
        } if area_mapping else None,
        "udp_setup": dict(manager.status) if manager else {"state": "disabled"},
        "transport": router.diagnostics() if router else None,
        "udp_receiver": {
            "packets": receiver.packets,
            "values": receiver.values,
            "dropped_unknown": receiver.dropped_unknown,
            "dropped_duplicate": receiver.dropped_duplicate,
        } if receiver else None,
    }
