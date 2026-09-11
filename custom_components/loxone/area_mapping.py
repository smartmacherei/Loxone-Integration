"""Optional room-to-area assignments, scoped to one Miniserver config entry."""
from __future__ import annotations

import asyncio

CONF_ROOM_MAPPING = "room_area_mapping"


def room_index(config):
    """Resolve controls, inherited subcontrols and state entities by UUID."""
    result = {}

    def add(key, room):
        if isinstance(key, str) and key and room:
            key = key.lower()
            result[key] = room if key not in result or result[key] == room else ""

    def visit(key, control, inherited=""):
        room = control.get("room") or inherited
        add(key, room)
        add(control.get("uuidAction"), room)
        for uuid in control.get("states", {}).values():
            add(uuid, room)
        for child_key, child in control.get("subControls", {}).items():
            visit(child_key, child, room)

    for key, control in config.get("controls", {}).items():
        visit(key, control)
    return result


def room_for_entity(unique_id, rooms):
    key = str(unique_id).lower()
    if key in rooms:
        return rooms[key]
    if "/" in key:
        return rooms.get(key.split("/", 1)[0])
    return None


def plan_mapping(entry_id, entities, devices, rooms, mapping, valid_areas, owned, new_devices):
    """Return registry edits without taking over user-owned assignments.

    Removing a mapping releases ownership but retains the last area assignment.
    Explicit user edits, including clearing an area, survive later reloads.
    """
    mapping = {room: area for room, area in mapping.items() if area in valid_areas}
    entities = [e for e in entities if e.get("platform") == "loxone" and e.get("config_entry_id") == entry_id]
    devices = {d["id"]: d for d in devices}
    old_devices, old_entities = owned.get("devices", {}), owned.get("entities", {})
    blocked_devices = set(owned.get("overridden_devices", []))
    blocked_entities = set(owned.get("overridden_entities", []))
    device_edits, entity_edits, device_owned, entity_owned = {}, {}, {}, {}
    grouped = {}
    targets = {}
    for entity in entities:
        targets[entity["entity_id"]] = mapping.get(room_for_entity(entity["unique_id"], rooms))
        grouped.setdefault(entity.get("device_id"), []).append(entity)
        owner_id = entity.get("id", entity["entity_id"])
        if owner_id in old_entities and entity.get("area_id") != old_entities[owner_id]:
            blocked_entities.add(owner_id)
    for device_id, members in grouped.items():
        device = devices.get(device_id)
        if device and set(device.get("config_entries", [])) != {entry_id}:
            continue  # A shared device must not be moved by this entry.
        device_area = device.get("area_id") if device else None
        if device_id in old_devices and device_area != old_devices[device_id]:
            blocked_devices.add(device_id)
        if device_id in blocked_devices:
            continue
        if device_area is not None and device_id not in new_devices and old_devices.get(device_id) != device_area:
            continue  # Existing assignments without an ownership record are manual.
        desired = {targets[e["entity_id"]] for e in members}
        if device and None not in desired and len(desired) == 1:
            target = next(iter(desired))
            if device_area != target:
                device_edits[device_id] = target
            if device_id in new_devices or device_id in old_devices or device_area is None:
                device_owned[device_id] = target
            device_area = target
        elif device_id in old_devices and any(desired):
            device_owned[device_id] = device_area
        for entity in members:
            entity_id, current = entity["entity_id"], entity.get("area_id")
            owner_id = entity.get("id", entity_id)
            target = targets[entity_id]
            if not target or owner_id in blocked_entities:
                continue
            if current is not None and old_entities.get(owner_id) != current:
                continue
            # Multiroom hardware uses entity overrides. Do not create redundant
            # overrides on a device which already has the desired area.
            if current is None and device_area == target:
                continue
            if current != target:
                entity_edits[entity_id] = target
            entity_owned[owner_id] = target
    active_entities = {key for key, value in targets.items() if value}
    active_devices = {e.get("device_id") for e in entities if e["entity_id"] in active_entities}
    result = {"devices": device_owned, "entities": entity_owned,
              "overridden_devices": sorted(blocked_devices & active_devices),
              "overridden_entities": sorted(blocked_entities & {
                  e.get("id", e["entity_id"]) for e in entities if e["entity_id"] in active_entities})}
    return device_edits, entity_edits, result


class AreaMapping:
    """Apply mappings after registration, including delayed scene entities."""

    def __init__(self, hass, entry, config):
        from .registry_compat import registry_ids
        from homeassistant.helpers import device_registry as dr
        from homeassistant.helpers.storage import Store

        self.hass, self.entry = hass, entry
        self.mapping = dict(entry.options.get(CONF_ROOM_MAPPING, {}))
        self.rooms = room_index(config)
        self.store = Store(hass, 1, f"loxone.area_mapping.{entry.entry_id}")
        self.owned = {}
        self.initial_devices = registry_ids(dr.async_get(hass).devices)
        self.lock = asyncio.Lock()
        self.closed = False
        self.scheduled = None

    async def start(self):
        from homeassistant.core import callback
        from homeassistant.helpers import device_registry as dr, entity_registry as er

        self.owned = await self.store.async_load() or {}
        if not self.mapping:
            if self.owned:
                self.owned = {}
                await self.store.async_save({})
            return

        @callback
        def changed(event):
            self._changed(event)

        for event in (dr.EVENT_DEVICE_REGISTRY_UPDATED, er.EVENT_ENTITY_REGISTRY_UPDATED):
            self.entry.async_on_unload(self.hass.bus.async_listen(event, changed))
        self.entry.async_on_unload(self.close)

    def close(self):
        self.closed = True
        if self.scheduled:
            self.scheduled.cancel()
            self.scheduled = None

    def _changed(self, event):
        if not self.closed and self.scheduled is None:
            self.scheduled = self.hass.loop.call_soon(self._schedule_apply)

    def _schedule_apply(self):
        self.scheduled = None
        if not self.closed:
            self.hass.async_create_task(self.apply())

    async def apply(self):
        from .registry_compat import registry_entries, registry_ids
        from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er

        async with self.lock:
            if self.closed or not self.mapping:
                return
            devices, entities = dr.async_get(self.hass), er.async_get(self.hass)
            device_rows = [{"id": d.id, "area_id": d.area_id, "config_entries": d.config_entries}
                           for d in registry_entries(devices.devices)]
            entity_rows = [{"id": e.id, "entity_id": e.entity_id, "config_entry_id": e.config_entry_id,
                            "platform": e.platform, "unique_id": e.unique_id,
                            "device_id": e.device_id, "area_id": e.area_id}
                           for e in registry_entries(entities.entities)]
            de, ee, owned = plan_mapping(self.entry.entry_id, entity_rows, device_rows,
                                        self.rooms, self.mapping, registry_ids(ar.async_get(self.hass).areas),
                                        self.owned, registry_ids(devices.devices) - self.initial_devices)
            changed = owned != self.owned
            self.owned = owned
            for device_id, area_id in de.items():
                devices.async_update_device(device_id, area_id=area_id)
            for entity_id, area_id in ee.items():
                entities.async_update_entity(entity_id, area_id=area_id)
            if changed:
                await self.store.async_save(self.owned)

    def device_info(self, unique_id, info):
        if info and self.is_mapped(unique_id):
            # Avoid creating a second HA area with the original Loxone room name.
            # Assignment to the selected existing area happens after registration.
            return {**info, "suggested_area": None}
        return info

    def is_mapped(self, unique_id):
        return room_for_entity(unique_id, self.rooms) in self.mapping
