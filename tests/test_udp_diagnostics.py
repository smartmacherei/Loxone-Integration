"""Offline error reporting tests; fake network boundaries, real transaction flow."""
import asyncio
import ftplib
import json
import logging
import sys
import threading
from types import SimpleNamespace as NS

import pytest

from test_udp_install import FakeClient, FakeFTP, PACKAGE, archive, installer, module, program, run

SECRET = "password=TOPSECRET Authorization: Bearer PRIVATE_TOKEN <project>PRIVATE_XML</project>"


@pytest.fixture
def reporting(monkeypatch):
    messages, dismissed = [], []
    notification = NS(async_create=lambda hass, message, **kw: messages.append(message),
                      async_dismiss=lambda *args: dismissed.append(args))
    for name, value in {
        "homeassistant": NS(),
        "homeassistant.components": NS(persistent_notification=notification),
        "homeassistant.components.sensor": NS(SensorEntity=object),
        "homeassistant.helpers": NS(),
        "homeassistant.helpers.event": NS(async_track_time_interval=lambda *args: None),
        "homeassistant.const": NS(EntityCategory=NS(DIAGNOSTIC="diagnostic")),
        "homeassistant.config_entries": NS(ConfigEntry=object),
        "homeassistant.core": NS(HomeAssistant=object),
        PACKAGE + ".const": NS(DOMAIN="loxone"),
        PACKAGE + ".topology": NS(enumerate_discoverable=lambda *args: []),
    }.items():
        monkeypatch.setitem(sys.modules, name, value)
    return NS(setup=module("udp_setup"), status=module("udp_status"), diagnostics=module("diagnostics"), messages=messages, dismissed=dismissed)


def manager(reporting, tmp_path, language="de"):
    async def executor(function, *args): return function(*args)
    hass = NS(config=NS(path=lambda *parts: str(tmp_path), language=language),
              async_add_executor_job=executor, data={})
    entry = NS(entry_id="demo", options={"host": "offline.invalid", "port": 80, "username": "user", "password": SECRET})
    result = reporting.setup.UdpSetup(hass, entry, None)
    result.client = FakeClient(tmp_path)
    result.select = lambda raw, xml: {"18f7cbc0-017a-4c94-ffffa13734b4be2f"}
    return result


@pytest.mark.parametrize("language,label", [("de", "Schritt: UDP-Ziel ermitteln"), ("en", "Step: Determine UDP destination")])
def test_notification_and_logs_are_safe_and_localized(reporting, tmp_path, caplog, language, label):
    setup = manager(reporting, tmp_path, language)
    def fail(port): raise RuntimeError(SECRET)
    setup.client.destination = fail
    with caplog.at_level(logging.WARNING): asyncio.run(setup.check())
    assert label in reporting.messages[-1]
    assert ("Ausnahmetyp: RuntimeError" if language == "de" else "Exception type: RuntimeError") in reporting.messages[-1]
    assert "UDP_DESTINATION_FAILED" in reporting.messages[-1]
    assert setup.status["error_code"] == "UDP_DESTINATION_FAILED"
    assert setup.status["error_step"] == "udp_destination"
    assert setup.status["error_timestamp"]
    assert "RuntimeError" in caplog.text and "UDP_DESTINATION_FAILED" in caplog.text
    combined = caplog.text + json.dumps(setup.status) + str(reporting.messages)
    for secret in ("TOPSECRET", "PRIVATE_TOKEN", "PRIVATE_XML"):
        assert secret not in combined
    assert setup.status["backup_verified"] is False
    assert ("Vorgesehener Sicherungsort" if language == "de" else "Intended backup location") in reporting.messages[-1]


