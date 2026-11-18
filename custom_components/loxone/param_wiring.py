"""Weg 3 on block parameters: wire an HA value through a remanent Analog Memory.

For a labelled parameter number, Weg 3 holds two analog commands on its
virtual UDP input: ``<key>=\\v`` (the value) and ``<key>.set=\\v`` (the trigger).
On the page of the block this module adds what Config itself writes:

    InputRef(value) -> AMemory.Input
    InputRef(set)   -> AMemory.Trigger      (HA sends set=1, set=0 after the value)
    AMemory.AQ      -> parameter connector of the block

The memory has remanence on, so after a Miniserver restart the parameter keeps
its last value even while HA is offline. Only single-Miniserver programs are
wired; a parameter the user wired is never touched. The parameter's own value
(``Def``) stays in the program and applies again once HA lets go of it.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from .block_parameters import document_id, ids, object_ids, wired_by_us
from .udp_program import _append, _span, stamp_document

TITLE = "Home Assistant - Parameter"
SET_SUFFIX = ".set"


def _input_ref(i, ref, title, command, x, y, version):
    el = ET.Element("C", Type="InputRef", V=version, U=i[ref], Title=title, Px=str(x), Py=str(y),
                    Px2=str(x + 2112), Py2=str(y + 192), Cl="0,0,0", Nio="4", Ref=command.get("U"),
                    WF="149504", Analog="true", LinkRefType="79")
    outputs = {co.get("K"): co.get("U") for co in command.findall("Co")}
    for k, source in (("AI", "AQ"), ("I", "Q")):
        ET.SubElement(ET.SubElement(el, "Co", K=k, Nc="1", U=i[f"{ref}_{k}"]), "In", Input=outputs[source])
    for k in ("AQ", "Q"):
        ET.SubElement(el, "Co", K=k, U=i[f"{ref}_{k}"])
    return el


def _memory(i, x, y, version):
    el = ET.Element("C", Type="AMemory", V=version, U=i["memory"], Title=TITLE, Px=str(x), Py=str(y),
                    Px2=str(x + 1344), Py2=str(y + 1080), Cl="141,255,112", Nio="5", WF="147456")
    for k, source in (("Input", i["value_ref_AQ"]), ("Trigger", i["set_ref_Q"])):
        ET.SubElement(ET.SubElement(el, "Co", K=k, Nc="1", U=i["memory_" + k]), "In", Input=source)
    ET.SubElement(el, "Co", K="Reset", U=i["memory_Reset"])
    ET.SubElement(el, "Co", K="Remanence", Inv="true", U=i["memory_Remanence"])  # remanence on
    ET.SubElement(el, "Co", K="AQ", U=i["memory_AQ"])
    return el


def _fed(el, k, source) -> bool:
    links = el.findall(f"Co[@K='{k}']/In")
    return len(links) == 1 and links[0].get("Input", "").lower() == source.lower()


def _intact(i, objects, value_cmd, set_cmd) -> bool:
    """Memory and both InputRefs exist and link to each other and to the current commands."""
    memory = objects.get(i["memory"].lower())
    if memory is None or not (_fed(memory, "Input", i["value_ref_AQ"]) and _fed(memory, "Trigger", i["set_ref_Q"])):
        return False
    for ref, command in (("value_ref", value_cmd), ("set_ref", set_cmd)):
        el = objects.get(i[ref].lower())
        outputs = {co.get("K"): co.get("U", "") for co in command.findall("Co")}
        if (el is None or el.get("Ref", "").lower() != command.get("U", "").lower()
                or not (_fed(el, "AI", outputs.get("AQ", "")) and _fed(el, "I", outputs.get("Q", "")))):
            return False
    return True


def _remove(text, i, present) -> str:
    for object_id in (i["memory"], i["value_ref"], i["set_ref"]):
        if object_id.lower() in present:
            start, end = _span(text, object_id)
            text = text[:start] + text[end:]
    return text


def _rewrite_connector(text: str, block_id: str, connector_id: str, source: str | None) -> str:
    """Replace one connector of a block: fed by ``source``, or unconnected for ``None``."""
    start, end = _span(text, block_id)
    match = re.search(r'<Co\b[^>]*\bU="' + re.escape(connector_id) + r'"[^>]*?(/?)>', text[start:end])
    if match is None:
        raise ValueError("Cannot locate parameter connector")
    co_start = start + match.start()
    co_end = start + match.end()
    if not match.group(1):  # an element with inputs: up to its closing tag
        co_end = text.index("</Co>", co_end) + len("</Co>")
    tag = re.sub(r'\s+Nc="[^"]*"', "", match.group()[:-(2 if match.group(1) else 1)]).rstrip()
    new = tag + (f' Nc="1">\n<In Input="{source}" />\n</Co>' if source else " />")
    return text[:co_start] + new + text[co_end:]


def patch_parameter_wiring(xml: bytes, entries) -> tuple[bytes, dict]:
    """Wire every entry with a ``target`` connector; unwire parameters no longer wanted.

    Runs after ``patch_ha_values``, so the value and set commands exist.
    """
    root = ET.fromstring(xml)
    doc_id = document_id(root)
    report = {"param_wired": 0, "param_skipped": []}
    objects = {el.get("U", "").lower(): el for el in root.iter("C")}
    parent = {c: p for p in root.iter() for c in p}
    connectors = {co.get("U", "").lower(): co for co in root.iter("Co") if co.get("U")}
    commands = {el.get("Check"): el for el in objects.values() if el.get("Type") == "VirtualUdpInCmd"}
    wanted = {e["target"].lower(): e for e in entries if e.get("target")}
    single = len([el for el in objects.values() if el.get("Type") == "Program"]) == 1
    text = xml.decode("utf-8")
    changed = False

    def page_of(el):
        while el in parent:
            el = parent[el]
            if el.get("Type") == "Page":
                return el
        return None

    candidates = {u for u, el in objects.items() if el.get("Type") in {"AMemory", "InputRef"}}
    for connector_id, connector in connectors.items():
        if connector_id in wanted and single:
            continue
        fed = wired_by_us(doc_id, connector)
        if not (fed or candidates):
            continue
        mine = object_ids(doc_id, connector_id)
        # Also the leftovers of a memory the user deleted in Config, found by our ids.
        if not fed and not {u.lower() for u in mine.values()} & candidates:
            continue
        if fed:
            text = _rewrite_connector(text, parent[connector].get("U"), connector.get("U"), None)
        text = _remove(text, mine, objects)
        changed = True

    if not single:
        report["param_skipped"] = sorted(wanted)  # Gateway/Client: not supported yet
        wanted = {}
    for connector_id, entry in sorted(wanted.items()):
        connector = connectors.get(connector_id)
        block = parent.get(connector) if connector is not None else None
        page = page_of(block) if block is not None else None
        value_cmd = commands.get(entry["key"] + "=\\v")
        set_cmd = commands.get(entry["key"] + SET_SUFFIX + "=\\v")
        if page is None or value_cmd is None or set_cmd is None:
            report["param_skipped"].append(connector_id)
            continue
        i = ids(doc_id, connector_id)
        ours = wired_by_us(doc_id, connector)
        if ours and _intact(i, objects, value_cmd, set_cmd):
            report["param_wired"] += 1
            continue
        if connector.findall("In") and not ours:
            report["param_skipped"].append(connector_id)  # the user's own wiring stays
            continue
        text = _remove(text, i, objects)  # leftovers of a partial deletion or a renamed entity
        version = block.get("V")
        x = max(0, int(float(block.get("Px", "0"))) - 6912)
        y = int(float(block.get("Py", "0")))
        fragment = "".join(ET.tostring(el, encoding="unicode") for el in (
            _input_ref(i, "value_ref", entry["title"], value_cmd, x, y, version),
            _input_ref(i, "set_ref", entry["title"] + " setzen", set_cmd, x, y + 384, version),
            _memory(i, x + 2880, y, version)))
        text = _append(text, page.get("U"), fragment)
        text = _rewrite_connector(text, block.get("U"), connector.get("U"), i["memory_AQ"])
        report["param_wired"] += 1
        changed = True
    if not changed:
        return xml, report
    return stamp_document(text, doc_id, root), report
