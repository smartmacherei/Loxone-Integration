"""Room UUID mappings must not take ownership of manual HA assignments."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components/loxone"


def mapping_module():
    spec = importlib.util.spec_from_file_location("area_mapping", ROOT / "area_mapping.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def entity(entity_id="light.demo", room="r1", **kwargs):
    return dict(entity_id=entity_id, config_entry_id="entry", platform="loxone",
                unique_id=room, device_id="device", area_id=None, **kwargs)


def plan(entities=None, device_area=None, mapping=None, owned=None, new=True):
    return mapping_module().plan_mapping(
        "entry", entities or [entity()],
        [{"id": "device", "area_id": device_area, "config_entries": ["entry"]}],
        {"r1": "r1", "r2": "r2"}, mapping or {"r1": "office"},
        {"office", "kitchen"}, owned or {}, {"device"} if new else set(),
    )


def test_new_device_uses_selected_existing_area():
    devices, entities, owned = plan()
    assert devices == {"device": "office"}
    assert entities == {}
    assert owned["devices"] == {"device": "office"}


def test_preexisting_manual_device_area_is_not_overwritten():
    devices, entities, owned = plan(device_area="kitchen", new=False)
    assert devices == entities == {}
    assert owned["devices"] == {}


def test_owned_mapping_can_change_without_touching_manual_entity_area():
    devices, entities, owned = plan(
        [dict(entity(), area_id="personal")], device_area="office",
        mapping={"r1": "kitchen"}, owned={"devices": {"device": "office"}}, new=False,
    )
    assert devices == {"device": "kitchen"}
    assert entities == {}


def test_multiroom_device_maps_entities_individually():
    devices, entities, owned = plan(
        [entity(), entity("sensor.other", "r2")], mapping={"r1": "office", "r2": "kitchen"},
    )
    assert devices == {}
    assert entities == {"light.demo": "office", "sensor.other": "kitchen"}


def test_user_cleared_owned_device_stays_cleared_after_reload():
    devices, entities, owned = plan(device_area=None, owned={"devices": {"device": "office"}}, new=False)
    assert devices == entities == {}
    devices, entities, _ = plan(device_area=None, owned=owned, new=False)
    assert devices == entities == {}


def test_deleted_target_area_is_not_recreated():
    devices, entities, _ = plan(mapping={"r1": "deleted"})
    assert devices == entities == {}


def test_entity_rename_preserves_stable_ownership_and_manual_override():
    row = dict(entity(), id="stable-id", entity_id="scene.renamed", device_id=None, area_id="office")
    _, edits, owned = plan([row], mapping={"r1": "kitchen"}, owned={"entities": {"stable-id": "office"}})
    assert edits == {"scene.renamed": "kitchen"}
    assert owned["entities"] == {"stable-id": "kitchen"}
    row["area_id"] = None
    _, edits, owned = plan([row], mapping={"r1": "kitchen"}, owned=owned)
    assert edits == {}
    row["entity_id"] = "scene.renamed_again"
    _, edits, _ = plan([row], mapping={"r1": "kitchen"}, owned=owned)
    assert edits == {}


def test_room_lookup_uses_ids_for_controls_states_and_subcontrols():
    rooms = mapping_module().room_index({"controls": {
        "controller": {"uuidAction": "controller", "room": "r1", "states": {"state": "state-id"},
                       "subControls": {"controller/child": {"uuidAction": "controller/child"}}},
    }})
    assert rooms == {"controller": "r1", "state-id": "r1", "controller/child": "r1"}