def test_error_clears_only_after_verified_recovery(reporting, tmp_path):
    setup = manager(reporting, tmp_path)
    setup.client.corrupt = True
    asyncio.run(setup.check())
    original = setup.status["error"]
    assert original["code"] == "UPLOAD_SIZE_MISMATCH"
    asyncio.run(setup.check())
    assert setup.status["state"] == "blocked" and setup.status["error"] == original
    # A new manager models HA restarting; the on-disk guard still has the cause.
    restarted = manager(reporting, tmp_path)
    asyncio.run(restarted.check())
    assert restarted.status["error"] == original
    assert "UPLOAD_SIZE_MISMATCH" in reporting.messages[-1]
    restarted.client.raw = program.prepare(archive(), "/dev/udp/192.168.0.223/55555", {"18f7cbc0-017a-4c94-ffffa13734b4be2f"})[0]
    asyncio.run(restarted.check())
    assert restarted.status["state"] == "configured"
    assert restarted.status.get("error") is None
    assert restarted.status.get("error_code") is None
    assert restarted.status.get("error_step") is None
    assert restarted.status.get("error_timestamp") is None
    assert restarted.status["last_error"]["historical"] is True
    assert reporting.dismissed


@pytest.mark.parametrize("state", ["checking", "error", "blocked", "restarting"])
def test_setup_state_not_hidden_by_receiver(reporting, state):
    for receiver in (None, NS(last_valid_received=None)):
        sensor = reporting.status.UdpStatusSensor("demo", "serial")
        sensor.hass = NS(data={"loxone_udp_setup": {"demo": NS(status={"state": state, "error_code": "FTP_LOGIN_FAILED"})}, "loxone_udp": {"demo": receiver}})
        asyncio.run(sensor.async_update())
        assert sensor._attr_native_value == state
        assert sensor._attr_extra_state_attributes["setup_state"] == state
        assert sensor._attr_extra_state_attributes["error_code"] == "FTP_LOGIN_FAILED"


def test_automatic_setup_is_checking_before_manager_is_registered(reporting):
    sensor = reporting.status.UdpStatusSensor("demo", "serial")
    sensor.hass = NS(
        data={"loxone_udp": {"demo": NS(last_valid_received=None)}},
        config_entries=NS(async_get_entry=lambda entry_id: NS(options={"auto_configure_udp": True})),
    )
    asyncio.run(sensor.async_update())
    assert sensor._attr_native_value == "checking"
    assert sensor._attr_extra_state_attributes["setup_state"] == "checking"


def test_diagnostics_include_safe_setup_error_not_project(reporting, tmp_path):
    setup = manager(reporting, tmp_path)
    setup.client.corrupt = True
    asyncio.run(setup.check())
    setup.hass.data = {"loxone_udp_setup": {"demo": setup}, "loxone": {"demo": NS(miniserver=NS(lox_config=NS(json={"password": SECRET})))}}
    result = asyncio.run(reporting.diagnostics.async_get_config_entry_diagnostics(setup.hass, setup.entry))
    assert result["udp_setup"]["error_code"] == "UPLOAD_SIZE_MISMATCH"
    assert "TOPSECRET" not in json.dumps(result)


@pytest.mark.parametrize("where,step,code", [("connect", "ftp_connect", "FTP_CONNECT_FAILED"), ("auth", "ftp_tls", "FTP_TLS_FAILED"), ("login", "ftp_login", "FTP_LOGIN_FAILED"), ("prot_p", "ftp_tls", "FTP_TLS_FAILED")])
def test_real_ftp_client_reports_each_phase_without_retry(tmp_path, monkeypatch, where, step, code):
    events = []
    class FTP:
        def __init__(self, **kwargs): pass
        def operation(self, name):
            events.append(name)
            if name == where: raise ftplib.error_perm("530 " + SECRET)
        def connect(self, *args): self.operation("connect")
        def auth(self): self.operation("auth")
        def login(self, *args): self.operation("login")
        def prot_p(self): self.operation("prot_p")
        def close(self): events.append("close")
    monkeypatch.setattr(installer.ftplib, "FTP_TLS", FTP)
    client = FakeClient(tmp_path)
    real = installer.ProgramClient("offline.invalid", 80, "user", SECRET)
    client.ftp = real.ftp
    with pytest.raises(ftplib.error_perm) as caught: run(client)
    assert caught.value.udp_failure["step"] == step
    assert caught.value.udp_failure["code"] == code
    assert "TOPSECRET" not in json.dumps(caught.value.udp_failure)
    assert events.count("connect") == 1
    assert run(client)["error"] == caught.value.udp_failure
    assert events.count("connect") == 1


