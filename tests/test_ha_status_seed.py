"""A brand-new installation gets one ready-made HA -> Loxone value; updates never do.

Home Assistant is not installed offline, so its entity and label registries are
replaced by small fakes behind ``homeassistant.helpers``.
"""
import asyncio
import json
import sys
import types
from types import SimpleNamespace as NS

import pytest

from test_udp_install import module

values = module("ha_values")
errors = module("udp_errors")

STATUS_ID = "binary_sensor.loxone_ha_verbunden"


def test_status_attributes_stay_far_below_the_recorder_limit():
    # 391 configured terminals (826 discovered) made the attributes exceed HA's 16384 byte limit.
    uuids = [f"13884890-{i:04x}-1236-ffff949738c6754e" for i in range(826)]
    program = "13884893-0033-12a0-ffff949738c6754e"
    status = {"state": "configured", "scopes": {program: uuids}, "signal_limit": 500}
    slim = errors.slim_status(status)
    assert "scopes" not in slim
    assert slim["scope_signals"] == {program: 826}
    assert slim["state"] == "configured" and slim["signal_limit"] == 500
    assert status["scopes"][program] == uuids, "the manager's own status must stay untouched"
    assert len(json.dumps(slim)) < 2000
    assert errors.slim_status({"state": "manual"}) == {"state": "manual"}


@pytest.mark.parametrize("stored,fresh,due", [
    (None, True, True), ({"entries": []}, True, True),
    ({"entries": [], "seeded": True}, True, False),
    (None, False, False), ({"entries": [{"key": "x"}]}, False, False)])
def test_seeding_is_due_only_for_brand_new_installations_and_only_once(stored, fresh, due):
    assert values.seed_due(stored, fresh) is due


def test_status_entity_exports_a_digital_value_and_sends_one():
    entry, = values.entries_for(STATUS_ID, NS(state="on", attributes={"friendly_name": "Loxone Home Assistant verbunden"}))
    assert entry["digital"] is True and entry["key"] == STATUS_ID
    assert values.value_of(entry, NS(state="on", attributes={})) == 1.0


def install_fakes(monkeypatch, entities, labels):
    """Minimal entity and label registries behind homeassistant.helpers."""
    registry = NS(entries=entities)

    def update_entity(entity_id, labels=None):
        for e in registry.entries:
            if e.entity_id == entity_id:
                e.labels = set(labels)
    registry.async_update_entity = update_entity
    label_registry = NS(labels={l.label_id: l for l in labels}, created=[])

    def create(name, *, icon=None, color=None, description=None):
        label = NS(label_id=name, name=name, icon=icon, color=color)
        label_registry.labels[name] = label
        label_registry.created.append(label)
        return label
    label_registry.async_create = create
    label_registry.async_list_labels = lambda: list(label_registry.labels.values())
    label_registry.async_get_label_by_name = lambda name: next(
        (l for l in label_registry.labels.values() if (l.name or "").casefold() == name.casefold()), None)
    er = types.ModuleType("homeassistant.helpers.entity_registry")
    er.async_get = lambda hass: registry
    er.async_entries_for_config_entry = lambda reg, entry_id: [e for e in reg.entries if e.config_entry_id == entry_id]
    er.async_entries_for_label = lambda reg, label_id: [e for e in reg.entries if label_id in e.labels]
    lr = types.ModuleType("homeassistant.helpers.label_registry")
    lr.async_get = lambda hass: label_registry
    helpers = types.ModuleType("homeassistant.helpers")
    helpers.entity_registry, helpers.label_registry = er, lr
    ha = types.ModuleType("homeassistant")
    ha.helpers = helpers
    for name, mod in {"homeassistant": ha, "homeassistant.helpers": helpers,
                      "homeassistant.helpers.entity_registry": er,
                      "homeassistant.helpers.label_registry": lr}.items():
        monkeypatch.setitem(sys.modules, name, mod)
    return registry, label_registry


def entity(entity_id="binary_sensor.loxone_ha_verbunden", unique_id="504F941162D7-ha_connected",
           domain="binary_sensor", labels=()):
    return NS(entity_id=entity_id, domain=domain, unique_id=unique_id, config_entry_id="e1",
              labels=set(labels), disabled_by=None)


class FakeStore:
    def __init__(self, data=None):
        self.data, self.saved = data, None

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        self.saved = data


