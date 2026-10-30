"""Gateway/Client beta: one logger per Miniserver, identical in project and partials."""
import ast
import asyncio
import io
import json
import logging
import sys
import threading
from types import SimpleNamespace as NS
import xml.etree.ElementTree as ET
import zipfile

import pytest

from test_udp_diagnostics import SECRET, manager, reporting  # noqa: F401 (fixture)
from test_udp_install import PACKAGE, ROOT, TARGET, U, XML, FakeClient, installer, module, program

cleanup = module("registry_cleanup")
errors = sys.modules[PACKAGE + ".udp_errors"]
topology = module("topology")

GW, CL = "10000000-0000-0000-ffff000000000001", "20000000-0000-0000-ffff000000000002"
GW_IN, CL_IN = "10000000-0000-0001-ffff000000000001", "20000000-0000-0001-ffff000000000002"
SECOND = "30000000-0000-0000-ffff000000000003"
DOC = "18f7cbc0-0000-0000-ffffa13734b4be2f"


def live(uuid, title, terminal, extra=""):
    return (f'<C Type="LoxLIVE" V="174" U="{uuid}" Title="{title}" IntAddr="192.168.9.{uuid[0]}0">'
            f'<C Type="LoggerOutCaption" V="174" U="{uuid[:-1]}9"/>'
            f'<C Type="DigitalIn" V="174" U="{terminal}" Title="Kontakt {title}">'
            f'<IoData Visu="false"/><Display Unit="&lt;v&gt;"/><Co K="Q" U="{terminal[:-1]}f"/></C>{extra}</C>')


def prog(owner, title, content=""):
    return (f'<C Type="Program" V="174" U="{owner[:-1]}6" Title="{title}" Ref="{owner}">'
            f'<C Type="Page" V="174" U="{owner[:-1]}5" Title="Seite">{content}</C></C>')


def document(*parts):
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<Loxone>\n<C Type="Document" V="17020828" U="{DOC}" '
            f'Date="2026-09-05 12:00:00" DateS="1" NumO="9">'
            f'<C Type="TimeCaption" V="174" U="{DOC[:-1]}8"><C Type="Second" V="174" U="{SECOND}" Title="Sekunden">'
            f'<Co K="Q" U="{SECOND[:-1]}f"/></C></C>' + "".join(parts) + "</C>\n</Loxone>").encode()


GATEWAY_OBJ = (f'<C Type="Gateway" V="174" U="{GW[:-1]}7" Title="Gateway" Concentrator="true">'
               f'<SLAVE Used="true" Name="Client" IP="192.168.9.20" Type="1" Port="80" uuid="{CL}"/></C>')
# A client program sees a foreign input only as a Memory proxy with the same UUID.
PROXY = f'<C Type="Memory" V="174" U="{GW_IN}" Title="Kontakt Gateway" Tp="0"><Co K="Q" U="{GW_IN[:-1]}f"/></C>'
FULL = document(live(GW, "Gateway", GW_IN, GATEWAY_OBJ), live(CL, "Client", CL_IN), prog(GW, "Gateway"), prog(CL, "Client"))
PART_GW = document(live(GW, "Gateway", GW_IN, GATEWAY_OBJ), prog(GW, "Gateway"))
PART_CL = document(live(CL, "Client", CL_IN), prog(CL, "Client", PROXY))


def archive(full=FULL, parts=(PART_GW, PART_CL), project=True, structure=b'{"lastModified":"2026-09-05 12:00:00","controls":{}}'):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        if project:
            z.writestr("sps.Loxone", b"\xef\xbb\xbf" + full)
        for index, part in enumerate(parts):
            z.writestr(f"sps{index}.LoxCC", program.encode(part))
            z.writestr(f"LoxAPP3_{index}.LoxCC", program.encode(b'{"lastModified":"2026-09-05 12:00:00"}'))
        z.writestr("LoxAPP3.json", structure)
        z.writestr("permissions.bin", b"p")
        z.writestr("Emergency.LoxCC", b"e")
        z.writestr("Music.json", b"{}")
    return output.getvalue()


def managed(xml):
    root = ET.fromstring(xml)
    pages = {el.get("U") for el in root.iter("C") if el.get("Type") == "Page" and el.get("Title") == program.TITLE}
    loggers = {el.get("U") for el in root.iter("C") if el.get("Type") == "Logger" and el.get("Title") == program.TITLE}
    refs = {(ref.get("U"), ref.find("LoggerMailer").get("On"), ref.find("Co[@K='AI']/In").get("Input"))
            for el in root.iter("C") if el.get("U") in pages for ref in el.findall("C")}
    return pages, loggers, refs