def test_uncertain_staged_cleanup_stays_visible_after_restart(reporting, tmp_path):
    setup = manager(reporting, tmp_path)
    setup.client.restart_fails = True
    ftp = FakeFTP(setup.client)
    original_delete = ftp.delete
    def fail(name):
        if name == "sps_new.zip": raise OSError(SECRET)
        original_delete(name)
    ftp.delete = fail
    setup.client.ftp = lambda: ftp
    asyncio.run(setup.check())
    assert setup.status["error_code"] == "ACTIVATION_CLEANUP_UNCONFIRMED"
    assert setup.status["activation_error"]["code"] == "PROGRAM_ACTIVATE_FAILED"
    assert setup.status["activation_error"]["exception_type"] == "OSError"
    assert "PROGRAM_ACTIVATE_FAILED" in reporting.messages[-1]
    assert "/prog/sps_new.zip" in reporting.messages[-1]
    assert "Vor einem Neustart" in reporting.messages[-1]
    restarted = manager(reporting, tmp_path)
    asyncio.run(restarted.check())
    assert restarted.status["state"] == "blocked"
    assert restarted.status["error_code"] == "ACTIVATION_CLEANUP_UNCONFIRMED"
    assert restarted.status["activation_error"] == setup.status["activation_error"]
    assert "Vor einem Neustart" in reporting.messages[-1]


def test_unmatched_staged_program_reports_cleanup_uncertainty(tmp_path):
    client = FakeClient(tmp_path)
    client.restart_fails = True
    ftp = FakeFTP(client)
    original_retrieve = ftp.retrbinary
    def retrieve(command, callback):
        if command == "RETR sps_new.zip": callback(b"different staged program")
        else: original_retrieve(command, callback)
    ftp.retrbinary = retrieve
    client.ftp = lambda: ftp
    with pytest.raises(installer.ActivationUncertainError): run(client)
    assert "sps_new.zip" in client.files


def test_ftp_550_does_not_prove_staged_program_was_removed(tmp_path):
    client = FakeClient(tmp_path)
    client.restart_fails = True
    ftp = FakeFTP(client)
    original_retrieve = ftp.retrbinary
    def retrieve(command, callback):
        if command == "RETR sps_new.zip": raise ftplib.error_perm("550 Permission denied " + SECRET)
        original_retrieve(command, callback)
    ftp.retrbinary = retrieve
    client.ftp = lambda: ftp
    with pytest.raises(installer.ActivationUncertainError): run(client)
    result = run(client)
    assert result["error"]["code"] == "ACTIVATION_CLEANUP_UNCONFIRMED"
    assert "sps_new.zip" in client.files


def test_failed_temporary_cleanup_is_reported_without_extra_actions(reporting, tmp_path):
    setup = manager(reporting, tmp_path)
    setup.client.corrupt = True
    ftp = FakeFTP(setup.client)
    def fail(name): raise OSError(SECRET)
    ftp.delete = fail
    setup.client.ftp = lambda: ftp
    asyncio.run(setup.check())
    assert setup.status["state"] == "error"
    assert setup.status["cleanup_warning"]["code"] == "TEMPORARY_CLEANUP_UNCONFIRMED"
    assert "Bereinigung" in reporting.messages[-1]
    assert "TOPSECRET" not in str(reporting.messages)
    assert setup.client.events == ["upload"]
    setup.client.raw = program.prepare(archive(), "/dev/udp/192.168.0.223/55555", {"18f7cbc0-017a-4c94-ffffa13734b4be2f"})[0]
    asyncio.run(setup.check())
    assert setup.status.get("cleanup_warning") is None
    assert setup.status["last_cleanup_warning"]["historical"] is True


@pytest.mark.parametrize("bad", [None, {}, {"step": []}, {"step": "ftp_login", "code": []},
    {"step": "ftp_login", "code": "FTP_LOGIN_FAILED", "exception_type": [], "timestamp": "bad"}])
