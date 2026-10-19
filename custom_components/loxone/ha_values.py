"""Weg 3: HA entities labelled "loxone" become values in the Loxone program.

Value rules and formatting are plain functions (offline testable); the
sender, the store and the apply flow import Home Assistant lazily.
"""
from __future__ import annotations

import logging
import socket
from datetime import timedelta

from .ha_values_program import PORT

try:
    from .const import DOMAIN
    from homeassistant.core import callback
except ImportError:  # offline tests load this module without Home Assistant
    DOMAIN = "loxone"

    def callback(func):
        return func

_LOGGER = logging.getLogger(__name__)

LABEL = "loxone"
LABEL_ICON, LABEL_COLOR = "mdi:alpha-l-box", "green"
STATUS_UNIQUE_SUFFIX = "-ha_connected"
KEY = DOMAIN + "_ha_values"
RESEND = timedelta(minutes=5)
UNKNOWN = {None, "", "unknown", "unavailable"}
BOOL = {"on": 1, "off": 0, "true": 1, "false": 0, "open": 1, "closed": 0, "locked": 1, "unlocked": 0,
        "home": 1, "not_home": 0, "wet": 1, "dry": 0, "detected": 1, "clear": 0}
ACTIONS = ["off", "heating", "cooling", "drying", "idle", "fan", "preheating", "defrosting"]
CLIMATE = ("current_temperature", "temperature", "hvac_action")
# Domains whose state is on/off-like; decides digital when the state is not known yet.
DIGITAL_DOMAINS = {"binary_sensor", "switch", "light", "input_boolean", "lock", "cover", "fan", "siren", "valve"}
LABELS = {"de": {"current_temperature": "Ist-Temperatur", "temperature": "Solltemperatur", "hvac_action": "Aktion"},
          "en": {"current_temperature": "current temperature", "temperature": "target temperature", "hvac_action": "action"}}


