"""Build an offline Air/Tree test room using the installed Config product catalog.

Loxone Config generates the real device XML from the resulting .LxPlan. This
script never invents terminal templates, pairs devices or contacts a Miniserver.
Run --verify-project after exporting the generated project from Config.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def discover_config(program_data=None):
    base = Path(program_data or os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Loxone"
    found = [p for p in base.glob("Loxone Config *")
             if (p / "ProjectPlanning" / "pricelist.json").is_file()]
    if not found:
        raise ValueError("No installed Config catalog found; provide --config-data")
    return max(found, key=lambda p: tuple(map(int, re.findall(r"\d+", p.name))))


def key(product):
    # devType is the device model ID; unknown IDs cannot safely be deduplicated.
    if product["dev_type"] is None:
        return (product["transport"], "unknown", product["article"])
    return (product["transport"], product["dev_type"], product["dev_subtype"], product["hw_type"])


def catalog_products(catalog, unique_types=False, documented=None):
    products, seen = [], set()
    for article, entry in sorted(catalog.items()):
        transport = entry.get("creationType")
        if transport not in {"Air", "Tree"}:
            # IDs in other categories have different namespaces. Only this
            # verified category/model pair identifies an additional Tree device.
            if not (transport == "PowerSupply" and entry.get("devType") == 32801
                    and ("Tree", 32801) in (documented or set())):
                continue
            transport = "Tree"
        product = {"article": article, "name": entry.get("name", article),
                   "transport": transport, "dev_type": entry.get("devType"),
                   "dev_subtype": entry.get("devSubType"), "hw_type": entry.get("hwType"),
                   "catalog_status": entry.get("status")}
        identity = key(product)
        if unique_types and identity in seen:
            continue
        products.append(product)
        seen.add(identity)
    if not products:
        raise ValueError("Catalog contains no Air/Tree articles")
    return products


def make_plan(template, products, room_name, catalog):
    if template.get("formatVersion") != 1:
        raise ValueError("Unsupported planning format")
    central = next((r for r in template["rooms"] if not r.get("allowEdit", True)), None)
    room = next((r for r in template["rooms"] if r.get("allowEdit", False)), None)
    if central is None or room is None:
        raise ValueError("Expected central and editable room templates")
    plan = copy.deepcopy(template)
    plan["decision"] = []
    plan["power"] = {"cat": "none", "products": []}
    central, room = copy.deepcopy(central), copy.deepcopy(room)
    for item in (central, room):
        item.update(space=0, windows=0, doors=0, heatCircuits=0, heatCircuitsAuto=False)
        for selection in item["selection"]:
            selection.update(customized=True, products=[])
    room.update(name=room_name, nameId=0, allowEdit=True)
    selection = next((s for s in room["selection"] if s["cat"] == "customDevices"), None)
    if selection is None:
        raise ValueError("Template has no customDevices category")
    selection["products"] = [{"artNr": p["article"], "count": 1} for p in products]
    # Support hardware lives centrally; all test articles are in the one test room.
    extensions = next((s for s in central["selection"] if s["cat"] == "extensions"), None)
    if extensions is None:
        raise ValueError("Template has no extensions category")
    for article in ("100114", "100218"):  # Air Base and Tree Extension, verified local catalog IDs.
        if catalog.get(article, {}).get("creationType") != "Extension":
            raise ValueError("Support extension is missing from the selected catalog")
        extensions["products"].append({"artNr": article, "count": 1})
    plan["rooms"] = [central, room]
    return plan


def decoder():
    path = ROOT / "custom_components" / "loxone" / "udp_program.py"
    spec = importlib.util.spec_from_file_location("loxone_offline_codec", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def documented_models(path):
    if path is None:
        return None
    raw = Path(path).read_bytes()
    xml = decoder().decode(raw) if raw[:4] == b"\xee\xcc\xbb\xaa" else raw
    root = ET.fromstring(xml)
    models = set()
    for device in root.iter("Device"):
        transport = {"171": "Air", "181": "Tree"}.get(device.get("ControlType"))
        subtype = device.get("SubType", "")
        if transport and subtype.isdecimal():
            models.add((transport, int(subtype)))
    return models


def coverage_details(path, missing, products):
    lines = ["# Unmatched device metadata", "",
             "These are unmatched model IDs, not confirmed missing devices. Different",
             "article generations may use other IDs. Config conversion remains unverified.", "",
             "Labels below come from the installed technical documentation; multiple",
             "labels may refer to one ID. A documented device is not proof of catalog availability.", "",
             "| Bus | Model ID | Documentation labels |", "| --- | --- | --- |"]
    labels = {}
    if path:
        raw = Path(path).read_bytes()
        root = ET.fromstring(decoder().decode(raw) if raw[:4] == b"\xee\xcc\xbb\xaa" else raw)
        for device in root.iter("Device"):
            bus = {"171": "Air", "181": "Tree"}.get(device.get("ControlType"))
            subtype = device.get("SubType", "")
            if not subtype.isdecimal() or (bus, int(subtype)) not in (missing or []):
                continue
            names = [e.get("Name", "").replace("$$B::", "").replace("$$", "")
                     for e in device.findall("./Documents/Document")]
            label = "; ".join(names) or device.get("ShortLink") or device.get("ShortDescription", "Unknown")
            labels.setdefault((bus, int(subtype)), set()).add(label)
        for (bus, model), names in sorted(labels.items()):
            label = "; ".join(sorted(names)).replace("|", "/").replace("\n", " ")
            lines.append(f"| {bus} | {model} | {label} |")
    else:
        lines.extend(["", "No technical documentation supplied; comparison unavailable."])
    lines.extend(["", "## Selected articles without generation model IDs", ""])
    lines.extend(f"- {p['article']}: {p['name']}" for p in products if p['dev_type'] is None)
    return "\n".join(lines) + "\n"


def generate(config_data, output, room_name, unique_types=False, techdoc=None):
    if not room_name.strip():
        raise ValueError("Room name must not be empty")
    planning = Path(config_data) / "ProjectPlanning"
    catalog = load_json(planning / "pricelist.json")
    docs = documented_models(techdoc)
    products = catalog_products(catalog, unique_types, docs)
    plan = make_plan(load_json(planning / "Default.LxPlan"), products, room_name, catalog)
    catalog_models = {(p["transport"], p["dev_type"]) for p in catalog_products(catalog, documented=docs)
                      if p["dev_type"] is not None}
    missing = sorted(docs - catalog_models) if docs is not None else None
    report = {
        "config_data": str(Path(config_data).resolve()), "room": room_name,
        "catalog_sha256": hashlib.sha256((planning / "pricelist.json").read_bytes()).hexdigest(),
        "mode": "unique_types" if unique_types else "all_articles",
        "article_counts": dict(Counter(p["transport"] for p in products)),
        "products": products,
        "unresolved_articles": [p["article"] for p in products if p["dev_type"] is None],
        "documented_models_missing_from_catalog": missing,
        "documented_model_ids_covered_by_catalog": not missing if docs is not None else None,
        "all_config_devices_verified": False,
        "config_conversion_verified": False,
        "note": "Missing model IDs mean unmatched metadata, not necessarily missing devices: article variants may use different IDs. Catalog coverage is not proof of complete Config coverage or live hardware behavior.",
    }
    output = Path(output)
    # Never overwrite a test plan that Config may have edited in memory or on disk.
    output.mkdir(parents=True, exist_ok=False)
    (output / "Air-Tree-Test.LxPlan").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "catalog.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "coverage-details.md").write_text(coverage_details(techdoc, missing, products), encoding="utf-8")
    with (output / "devices.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(products[0]), delimiter=";")
        writer.writeheader()
        writer.writerows(products)
    (output / "README.txt").write_text(
        "AIR / TREE TEST ROOM - OFFLINE PLAN\n\n"
        "DE: Air-Tree-Test.LxPlan in der Projektplanung von Loxone Config laden.\n"
        "Eine neue, separate Planung verwenden. Die eingeplanten Artikel kontrollieren\n"
        "und mit Config in ein Programm uebernehmen. Keine Auto-Konfiguration fuer\n"
        "Bedienbausteine starten: Hier sollen zunaechst nur die Geraete entstehen.\n"
        "Das Ergebnis separat als Air-Tree-Test.Loxone speichern und mit dem Skript\n"
        "--verify-project und --manifest catalog.json pruefen. Erst die Pruefung zeigt,\n"
        "welche Geraete Config tatsaechlich erzeugt hat und dem Testraum zuordnet.\n\n"
        "EN: Load Air-Tree-Test.LxPlan in Config project planning as a separate plan.\n"
        "Review the articles, transfer the plan to a program, skip optional automatic\n"
        "function-block configuration, and save it separately as Air-Tree-Test.Loxone.\n"
        "Run --verify-project with --manifest catalog.json to check actual coverage.\n\n"
        "All selected catalog articles are assigned to one test room; support extensions\n"
        "are central. Unknown model IDs and documented models absent from the planning\n"
        "catalog are listed in catalog.json. This is not a verified all-device template.\n"
        "No Miniserver was contacted. No serial numbers or live hardware were invented.\n"
        "Without hardware, this tests structure/discovery, not real radio/bus signals.\n"
        "Do not upload this test program to a customer installation.\n", encoding="utf-8")
    return report


def verify_project(project, manifest):
    expected = load_json(manifest)
    raw = Path(project).read_bytes()
    if raw[:4] == b"\xee\xcc\xbb\xaa":
        raw = decoder().decode(raw)
    # Parsing is read-only; no XML roundtrip can alter user code or attributes.
    root = ET.fromstring(raw)
    rooms = {e.get("U") for e in root.iter("C") if e.get("Type") == "Place" and e.get("Title") == expected["room"]}
    devices, counts = [], Counter()
    for device in root.iter("C"):
        transport = {"TreeDevice": "Tree", "LoxAIRDevice": "Air"}.get(device.get("Type"))
        if not transport:
            continue
        subtype = device.get("TreeType" if transport == "Tree" else "AirType", device.get("SubType", ""))
        model = int(subtype) if subtype.isdecimal() else None
        io = device.find("IoData")
        in_room = io is not None and io.get("Pr") in rooms
        terminals = [e for e in device.iter("C") if e is not device and (e.find("Co") is not None)]
        item = {"transport": transport, "dev_type": model, "name": device.get("Title"),
                "in_test_room": in_room, "terminals": len(terminals),
                "visualized_terminals": sum(1 for e in terminals if e.find("IoData") is not None
                                             and e.find("IoData").get("Visu") == "true")}
        devices.append(item)
        if in_room and terminals:
            counts[(transport, model)] += 1
    wanted = Counter((p["transport"], p["dev_type"]) for p in expected["products"] if p["dev_type"] is not None)
    missing = [{"transport": t, "dev_type": m, "missing_instances": count - counts[(t, m)]}
               for (t, m), count in sorted(wanted.items()) if counts[(t, m)] < count]
    return {"test_room_found": len(rooms) == 1, "devices": devices, "missing": missing,
            "unresolved_articles": expected["unresolved_articles"],
            "catalog_coverage_verified": len(rooms) == 1 and not missing and not expected["unresolved_articles"],
            "note": "Verification compares model counts and room assignment; it cannot prove live values or cosmetic variants."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-data", type=Path, help="Installed ProgramData/Loxone/Loxone Config VERSION folder")
    parser.add_argument("--output", type=Path, default=Path("dist/air-tree-test"))
    parser.add_argument("--room", default="HA Air Tree Test")
    parser.add_argument("--unique-types", action="store_true", help="One article per known functional model instead of all variants")
    parser.add_argument("--techdoc", type=Path, help="Optional matching tdd_ENG.LxRes to report models absent from the catalog")
    parser.add_argument("--verify-project", type=Path, help="Read-only verification of the .Loxone file exported by Config")
    parser.add_argument("--manifest", type=Path, help="catalog.json from the generated test plan")
    args = parser.parse_args()
    try:
        if args.verify_project:
            if not args.manifest:
                parser.error("--verify-project requires --manifest")
            report = verify_project(args.verify_project, args.manifest)
            print(json.dumps(report, ensure_ascii=True, indent=2))
            return 0 if report["catalog_coverage_verified"] else 2
        report = generate(args.config_data or discover_config(), args.output,
                          args.room, args.unique_types, args.techdoc)
        print(json.dumps({"output": str(args.output.resolve()), "articles": report["article_counts"],
                          "unresolved_articles": len(report["unresolved_articles"]),
                          "documented_models_missing_from_catalog": len(report["documented_models_missing_from_catalog"] or []),
                          "config_conversion_verified": False}, ensure_ascii=True, indent=2))
        return 0
    except (OSError, ValueError, ET.ParseError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