def test_untrusted_journal_error_never_becomes_prose(tmp_path, bad):
    client = FakeClient(tmp_path)
    run(client)
    path = tmp_path / "activation.json"
    data = json.loads(path.read_text())
    data["error"] = bad
    path.write_text(json.dumps(data))
    client.events.clear()
    result = run(client)
    assert result["state"] == "blocked"
    assert result["error"]["code"] == "ACTIVATION_UNCONFIRMED"
    assert client.events == []


def test_persist_failure_keeps_guard_and_safe_original_error(reporting, tmp_path, monkeypatch):
    setup = manager(reporting, tmp_path)
    setup.client.corrupt = True
    write = installer._write_journal
    def persist(path, value):
        if "error" in value: raise OSError(SECRET)
        write(path, value)
    monkeypatch.setattr(installer, "_write_journal", persist)
    asyncio.run(setup.check())
    assert setup.status["error_code"] == "UPLOAD_SIZE_MISMATCH"
    assert setup.status["error_persisted"] is False
    assert "nicht dauerhaft gespeichert" in reporting.messages[-1]
    assert "TOPSECRET" not in str(reporting.messages)
    setup.client.events.clear()
    asyncio.run(setup.check())
    assert setup.status["state"] == "blocked"
    assert setup.status["error_code"] == "UPLOAD_SIZE_MISMATCH"
    assert setup.client.events == []


def test_progress_replaces_configured_state_while_worker_runs(reporting, tmp_path):
    setup = manager(reporting, tmp_path)
    setup.status["state"] = "configured"
    started, release = threading.Event(), threading.Event()
    destination = setup.client.destination
    def pause(port):
        started.set()
        assert release.wait(5)
        return destination(port)
    setup.client.destination = pause
    setup.client.corrupt = True
    async def executor(function, *args): return await asyncio.to_thread(function, *args)
    setup.hass.async_add_executor_job = executor
    async def check():
        task = asyncio.create_task(setup.check())
        try:
            assert await asyncio.to_thread(started.wait, 5)
            await asyncio.sleep(0)
            assert setup.status["state"] == "checking"
            assert setup.status["step"] == "udp_destination"
            sensor = reporting.status.UdpStatusSensor("demo", "serial")
            sensor.hass = NS(data={"loxone_udp_setup": {"demo": setup}, "loxone_udp": {"demo": NS(last_valid_received=None)}})
            await sensor.async_update()
            assert sensor._attr_native_value == "checking"
        finally:
            release.set()
            await task
        assert setup.status["state"] == "error"
        assert setup.status["step"] == "upload_verify"
    asyncio.run(check())


def test_explicit_unsupported_tls_keeps_existing_plain_ftp_fallback(tmp_path, monkeypatch):
    events = []
    class Plain(FakeFTP):
        def __init__(self, **kwargs): super().__init__(client)
        def connect(self, *args): events.append("plain_connect")
        def login(self, *args): events.append("plain_login")
        def cwd(self, path): events.append("cwd")
    class TLS(Plain):
        def connect(self, *args): events.append("tls_connect")
        def auth(self):
            events.append("auth")
            raise ftplib.error_perm("502 AUTH unsupported " + SECRET)
        def close(self): events.append("close")
    monkeypatch.setattr(installer.ftplib, "FTP_TLS", TLS)
    monkeypatch.setattr(installer.ftplib, "FTP", Plain)
    client = FakeClient(tmp_path)
    client.ftp = installer.ProgramClient("offline.invalid", 80, "user", SECRET).ftp
    assert run(client)["state"] == "restarting"
    assert events == ["tls_connect", "auth", "close", "plain_connect", "plain_login", "cwd"]
    assert client.events == ["upload", "activate", "restart"]


def test_timeout_description_does_not_invent_firewall_cause(tmp_path):
    client = FakeClient(tmp_path)
    def fail(): raise TimeoutError(SECRET)
    client.current = fail
    with pytest.raises(TimeoutError) as caught: run(client)
    errors = sys.modules[PACKAGE + ".udp_errors"]
    for language in ("de", "en"):
        text = errors.notification(caught.value.udp_failure, language)
        assert "PROGRAM_DOWNLOAD_TIMEOUT" in text
        assert "Firewall" not in text and "firewall" not in text
        assert "TOPSECRET" not in text
        assert ("nicht bestätigt" if language == "de" else "unconfirmed") in text
