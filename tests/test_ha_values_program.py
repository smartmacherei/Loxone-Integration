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
            f'<C Type="LoggerOutCaption" V="174" U="{uuid[:-1]}9"/>'
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


def test_analog_values_carry_the_analog_flag_and_missing_flag_triggers_a_rebuild():
    patched, _ = values.patch_ha_values(SINGLE, ENTRIES)
    block = managed(patched)[0]
    flags = {c.get("Title"): c.get("Analog") for c in block.findall("C")}
    assert flags == {"Tor": None, "Pool": "true"}  # digital command stays digital, number is analog
    stripped = patched.replace(b' Analog="true"', b'')
    rebuilt, report = values.patch_ha_values(stripped, ENTRIES)
    assert report["ha_values_changed"] and b'Analog="true"' in rebuilt


def test_input_recreated_by_config_with_new_uuids_is_adopted_not_duplicated():
    patched, _ = values.patch_ha_values(SINGLE, ENTRIES)
    block = managed(patched)[0]
    # Config re-created the input and its commands with fresh UUIDs, kept our title and
    # short names, and the user renamed one command.
    foreign = patched
    for el in [block] + block.findall("C") + [co for c in block.findall("C") for co in c.findall("Co")]:
        foreign = foreign.replace(el.get("U").encode(), el.get("U")[:8].encode() + b"-dead-beef-" + el.get("U")[-16:].encode(), 1)
    foreign = foreign.replace(b'Title="Pool"', b'Title="Pooltemperatur"')
    assert managed(foreign)[0].get("U") != block.get("U")
    rebuilt, report = values.patch_ha_values(foreign, ENTRIES)
    assert report["ha_values_changed"]
    new_block, commands = managed(rebuilt)
    assert new_block.get("U") == block.get("U")  # the input is back on our deterministic identity
    # The commands keep the UUIDs Config gave them, so pages wired to them stay valid.
    assert [c[3] for c in commands] == ["Tor", "Pooltemperatur"] and rebuilt.count(b'IName="HAV1"') == 1
    assert all("-dead-beef-" in c[1] for c in commands)
    assert values.patch_ha_values(rebuilt, ENTRIES)[1]["ha_values_changed"] is False  # and it stays quiet


def test_user_changes_on_existing_commands_survive_a_rebuild():
    patched, _ = values.patch_ha_values(SINGLE, ENTRIES)
    # The user switched the digital command to analog and changed scaling in Config.
    edited = patched.replace(b'Check="binary_sensor.tor=1" Signed="true" SourceValHigh="100"',
                             b'Check="binary_sensor.tor=\\v" Analog="true" Signed="true" SourceValHigh="10"')
    assert edited != patched
    rebuilt, report = values.patch_ha_values(edited, ENTRIES + [{"key": "sensor.neu", "title": "Neu", "digital": False}])
    assert report["ha_values_changed"]
    tor = next(c for c in managed(rebuilt)[0].findall("C") if c.get("Check") == "binary_sensor.tor=\\v")
    assert tor.get("Analog") == "true" and tor.get("SourceValHigh") == "10"


def test_input_and_commands_are_created_under_the_caption():
    patched, report = values.patch_ha_values(SINGLE, ENTRIES)
    assert report == {"ha_values": 2, "ha_values_changed": True}
    block, commands = managed(patched)
    assert block.get("Port") == "55556" and block.get("Title") == values.TITLE and block.get("V") == "178"
    parent = next(el for el in ET.fromstring(patched).iter("C") if el.get("Type") == "VirtualInCaption")
    assert block.get("U") in {el.get("U") for el in parent}
    assert [(c[0], c[2], c[3], c[4]) for c in commands] == [
        ("HAV1", "binary_sensor.tor=1", "Tor", "<v>"), ("HAV2", "sensor.pool=\\v", "Pool", "<v.2>")]
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
    # Existing commands keep short name, UUID and the user's title; the new one gets the next number.
    assert [(c[0], c[3]) for c in commands] == [("HAV1", "Tor"), ("HAV3", "Bad Soll"), ("HAV2", "Pooltemperatur")]
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


