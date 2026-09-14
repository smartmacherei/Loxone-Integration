"""Gateway/Client beta: one logger per Miniserver, identical in project and partials."""
import io
import threading
import xml.etree.ElementTree as ET
import zipfile

import pytest

from test_udp_install import TARGET, U, XML, FakeClient, installer, program

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


def archive(full=FULL, parts=(PART_GW, PART_CL), project=True):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        if project:
            z.writestr("sps.Loxone", b"\xef\xbb\xbf" + full)
        for index, part in enumerate(parts):
            z.writestr(f"sps{index}.LoxCC", program.encode(part))
            z.writestr(f"LoxAPP3_{index}.LoxCC", program.encode(b'{"lastModified":"2026-09-05 12:00:00"}'))
        z.writestr("LoxAPP3.json", b'{"lastModified":"2026-09-05 12:00:00","controls":{}}')
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