def test_archive_needs_the_beta_flag_and_the_full_project():
    raw = archive()
    with pytest.raises(ValueError) as caught:
        program.unpack(raw)
    assert caught.value.udp_code == "ARCHIVE_MULTIPLE_PROGRAMS"
    assert program.unpack(raw, gateway=True)[0] == "sps.Loxone"
    with pytest.raises(ValueError) as caught:
        program.unpack(archive(project=False), gateway=True)
    assert caught.value.udp_code == "ARCHIVE_PROJECT_MISSING"


def test_programs_get_identical_objects_in_project_and_partials():
    raw = archive()
    with pytest.raises(ValueError):  # without the flag the archive is refused before any change
        program.prepare(raw, TARGET, {GW_IN, CL_IN})
    changed, report = program.prepare(raw, TARGET, {GW_IN, CL_IN}, gateway=True)
    assert changed != raw and report["managed"] == 4  # two terminals, two heartbeats
    assert report["scopes"] == {GW[:-1] + "6": [GW_IN], CL[:-1] + "6": [CL_IN]}
    _, project = program.unpack(changed, gateway=True)
    pages, loggers, refs = managed(project)
    assert len(pages) == 2 and len(loggers) == 2
    root = ET.fromstring(project)
    for owner in (GW, CL):  # each logger under the LoggerOutCaption of its own Miniserver
        caption = next(el for el in root.iter("C") if el.get("U") == owner[:-1] + "9")
        assert [el.get("Title") for el in caption.findall("C")] == [program.TITLE]
    # Heartbeats are keyed by the Miniserver, terminals by themselves.
    assert {on for _, on, _ in refs} == {GW_IN + ";<v>", CL_IN + ";<v>", GW + ";<v>", CL + ";<v>"}
    members = program.program_members(changed)
    for name, owner, terminal in (("sps0.LoxCC", GW, GW_IN), ("sps1.LoxCC", CL, CL_IN)):
        part_pages, part_loggers, part_refs = managed(members[name])
        assert part_pages <= pages and part_loggers <= loggers
        assert part_refs == {r for r in refs if r[1] in {terminal + ";<v>", owner + ";<v>"}}
    with zipfile.ZipFile(io.BytesIO(changed)) as after:
        assert b'"lastModified":"2026-09-05 12:00:00"' not in after.read("LoxAPP3.json")
        assert b"2026-09-05 12:00:00" not in program.decode(after.read("LoxAPP3_1.LoxCC"))
        assert after.read("permissions.bin") == b"p"
    assert program.prepare(changed, TARGET, {GW_IN, CL_IN}, gateway=True)[0] == changed


def test_partial_proxy_never_gets_a_foreign_terminal():
    changed, _ = program.prepare(archive(), TARGET, {GW_IN}, gateway=True)
    members = program.program_members(changed)
    assert {on for _, on, _ in managed(members["sps1.LoxCC"])[2]} == {CL + ";<v>"}
    assert {on for _, on, _ in managed(members["sps0.LoxCC"])[2]} == {GW_IN + ";<v>", GW + ";<v>"}


def test_project_and_all_partials_share_one_program_date(monkeypatch):
    # Config writes one Date/DateS into sps.Loxone and every spsN. A client whose
    # partial program carries another date is reported as outdated by the gateway.
    real = program.dt.datetime

    class Ticking(real):  # every clock read is one second later
        ticks = 0

        @classmethod
        def now(cls, tz=None):
            cls.ticks += 1
            return real(2026, 9, 23, 14, 24, 41, tzinfo=tz) + program.dt.timedelta(seconds=cls.ticks)

    first, _ = program.prepare(archive(), TARGET, {GW_IN}, gateway=True)
    monkeypatch.setattr(program.dt, "datetime", Ticking)
    # Second run changes only the client's partial, like a re-patch after a Config save.
    for raw in (archive(), first):
        changed, _ = program.prepare(raw, TARGET, {GW_IN, CL_IN}, gateway=True)
        _, project = program.unpack(changed, gateway=True)
        documents = [project] + list(program.program_members(changed).values())
        stamps = {tuple(next(el for el in ET.fromstring(xml).iter("C") if el.get("Type") == "Document").get(key)
                        for key in ("Date", "DateS")) for xml in documents}
        assert len(stamps) == 1 and stamps != {("2026-09-05 12:00:00", "1")}


