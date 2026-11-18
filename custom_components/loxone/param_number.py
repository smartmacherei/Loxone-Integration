"""Function block parameters as number entities (see block_parameters.py, param_wiring.py).

Not wired: shows the program value (read at load and daily over HTTP) and
refuses changes with a hint. Wired by Weg 3: HA holds the value; a change
reaches the Miniserver through Weg 3 at once and is kept there remanently.
"""
from __future__ import annotations

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory

from .helpers import get_or_create_device, get_room_name_from_room_uuid

SIGNAL_PARAMETERS = "loxone_parameters_{}"
HINT = {
    "de": "Dieser Parameter wird noch nicht aus HA gesteuert: Entität mit dem Label „loxone“ versehen "
          "und „HA-Werte ins Programm übernehmen“ drücken.",
    "en": "This parameter is not controlled from HA yet: add the label “loxone” to the entity and "
          "press “Apply HA values to program”.",
}


class BlockParameterNumber(RestoreNumber):
    """One parameter; Visu blocks start enabled, pure logic blocks disabled."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX

    def __init__(self, entry_id: str, loxconfig: dict, param: dict):
        self._entry_id = entry_id
        self._wired = param["ha_wired"]
        limits = param["limits"]
        self._attr_unique_id = param["unique_id"]
        self._attr_name = param["label"]
        self._attr_native_value = param["value"]
        self._attr_native_unit_of_measurement = param["unit"]
        self._attr_native_min_value = limits.get("min", -1e9)
        self._attr_native_max_value = limits.get("max", 1e9)
        self._attr_native_step = limits.get("step", 0.01)
        self._attr_entity_registry_enabled_default = param["visu"]
        self._attr_extra_state_attributes = {
            "block_uuid": param["block"], "block_type": param["block_type"],
            "parameter": param["key"], "controlled_by_ha": self._wired,
            **{k: v for k, v in limits.items() if k == "default"},
        }
        # A Visu block already has a device from its control; keep that control's
        # name and type so existing devices do not change.
        control = loxconfig.get("controls", {}).get(param["block"], {})
        self._attr_device_info = get_or_create_device(
            param["block"], control.get("name") or param["block_title"],
            control.get("type") or param["block_type"],
            get_room_name_from_room_uuid(loxconfig, control.get("room") or param["room"]))

    async def async_added_to_hass(self):
        if self._wired:
            # HA is the source: keep the last value set here across HA restarts.
            last = await self.async_get_last_number_data()
            if last is not None and last.native_value is not None:
                self._attr_native_value = last.native_value
        else:
            self.async_on_remove(async_dispatcher_connect(
                self.hass, SIGNAL_PARAMETERS.format(self._entry_id), self._update))

    @callback
    def _update(self, values: dict) -> None:
        value = values.get(self.unique_id)
        if value != self._attr_native_value:
            self._attr_native_value = value
            self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        if not self._wired:
            language = str(getattr(self.hass.config, "language", "en"))
            raise HomeAssistantError(HINT["de" if language.lower().startswith("de") else "en"])
        # Weg 3 follows this entity's state and sends the value with its trigger edge.
        self._attr_native_value = value
        self.async_write_ha_state()