def test_prepare_places_the_input_in_project_and_gateway_partial_only():
    from test_gateway_udp import archive
    from test_udp_install import TARGET, program
    raw = archive(full=FULL, parts=(PART_GW, PART_CL))
    result, report = program.prepare(raw, TARGET, set(), gateway=True, ha_values=ENTRIES)
    assert report["ha_values"] == 2 and report["ha_values_changed"]
    members = program.program_members(result)
    project = program.unpack(result, gateway=True)[1]
    assert managed(project)[1] == managed(members["sps0.LoxCC"])[1]
    assert managed(members["sps1.LoxCC"]) is None
    unchanged, again = program.prepare(result, TARGET, set(), gateway=True, ha_values=ENTRIES)
    assert unchanged == result and again["ha_values_changed"] is False
    without, _ = program.prepare(raw, TARGET, set(), gateway=True)  # None: Weg 3 untouched
    assert managed(program.unpack(without, gateway=True)[1]) is None


def test_digital_values_get_exact_on_text_and_numbers_the_value_placeholder():
    patched, _ = values.patch_ha_values(SINGLE, ENTRIES)
    checks = {c[3]: c[2] for c in managed(patched)[1]}
    # Measured on a real Miniserver: a digital command with "=\\v" never matched "tor=1".
    assert checks == {"Tor": "binary_sensor.tor=1", "Pool": "sensor.pool=\\v"}


def test_stale_digital_value_placeholder_is_migrated_and_keeps_identity():
    patched, _ = values.patch_ha_values(SINGLE, ENTRIES)
    old = patched.replace(b'Check="binary_sensor.tor=1"', b'Check="binary_sensor.tor=\\v"')  # what 1.8.0 wrote
    assert old != patched
    rebuilt, report = values.patch_ha_values(old, ENTRIES)
    assert report["ha_values_changed"]
    before = {c[0]: c[1] for c in managed(old)[1]}
    after = {c[0]: (c[1], c[2], c[3]) for c in managed(rebuilt)[1]}
    assert after["HAV1"] == (before["HAV1"], "binary_sensor.tor=1", "Tor")  # same UUID, short name and title
    assert values.patch_ha_values(rebuilt, ENTRIES)[1]["ha_values_changed"] is False


def test_user_edited_recognition_text_is_kept_and_stays_quiet():
    patched, _ = values.patch_ha_values(SINGLE, ENTRIES)
    edited = patched.replace(b'Check="binary_sensor.tor=1"', b'Check="binary_sensor.tor=ein"')
    assert edited != patched
    same, report = values.patch_ha_values(edited, ENTRIES)
    assert same == edited and report["ha_values_changed"] is False
    rebuilt, _ = values.patch_ha_values(edited, ENTRIES + [{"key": "sensor.neu", "title": "Neu", "digital": False}])
    assert "binary_sensor.tor=ein" in [c[2] for c in managed(rebuilt)[1]]


def test_default_attributes_config_strips_on_save_do_not_cause_a_rebuild():
    patched, _ = values.patch_ha_values(SINGLE, ENTRIES)
    # Loxone Config drops attributes that hold their default when it saves the project.
    saved = patched.replace(b' MinChange="0"', b'').replace(b' MinTime="0"', b'')
    assert saved != patched
    assert values.patch_ha_values(saved, ENTRIES) == (saved, {"ha_values": 2, "ha_values_changed": False})