def test_config_proxy_duplicates_are_tolerated_but_real_duplicates_are_not():
    # Config repeats a foreign input used on two pages as two Memory proxies with one
    # object UUID (their connectors stay unique, as in the tester's archive).
    part = PART_CL.replace(PROXY.encode(), (PROXY + PROXY.replace(GW_IN[:-1] + "f", GW_IN[:-1] + "e")).encode())
    changed, _ = program.prepare(archive(parts=(PART_GW, part)), TARGET, {GW_IN, CL_IN}, gateway=True)
    _, _, refs = managed(program.program_members(changed)["sps1.LoxCC"])
    assert {on for _, on, _ in refs} == {CL_IN + ";<v>", CL + ";<v>"}
    twin = PART_CL.replace(b'Title="Kontakt Client"', b'Title="Kontakt Client"/><C Type="DigitalIn" V="174" U="' + CL_IN.encode() + b'" Title="Zwilling"')
    with pytest.raises(ValueError, match="Duplicate UUID"):
        program.prepare(archive(parts=(PART_GW, twin)), TARGET, {GW_IN, CL_IN}, gateway=True)


def test_format_174_is_only_accepted_on_the_gateway_path():
    single = XML.replace(b'V="178"', b'V="174"')
    with pytest.raises(ValueError) as caught:
        program.patch_xml(single, TARGET, {U})
    assert caught.value.udp_code == "PROGRAM_FORMAT_UNSUPPORTED"
    changed, report = program.patch_xml(PART_GW, TARGET, {GW_IN}, gateway=True)
    assert report["managed"] == 2 and b'Type="Page" V="174"' in changed
    # A program without its Miniserver reference cannot be scoped and is refused.
    with pytest.raises(ValueError) as caught:
        program.patch_xml(PART_GW.replace(f' Ref="{GW}"'.encode(), b""), TARGET, {GW_IN}, gateway=True)
    assert caught.value.udp_code == "PROGRAM_FORMAT_UNSUPPORTED"


def test_install_uploads_the_whole_archive_to_the_gateway_only(tmp_path):
    client = FakeClient(tmp_path)
    client.raw = archive()
    with pytest.raises(ValueError) as caught:
        installer.install(client, str(tmp_path), 55555, lambda raw, xml: {GW_IN, CL_IN}, threading.Event())
    assert caught.value.udp_failure["code"] == "ARCHIVE_MULTIPLE_PROGRAMS" and client.events == []
    folder = tmp_path / "beta"
    client = FakeClient(folder)
    client.raw = archive()
    result = installer.install(client, str(folder), 55555, lambda raw, xml: {GW_IN, CL_IN},
                               threading.Event(), gateway=True)
    assert result["state"] == "restarting" and result["managed"] == 4
    assert client.events == ["ftp", "upload", "activate", "restart"]
    uploaded = client.files["sps_new.zip"]
    assert program.unpack(uploaded, gateway=True)[0] == "sps.Loxone"
    assert set(program.program_members(uploaded)) == {"sps0.LoxCC", "sps1.LoxCC"}
    backups = list(folder.glob("*.Loxone"))
    assert len(backups) == 1 and b'Type="Program"' in backups[0].read_bytes()


def test_upload_waits_until_every_client_answers(tmp_path):
    client = FakeClient(tmp_path)
    client.raw = archive()
    client.client_down = True
    with pytest.raises(OSError) as caught:
        installer.install(client, str(tmp_path), 55555, lambda raw, xml: {GW_IN, CL_IN}, threading.Event(), gateway=True)
    assert caught.value.udp_failure["code"] == "CLIENT_UNREACHABLE"
    assert caught.value.udp_failure["step"] == "clients_check" and client.events == []
    client.client_down = False
    result = installer.install(client, str(tmp_path), 55555, lambda raw, xml: {GW_IN, CL_IN}, threading.Event(), gateway=True)
    assert result["state"] == "restarting" and client.events == ["ftp", "upload", "activate", "restart"]


def test_gateway_upload_can_be_withheld_while_clients_may_distribute(tmp_path):
    """A Config save closes the connection; the reload must not restart the logic again."""
    client = FakeClient(tmp_path)
    client.raw = archive()
    result = installer.install(client, str(tmp_path), 55555, lambda raw, xml: {GW_IN, CL_IN}, threading.Event(),
                               gateway=True, allow_upload=False)
    assert result["state"] == "upload_deferred"
    assert client.events == []
    assert list(tmp_path.glob("*.zip")) == [] and not (tmp_path / "activation.json").exists()