def _number(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _entry(entity_id, attribute, title, digital):
    return {"key": entity_id + ("." + attribute if attribute else ""), "entity_id": entity_id,
            "attribute": attribute, "title": title, "digital": digital}


def entries_for(entity_id, state, language="de"):
    """Values an entity contributes, or ``None`` when its state is not a number."""
    attributes = getattr(state, "attributes", None) or {}
    name = attributes.get("friendly_name") or entity_id
    if entity_id.startswith("climate."):
        words = LABELS["de" if language.lower().startswith("de") else "en"]
        return [_entry(entity_id, None, name, False)] + [
            _entry(entity_id, attribute, f"{name} {words[attribute]}", False) for attribute in CLIMATE]
    if "options" in attributes:
        return [_entry(entity_id, None, name, False)]
    value = getattr(state, "state", None)
    if value in BOOL:
        return [_entry(entity_id, None, name, True)]
    if value in UNKNOWN:
        return [_entry(entity_id, None, name, entity_id.split(".", 1)[0] in DIGITAL_DOMAINS)]
    if _number(value) is not None:
        return [_entry(entity_id, None, name, False)]
    return None


def value_of(entry, state):
    """Number to send for one entry, or ``None`` to leave the Loxone input as it is."""
    if state is None or state.state in UNKNOWN:
        return None
    attributes = state.attributes or {}
    attribute = entry["attribute"]
    if entry["entity_id"].startswith("climate."):
        if attribute is None:
            modes = attributes.get("hvac_modes") or []
            return float(modes.index(state.state)) if state.state in modes else None
        if attribute == "hvac_action":
            action = attributes.get("hvac_action")
            return float(ACTIONS.index(action)) if action in ACTIONS else None
        return _number(attributes.get(attribute))
    options = attributes.get("options")
    if options is not None:
        return float(options.index(state.state)) if state.state in options else None
    if state.state in BOOL:
        return float(BOOL[state.state])
    return _number(state.state)


def format_number(value):
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def program_entries(entries):
    return [{"key": e["key"], "title": e["title"], "digital": e["digital"]} for e in entries]


def desired(hass, limit, language):
    """Wish list from the registry: (entries, unsupported entity_ids, keys beyond the limit)."""
    from homeassistant.helpers import entity_registry as er, label_registry as lr
    registry, labels = er.async_get(hass), lr.async_get(hass)
    listed = labels.async_list_labels() if hasattr(labels, "async_list_labels") else labels.labels.values()
    label_ids = {LABEL} | {label.label_id for label in listed if (label.name or "").lower() == LABEL}
    entries, unsupported, seen = [], [], set()
    for label_id in sorted(label_ids):
        for entry in er.async_entries_for_label(registry, label_id):
            if entry.entity_id in seen or entry.disabled_by:
                continue
            seen.add(entry.entity_id)
            found = entries_for(entry.entity_id, hass.states.get(entry.entity_id), language)
            if found is None:
                unsupported.append(entry.entity_id)
            else:
                entries.extend(found)
    entries.sort(key=lambda e: e["key"])
    return entries[:limit], sorted(unsupported), [e["key"] for e in entries[limit:]]


def seed_due(stored, fresh):
    """The HA status value is prepared once, for brand-new installations only.

    An update never touches an existing entry; its program changes on the button.
    """
    return bool(fresh) and not (stored or {}).get("seeded")


async def _async_seed(hass, entry, state, store):
    """Label the HA status entity (creating the label if needed) and store the wish list."""
    from homeassistant.helpers import entity_registry as er, label_registry as lr
    registry, labels = er.async_get(hass), lr.async_get(hass)
    status = next((e for e in er.async_entries_for_config_entry(registry, entry.entry_id)
                   if e.domain == "binary_sensor" and (e.unique_id or "").endswith(STATUS_UNIQUE_SUFFIX)), None)
    if status is None:
        _LOGGER.debug("Loxone HA status entity is not registered; nothing to prepare")
        return False
    by_name = getattr(labels, "async_get_label_by_name", None)
    if by_name is not None:
        label = by_name(LABEL)
    else:
        listed = labels.async_list_labels() if hasattr(labels, "async_list_labels") else labels.labels.values()
        label = next((item for item in listed if (item.name or "").lower() == LABEL), None)
    if label is None:
        label = labels.async_create(LABEL, icon=LABEL_ICON, color=LABEL_COLOR)
    registry.async_update_entity(status.entity_id, labels=set(status.labels) | {label.label_id})
    # Only the status entity: further labelled entities show up as pending_add and
    # reach the program with the button, never silently.
    found = entries_for(status.entity_id, hass.states.get(status.entity_id), hass.config.language) or []
    entries = sorted(found, key=lambda e: e["key"])
    state["entries"] = entries
    await store.async_save({"entries": entries, "seeded": True})
    return True


def _store(hass, entry_id):
    from homeassistant.helpers.storage import Store
    return Store(hass, 1, f"loxone.ha_values.{entry_id}")


class HaValuesSender:
    """Sends ``key=value`` datagrams.

    Numbers go out on every change, every 5 minutes, at start and after a program change.
    A digital value is a pulse on the Loxone side (the command fires on ``key=1``), so it
    goes out only when the state really changes: a repeat would ring the bell or toggle a
    light again.
    """

    def __init__(self, hass, entries, host, port=PORT):
        self.hass, self.entries, self.host, self.port = hass, entries, host, port
        self.socket = None
        self.unsub = []

    def start(self):
        from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setblocking(False)
        ids = sorted({e["entity_id"] for e in self.entries})
        if ids:
            self.unsub.append(async_track_state_change_event(self.hass, ids, self._changed))
            self.unsub.append(async_track_time_interval(self.hass, self._tick, RESEND))
        self.send_all()

    @callback
    def _changed(self, event):
        entity_id = event.data.get("entity_id")
        old, new = event.data.get("old_state"), event.data.get("new_state")
        # Unknown predecessors (restart, entity just appeared) and attribute-only updates send no pulse.
        changed = old is not None and new is not None and old.state not in UNKNOWN and old.state != new.state
        self.send([e for e in self.entries if e["entity_id"] == entity_id and (changed or not e["digital"])])

    @callback
    def _tick(self, _now):
        self.send_all()

    def send_all(self):
        self.send([e for e in self.entries if not e["digital"]])

    def send(self, entries):
        if self.socket is None or not self.host:
            return
        for entry in entries:
            value = value_of(entry, self.hass.states.get(entry["entity_id"]))
            if value is None:
                continue
            try:
                self.socket.sendto(f"{entry['key']}={format_number(value)}".encode(), (self.host, self.port))
            except OSError as err:
                _LOGGER.debug("Loxone HA values: send failed: %s", err)

    def stop(self):
        for unsub in self.unsub:
            unsub()
        self.unsub = []
        if self.socket is not None:
            self.socket.close()
            self.socket = None


def _attach(hass, entry, state):
    """Hand the stored wish list to the setup manager and (re)start the sender."""
    manager = hass.data.get(DOMAIN + "_udp_setup", {}).get(entry.entry_id)
    if manager is not None:
        manager.ha_values = program_entries(state["entries"])
    if state.get("sender") is not None:
        state["sender"].stop()
    sender = HaValuesSender(hass, state["entries"], entry.options.get("host"))
    sender.start()
    state["sender"] = sender
    if manager is not None:
        manager.configured_callbacks = [sender.send_all]


async def async_setup_values(hass, entry, fresh=False):
    store = _store(hass, entry.entry_id)
    data = await store.async_load()
    state = {"entries": list((data or {}).get("entries", [])), "sender": None}
    hass.data.setdefault(KEY, {})[entry.entry_id] = state
    if seed_due(data, fresh):
        try:
            await _async_seed(hass, entry, state, store)
        except Exception as err:  # noqa: BLE001 - a convenience, never a reason to fail the setup
            _LOGGER.warning("Loxone HA status value could not be prepared: %s", type(err).__name__)
    _attach(hass, entry, state)


def async_unload_values(hass, entry):
    state = hass.data.get(KEY, {}).pop(entry.entry_id, None)
    if state and state.get("sender") is not None:
        state["sender"].stop()


async def async_apply(hass, entry):
    """Button: freeze the labelled entities into the wish list and change the program now."""
    from homeassistant.components import persistent_notification
    german = str(getattr(hass.config, "language", "en")).lower().startswith("de")
    limit = int(entry.options.get("udp_max_signals") or 500)
    entries, unsupported, beyond = desired(hass, limit, hass.config.language)
    store = _store(hass, entry.entry_id)
    await store.async_save({**((await store.async_load()) or {}), "entries": entries})
    state = hass.data.setdefault(KEY, {}).setdefault(entry.entry_id, {"entries": [], "sender": None})
    state["entries"] = entries
    _attach(hass, entry, state)
    if beyond:
        _LOGGER.warning("Loxone HA values: %s values exceed the limit of %s (option udp_max_signals)", len(beyond), limit)
    manager = hass.data.get(DOMAIN + "_udp_setup", {}).get(entry.entry_id)
    notification_id = "loxone_ha_values_" + entry.entry_id
    if manager is None:
        persistent_notification.async_create(
            hass, ("Weg 3 braucht Weg 2: Bitte in den Optionen „Echtzeitwerte per UDP automatisch einrichten“ "
                   "einschalten, dann den Knopf erneut drücken." if german else
                   "Way 3 needs way 2: enable “Set up real-time values over UDP automatically” in the options, "
                   "then press the button again."), title="Loxone HA → Loxone", notification_id=notification_id)
        return
    if manager.task is not None and not manager.task.done():
        persistent_notification.async_create(
            hass, "Eine Prüfung läuft bereits; bitte kurz warten." if german else "A check is already running; please wait.",
            title="Loxone HA → Loxone", notification_id=notification_id)
        return
    persistent_notification.async_dismiss(hass, notification_id)
    manager.task = hass.async_create_task(manager.check())
