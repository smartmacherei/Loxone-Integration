"""Weg 3: HA values as a virtual UDP input, only in the gateway program."""
import xml.etree.ElementTree as ET

import pytest

from test_udp_install import XML, module
from test_gateway_udp import CL, GATEWAY_OBJ, GW, document, prog

values = module("ha_values_program")

CAPTION = '<C Type="VirtualInCaption" V="178" U="18f7cbc0-0000-0004-ffffa13734b4be2f" Title="Virtuelle Eingaenge"/>'
SINGLE = XML.replace(b'  <C Type="LoggerOutCaption"', CAPTION.encode() + b'\n  <C Type="LoggerOutCaption"')
ENTRIES = [{"key": "sensor.pool", "title": "Pool", "digital": False},
           {"key": "binary_sensor.tor", "title": "Tor", "digital": True}]


def live(uuid, title, extra=""):
    return (f'<C Type="LoxLIVE" V="174" U="{uuid}" Title="{title}">'
            f'<C Type="VirtualInCaption" V="174" U="{uuid[:-1]}4" Title="Virtuelle Eingaenge"/>{extra}</C>')


FULL = document(live(GW, "Gateway", GATEWAY_OBJ), live(CL, "Client"), prog(GW, "Gateway"), prog(CL, "Client"))
PART_GW = document(live(GW, "Gateway", GATEWAY_OBJ), prog(GW, "Gateway"))
CLIENT_OBJ = f'<C Type="GatewayClient" V="174" U="{CL[:-1]}7" Title="Client" ProgType="1" GwAddr="192.168.9.10"/>'
PART_CL = document(live(CL, "Client", CLIENT_OBJ), prog(CL, "Client"))


def managed(xml):
    root = ET.fromstring(xml)
    inputs = [el for el in root.iter("C") if el.get("Type") == "VirtualUdpIn" and el.get("IName") == values.INAME]
    assert len(inputs) <= 1
    if not inputs:
        return None
    block = inputs[0]
    return block, [(c.get("IName"), c.get("U"), c.get("Check"), c.get("Title"), c.find("Display").get("Unit"))
                   for c in block.findall("C")]


def test_input_and_commands_are_created_under_the_caption():
    patched, report = values.patch_ha_values(SINGLE, ENTRIES)
    assert report == {"ha_values": 2, "ha_values_changed": True}
    block, commands = managed(patched)
    assert block.get("Port") == "55556" and block.get("Title") == values.TITLE and block.get("V") == "178"
    parent = next(el for el in ET.fromstring(patched).iter("C") if el.get("Type") == "VirtualInCaption")
    assert block.get("U") in {el.get("U") for el in parent}
    assert [(c[0], c[2], c[3], c[4]) for c in commands] == [
        ("HAV1", "binary_sensor.tor=\\v", "Tor", "<v>"), ("HAV2", "sensor.pool=\\v", "Pool", "<v.2>")]
    doc = next(el for el in ET.fromstring(patched).iter("C") if el.get("Type") == "Document")
    assert doc.get("NumO") == str(len(list(ET.fromstring(patched).iter("C"))))
    # Deterministic identities: the same key yields the same UUIDs on every run.
    again, _ = values.patch_ha_values(SINGLE, list(reversed(ENTRIES)))
    assert managed(again)[1] == commands


def test_unchanged_wish_list_leaves_program_untouched():
    patched, _ = values.patch_ha_values(SINGLE, ENTRIES)
    same, report = values.patch_ha_values(patched, ENTRIES)
    assert same == patched and report == {"ha_values": 2, "ha_values_changed": False}
    assert values.patch_ha_values(SINGLE, []) == (SINGLE, {"ha_values": 0, "ha_values_changed": False})


def test_changed_wish_list_rebuilds_but_keeps_user_titles():
    patched, _ = values.patch_ha_values(SINGLE, ENTRIES)
    renamed = patched.replace(b'Title="Pool"', b'Title="Pooltemperatur"')
    rebuilt, report = values.patch_ha_values(
        renamed, ENTRIES + [{"key": "climate.bad.temperature", "title": "Bad Soll", "digital": False}])
    assert report["ha_values_changed"] and report["ha_values"] == 3
    _, commands = managed(rebuilt)
    assert [(c[0], c[3]) for c in commands] == [("HAV1", "Tor"), ("HAV2", "Bad Soll"), ("HAV3", "Pooltemperatur")]
    removed, _ = values.patch_ha_values(rebuilt, [])
    assert managed(removed) is None and b"Pooltemperatur" not in removed


def test_foreign_port_or_short_name_blocks_the_change():
    foreign = SINGLE.replace(CAPTION.encode(), CAPTION.encode()[:-2] + (
        b'><C Type="VirtualUdpIn" IName="VUI1" V="178" U="18f7cbc0-0000-0005-ffffa13734b4be2f" '
        b'Title="Fremd" Port="55556"/></C>'))
    with pytest.raises(ValueError) as caught:
        values.patch_ha_values(foreign, ENTRIES)
    assert caught.value.udp_code == "HA_VALUES_PORT_IN_USE"
    clash = SINGLE.replace(b'Title="Button &amp; contact"', b'Title="Button" IName="HAV7"')
    with pytest.raises(ValueError, match="short name"):
        values.patch_ha_values(clash, ENTRIES)
    with pytest.raises(ValueError, match="key"):
        values.patch_ha_values(SINGLE, [{"key": "sensor.a b", "title": "x", "digital": False}])


def test_gateway_project_and_partial_agree_and_client_is_untouched():
    full, _ = values.patch_ha_values(FULL, ENTRIES)
    part_gw, _ = values.patch_ha_values(PART_GW, ENTRIES)
    assert managed(full)[1] == managed(part_gw)[1]
    captions = {el.get("U"): [c.get("Type") for c in el]
                for el in ET.fromstring(full).iter("C") if el.get("Type") == "VirtualInCaption"}
    assert captions == {GW[:-1] + "4": ["VirtualUdpIn"], CL[:-1] + "4": []}
    assert values.patch_ha_values(PART_CL, ENTRIES) == (PART_CL, {"ha_values": 0, "ha_values_changed": False})