WISH = [{"key": "light.a", "title": "Licht", "digital": True}]
CAPTION = f'<C Type="VirtualInCaption" V="174" U="{GW[:-1]}4"/>'
FOREIGN_HAV = f'<C Type="Memory" V="174" U="{GW[:-1]}3" IName="HAV1" Title="Eigener Merker"/>'
FULL_HAV = document(live(GW, "Gateway", GW_IN, GATEWAY_OBJ + CAPTION + FOREIGN_HAV), live(CL, "Client", CL_IN), prog(GW, "Gateway"), prog(CL, "Client"))
NO_LOGGER_CAPTION = FULL.replace(f'<C Type="LoggerOutCaption" V="174" U="{GW[:-1]}9"/>'.encode(), b"")


@pytest.mark.parametrize("full,wish,reason", [
    (FULL, WISH, "Ambiguous or missing VirtualInCaption"),
    (FULL_HAV, WISH, "Foreign object uses the HA values short name"),
    (NO_LOGGER_CAPTION, None, "Ambiguous or missing LoggerOutCaption"),
], ids=["no_input_caption", "foreign_short_name", "no_logger_caption"])
def test_prepare_failure_names_the_failed_check(tmp_path, full, wish, reason):
    client = FakeClient(tmp_path)
    client.raw = archive(full=full)
    with pytest.raises(ValueError) as caught:
        installer.install(client, str(tmp_path), 55555, lambda raw, xml: {GW_IN, CL_IN}, threading.Event(),
                          gateway=True, ha_values=wish)
    data = caught.value.udp_failure
    assert (data["code"], data["step"], data["exception_type"]) == ("PROGRAM_PREPARE_FAILED", "program_prepare", "ValueError")
    assert data["reason"] == reason
    assert reason in data["description"]
    assert client.events == [] and list(tmp_path.glob("*.zip")) == []


@pytest.mark.parametrize("error", [
    ValueError(SECRET), ValueError("Halle WIFI Temp/Humidity"), ValueError("Ambiguous or missing Halle"),
    ValueError("Ambiguous or missing VirtualInCaption", SECRET), ValueError(),
    ET.ParseError("not well-formed: <project>PRIVATE_XML</project>"), RuntimeError("Ambiguous or missing Program"),
    ValueError("Partial program ../" + SECRET + " does not match the project"),
])
def test_only_our_own_fixed_texts_become_a_reason(error):
    data = errors.failure("program_prepare", error)
    assert "reason" not in data
    assert data["description"] == "The step failed; a more specific cause is unconfirmed."
    assert "TOPSECRET" not in json.dumps(data) and "PRIVATE_XML" not in json.dumps(data)


def test_reason_from_a_journal_is_checked_again():
    data = errors.failure("program_prepare", ValueError("Expected one Document"))
    assert errors.restore_failure(data) == data
    assert errors.restore_failure(dict(data, reason=SECRET)).get("reason") is None
    assert "TOPSECRET" not in errors.notification(dict(data, reason=SECRET), "de")
    assert "Expected one Document" in errors.notification(data, "de")


def own_messages():
    """Every text the program path raises as ValueError, read from the source."""
    constant, variable = set(), set()
    for name in ("udp_program", "ha_values_program", "signal_bindings", "udp_install"):
        for node in ast.walk(ast.parse((ROOT / (name + ".py")).read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)
                    and getattr(node.exc.func, "id", None) == "ValueError"):
                argument = node.exc.args[0]
                if isinstance(argument, ast.Constant):
                    constant.add(argument.value)
                else:
                    variable.add(ast.unparse(argument))
    return constant, variable


def test_every_fixed_text_of_the_program_path_is_allowed():
    constant, variable = own_messages()
    assert {"Foreign object uses the HA values short name", "Unmanaged content on the managed UDP page"} <= constant
    assert {text for text in constant if errors.safe_reason(text) != text} == set()
    # A text built at runtime could carry a value. Each one is reviewed here: the parts
    # are loop constants, the name passed the sps*.LoxCC filter of program_members().
    assert variable == {"'Ambiguous or missing ' + type_", "'Partial program ' + name + ' does not match the project'",
                        "'Missing Document attribute ' + key", "'Missing Document attribute ' + key.decode()"}
    for text in ("Ambiguous or missing LoggerOutCaption", "Ambiguous or missing Program",
                 "Partial program sps1.LoxCC does not match the project", "Missing Document attribute Date",
                 "Missing Document attribute DateS", "Missing Document attribute NumO"):
        assert errors.safe_reason(text) == text


