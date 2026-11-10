"""Function block parameters from the Miniserver program (read-only, HTTP only).

Which connectors of a block are parameters comes from Loxone Config's TechDoc,
shipped as ``block_parameters.json`` (scripts/build_block_parameters.py). The
value is the connector's ``Def`` attribute in the program; Config omits ``Def``
when the value is 0. A parameter the user wired to another block has no fixed
value and is left out; one wired by this integration (param_wiring) is kept
with ``ha_wired``, its value then lives in HA.

These values never use UDP, the 30-second polling or the signal limit: the
program is fetched once at setup and then once a day.
"""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re
import uuid
import xml.etree.ElementTree as ET

REFRESH_HOURS = 24


def ids(doc_id: str, connector: str) -> dict[str, str]:
    """Deterministic UUIDs of what param_wiring adds for one parameter connector."""
    connector = connector.lower()

    def uid(label):
        value = uuid.uuid5(uuid.NAMESPACE_URL, f"{doc_id}/smartmacherei/param/{connector}/{label}").hex
        return f"{value[:8]}-{value[8:12]}-{value[12:16]}-{doc_id[-16:]}"
    tail = uuid.uuid5(uuid.NAMESPACE_URL, doc_id + "/param/" + connector).hex[-12:]
    result = {"memory": uid("memory"), "value_ref": uid("value_ref"), "set_ref": uid("set_ref")}
    for n, k in enumerate(("Input", "Trigger", "Reset", "Remanence", "AQ")):
        result["memory_" + k] = uid("memory/" + k)[:19] + f"{n:02x}ff" + tail
    for ref in ("value_ref", "set_ref"):
        for n, k in enumerate(("AI", "I", "AQ", "Q")):
            result[f"{ref}_{k}"] = uid(f"{ref}/{k}")[:19] + f"{n:02x}ff" + tail
    return result


def document_id(root) -> str:
    documents = [el for el in root.iter("C") if el.get("Type") == "Document"]
    if len(documents) != 1:
        raise ValueError("Expected one Document")
    return documents[0].get("U", "")


def wired_by_us(doc_id: str, connector) -> bool:
    """The parameter connector is fed by exactly the integration's Analog Memory."""
    inputs = connector.findall("In")
    return bool(len(inputs) == 1 and connector.get("U")
                and inputs[0].get("Input", "").lower() == ids(doc_id, connector.get("U"))["memory_AQ"].lower())


@lru_cache(maxsize=1)
def load_table() -> dict:
    path = Path(__file__).with_name("block_parameters.json")
    return json.loads(path.read_text(encoding="utf-8"))["blocks"]


def _matcher(key: str):
    """'Input%d' -> regex for 'Input1', 'Input2' ...; plain keys match exactly."""
    if "%d" in key:
        return re.compile(re.escape(key).replace("%d", r"\d+") + r"\Z")
    return None


def _value(raw):
    if raw is None:
        return 0.0
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def enumerate_parameters(program_xml: bytes, table: dict | None = None) -> list[dict]:
    """One entry per unwired, numeric parameter of every known block."""
    table = load_table() if table is None else table
    try:
        root = ET.fromstring(program_xml)
    except ET.ParseError:
        return []
    documents = [el for el in root.iter("C") if el.get("Type") == "Document"]
    doc_id = documents[0].get("U", "") if len(documents) == 1 else None
    out = []
    for block in root.iter("C"):
        spec = table.get(block.get("Type", ""))
        block_id = block.get("U")
        if not spec or not block_id:
            continue
        iodata = block.find("IoData")
        connectors = block.findall("Co")
        for param in spec["parameters"]:
            pattern = _matcher(param["key"])
            for co in connectors:
                key = co.get("K", "")
                if not (pattern.match(key) if pattern else key == param["key"]):
                    continue
                if not co.get("U"):
                    continue
                # Wired by the user: the value comes from another block. Wired by this
                # integration: HA holds the value (param_wiring), the program keeps Def.
                ha_wired = doc_id is not None and wired_by_us(doc_id, co)
                if co.find("In") is not None and not ha_wired:
                    continue
                value = _value(co.get("Def"))
                if value is None:
                    continue
                label = param["label"]
                if pattern:
                    label = label + " " + re.sub(r"^\D*", "", key)
                out.append({
                    # The connector UUID: unique, stable, and registry cleanup
                    # removes the entity once the block is deleted in Config.
                    "unique_id": co.get("U"),
                    "block": block_id,
                    "block_type": block.get("Type"),
                    "block_title": block.get("Title") or spec["name"],
                    "visu": iodata is not None and iodata.get("Visu") == "true",
                    "room": iodata.get("Pr", "") if iodata is not None else "",
                    "key": key,
                    "label": label,
                    "unit": param.get("unit"),
                    "limits": {k: param[k] for k in ("min", "max", "step", "default") if k in param},
                    "value": value,
                    "ha_wired": ha_wired,
                })
    return out


def without_structure_ids(params: list[dict], loxconfig: dict) -> list[dict]:
    """Drop parameters whose connector UUID LoxAPP3 already uses (e.g. as a state).

    Such a UUID may already be the unique ID of another entity; it is also
    live over the WebSocket there, so nothing is lost.
    """
    used = set(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{16}",
                          json.dumps(loxconfig).lower()))
    return [p for p in params if p["unique_id"].lower() not in used]


def parameter_values(program_xml: bytes, table: dict | None = None) -> dict[str, float]:
    """Daily refresh: program values of the parameters HA does not hold itself."""
    return {p["unique_id"]: p["value"] for p in enumerate_parameters(program_xml, table)
            if not p["ha_wired"]}
