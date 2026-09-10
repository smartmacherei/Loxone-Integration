"""Blocking Miniserver transaction, run in HA's executor (never the event loop)."""
from __future__ import annotations

import ftplib
import http.client
import io
import json
import os
from pathlib import Path
import socket
import threading
import uuid

from .udp_program import MAX_SIZE, backup, digest, newest_archive, prepare, unpack
from .udp_errors import TRACE, SetupTrace, coded_error, failure, mark, restore_failure

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


class ActivationUncertainError(OSError):
    """A staged program may still be waiting for a future Miniserver restart."""
    udp_code = "ACTIVATION_CLEANUP_UNCONFIRMED"


class ProgramClient:
    def __init__(self, host, port, username, password, source_address=None):
        self.host, self.port = host, int(port)
        self.username, self.password = username, password
        self.source_address = source_address

    def get(self, path):
        import base64
        auth = base64.b64encode(f"{self.username}:{self.password}".encode("latin-1")).decode()
        conn = http.client.HTTPConnection(self.host, self.port, timeout=30,
                                          source_address=self.source_address)
        try:
            conn.request("GET", path, headers={"Authorization": "Basic " + auth})
            response = conn.getresponse()
            if response.status != 200:
                raise OSError(f"Miniserver HTTP status {response.status}")
            data = response.read(MAX_SIZE + 1)
            if len(data) > MAX_SIZE:
                raise ValueError("Miniserver response exceeds size limit")
            return data
        finally:
            conn.close()

    def current(self):
        name = newest_archive(self.get("/dev/fslist/prog").decode())
        return name, self.get("/dev/fsget/prog/" + name)

    def destination(self, port):
        # TCP route selection to this Miniserver gives HA's reachable source IP.
        with socket.create_connection((self.host, self.port), timeout=10,
                                      source_address=self.source_address) as conn:
            address = conn.getsockname()[0]
        if ":" in address:
            raise ValueError("Automatic UDP setup currently requires IPv4")
        return f"/dev/udp/{address}/{port}"

    def ftp(self):
        # Prefer FTPS as supported by Miniserver Gen 2. Fall back only when AUTH
        # TLS is explicitly unsupported, not after a failed login or TLS session.
        mark("ftp_connect")
        ftp = ftplib.FTP_TLS(timeout=30, source_address=self.source_address)
        try:
            ftp.connect(self.host, 21)
            mark("ftp_tls")
            try:
                ftp.auth()
            except ftplib.error_perm as err:
                if not str(err).startswith(("500", "502", "504")):
                    raise
                ftp.close()
                mark("ftp_connect")
                ftp = ftplib.FTP(timeout=30, source_address=self.source_address)
                ftp.connect(self.host, 21)
            mark("ftp_login")
            ftp.login(self.username, self.password)
            if isinstance(ftp, ftplib.FTP_TLS):
                mark("ftp_tls")
                ftp.prot_p()
            mark("upload")
            ftp.cwd("/prog")
            return ftp
        except BaseException:
            ftp.close()
            raise