def test_status_log_and_diagnostics_carry_the_reason(reporting, tmp_path, caplog):
    setup = manager(reporting, tmp_path)
    setup.gateway_beta, setup.ha_values = True, WISH
    setup.select = lambda raw, xml: {GW_IN, CL_IN}
    setup.client.raw = archive()
    with caplog.at_level(logging.WARNING):
        asyncio.run(setup.check())
    reason = "Ambiguous or missing VirtualInCaption"
    assert setup.status["error_code"] == "PROGRAM_PREPARE_FAILED"
    assert setup.status["error_reason"] == reason and setup.status["error"]["reason"] == reason
    assert "reason=" + reason in caplog.text
    assert reason in reporting.messages[-1]
    setup.hass.data = {"loxone_udp_setup": {"demo": setup}}
    result = asyncio.run(reporting.diagnostics.async_get_config_entry_diagnostics(setup.hass, setup.entry))
    assert result["udp_setup"]["error"]["reason"] == reason
    sensor = reporting.status.UdpStatusSensor("demo", "serial")
    sensor.hass = NS(data=setup.hass.data, config_entries=NS(async_get_entry=lambda _: None))
    asyncio.run(sensor.async_update())
    assert sensor._attr_extra_state_attributes["error_reason"] == reason
    # Another check failing on the same step is new information, so it is logged again.
    setup.client.raw = archive(full=FULL_HAV)
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        asyncio.run(setup.check())
    assert "reason=Foreign object uses the HA values short name" in caplog.text
    # A verified recovery clears the current reason and keeps it only as history.
    setup.ha_values = None
    setup.client.raw = program.prepare(archive(), TARGET, {GW_IN, CL_IN}, gateway=True)[0]
    asyncio.run(setup.check())
    assert setup.status["state"] == "configured" and "error_reason" not in setup.status
    assert setup.status["last_error"]["reason"] == "Foreign object uses the HA values short name"


def test_foreign_exception_text_reaches_neither_status_nor_log(reporting, tmp_path, caplog):
    setup = manager(reporting, tmp_path)
    def fail(port): raise ValueError(SECRET)
    setup.client.destination = fail
    with caplog.at_level(logging.WARNING):
        asyncio.run(setup.check())
    assert setup.status["error_code"] == "UDP_DESTINATION_FAILED" and setup.status["error_reason"] is None
    assert "reason=-" in caplog.text
    assert "TOPSECRET" not in caplog.text + json.dumps(setup.status) + str(reporting.messages)


SERIAL = "504F00000001"
ENTRY = "our-entry"
APP = {"controls": {}, "msInfo": {"serialNr": SERIAL}}
STRUCTURE = json.dumps(dict(APP, lastModified="2026-09-05 12:00:00")).encode()
STALE = "99999999-0000-0000-ffff000000000001"
CLIENT_OBJ = f'<C Type="GatewayClient" V="174" U="{CL[:-1]}7" ProgType="1"/>'


def run_cleanup(monkeypatch, tmp_path, loaded, raw):
    """The real cleanup and program code; only network and HA registries are fakes."""
    calls = []
    def entity(entity_id, unique_id, device_id):
        return entity_id, NS(entity_id=entity_id, platform="loxone", config_entry_id=ENTRY,
                             unique_id=unique_id, device_id=device_id)
    def device(device_id, identifier):
        return device_id, NS(id=device_id, identifiers=[("loxone", identifier)], config_entries=[ENTRY])
    # Nothing here is loaded in HA, like disabled entities: only the project protects them.
    entities = NS(entities=dict([
        entity("sensor.gateway", GW_IN, "dev_gateway"), entity("sensor.client", CL_IN, "dev_client"),
        entity("sensor.client_sub", CL_IN.upper() + "/AI1", "dev_client"),
        entity("sensor.client_output", CL_IN[:-1] + "f", "dev_client"), entity("sensor.stale", STALE, "dev_stale")]))
    devices = NS(devices=dict([device("dev_gateway", GW), device("dev_client", CL), device("dev_stale", STALE)]))
    devices.async_get, entities.async_get = devices.devices.get, entities.entities.get
    devices.async_remove_device = lambda key: calls.append(key)
    entities.async_remove = lambda key: calls.append(key)
    for name, value in {
        "attr": NS(asdict=lambda obj, **kw: vars(obj).copy()),
        "homeassistant.helpers": NS(entity_registry=NS(async_get=lambda h: entities), device_registry=NS(async_get=lambda h: devices)),
    }.items():
        monkeypatch.setitem(sys.modules, name, value)
    class Client:
        def __init__(self, *args): pass
        def current(self): return "sps_1_20260905120000.zip", raw
    monkeypatch.setattr(installer, "ProgramClient", Client)
    async def executor(function, *args): return function(*args)
    hass = NS(async_add_executor_job=executor, config=NS(path=lambda *parts: str(tmp_path.joinpath(*parts))),
              states=NS(async_entity_ids=set))
    # The beta option stays off: reading the project needs no permission to change it.
    entry = NS(entry_id=ENTRY, options=dict(host="host", port=80, username="user", password="private"))
    asyncio.run(cleanup.async_cleanup_registry(hass, entry, loaded, APP))
    return calls


