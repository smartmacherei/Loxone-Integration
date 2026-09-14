"""Weg 3: HA values as one virtual UDP input in the gateway program (HA-free).

The input and its commands live under the VirtualInCaption of the gateway
Miniserver (or of the only Miniserver). Clients reach them like any gateway
input; Loxone Config creates the Memory proxies itself once the user wires
them. Object identities are deterministic, so project and partial agree.
"""
import re
import uuid
import xml.etree.ElementTree as ET

from .udp_errors import coded_error
from .udp_program import _append, _span, stamp_document

PORT = 55556
TITLE = "HA Werte"
INAME = "HAV"
KEY = re.compile(r"[a-z0-9_]+\.[a-z0-9_]+(?:\.[a-z0-9_]+)?")


def _caption(root):
    """VirtualInCaption of the gateway (or only) Miniserver and its program version."""
    lives = [el for el in root.iter("C") if el.get("Type") == "LoxLIVE"]
    gateway = [live for live in lives if any(el.get("Type") == "Gateway" for el in live.iter("C"))]
    if gateway:
        scope = gateway[0]
    elif len(lives) > 1 or any(el.get("Type") == "GatewayClient" for el in root.iter("C")):
        return None, None  # a client partial program: nothing to place here
    else:
        scope = lives[0] if lives else root
    captions = [el for el in scope.iter("C") if el.get("Type") == "VirtualInCaption"]
    if len(captions) != 1:
        raise ValueError("Ambiguous or missing VirtualInCaption")
    programs = [el for el in root.iter("C") if el.get("Type") == "Program"
                and (scope is root or el.get("Ref") in (None, scope.get("U")))]
    if len(programs) != 1:
        raise ValueError("Ambiguous or missing Program")
    return captions[0], programs[0].get("V")


def patch_ha_values(xml: bytes, entries, port: int = PORT) -> tuple[bytes, dict]:
    """Replace the managed input only when its command set or port differs.

    ``entries``: ``[{"key", "title", "digital"}]``. Titles a user changed in
    Config survive a rebuild, since the same key keeps the same UUID.
    """
    root = ET.fromstring(xml)
    documents = [el for el in root.iter("C") if el.get("Type") == "Document"]
    if len(documents) != 1:
        raise ValueError("Expected one Document")
    doc_id = documents[0].get("U", "")
    report = {"ha_values": 0, "ha_values_changed": False}

    def uid(label):
        value = uuid.uuid5(uuid.NAMESPACE_URL, doc_id + "/smartmacherei/havalues/" + label).hex
        return f"{value[:8]}-{value[8:12]}-{value[12:16]}-{doc_id[-16:]}"

    wanted = sorted(entries, key=lambda e: e["key"])
    for entry in wanted:
        if not KEY.fullmatch(entry["key"]):
            raise ValueError("Unsupported HA value key")
    input_id = uid("input")
    objects = list(root.iter("C"))
    existing = next((el for el in objects if el.get("U") == input_id), None)
    if existing is not None and (existing.get("Type") != "VirtualUdpIn" or existing.get("IName") != INAME):
        raise ValueError("Managed object was modified; refusing to overwrite it")
    desired = {(uid(e["key"]), e["key"] + "=\\v") for e in wanted}
    report["ha_values"] = len(wanted)
    if existing is not None:
        current = {(c.get("U"), c.get("Check")) for c in existing.findall("C")}
        if existing.get("Port") == str(port) and current == desired:
            return xml, report
    elif not wanted:
        return xml, report
    caption, version = _caption(root)
    if caption is None:
        return xml, {"ha_values": 0, "ha_values_changed": False}
    owned = set(existing.iter()) if existing is not None else set()
    for el in objects:
        if el in owned:
            continue
        if el.get("Type") == "VirtualUdpIn" and el.get("Port") == str(port):
            raise coded_error("HA_VALUES_PORT_IN_USE", "UDP port for HA values is used by another virtual input", ValueError)
        if (el.get("IName") or "").startswith(INAME):
            raise ValueError("Foreign object uses the HA values short name")
    titles = {c.get("U"): c.get("Title") for c in existing.findall("C")} if existing is not None else {}
    block = ET.Element("C", Type="VirtualUdpIn", IName=INAME, V=version, U=input_id, Title=TITLE,
                       WF="16384", Address="", Port=str(port))
    for index, entry in enumerate(wanted, 1):
        key = entry["key"]
        cmd = ET.SubElement(block, "C", Type="VirtualUdpInCmd", IName=f"{INAME}{index}", V=version, U=uid(key),
                            Title=titles.get(uid(key)) or entry["title"], Cl="238,238,238", Nio="2", WF="16400",
                            Check=key + "=\\v", Signed="true", SourceValHigh="100", DestValHigh="100",
                            MinVal="-1000000000", MaxVal="1000000000", MinChange="0", MinTime="0")
        tail = uuid.uuid5(uuid.NAMESPACE_URL, doc_id + key).hex[-12:]
        ET.SubElement(cmd, "Co", K="AQ", U=uid(key + "/AQ")[:19] + "00ff" + tail)
        ET.SubElement(cmd, "Co", K="Q", U=uid(key + "/Q")[:19] + "01ff" + tail)
        ET.SubElement(cmd, "Display", Type="1", Unit="<v>" if entry.get("digital") else "<v.2>", StateOnly="true")
    text = xml.decode("utf-8")
    if existing is not None:
        start, end = _span(text, input_id)
        text = text[:start] + text[end:]
    if wanted:
        text = _append(text, caption.get("U"), ET.tostring(block, encoding="unicode"))
    report["ha_values_changed"] = True
    # Config writes one Memory proxy per page for a foreign terminal, all with
    # the terminal's UUID. Those duplicates pre-exist; only new ones are rejected.
    from collections import Counter
    counts = Counter(el.get("U").lower() for el in root.iter() if el.tag in {"C", "Co"} and el.get("U"))
    preexisting = {value for value, n in counts.items() if n > 1}
    return stamp_document(text, doc_id, preexisting), report
