"""Test offline catalog planning and fail-closed coverage reporting."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "scripts" / "create_device_test_room.py"
SPEC = importlib.util.spec_from_file_location("device_test_room", PATH)
planner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(planner)


def catalog():
    return {
        "air-white": {"name": "Air white", "creationType": "Air", "devType": 22},
        "air-black": {"name": "Air black", "creationType": "Air", "devType": 22},
        "tree": {"name": "Tree", "creationType": "Tree", "devType": 32771},
        "unknown1": {"name": "Unknown1", "creationType": "Air", "devType": None},
        "unknown2": {"name": "Unknown2", "creationType": "Air", "devType": None},
        "accessory": {"name": "Bracket", "creationType": ""},
        "100114": {"creationType": "Extension"},
        "100218": {"creationType": "Extension"},
    }


def template():
    room = {"name": "Old room", "nameId": 123, "type": 2, "allowEdit": True,
            "selection": [{"cat": "customDevices", "type": 11, "products": []},
                          {"cat": "extensions", "type": 12, "products": []},
                          {"cat": "lighting", "type": 0, "products": [{"decision": "old"}]}]}
    central = copy.deepcopy(room)
    central.update(name="Central", type=4, allowEdit=False)
    return {"formatVersion": 1, "settings": [{"type": 12, "data": "miniserver"}],
            "decision": [{"id": "old"}], "rooms": [central, room]}


def test_all_variants_and_unknowns_are_retained():
    assert len(planner.catalog_products(catalog())) == 5
    unique = planner.catalog_products(catalog(), True)
    assert len(unique) == 4
    assert sum(p["dev_type"] is None for p in unique) == 2


def test_other_catalog_category_included_only_with_documented_transport():
    entries = catalog()
    entries["power"] = {"name": "Power Supply and Backup", "creationType": "PowerSupply", "devType": 32801}
    entries["collision"] = {"name": "Unrelated extension", "creationType": "Extension", "devType": 22}
    assert len(planner.catalog_products(entries)) == 5
    products = planner.catalog_products(entries, documented={("Tree", 32801), ("Air", 22)})
    assert len(products) == 6
    assert next(p for p in products if p["article"] == "power")["transport"] == "Tree"


def test_one_test_room_and_no_automatic_extra_products():
    original = template()
    snapshot = copy.deepcopy(original)
    products = planner.catalog_products(catalog())
    plan = planner.make_plan(original, products, "Test room", catalog())
    assert original == snapshot
    assert len(plan["rooms"]) == 2
    room = plan["rooms"][1]
    assert room["name"] == "Test room" and room["nameId"] == 0
    assert plan["decision"] == []
    selections = {s["cat"]: s for s in room["selection"]}
    assert len(selections["customDevices"]["products"]) == 5
    assert all(p["count"] == 1 for p in selections["customDevices"]["products"])
    assert all(s["customized"] for r in plan["rooms"] for s in r["selection"])
    assert selections["lighting"]["products"] == []


def test_generate_never_overwrites_output(tmp_path):
    data = tmp_path / "Config"
    (data / "ProjectPlanning").mkdir(parents=True)
    for name, value in (("pricelist.json", catalog()), ("Default.LxPlan", template())):
        (data / "ProjectPlanning" / name).write_text(json.dumps(value), encoding="utf-8")
    output = tmp_path / "test-room"
    report = planner.generate(data, output, "Test")
    assert report["all_config_devices_verified"] is False
    assert report["config_conversion_verified"] is False
    assert report["documented_models_missing_from_catalog"] is None
    before = (output / "Air-Tree-Test.LxPlan").read_bytes()
    with pytest.raises(FileExistsError):
        planner.generate(data, output, "Replacement")
    assert before == (output / "Air-Tree-Test.LxPlan").read_bytes()


def test_verification_requires_room_and_real_terminals(tmp_path):
    manifest = tmp_path / "catalog.json"
    manifest.write_text(json.dumps({"room": "Test", "products": [{"transport": "Air", "dev_type": 22}],
                                    "unresolved_articles": []}), encoding="utf-8")
    project = tmp_path / "result.Loxone"
    project.write_text('<Root><C Type="Place" U="room" Title="Test"/>'
                       '<C Type="LoxAIRDevice" AirType="22"><IoData Pr="room"/>'
                       '</C></Root>', encoding="utf-8")
    assert planner.verify_project(project, manifest)["catalog_coverage_verified"] is False
    project.write_text(project.read_text().replace('</C>', '<C Type="LoxAIRsensor"><Co K="Q"/>'
                                                   '</C></C>'), encoding="utf-8")
    before = project.read_bytes()
    assert planner.verify_project(project, manifest)["catalog_coverage_verified"] is True
    assert project.read_bytes() == before
    project.write_text(project.read_text().replace('Pr="room"', 'Pr="elsewhere"'), encoding="utf-8")
    assert planner.verify_project(project, manifest)["catalog_coverage_verified"] is False


def test_missing_documented_types_are_visible(tmp_path):
    doc = tmp_path / "devices.xml"
    doc.write_text('<TechDoc><Device ControlType="171" SubType="22"/>'
                   '<Device ControlType="181" SubType="32771"/>'
                   '<Device ControlType="181" SubType="32799"/></TechDoc>', encoding="utf-8")
    assert planner.documented_models(doc) == {("Air", 22), ("Tree", 32771), ("Tree", 32799)}


def test_unknown_articles_prevent_claiming_full_coverage(tmp_path):
    manifest = tmp_path / "catalog.json"
    manifest.write_text(json.dumps({"room": "Test", "products": [], "unresolved_articles": ["unknown"]}))
    project = tmp_path / "result.Loxone"
    project.write_text('<Root><C Type="Place" U="room" Title="Test"/></Root>')
    assert planner.verify_project(project, manifest)["catalog_coverage_verified"] is False