def test_cleanup_in_a_gateway_system_removes_only_what_the_whole_project_lacks(monkeypatch, tmp_path, caplog):
    raw = archive(structure=STRUCTURE)
    with caplog.at_level(logging.WARNING):
        calls = run_cleanup(monkeypatch, tmp_path, topology.program_from_zip(raw), raw)
    assert calls == ["sensor.stale", "dev_stale"]
    assert "registry cleanup skipped" not in caplog.text
    backups = list((tmp_path / "loxone_registry_backups").rglob("*.json"))
    assert len(backups) == 1 and json.loads(backups[0].read_text())["remove_entities"] == ["sensor.stale"]


@pytest.mark.parametrize("project", [
    pytest.param(PART_GW, id="gateway_partial"),
    pytest.param(document(live(CL, "Client", CL_IN, CLIENT_OBJ), prog(CL, "Client", PROXY)), id="client_partial"),
    pytest.param(document(live(GW, "Gateway", GW_IN), live(CL, "Client", CL_IN), prog(GW, "Gateway"), prog(CL, "Client")), id="no_gateway"),
    pytest.param(document(live(GW, "Gateway", GW_IN, GATEWAY_OBJ), live(CL, "Client", CL_IN), prog(GW, "Gateway")), id="client_program_missing"),
    pytest.param(document(live(GW, "Gateway", GW_IN, GATEWAY_OBJ), live(CL, "Client", CL_IN), prog(GW, "Gateway"), prog(GW, "Zwei")), id="program_twice"),
    pytest.param(FULL.replace(f' Ref="{CL}"'.encode(), b""), id="program_without_miniserver"),
    pytest.param(FULL.replace(f'uuid="{CL}"'.encode(), f'uuid="{STALE}"'.encode()), id="client_not_in_project"),
])
def test_a_project_without_the_whole_system_never_drives_removal(monkeypatch, tmp_path, caplog, project):
    with pytest.raises(ValueError):
        cleanup.inventory(project, APP)
    raw = archive(full=project, structure=STRUCTURE)
    with caplog.at_level(logging.WARNING):
        assert run_cleanup(monkeypatch, tmp_path, project, raw) == []
    assert "Loxone registry cleanup skipped (Project" in caplog.text
    assert not (tmp_path / "loxone_registry_backups").exists()


def test_cleanup_keeps_everything_without_the_full_project(monkeypatch, tmp_path, caplog):
    # No sps.Loxone: discovery merges the partials, but nothing proves they are complete.
    raw = archive(project=False, structure=STRUCTURE)
    with caplog.at_level(logging.WARNING):
        assert run_cleanup(monkeypatch, tmp_path, topology.program_from_zip(raw), raw) == []
    assert "Loxone registry cleanup skipped (ARCHIVE_PROJECT_MISSING)" in caplog.text


@pytest.mark.parametrize("change", ["other_miniserver", "newer_program"])
def test_cleanup_defers_when_the_archive_is_not_the_loaded_project(monkeypatch, tmp_path, change):
    structure = STRUCTURE.replace(SERIAL.encode(), b"504F00000002") if change == "other_miniserver" else STRUCTURE
    full = FULL.replace(b'NumO="9"', b'NumO="10"') if change == "newer_program" else FULL
    assert run_cleanup(monkeypatch, tmp_path, topology.program_from_zip(archive(structure=STRUCTURE)),
                       archive(full=full, structure=structure)) == []
    assert not (tmp_path / "loxone_registry_backups").exists()
