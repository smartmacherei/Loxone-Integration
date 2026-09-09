"""Customer-visible state of UDP setup, separate from receipt of live data."""
import time

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory

from .const import DOMAIN


class UdpStatusSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "udp_status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:lan-connect"
    _attr_should_poll = True

    def __init__(self, entry_id, serial):
        self.entry_id = entry_id
        self._attr_unique_id = f"{serial}-udp_status"
        self._attr_device_info = {"identifiers": {(DOMAIN, serial)}}

    async def async_update(self):
        manager = self.hass.data.get(DOMAIN + "_udp_setup", {}).get(self.entry_id)
        receiver = self.hass.data.get(DOMAIN + "_udp", {}).get(self.entry_id)
        status = dict(manager.status) if manager else {"state": "manual"}
        state = status.pop("state")
        if receiver and state in {"configured", "manual"}:
            if receiver.last_valid_received is None:
                state = "waiting_for_data"
            elif time.monotonic() - receiver.last_valid_received < 120:
                state = "receiving"
            else:
                state = "idle"
        elif not receiver:
            state = "disabled"
        self._attr_native_value = state
        self._attr_extra_state_attributes = status
        router = self.hass.data.get(DOMAIN + "_transport", {}).get(self.entry_id)
        if router:
            self._attr_extra_state_attributes.update(router.diagnostics())