def _write_journal(path: Path, value: dict):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        os.chmod(temporary, 0o600)
        json.dump(value, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    if os.name != "nt":
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def install(client, directory, udp_port, select, stop: threading.Event, progress=None):
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(directory, threading.Lock())
    if not lock.acquire(blocking=False):
        return {"state": "busy"}
    trace = SetupTrace(progress)
    token = TRACE.set(trace)
    try:
        return _install(client, directory, udp_port, select, stop)
    except Exception as error:
        data = failure(trace.step, error)
        error.udp_failure = data
        error.udp_source_program = trace.source_program
        error.udp_backup = trace.backup
        error.udp_attempt = trace.attempt
        error.udp_cleanup_warning = trace.cleanup_warning
        error.udp_activation_error = trace.activation_error if isinstance(error, ActivationUncertainError) else None
        # Only enrich an existing guard. Never create/unlock/retry an attempt here.
        if trace.journal_path is not None and trace.journal is not None:
            trace.journal["error"] = data
            if trace.cleanup_warning:
                trace.journal["cleanup_warning"] = trace.cleanup_warning
            if error.udp_activation_error:
                trace.journal["activation_error"] = error.udp_activation_error
            try:
                _write_journal(trace.journal_path, trace.journal)
            except Exception:
                error.udp_error_persisted = False
            else:
                error.udp_error_persisted = True
        raise
    finally:
        TRACE.reset(token)
        lock.release()


def _install(client, directory, udp_port, select, stop: threading.Event):
    """At most one activation attempt per source archive and UDP destination.

    A failed/uncertain activation stays blocked across HA restarts. A new program
    has a new hash and is evaluated again. No automatic rollback/restart loop.
    """
    mark("program_download")
    name, original = client.current()
    TRACE.get().source_program = original
    _, xml = unpack(original)
    mark("udp_destination")
    target = client.destination(udp_port)
    mark("program_prepare")
    candidate, report = prepare(original, target, select(original, xml))
    report.update(source_sha256=digest(original), xml_sha256=digest(xml))
    if candidate == original:
        return dict(report, state="configured")
    mark("backup_write")
    backup_path = backup(directory, name, original)
    trace = TRACE.get()
    trace.backup = backup_path
    mark("activation_verify")
    # Store next to the backup so integration removal/reinstallation preserves it.
    journal_path = Path(directory) / "activation.json"
    journal = json.loads(journal_path.read_text()) if journal_path.exists() else {}
    attempt = digest(original + target.encode())
    trace.attempt = attempt
    if journal.get("attempt") == attempt:
        data = restore_failure(journal.get("error"))
        if data is None:
            code = "ACTIVATION_UNCONFIRMED" if journal.get("state") == "activation_requested" else "PREVIOUS_ATTEMPT_BLOCKED"
            data = failure("activation_verify", code=code)
            # No historical timestamp is invented for legacy journals.
            data["timestamp"] = None
        return dict(report, state="blocked", backup=backup_path, backup_verified=True, error=data,
                    error_attempt=attempt, cleanup_warning=restore_failure(journal.get("cleanup_warning")),
                    activation_error=restore_failure(journal.get("activation_error")))
    if stop.is_set():
        return dict(report, state="stopped", backup=backup_path, backup_verified=True)
    _, expected_xml = unpack(candidate)
    journal = {"attempt": attempt, "backup": backup_path,
               "expected_xml_sha256": digest(expected_xml), "state": "pending"}
    mark("backup_write")
    _write_journal(journal_path, journal)
    trace.journal_path, trace.journal = journal_path, journal
    temporary = "ha_udp_" + uuid.uuid4().hex + ".tmp"
    staged = False
    renamed = False
    mark("ftp_connect")
    with client.ftp() as ftp:
        try:
            mark("upload")
            if any(Path(item).name.lower().startswith("sps_new.") for item in ftp.nlst()):
                raise coded_error("PROGRAM_UPLOAD_PENDING", "Another program upload is pending; automatic setup blocked")
            ftp.storbinary("STOR " + temporary, io.BytesIO(candidate))
            mark("upload_verify")
            received = bytearray()

            def receive(chunk):
                received.extend(chunk)
                if len(received) > len(candidate):
                    raise coded_error("UPLOAD_SIZE_MISMATCH", "Uploaded archive exceeds expected size")

            ftp.retrbinary("RETR " + temporary, receive)
            if digest(bytes(received)) != digest(candidate):
                raise coded_error("UPLOAD_CHECKSUM_MISMATCH", "FTP read-back checksum mismatch")
            # Recheck the full source archive, not just its filename.
            mark("activation_verify")
            current_name, current_raw = client.current()
            if current_name != name or current_raw != original:
                raise coded_error("SOURCE_PROGRAM_CHANGED", "Program changed during setup; upload not activated")
            if stop.is_set():
                raise coded_error("SETUP_STOPPED", "Integration unloading; upload not activated")
            if any(Path(item).name.lower().startswith("sps_new.") for item in ftp.nlst()):
                raise coded_error("PROGRAM_UPLOAD_PENDING", "Another program upload is pending")
            mark("program_activate")
            ftp.rename(temporary, "sps_new.zip")
            renamed = True
            staged = True
            answer = json.loads(client.get("/jdev/sps/restart"))
            if str(answer.get("LL", {}).get("Code")) != "200":
                raise coded_error("ACTIVATION_REJECTED", "Miniserver did not confirm program restart")
            staged = False  # Activation acknowledged; never delete somebody else's next upload.
            journal["state"] = "activation_requested"
            mark("activation_verify")
            _write_journal(journal_path, journal)
        except BaseException as original_error:
            if staged:
                trace.activation_error = failure(trace.step, original_error)
                # An unactivated sps_new.zip would otherwise load on a later reboot.
                try:
                    pending = bytearray()
                    ftp.retrbinary("RETR sps_new.zip", pending.extend)
                    if bytes(pending) == candidate:
                        ftp.delete("sps_new.zip")
                    else:
                        raise ActivationUncertainError("Pending upload cleanup could not be verified")
                except Exception:
                    # Even FTP 550 may mean denied access, not an absent file.
                    # Keep the same cleanup operations, but report uncertainty.
                    raise ActivationUncertainError("Pending upload cleanup could not be verified") from original_error
            raise
        finally:
            try:
                ftp.delete(temporary)
            except Exception as cleanup_error:
                # Rename already removed our temporary pathname on success.
                # Otherwise report uncertainty without another remote operation.
                if not renamed:
                    trace.cleanup_warning = failure("upload_verify", cleanup_error,
                                                    code="TEMPORARY_CLEANUP_UNCONFIRMED")
    return dict(report, state="restarting", step="activation_verify", backup=backup_path, backup_verified=True)
