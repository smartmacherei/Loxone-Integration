"""Weg 3 on block parameters: value and trigger command, remanent memory, wiring and unwiring."""
from types import SimpleNamespace as NS
import xml.etree.ElementTree as ET

from test_udp_install import XML, module
from test_ha_values_program import CAPTION, FULL

values_program = module("ha_values_program")
wiring = module("param_wiring")
params = module("block_parameters")
values = module("ha_values")

BLOCK = "18f7cbc0-0000-0010-ffffa13734b4be2f"
TIME_END = "18f7cbc0-0000-0011-00ffa13734b4be2f"
USER_WIRED = "18f7cbc0-0000-0012-01ffa13734b4be2f"
PAGE_BLOCK = (f'<C Type="Page" V="178" U="18f7cbc0-0000-0003-ffffa13734b4be2f" Title="Customer logic">'
              f'<C Type="AutoJalousie" V="178" U="{BLOCK}" Title="Beschattung" Px="5952" Py="576" Px2="8640" Py2="2040">'
              f'<Co K="TimeEnd" Def="75" U="{TIME_END}" />'
              f'<Co K="TimeEndDown" Def="70" Nc="1" U="{USER_WIRED}"><In Input="18f7cbc0-0000-0013-00ffa13734b4be2f" /></Co>'
              f'<IoData Visu="true" /></C></C>')
SINGLE = (XML.replace(b'  <C Type="LoggerOutCaption"', CAPTION.encode() + b'\n  <C Type="LoggerOutCaption"')
          .replace(b'<C Type="Page" V="178" U="18f7cbc0-0000-0003-ffffa13734b4be2f" Title="Customer logic"/>',
                   PAGE_BLOCK.encode()))
KEY = "number.beschattung_opening_duration"
ENTRY = {"key": KEY, "entity_id": KEY, "attribute": None, "title": "Opening duration", "digital": False,
         "target": TIME_END}


def patch(xml, entries):
    program_entries = values.program_entries(entries)
    xml, _ = values_program.patch_ha_values(xml, program_entries)
    return wiring.patch_parameter_wiring(xml, program_entries)


def connector(xml, uid):
    return next(co for co in ET.fromstring(xml).iter("Co") if co.get("U") == uid)


def test_program_gets_value_and_trigger_commands():
    entries = values.program_entries([ENTRY])
    assert [e["key"] for e in entries] == [KEY, KEY + ".set"]
    assert entries[0]["target"] == TIME_END and "target" not in entries[1]


def test_parameter_is_fed_by_a_remanent_memory_on_its_page():
    xml, report = patch(SINGLE, [ENTRY])
    assert report["param_wired"] == 1 and report["param_skipped"] == []
    root = ET.fromstring(xml)
    i = params.ids("18f7cbc0-0000-0000-ffffa13734b4be2f", TIME_END)
    page = next(el for el in root.iter("C") if el.get("Type") == "Page")
    added = {el.get("U"): el for el in page.findall("C")}
    memory = added[i["memory"]]
    assert memory.find("Co[@K='Remanence']").get("Inv") == "true"
    commands = {c.get("Check"): c for c in root.iter("C") if c.get("Type") == "VirtualUdpInCmd"}
    value_cmd, set_cmd = commands[KEY + "=\\v"], commands[KEY + ".set=\\v"]
    assert value_cmd.get("Analog") == set_cmd.get("Analog") == "true"
    assert added[i["value_ref"]].get("Ref") == value_cmd.get("U")
    assert added[i["set_ref"]].get("Ref") == set_cmd.get("U")
    assert memory.find("Co[@K='Input']/In").get("Input") == i["value_ref_AQ"]
    assert memory.find("Co[@K='Trigger']/In").get("Input") == i["set_ref_Q"]
    feed = connector(xml, TIME_END)
    assert feed.get("Def") == "75" and feed.find("In").get("Input") == i["memory_AQ"]
    # The parameter now counts as held by HA, the user's wiring stays untouched.
    found = {p["unique_id"]: p for p in params.enumerate_parameters(xml)}
    assert found[TIME_END]["ha_wired"] is True
    assert TIME_END not in params.parameter_values(xml)
    assert connector(xml, USER_WIRED).find("In").get("Input") == "18f7cbc0-0000-0013-00ffa13734b4be2f"


def test_second_run_changes_nothing_and_unwiring_restores_the_original():
    once, _ = patch(SINGLE, [ENTRY])
    twice, report = patch(once, [ENTRY])
    assert twice == once and report["param_wired"] == 1
    removed, _ = patch(once, [])
    root = ET.fromstring(removed)
    assert not [el for el in root.iter("C") if el.get("Type") in {"AMemory", "InputRef"}]
    restored = connector(removed, TIME_END)
    assert restored.find("In") is None and restored.get("Nc") is None and restored.get("Def") == "75"


def test_user_wired_parameter_is_never_rewired():
    xml, report = patch(SINGLE, [{**ENTRY, "target": USER_WIRED}])
    assert report["param_wired"] == 0 and report["param_skipped"] == [USER_WIRED.lower()]
    assert not [el for el in ET.fromstring(xml).iter("C") if el.get("Type") == "AMemory"]


def test_gateway_projects_are_not_wired():
    _, report = wiring.patch_parameter_wiring(FULL, values.program_entries([ENTRY]))
    assert report["param_wired"] == 0 and report["param_skipped"] == [TIME_END.lower()]


class Socket:
    def __init__(self):
        self.sent = []

    def sendto(self, data, address):
        self.sent.append(data.decode())


def test_value_goes_out_before_the_trigger_edge():
    later = []
    hass = NS(states=NS(get={KEY: NS(state="90", attributes={})}.get),
              loop=NS(call_later=lambda delay, func, *args: later.append((delay, func, args))))
    sender = values.HaValuesSender(hass, [ENTRY], "ms.invalid", 55556)
    sender.socket = Socket()
    sender.send_all()
    for _, func, args in sorted(later, key=lambda item: item[0]):
        func(*args)
    assert sender.socket.sent == [f"{KEY}=90", f"{KEY}.set=1", f"{KEY}.set=0"]
