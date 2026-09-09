"""Read-only special values; preserve color/text/structured state semantics."""
import json

from homeassistant.components.sensor import SensorEntity

from . import LoxoneEntity
from .helpers import get_or_create_device


class RawValueSensor(LoxoneEntity, SensorEntity):
    _attr_should_poll = False
    _attr_native_value = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._attr_device_info = get_or_create_device(
            kwargs.get("parent_id") or self.uuidAction, self.name,
            kwargs.get("control_type", "Terminal"), kwargs.get("room", ""))
        self._attr_extra_state_attributes.update(
            representation="read_only", loxone_format=kwargs.get("auto_format"),
            loxone_type=kwargs.get("auto_terminal_type") or kwargs.get("control_type"),
        )

    @property
    def available(self):
        return self._attr_native_value is not None

    def set_value(self, value):
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if isinstance(value, str) and len(value) > 255:
            # HA states have a 255-character limit; large payloads are attributes.
            self._attr_extra_state_attributes["value"] = value[:16384]
            self._attr_extra_state_attributes["value_truncated"] = len(value) > 16384
            value = "structured_value"
        else:
            self._attr_extra_state_attributes.pop("value", None)
            self._attr_extra_state_attributes.pop("value_truncated", None)
        self._attr_native_value = value

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        from .helpers import initial_values
        if self.uuidAction in initial_values:
            self.set_value(initial_values[self.uuidAction])

    async def event_handler(self, event):
        if self.uuidAction in event.data:
            self.set_value(event.data[self.uuidAction])
            self.async_write_ha_state()