def hass_and_entry():
    states = {"binary_sensor.loxone_ha_verbunden": NS(state="on", attributes={"friendly_name": "HA verbunden"})}
    hass = NS(states=NS(get=states.get), config=NS(language="de"))
    return hass, NS(entry_id="e1", options={"udp_max_signals": 500})


def test_seeding_creates_the_label_like_the_screenshot_labels_the_entity_and_stores_the_wish_list(monkeypatch):
    registry, labels = install_fakes(monkeypatch, [entity()], [])
    hass, entry = hass_and_entry()
    state, store = {"entries": []}, FakeStore()
    assert asyncio.run(values._async_seed(hass, entry, state, store)) is True
    created, = labels.created
    assert (created.name, created.icon, created.color) == ("loxone", "mdi:alpha-l-box", "green")
    assert registry.entries[0].labels == {"loxone"}
    assert [e["key"] for e in state["entries"]] == [STATUS_ID]
    assert store.saved == {"entries": state["entries"], "seeded": True}


def test_an_existing_label_is_reused_and_never_recreated(monkeypatch):
    existing = NS(label_id="abc123", name="Loxone", icon="mdi:alpha-l-box", color="green")
    registry, labels = install_fakes(monkeypatch, [entity()], [existing])
    hass, entry = hass_and_entry()
    state, store = {"entries": []}, FakeStore()
    assert asyncio.run(values._async_seed(hass, entry, state, store)) is True
    assert labels.created == []
    assert registry.entries[0].labels == {"abc123"}


def test_other_labelled_entities_are_not_put_on_the_wish_list_silently(monkeypatch):
    other = entity("sensor.pool", "x-pool", "sensor", labels={"loxone"})
    registry, labels = install_fakes(monkeypatch, [entity(), other], [NS(label_id="loxone", name="loxone", icon=None, color=None)])
    hass, entry = hass_and_entry()
    hass.states.get.__self__["sensor.pool"] = NS(state="23.5", attributes={"friendly_name": "Pool"})
    state, store = {"entries": []}, FakeStore()
    asyncio.run(values._async_seed(hass, entry, state, store))
    assert [e["key"] for e in state["entries"]] == [STATUS_ID]
    assert store.saved["entries"] == state["entries"]


def test_without_the_status_entity_nothing_is_changed(monkeypatch):
    registry, labels = install_fakes(monkeypatch, [], [])
    hass, entry = hass_and_entry()
    state, store = {"entries": []}, FakeStore()
    assert asyncio.run(values._async_seed(hass, entry, state, store)) is False
    assert labels.created == [] and store.saved is None and state["entries"] == []


@pytest.fixture
def setup(monkeypatch):
    attached = []
    monkeypatch.setattr(values, "_attach", lambda hass, entry, state: attached.append(list(state["entries"])))
    hass, entry = hass_and_entry()
    hass.data = {}
    return hass, entry, attached


def test_setup_seeds_a_fresh_installation_before_attaching_the_wish_list(monkeypatch, setup):
    hass, entry, attached = setup
    registry, labels = install_fakes(monkeypatch, [entity()], [])
    store = FakeStore()
    monkeypatch.setattr(values, "_store", lambda hass, entry_id: store)
    asyncio.run(values.async_setup_values(hass, entry, fresh=True))
    assert [e["key"] for e in attached[0]] == [STATUS_ID], "the sender must already know the value"
    assert store.saved["seeded"] is True


def test_setup_of_an_existing_installation_changes_nothing(monkeypatch, setup):
    hass, entry, attached = setup
    registry, labels = install_fakes(monkeypatch, [entity()], [])
    store = FakeStore({"entries": []})
    monkeypatch.setattr(values, "_store", lambda hass, entry_id: store)
    asyncio.run(values.async_setup_values(hass, entry, fresh=False))
    assert labels.created == [] and registry.entries[0].labels == set() and store.saved is None
    assert attached == [[]]


def test_a_failing_seed_never_breaks_the_setup(monkeypatch, setup):
    hass, entry, attached = setup
    registry, labels = install_fakes(monkeypatch, [entity()], [])
    registry.async_update_entity = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("registry busy"))
    store = FakeStore()
    monkeypatch.setattr(values, "_store", lambda hass, entry_id: store)
    asyncio.run(values.async_setup_values(hass, entry, fresh=True))
    assert attached == [[]] and store.saved is None
