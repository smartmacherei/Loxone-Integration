"""The diagnostic probe must explain failures without writes or secret leakage."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/loxone"


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_registry_ids_accept_mapping_and_entry_iterators():
    compat = load("registry_compat")
    entries = [NS(id="one", values=set()), NS(id="two", values=set())]
    class Registry(dict):
        def __iter__(self):
            return iter(self.values())
    for items in ({e.id: e for e in entries}, Registry({e.id: e for e in entries}), entries):
        assert compat.registry_ids(items) == {"one", "two"}


@pytest.mark.parametrize("failure,expected", [(None, None), ("web401", "HTTP_LOGIN_REJECTED"),
    ("ftp_login", "FTP_LOGIN_REJECTED"), ("ftp_connect", "CONNECTION_REFUSED"),
    ("web_timeout", "TIMEOUT"), ("ftp_directory", "FTP_PATH_OR_PERMISSION_REJECTED"),
    ("structure", "MINISERVER_STRUCTURE_INVALID"), ("ftp_tls", "TLS_FAILED"),
    ("ftp_fallback", None)])
def test_checks_are_read_only_and_safe(monkeypatch, caplog, failure, expected):
    module = load("connection_probe")
    secret = "PASSWORD_TOKEN_SERVER_PRIVATE_PROJECT"
    operations = []
    class HTTP:
        def __init__(self, host, port, **kwargs):
            assert (host, port) == ("miniserver.invalid", 80)
        def connect(self):
            if failure == "web_timeout": raise TimeoutError(secret)
        def request(self, method, path, **kwargs):
            operations.append((method, path))
            assert method == "GET" and path == "/data/LoxAPP3.json"
        def getresponse(self):
            return NS(status=401 if failure == "web401" else 200,
                      read=lambda _: json.dumps({"password": secret} if failure == "structure" else {"msInfo": {}, "controls": {}, "private": secret}).encode())
        def close(self): pass
    class FTP:
        def __init__(self, **kwargs): pass
        def connect(self, host, port):
            assert port == 21
            if failure == "ftp_connect": raise ConnectionRefusedError(secret)
        def auth(self):
            operations.append("AUTH")
            if failure == "ftp_tls": raise module.ssl.SSLError(secret)
            if failure == "ftp_fallback": raise module.ftplib.error_perm("502 " + secret)
        def login(self, *args):
            operations.append("LOGIN")
            if failure == "ftp_login": raise module.ftplib.error_perm("530 " + secret)
        def prot_p(self): operations.append("PROT")
        def cwd(self, path):
            assert path == "/prog"
            if failure == "ftp_directory": raise module.ftplib.error_perm("550 " + secret)
        def retrlines(self, command, callback):
            assert command == "NLST"
            callback(secret)
        def close(self): operations.append("CLOSE")
    monkeypatch.setattr(module.http.client, "HTTPConnection", HTTP)
    monkeypatch.setattr(module.ftplib, "FTP_TLS", FTP)
    monkeypatch.setattr(module.ftplib, "FTP", FTP)
    result = module.probe({"host": "miniserver.invalid", "port": 80, "username": "test", "password": secret})
    assert result["provisioning_performed"] is False
    assert result["write_access_tested"] is False
    assert secret not in json.dumps(result) + module.describe(result, "de") + module.describe(result, "en") + caplog.text
    if expected:
        assert expected in [c["code"] for c in result["checks"].values()]
        assert result["state"] == "failed"
    else:
        assert result["state"] == "completed"
    if failure == "ftp_login":
        assert operations.count("LOGIN") == 1
        assert result["checks"]["ftp_directory"]["state"] == "not_tested"
    if failure == "ftp_tls":
        assert "LOGIN" not in operations