def with_command(xml, check, title, iname, u, first=True):
    """Insert a command the user created in Config into the managed input."""
    import re
    tag = re.search(rb'<C Type="VirtualUdpIn" IName="HAV"[^>]*>', xml).group(0)
    cmd = (f'<C Type="VirtualUdpInCmd" IName="{iname}" V="178" U="{u}" Title="{title}" Cl="238,238,238" Nio="2" '
           f'WF="16400" Check="{check}" Signed="true" SourceValHigh="100" DestValHigh="100" '
           f'MinVal="-1000000000" MaxVal="1000000000"><Co K="AQ" U="{u[:-2]}aa"/><Co K="Q" U="{u[:-2]}bb"/>'
           f'<Display Type="1" Unit="&lt;v&gt;" StateOnly="true"/></C>').encode()
    return xml.replace(tag, tag + cmd, 1) if first else xml.replace(b"</C></C><C Type=\"LoggerOutCaption\"", cmd + b"</C></C><C Type=\"LoggerOutCaption\"", 1)


MORE = ENTRIES + [{"key": "sensor.neu", "title": "Neu", "digital": False}]
TWIN_U = "aaaaaaaa-0000-0000-ffffa13734b4be2f"


def test_extra_command_for_the_same_key_survives_a_rebuild():
    # Nothing documents a command for the state 0, so a user adds "tor=0" next to ours.
    patched, _ = values.patch_ha_values(SINGLE, ENTRIES)
    twin = with_command(patched, "binary_sensor.tor=0", "Tor aus", "VUIC9", TWIN_U)
    rebuilt, report = values.patch_ha_values(twin, MORE)
    assert report["ha_values_changed"]
    commands = managed(rebuilt)[1]
    assert (TWIN_U, "binary_sensor.tor=0") in [(c[1], c[2]) for c in commands]
    assert sum(1 for c in commands if c[2] == "binary_sensor.tor=1") == 1  # ours is still there with its UUID


def test_stale_placeholder_is_migrated_even_when_a_twin_comes_first():
    patched, _ = values.patch_ha_values(SINGLE, ENTRIES)
    old = patched.replace(b'Check="binary_sensor.tor=1"', b'Check="binary_sensor.tor=\\v"')
    twin = with_command(old, "binary_sensor.tor=0", "Tor aus", "VUIC9", TWIN_U)
    rebuilt, report = values.patch_ha_values(twin, ENTRIES)
    assert report["ha_values_changed"]
    checks = [c[2] for c in managed(rebuilt)[1]]
    assert "binary_sensor.tor=1" in checks and "binary_sensor.tor=0" in checks
    assert "binary_sensor.tor=\\v" not in checks


def test_command_without_a_recognisable_key_is_kept():
    patched, _ = values.patch_ha_values(SINGLE, ENTRIES)
    foreign = with_command(patched, "Tor ein", "Mein Befehl", "VUIC8", TWIN_U)
    quiet = values.patch_ha_values(foreign, ENTRIES)
    assert quiet == (foreign, {"ha_values": 2, "ha_values_changed": False})
    rebuilt, _ = values.patch_ha_values(foreign, MORE)
    assert (TWIN_U, "Tor ein", "Mein Befehl") in [(c[1], c[2], c[3]) for c in managed(rebuilt)[1]]


def test_command_switched_to_analog_gets_the_value_placeholder_too():
    # An entity that turns from digital to numeric: the exact text "...=1" would never carry a value.
    digital = [{"key": "sensor.pool", "title": "Pool", "digital": True}]
    patched, _ = values.patch_ha_values(SINGLE, digital)
    assert managed(patched)[1][0][2] == "sensor.pool=1"
    rebuilt, report = values.patch_ha_values(patched, [{"key": "sensor.pool", "title": "Pool", "digital": False}])
    assert report["ha_values_changed"]
    block, commands = managed(rebuilt)
    assert commands[0][2] == "sensor.pool=\\v" and block.find("C").get("Analog") == "true"
    assert values.patch_ha_values(rebuilt, [{"key": "sensor.pool", "title": "Pool", "digital": False}])[1]["ha_values_changed"] is False
