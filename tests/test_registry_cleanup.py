"""Deletion requires project absence, not an unavailable HA state."""
import importlib.util
import json
import asyncio
from pathlib import Path
import sys
import types

import pytest

spec = importlib.util.spec_from_file_location("registry_cleanup", Path(__file__).resolve().parents[1] / "custom_components/loxone/registry_cleanup.py")
cleanup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup)
U = "11111111-0000-0000-ffff000000000001"
D = "11111111-0000-0000-ffff000000000002"
ENTRY = "our-entry"


def entity(**changes):
    return {"entity_id": "sensor.old", "platform": "loxone", "config_entry_id": ENTRY,
            "unique_id": U, "device_id": "device", **changes}


def device(**changes):
    return {"id": "device", "identifiers": [("loxone", D)], "config_entries": [ENTRY], **changes}


def test_deleted_entities_and_devices_are_removed():
    assert cleanup.plan_cleanup(ENTRY, [device()], [entity()], set(), {"live"}) == (["sensor.old"], ["device"])


@pytest.mark.parametrize("known,active", [({U, D}, set()), ({U}, set()), (set(), {"sensor.old"})])
def test_offline_disabled_or_still_loaded_entities_keep_device(known, active):
    assert cleanup.plan_cleanup(ENTRY, [device()], [entity(disabled_by="user")], active, known) == ([], [])


def test_removed_terminal_on_present_device():
    assert cleanup.plan_cleanup(ENTRY, [device()], [entity()], set(), {D}) == (["sensor.old"], [])


@pytest.mark.parametrize("foreign", [entity(config_entry_id="other-entry"), entity(platform="other")])
def test_foreign_entities_are_preserved(foreign):
    assert cleanup.plan_cleanup(ENTRY, [device()], [foreign], set(), set()) == ([], [])


@pytest.mark.parametrize("protected", [device(config_entries=[ENTRY, "other"]), device(identifiers=[("other", D)]), device(identifiers=[("loxone", "serial")])])
def test_shared_foreign_and_miniserver_devices_are_preserved(protected):
    assert cleanup.plan_cleanup(ENTRY, [protected], [], set(), set()) == ([], [])


def test_unknown_unique_ids_and_parent_devices_are_preserved():
    assert cleanup.plan_cleanup(ENTRY, [device()], [entity(unique_id="serial-udp_status")], set(), set()) == ([], [])
    assert cleanup.plan_cleanup(ENTRY, [device(), device(id="child", via_device_id="device", identifiers=[])], [], set(), set()) == ([], [])


def test_subcontrol_uses_parent_uuid():
    assert cleanup.plan_cleanup(ENTRY, [device()], [entity(unique_id=U.upper()+"/AI1")], set(), {U}) == ([], [])


def test_inventory_requires_full_project_and_preserves_nested_states():
    xml = b'<Loxone><C Type="Document"><C Type="Program"/><C Type="LoxLIVE"/></C></Loxone>'
    app = {"controls": {"c": {"subControls": {"child": {"states": {"value": U}}}}}, "msInfo": {"serialNr": "serial"}}
    assert U in cleanup.inventory(xml, app)
    with pytest.raises(ValueError):
        cleanup.inventory(xml, {"controls": {}})
    with pytest.raises(ValueError):
        cleanup.inventory(b'<Loxone/>', app)


def test_backup_is_complete_and_failure_propagates(tmp_path):
    snapshot = {"entities": [entity()], "devices": [device(config_entries={ENTRY})]}
    path = Path(cleanup.write_backup(tmp_path, snapshot))
    saved = json.loads(path.read_text())
    assert saved["entities"] == snapshot["entities"]
    assert saved["devices"][0]["config_entries"] == [ENTRY]
    with pytest.raises(OSError):
        cleanup.write_backup(path, snapshot)


