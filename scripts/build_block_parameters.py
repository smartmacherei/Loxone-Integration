"""Build custom_components/loxone/block_parameters.json from Loxone Config's TechDoc.

Loxone Config ships its function block documentation as ``tdc_DEV.LxRes``
(LoxCC container). Each block lists its parameter connectors with name, range,
step, unit and default. HA has no Config installation, so this table is shipped
with the integration. Only facts and short labels are kept, no descriptions.

Usage:
    python scripts/build_block_parameters.py "C:/Program Files (x86)/Loxone/LoxoneConfig" 17.2.10.21
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "loxone"
spec = importlib.util.spec_from_file_location("build_topology", ROOT / "topology.py")
topology = importlib.util.module_from_spec(spec)
spec.loader.exec_module(topology)


def _number(value):
    if value is None:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def build(techdoc_xml: bytes) -> dict:
    root = ET.fromstring(techdoc_xml)
    templates = {io.get("TemplateId"): io for group in root.findall("Templates")
                 for io in group.iter("IO") if io.get("TemplateId")}
    blocks = {}
    for block in root.iter("FunctionBlock"):
        block_type = block.get("LxType")
        if not block_type:
            continue
        params = []
        for group in block.findall("IOGroup"):
            if group.get("Type") != "Parameter":
                continue
            for io in group.findall("IO"):
                if not io.get("Name") and io.get("TemplateId") in templates:
                    io = templates[io.get("TemplateId")]
                if not io.get("Name"):
                    continue
                entry = {"key": io.get("Name"), "label": io.get("ShortDescription") or io.get("Name"),
                         "short": io.get("ShortName") or ""}
                for attr in ("Min", "Max", "Step", "Default"):
                    number = _number(io.get(attr))
                    if number is not None:
                        entry[attr.lower()] = number
                if io.get("Unit"):
                    entry["unit"] = io.get("Unit")
                params.append(entry)
        if params:
            blocks[block_type] = {"name": block.get("Name"), "parameters": params}
    return blocks


def main(config_dir: str, config_version: str) -> None:
    raw = (Path(config_dir) / "tdc_DEV.LxRes").read_bytes()
    blocks = build(topology.decode_loxcc(raw))
    out = {"source": "Loxone Config TechDoc tdc_DEV.LxRes", "config_version": config_version,
           "blocks": dict(sorted(blocks.items()))}
    (ROOT / "block_parameters.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    print(f"{len(blocks)} blocks, {sum(len(b['parameters']) for b in blocks.values())} parameters")


if __name__ == "__main__":
    main(*sys.argv[1:3])
