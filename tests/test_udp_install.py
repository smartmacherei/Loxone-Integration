"""Offline project integrity and transaction failure tests; no Miniserver writes."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import threading
import types
import xml.etree.ElementTree as ET
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "loxone"
PACKAGE = "loxone_udp_test"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = package

def module(name):
    spec = importlib.util.spec_from_file_location(PACKAGE + "." + name, ROOT / (name + ".py"))
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = loaded
    spec.loader.exec_module(loaded)
    return loaded

program = module("udp_program")
installer = module("udp_install")
U = "18f7cbc0-017a-4c94-ffffa13734b4be2f"
SOURCE = "18f7cbc0-017a-4c95-00ffa13734b4be2f"
TARGET = "/dev/udp/192.168.0.223/55555"
XML = f'''<?xml version="1.0" encoding="UTF-8"?>
<Loxone>
<C Type="Document" V="17020828" U="18f7cbc0-0000-0000-ffffa13734b4be2f" Date="2026-09-05 12:00:00" DateS="1" NumO="5">
  <!-- keep user formatting and comments -->
  <C Type="LoggerOutCaption" V="178" U="18f7cbc0-0000-0001-ffffa13734b4be2f"/>
  <C Type="Program" V="178" U="18f7cbc0-0000-0002-ffffa13734b4be2f">
    <C Type="Page" V="178" U="18f7cbc0-0000-0003-ffffa13734b4be2f" Title="Customer logic"/>
  </C>
  <C Type="DigitalIn" V="178" U="{U}" Title="Button &amp; contact">
    <IoData Visu="false"/><Display Unit="&lt;v&gt;"/><Co K="Q" U="{SOURCE}"/>
  </C>
</C>
</Loxone>'''.encode()

def archive(xml=XML):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("sps0.LoxCC"), program.encode(xml))
        z.writestr(zipfile.ZipInfo("LoxAPP3.json"), b'{"lastModified":"2026-09-05 12:00:00","controls":{}}')
        z.writestr(zipfile.ZipInfo("permissions.bin"), b"original permissions")
        z.writestr(zipfile.ZipInfo("Emergency.LoxCC"), b"original emergency program")
        z.writestr(zipfile.ZipInfo("Music.json"), b"{}")
        z.writestr(zipfile.ZipInfo("other.bin"), b"unchanged customer data")
    return output.getvalue()

def test_boolean_u_settings_are_not_duplicate_object_ids():
    xml = XML.replace(b'<IoData Visu="false"/>',
                      b'<IoData Visu="false"/><MO U="true"/><AF U="true"/><FS U="true"/>')
    changed, report = program.patch_xml(xml, TARGET, {U})
    assert report["managed"] == 1
    assert b'<MO U="true"/><AF U="true"/><FS U="true"/>' in changed
    again, _ = program.patch_xml(changed, TARGET, {U})
    assert again == changed


def test_heartbeat_reuses_existing_second_output_without_visualization():
    heartbeat = '00000000-0000-0000-0000000000000002'
    xml = XML.replace(b'</Loxone>', f'<C Type="Second" U="{heartbeat}"><Co K="Q" U="00000000-0000-0000-0000000000000003"/></C></Loxone>'.encode())
    changed, report = program.patch_xml(xml, TARGET, {U})
    root = ET.fromstring(changed)
    messages = [e.get("On") for e in root.iter("LoggerMailer")]
    assert heartbeat + ';<v>' in messages
    assert report['managed'] == 2
    assert b'Visu="true"' not in changed


def test_milliamp_precision_is_preserved_in_logger_message():
    xml = XML.replace(b'&lt;v&gt;', b'&lt;v.3&gt;mA').replace(b'Type="DigitalIn"', b'Type="DimCurrentIn"')
    changed, _ = program.patch_xml(xml, TARGET, {U})
    assert ET.fromstring(changed).find('.//LoggerMailer').get('On') == U + ';<v.3>'


@pytest.mark.parametrize("tag", ["C", "Co"])
def test_duplicate_real_ids_still_rejected(tag):
    xml = XML.replace(b'<IoData Visu="false"/>',
                      f'<IoData Visu="false"/><{tag} U="{U.upper()}"/>'.encode())
    with pytest.raises(ValueError, match="Duplicate UUID"):
        program.patch_xml(xml, TARGET, {U})


def test_archive_roundtrip_preserves_original_files_and_user_xml():
    original = archive()
    changed, report = program.prepare(original, TARGET, {U})
    assert changed != original and report["managed"] == 1
    with zipfile.ZipFile(io.BytesIO(original)) as before, zipfile.ZipFile(io.BytesIO(changed)) as after:
        for name in ("permissions.bin", "Emergency.LoxCC", "Music.json", "other.bin"):
            assert before.read(name) == after.read(name)
    _, xml = program.unpack(changed)
    assert b"<!-- keep user formatting and comments -->" in xml
    assert b'Title="Customer logic"/>' in xml
    root = ET.fromstring(xml)
    document = next(el for el in root.iter("C") if el.get("Type") == "Document")
    assert int(document.get("NumO")) == len(list(root.iter("C")))
    assert program.prepare(changed, TARGET, {U})[0] == changed


def test_config_flag_changes_do_not_trigger_reinstall():
    changed, _ = program.prepare(archive(), TARGET, {U})
    _, xml = program.unpack(changed)
    xml = xml.replace(b'WF="147456"', b'WF="42"')
    roundtrip = archive(xml)
    assert program.prepare(roundtrip, TARGET, {U})[0] == roundtrip


def test_target_or_wiring_change_updates_owned_references():
    first, _ = program.prepare(archive(), TARGET, {U})
    second, _ = program.prepare(first, TARGET.replace("223", "224"), {U})
    assert first != second
    _, xml = program.unpack(second)
    assert len([el for el in ET.fromstring(xml).iter("C") if el.get("Type") == "Logger"]) == 1
    assert program.prepare(second, TARGET.replace("223", "224"), {U})[0] == second


def test_legacy_matching_logger_reused():
    changed, _ = program.prepare(archive(), TARGET, {U})
    _, xml = program.unpack(changed)
    # Legacy/manual IDs and titles differ but their complete wiring is correct.
    root = ET.fromstring(xml)
    ids = [el.get("U") for el in root.iter("C") if el.get("Title") == program.TITLE]
    for i, value in enumerate(ids):
        xml = xml.replace(value.encode(), f"18f7cbc0-aaaa-{i:04x}-ffffa13734b4be2f".encode())
    xml = xml.replace(program.TITLE.encode(), b"HA UDP")
    legacy = archive(xml)
    assert program.prepare(legacy, TARGET, {U})[0] == legacy


def test_owned_page_with_user_logic_is_not_deleted():
    changed, _ = program.prepare(archive(), TARGET, {U})
    _, xml = program.unpack(changed)
    xml = xml.replace(b'Type="OutputRefLM"', b'Type="Switch"')
    with pytest.raises(ValueError, match="Unmanaged content"):
        program.prepare(archive(xml), TARGET, {U})


def disconnected_reference(delete_source=True):
    xml, _ = program.patch_xml(XML, TARGET, {U})
    root = ET.fromstring(xml)
    for parent in root.iter():
        for child in list(parent):
            if child.tag == "In" or (delete_source and child.get("U") == U):
                parent.remove(child)
    return root


def test_config_deleted_source_removes_owned_disconnected_logger():
    root = disconnected_reference()
    changed, report = program.prepare(archive(ET.tostring(root)), TARGET, set())
    _, xml = program.unpack(changed)
    assert not list(ET.fromstring(xml).iter("LoggerMailer"))
    assert report["managed"] == 0
    assert program.prepare(changed, TARGET, set())[0] == changed


@pytest.mark.parametrize("change", ["keep_source", "foreign_id", "foreign_logger", "user_content"])
def test_disconnected_but_unproven_reference_is_protected(change):
    root = disconnected_reference(delete_source=change != "keep_source")
    ref = next(e for e in root.iter("C") if e.get("Type") == "OutputRefLM")
    if change == "foreign_id":
        ref.set("U", SOURCE)
    elif change == "foreign_logger":
        ref.find("LoggerMailer").set("RefLogger", SOURCE)
    elif change == "user_content":
        ET.SubElement(ref, "C", Type="Switch")
    with pytest.raises(ValueError, match="Unmanaged content"):
        program.prepare(archive(ET.tostring(root)), TARGET, set())


@pytest.mark.parametrize("size", [1, 14, 15, 16, 270, 4096])
def test_loxcc_codec(size):
    data = b"x" * size
    assert program.decode(program.encode(data)) == data


def test_corrupt_loxcc_rejected():
    encoded = bytearray(program.encode(XML))
    encoded[-1] ^= 1
    with pytest.raises(ValueError, match="checksum"):
        program.decode(bytes(encoded))


def test_newer_bare_program_blocks_old_zip():
    with pytest.raises(ValueError, match="Latest program"):
        program.newest_archive("sps_1_20260905120000.zip\nsps_2_20260906120000.LoxCC\n")
    assert program.newest_archive("sps_1_20260905120000.zip\nsps_1_20260905120000.LoxCC\n").endswith(".zip")


def test_backup_contains_complete_archive_and_openable_project(tmp_path):
    raw = archive()
    path = Path(program.backup(str(tmp_path), "sps_original.zip", raw))
    assert path.read_bytes() == raw
    assert path.with_suffix(".Loxone").read_bytes() == b"\xef\xbb\xbf" + XML
    assert json.loads(path.with_suffix(".json").read_text())["sha256"] == program.digest(raw)
    assert (tmp_path / "RESTORE.txt").is_file()
    assert program.backup(str(tmp_path), "sps_original.zip", raw) == str(path)
    path.write_bytes(b"corrupted backup")
    with pytest.raises(OSError, match="read-back"):
        program.backup(str(tmp_path), "sps_original.zip", raw)


class FakeFTP:
    def __init__(self, client): self.client = client
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def nlst(self): return list(self.client.files)
    def storbinary(self, command, handle):
        assert list(self.client.folder.glob("*.zip")), "Upload without backup"
        self.client.events.append("upload")
        self.client.files[command[5:]] = handle.read()
    def retrbinary(self, command, callback):
        callback(self.client.files[command[5:]] + (b"bad" if self.client.corrupt else b""))
    def rename(self, old, new):
        self.client.events.append("activate")
        self.client.files[new] = self.client.files.pop(old)
    def delete(self, name): self.client.files.pop(name, None)


class FakeClient:
    def __init__(self, folder):
        self.folder = folder
        self.raw = archive()
        self.files, self.events = {}, []
        self.corrupt = self.changed = self.restart_fails = False
        self.calls = 0
    def current(self):
        self.calls += 1
        return "sps_1_20260905120000.zip", self.raw + (b"changed" if self.changed and self.calls > 1 else b"")
    def destination(self, port): return TARGET
    def ftp(self):
        self.events.append("ftp")
        return FakeFTP(self)
    def get(self, path):
        assert path == "/jdev/sps/restart"
        self.events.append("restart")
        if self.restart_fails: raise OSError("restart rejected")
        return b'{"LL":{"Code":"200"}}'


def run(client):
    return installer.install(client, str(client.folder), 55555, lambda raw, xml: {U}, threading.Event())


def test_successful_transaction_and_persistent_restart_guard(tmp_path):
    client = FakeClient(tmp_path)
    assert run(client)["state"] == "restarting"
    assert client.events == ["ftp", "upload", "activate", "restart"]
    client.events.clear()
    assert run(client)["state"] == "blocked"
    assert client.events == []
    client.raw = client.files.pop("sps_new.zip")
    assert run(client)["state"] == "configured"
    assert client.events == []


def test_backup_failure_prevents_any_ftp(tmp_path, monkeypatch):
    client = FakeClient(tmp_path)
    def fail(*args): raise OSError("disk full")
    monkeypatch.setattr(installer, "backup", fail)
    with pytest.raises(OSError): run(client)
    assert client.events == []


@pytest.mark.parametrize("failure", ["corrupt", "changed", "pending", "restart_fails"])
def test_transaction_failures_do_not_leave_pending_program(tmp_path, failure):
    client = FakeClient(tmp_path)
    if failure == "pending": client.files["sps_new.zip"] = b"customer upload"
    else: setattr(client, failure, True)
    with pytest.raises(OSError): run(client)
    if failure != "restart_fails": assert "restart" not in client.events
    if failure == "pending": assert client.files == {"sps_new.zip": b"customer upload"}
    else: assert client.files == {}
    assert list(tmp_path.glob("*.zip"))


def test_stop_blocks_upload(tmp_path):
    client = FakeClient(tmp_path)
    stop = threading.Event()
    stop.set()
    result = installer.install(client, str(tmp_path), 55555, lambda raw, xml: {U}, stop)
    assert result["state"] == "stopped" and client.events == []


def test_unwired_output_is_reported_and_left_unchanged():
    xml = XML.replace(b'Type="DigitalIn"', b'Type="Actor"').replace(
        ('<Co K="Q" U="' + SOURCE + '"/>').encode(), b'<Co K="I"/>')
    raw = archive(xml)
    result, report = program.prepare(raw, TARGET, {U})
    assert result == raw
    assert report["unsupported"] == 1


def test_new_program_without_legacy_logger_gets_references():
    # Each new project is derived from its own archive, not from an earlier backup.
    xml = XML.replace(b'Title="Customer logic"', b'Title="New customer program"')
    raw = archive(xml)
    changed, report = program.prepare(raw, TARGET, {U})
    _, updated = program.unpack(changed)
    assert b'Title="New customer program"' in updated
    assert report["managed"] == 1
    assert program.prepare(changed, TARGET, {U})[0] == changed


def test_corrupt_project_copy_blocks_upload(tmp_path):
    client = FakeClient(tmp_path)
    path = Path(program.backup(str(tmp_path), "source.zip", client.raw))
    path.with_suffix(".Loxone").write_bytes(b"corrupt project")
    with pytest.raises(OSError, match="project backup"):
        run(client)
    assert client.events == []


def test_concurrent_install_is_not_started(tmp_path):
    client = FakeClient(tmp_path)
    lock = threading.Lock()
    installer._LOCKS[str(tmp_path)] = lock
    with lock:
        assert run(client)["state"] == "busy"
    assert client.events == []


def test_no_change_does_not_open_ftp(tmp_path):
    client = FakeClient(tmp_path)
    client.raw = program.prepare(client.raw, TARGET, {U})[0]
    assert run(client)["state"] == "configured"
    assert client.events == []


def test_incomplete_archive_rejected(tmp_path):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as z:
        z.writestr("sps0.LoxCC", program.encode(XML))
    with pytest.raises(ValueError, match="Incomplete"):
        program.backup(str(tmp_path), "incomplete.zip", raw.getvalue())
    assert list(tmp_path.iterdir()) == []


def test_unverified_cleanup_is_reported(tmp_path):
    client = FakeClient(tmp_path)
    client.restart_fails = True
    ftp = FakeFTP(client)
    original_delete = ftp.delete
    def fail_pending(name):
        if name == "sps_new.zip": raise OSError("connection lost")
        original_delete(name)
    ftp.delete = fail_pending
    client.ftp = lambda: ftp
    with pytest.raises(installer.ActivationUncertainError):
        run(client)
    assert "sps_new.zip" in client.files
    assert run(client)["state"] == "blocked"


@pytest.mark.parametrize("failure,step,code", [
    ("download", "program_download", "PROGRAM_DOWNLOAD_TIMEOUT"),
    ("archive", "archive_check", "ARCHIVE_CHECK_FAILED"),
    ("format", "program_format", "PROGRAM_FORMAT_UNSUPPORTED"),
    ("destination", "udp_destination", "UDP_DESTINATION_FAILED"),
    ("corrupt", "upload_verify", "UPLOAD_SIZE_MISMATCH"),
    ("changed", "activation_verify", "SOURCE_PROGRAM_CHANGED"),
    ("restart_fails", "program_activate", "PROGRAM_ACTIVATE_FAILED"),
])
def test_failure_identifies_step_without_exposing_exception(tmp_path, failure, step, code):
    client = FakeClient(tmp_path)
    secret = "password=SECRET Authorization: Bearer TOKEN <project>PRIVATE</project>"
    def fail_download(): raise TimeoutError(secret)
    def fail_destination(port): raise RuntimeError(secret)
    if failure == "download": client.current = fail_download
    elif failure == "archive": client.raw = b"not a zip"
    elif failure == "format": client.raw = archive(XML.replace(b'V="178"', b'V="999"'))
    elif failure == "destination": client.destination = fail_destination
    else: setattr(client, failure, True)
    with pytest.raises(Exception) as caught:
        run(client)
    data = getattr(caught.value, "udp_failure", {})
    assert data.get("step") == step
    assert data.get("code") == code
    assert data.get("exception_type")
    assert data.get("timestamp")
    assert data.get("description") and data.get("next_check")
    assert "SECRET" not in json.dumps(data) and "TOKEN" not in json.dumps(data)


def test_blocked_retry_restores_original_error_from_disk(tmp_path):
    client = FakeClient(tmp_path)
    client.corrupt = True
    with pytest.raises(OSError) as caught: run(client)
    original_error = getattr(caught.value, "udp_failure", {})
    assert original_error.get("code") == "UPLOAD_SIZE_MISMATCH"
    restarted = FakeClient(tmp_path)
    result = run(restarted)
    assert result["error"] == original_error
    assert result["backup_verified"] is True
    assert restarted.events == []
