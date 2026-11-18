"""Provide info to system health."""

from __future__ import annotations

from typing import Any

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN


@callback
def async_register(
    hass: HomeAssistant, register: system_health.SystemHealthRegistration
) -> None:
    """Register system health callbacks."""
    register.async_register_info(system_health_info)


async def system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Get info for the info page."""
    for coordinator in hass.data.get(DOMAIN, {}).values():
        miniserver = coordinator.miniserver
        ms_info = miniserver.lox_config.get("msInfo", {})
        return {
            "Loxone Miniserver Serial": miniserver.serial,
            "Project Name": ms_info.get("projectName"),
            "Local Url": ms_info.get("localUrl"),
            "Loxone Software Version": miniserver.software_version,
        }
    return {}
