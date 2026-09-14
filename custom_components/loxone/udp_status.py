"""Customer-visible state of UDP setup, separate from receipt of live data."""
import time

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory

from .const import DOMAIN


class HaValuesSensor(SensorEntity):
    """Weg 3: stored values and what a button press would change."""
    _attr_has_entity_name = True
    _attr_translation_key = "ha_values"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:export"
    _attr_should_poll = True

    def __init__(self, entry, serial):
        self.entry = entry
        self._attr_unique_id = f"{serial}-ha_values"
        self._attr_device_info = {"identifiers": {(DOMAIN, serial)}}

    async def async_update(self):
        from .ha_values import KEY, LABEL, PORT, desired
        stored = {e["key"] for e in self.hass.data.get(KEY, {}).get(self.entry.entry_id, {}).get("entries", [])}
        limit = int(self.entry.options.get("udp_max_signals") or 500)
        wanted, unsupported, beyond = desired(self.hass, limit, self.hass.config.language)
        keys = {e["key"] for e in wanted}
        self._attr_native_value = len(stored)
        self._attr_extra_state_attributes = {
            "label": LABEL, "port": PORT, "pending_add": sorted(keys - stored),
            "pending_remove": sorted(stored - keys), "unsupported": unsupported, "beyond_limit": beyond}


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
        if manager is None and receiver is not None:
            # Platforms can perform their first update before async_setup_entry
            # registers the automatic setup manager. Do not imply manual success.
            entry = self.hass.config_entries.async_get_entry(self.entry_id)
            if entry and entry.options.get("auto_configure_udp", False):
                status = {"state": "checking", "step": "program_download"}
        state = status.pop("state")
        status["setup_state"] = state
        if receiver and state in {"configured", "manual"}:
            if receiver.last_valid_received is None:
                state = "waiting_for_data"
            elif time.monotonic() - receiver.last_valid_received < 120:
                state = "receiving"
            else:
                state = "idle"
        elif not receiver and state in {"configured", "manual"}:
            state = "disabled"
        self._attr_native_value = state
        self._attr_extra_state_attributes = status
        from .connection_diagnostics import KEY, live_status
        entry = self.hass.config_entries.async_get_entry(self.entry_id)
        if entry:
            self._attr_extra_state_attributes.update(live_status(self.hass, entry))
        check = self.hass.data.get(KEY, {}).get(self.entry_id)
        if check:
            self._attr_extra_state_attributes["last_connection_check"] = check
        router = self.hass.data.get(DOMAIN + "_transport", {}).get(self.entry_id)
        if router:
            self._attr_extra_state_attributes.update(router.diagnostics())
