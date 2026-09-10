"""Archive rejection stays conservative and exposes only safe structural facts."""
import io
import json
import sys
import zipfile

import pytest

from test_udp_install import archive, program, FakeClient, run, PACKAGE


@pytest.mark.parametrize("mode,code", [
    ("missing_program", "ARCHIVE_PROGRAM_MISSING"),
    ("multiple_programs", "ARCHIVE_MULTIPLE_PROGRAMS"),
    ("missing_companion", "ARCHIVE_REQUIRED_FILES_MISSING"),
    ("duplicate", "ARCHIVE_DUPLICATE_ENTRIES"),
    ("oversize", "ARCHIVE_SIZE_LIMIT"),
    ("crc", "ARCHIVE_CHECKSUM_MISMATCH"),
])
def test_archive_failures_before_backup_or_upload(tmp_path, monkeypatch, mode, code):
    with zipfile.ZipFile(io.BytesIO(archive())) as source:
        entries = {n: source.read(n) for n in source.namelist()}
    if mode == "missing_program": entries.pop("sps0.LoxCC")
    if mode == "multiple_programs": entries["sps1.LoxCC"] = entries["sps0.LoxCC"]
    if mode == "missing_companion": entries.pop("Music.json")
    entries["PRIVATE_CUSTOMER_FILENAME"] = b"PASSWORD_SECRET_PROJECT"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as z:
        for name, data in entries.items(): z.writestr(name, data)
        if mode == "duplicate":
            with pytest.warns(UserWarning): z.writestr("Music.json", b"{}")
    if mode == "oversize": monkeypatch.setattr(program, "MAX_SIZE", 1)
    if mode == "crc": monkeypatch.setattr(zipfile.ZipFile, "testzip", lambda _: "PRIVATE_CUSTOMER_FILENAME")
    client = FakeClient(tmp_path)
    client.raw = output.getvalue()
    with pytest.raises(ValueError) as caught: run(client)
    data = caught.value.udp_failure
    assert data["code"] == code
    assert data["step"] == "archive_check"
    assert client.events == []
    assert not list(tmp_path.iterdir())
    assert "PRIVATE_CUSTOMER_FILENAME" not in json.dumps(data)
    assert "PASSWORD_SECRET_PROJECT" not in json.dumps(data)
    if mode == "missing_companion":
        assert data["archive_details"]["missing_required_files"] == ["Music.json"]
    if mode == "multiple_programs":
        assert data["archive_details"]["program_file_count"] == 2


def test_persisted_archive_metadata_cannot_inject_private_text():
    errors = sys.modules[PACKAGE + ".udp_errors"]
    data = errors.failure("archive_check", code="ARCHIVE_REQUIRED_FILES_MISSING")
    data["archive_details"] = {"entry_count": "PASSWORD_SECRET", "program_file_count": 2,
                               "missing_required_files": ["Music.json", "PASSWORD_SECRET"]}
    restored = errors.restore_failure(data)
    assert restored["archive_details"] == {"program_file_count": 2, "missing_required_files": ["Music.json"]}
    assert "PASSWORD_SECRET" not in errors.notification(restored, "de")
    assert "Music.json" in errors.notification(restored, "de")