@pytest.mark.parametrize("modern", [False, True])
@pytest.mark.parametrize("condition", ["success", "backup_failure", "changed_program", "changed_registry", "invalid_archive"])
def test_async_cleanup_guards_and_removal_order(monkeypatch, tmp_path, condition, modern):
    """Exercise the real lifecycle, including failures across executor awaits."""
    import io
    import zipfile
    from types import SimpleNamespace as NS
    xml = b'<Loxone><C Type="Document"><C Type="Program"/><C Type="LoxLIVE"/></C></Loxone>'
    app = {"controls": {}, "msInfo": {"serialNr": "serial"}}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("LoxAPP3.json", json.dumps(app))
    raw = buf.getvalue()
    calls = []
    class Client:
        count = 0
        def __init__(self, *args): pass
        def current(self):
            self.count += 1
            return "project", b'changed' if self.count == 2 and condition == "changed_program" else raw
    devices = NS(devices={"device": NS(**device())})
    entities = NS(entities={"sensor.old": NS(**entity())})
    devices.async_get = devices.devices.get
    entities.async_get = entities.entities.get
    devices.async_remove_device = lambda key: calls.append(("device", key))
    entities.async_remove = lambda key: calls.append(("entity", key))
    if modern:
        record = devices.devices["device"]
        record.config_entry_id = ENTRY
        del record.config_entries
        class DeviceCollection:
            def __iter__(self):
                return iter([record])
            def __getattr__(self, name):
                raise AssertionError("Deprecated mapping access: " + name)
        devices.devices = DeviceCollection()

    er, dr = NS(async_get=lambda h: entities), NS(async_get=lambda h: devices)
    def unpack(data):
        if condition == "invalid_archive": raise ValueError("checksum")
        return "project", xml
    for name, mod in {
        "attr": NS(asdict=lambda obj, **kw: vars(obj).copy()),
        "homeassistant.helpers": NS(entity_registry=er, device_registry=dr),
        "cleanup_test": types.ModuleType("cleanup_test"),
        "cleanup_test.registry_compat": NS(registry_entries=lambda items: items.values() if isinstance(items, dict) else iter(items)),
        "cleanup_test.udp_install": NS(ProgramClient=Client),
        "cleanup_test.udp_program": NS(unpack=unpack, digest=lambda value: "hash"),
    }.items():
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setattr(cleanup, "__package__", "cleanup_test")
    monkeypatch.setattr(cleanup, "__spec__", importlib.util.spec_from_loader("cleanup_test.registry_cleanup", loader=None))
    active = set()
    original = cleanup.write_backup
    def backup(*args):
        calls.append(("backup",))
        if condition == "backup_failure": raise OSError("disk full")
        if condition == "changed_registry": active.add("sensor.old")
        return original(*args)
    monkeypatch.setattr(cleanup, "write_backup", backup)
    async def executor(fn, *args): return fn(*args)
    hass = NS(async_add_executor_job=executor, config=NS(path=lambda *parts: str(tmp_path.joinpath(*parts))),
              states=NS(async_entity_ids=lambda: active))
    entry = NS(entry_id=ENTRY, options=dict(host="host", port=80, username="user", password="private"))
    asyncio.run(cleanup.async_cleanup_registry(hass, entry, xml, app))
    if condition == "success":
        assert calls == [("backup",), ("entity", "sensor.old"), ("device", "device")]
    else:
        assert not any(c[0] in {"entity", "device"} for c in calls)


def test_modern_device_ownership_and_child_protection():
    modern = device(config_entry_id=ENTRY)
    del modern["config_entries"]
    assert cleanup.plan_cleanup(ENTRY, [modern], [], set(), set()) == ([], ["device"])
    child = device(id="child", parent_device_id="device", identifiers=[])
    assert cleanup.plan_cleanup(ENTRY, [modern, child], [], set(), set()) == ([], [])
    modern["config_entry_id"] = "foreign"
    assert cleanup.plan_cleanup(ENTRY, [modern], [], set(), set()) == ([], [])
