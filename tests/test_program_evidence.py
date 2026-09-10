"""Support exports preserve the rejected bytes without another provisioning run."""
import base64
import json
from types import SimpleNamespace as NS

import pytest

from test_udp_install import module, archive


def test_exact_rejected_archive_is_exported_without_network():
    evidence = module("program_evidence")
    raw = b"not a ZIP: private project bytes"
    def unexpected(): raise AssertionError("Network must not be called")
    manager = NS(failed_program=(raw, "2026-09-10T14:00:00+00:00"),
                 client=NS(current=unexpected))
    result = evidence.collect(manager)
    assert base64.b64decode(result["data_base64"]) == raw
    assert result["size_bytes"] == len(raw)
    assert result["matches_failed_attempt"] is True
    assert result["contains_sensitive_project_data"] is True
    assert result["validation"]["code"] == "ARCHIVE_INVALID_ZIP"


def test_read_only_fallback_exports_current_archive():
    evidence = module("program_evidence")
    raw = archive()
    calls = []
    def current():
        calls.append("read")
        return "private-name.zip", raw
    result = evidence.collect(NS(failed_program=None, client=NS(current=current)))
    assert calls == ["read"]
    assert base64.b64decode(result["data_base64"]) == raw
    assert result["matches_failed_attempt"] is False
    assert "private-name" not in json.dumps(result)


def test_export_failure_does_not_leak_server_response():
    evidence = module("program_evidence")
    def current(): raise OSError("Authorization: PRIVATE_TOKEN")
    result = evidence.collect(NS(failed_program=None, client=NS(current=current)))
    assert result["state"] == "unavailable"
    assert "PRIVATE_TOKEN" not in json.dumps(result)


def test_export_has_size_limit(monkeypatch):
    evidence = module("program_evidence")
    monkeypatch.setattr(evidence, "MAX_SIZE", 2)
    result = evidence.collect(NS(failed_program=(b"abc", "now")))
    assert result["state"] == "size_limit"
    assert "data_base64" not in result


def test_support_tool_roundtrip_and_tampering(tmp_path):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("extract_support", Path(__file__).resolve().parents[1] / "scripts/extract_program_archive.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    evidence = module("program_evidence")
    raw = b"broken ZIP still needs to reach support"
    result = evidence.collect(NS(failed_program=(raw, "now")))
    source, output = tmp_path / "diagnostic.json", tmp_path / "original.zip"
    source.write_text(json.dumps({"data": {"program_archive": result}}))
    assert tool.extract(source, output) == len(raw)
    assert output.read_bytes() == raw
    with pytest.raises(FileExistsError): tool.extract(source, output)
    result["sha256"] = "0" * 64
    source.write_text(json.dumps({"program_archive": result}))
    with pytest.raises(ValueError, match="checksum"): tool.extract(source, tmp_path / "tampered.zip")
