"""Loxone ventilation controls; measurements use the sensor platforms."""

from __future__ import annotations

import logging

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from voluptuous import Any, Optional

from .startup_trace import tracked_platform
from . import LoxoneEntity
from .const import SENDDOMAIN
from .helpers import (add_room_and_cat_to_value_values, get_all,
                      get_or_create_device)
from .miniserver import get_miniserver_from_hass

_LOGGER = logging.getLogger(__name__)

# Speed for a preset chosen while the fan stands still
DEFAULT_FAN_SPEED_HOME = 30
# Length of a manual timer in seconds
TIMER_INTERVAL = 3600


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_devices: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """
    For now, we do nothing. Function is only to get rid of the error message of missing async_setup_platform
    """
    pass


@tracked_platform
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entry."""
    miniserver = get_miniserver_from_hass(hass, config_entry)
    loxconfig = miniserver.lox_config.json
    entities = []

    # Older releases registered these read-only measurements under fan.*.
    # Remove only those exact stale registrations; preserve the real fan IDs.
    from homeassistant.helpers import entity_registry as er
    from .ventilation_states import ventilation_states
    measurement_ids = {s["uuidAction"] for s in ventilation_states(loxconfig)}
    registry = er.async_get(hass)
    for entry in er.async_entries_for_config_entry(registry, config_entry.entry_id):
        if entry.domain == "fan" and entry.platform == "loxone" and entry.unique_id in measurement_ids:
            registry.async_remove(entry.entity_id)

    for fan in get_all(loxconfig, "Ventilation"):
        fan = add_room_and_cat_to_value_values(loxconfig, fan)
        fan.update(
            {
                "type": "ventilation",
                "async_add_devices": async_add_entities,
                "config_entry": config_entry,
            }
        )

        entities.append(LoxoneVentilation(**fan))

    async_add_entities(entities)


class LoxoneVentilation(LoxoneEntity, FanEntity):
    """Representation of a ventilation Loxone device."""

    def __init__(self, **kwargs) -> None:
        """Initialize the fan."""
        super().__init__(**kwargs)

        self._device_class = None
        self._state = STATE_UNKNOWN
        self._format = self._get_format(kwargs.get("details", {}).get("format", ""))
        self._attr_available = True

        self._stateAttribUuids = kwargs["states"]
        self._stateAttribValues = {}
        self._details = kwargs["details"]

        self.type = "Fan"
        self._attr_device_info = get_or_create_device(
            self.unique_id, self.name, self.type, self.room
        )

    @property
    def extra_state_attributes(self):
        """Return device specific state attributes.

        Implemented by platform classes.
        """
        return {
            **self._attr_extra_state_attributes,
            "device_type": self.type,
        }

    @property
    def supported_features(self):
        """Flag supported features."""
        return FanEntityFeature.PRESET_MODE | FanEntityFeature.SET_SPEED

    async def event_handler(self, event):
        # _LOGGER.debug(f"Fan Event data: {event.data}")
        update = False

        for key in set(self._stateAttribUuids.values()) & event.data.keys():
            self._stateAttribValues[key] = event.data[key]
            update = True

        if update:
            self.schedule_update_ha_state()

        # _LOGGER.debug(f"State attribs after event handling: {self._stateAttribValues}")

    @property
    def icon(self):
        """Return the fan icon."""
        return "mdi:fan"

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        if not hasattr(self, "_device_class"):
            return None
        else:
            return self._device_class

    @property
    def is_on(self) -> bool:
        """Return if device is on."""
        if self.percentage:
            return self.percentage > 0
        else:
            return False

    @property
    def _modes(self) -> dict[str, int]:
        """Mode names and ids from details.modes."""
        return {mode["name"]: mode["id"] for mode in self._details.get("modes", [])}

    @property
    def preset_modes(self) -> list[str]:
        """Return a list of available preset modes."""
        return list(self._modes)

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        mode = self.get_state_value("mode")
        return next((name for name, id_ in self._modes.items() if id_ == mode), None)

    @property
    def percentage(self) -> Optional[int]:
        """Return the current speed percentage."""
        return self.get_state_value("speed")

    @device_class.setter
    def device_class(self, device_class):
        if not hasattr(self, "_device_class"):
            setattr(self, "_device_class", device_class)
        else:
            self._device_class = device_class

    def get_state_value(self, name):
        uuid = self._stateAttribUuids[name]
        return (
            self._stateAttribValues[uuid] if uuid in self._stateAttribValues else None
        )

    def _set_timer(self, percentage: int | None, preset_mode: str | None = None) -> None:
        """Start a manual timer; unset values keep the current speed and mode."""
        if percentage is None:
            percentage = round(self.percentage or 0)
        if preset_mode is None:
            mode = self.get_state_value("mode")
            if mode is None:
                mode = next(iter(self._modes.values()))
        else:
            mode = self._modes[preset_mode]
        self.hass.bus.async_fire(
            SENDDOMAIN,
            dict(
                uuid=self.uuidAction,
                value=f"setTimer/{TIMER_INTERVAL}/{percentage}/{int(mode)}/-1",
            ),
        )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode of the fan."""
        await self.async_turn_on(preset_mode=preset_mode)

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed percentage of the fan."""
        self._set_timer(percentage)

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn the fan on; without speed or preset back to automatic."""
        if percentage is None and preset_mode is None:
            self.hass.bus.async_fire(SENDDOMAIN, dict(uuid=self.uuidAction, value="setTimer/0"))
            return
        if percentage is None and not self.is_on:
            percentage = DEFAULT_FAN_SPEED_HOME
        self._set_timer(percentage, preset_mode)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the fan off."""
        if self.is_on:
            self._set_timer(0)
