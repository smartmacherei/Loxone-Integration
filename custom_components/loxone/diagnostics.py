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
    return {
        "LoxAPP3.json": coordinator.miniserver.lox_config.json if coordinator else None,
        "udp_setup": dict(manager.status) if manager else {"state": "disabled"},
        "transport": router.diagnostics() if router else None,
        "udp_receiver": {
            "packets": receiver.packets,
            "values": receiver.values,
            "dropped_unknown": receiver.dropped_unknown,
            "dropped_duplicate": receiver.dropped_duplicate,
        } if receiver else None,
    }
