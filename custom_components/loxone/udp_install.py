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

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


class ActivationUncertainError(OSError):
    """A staged program may still be waiting for a future Miniserver restart."""


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
        ftp = ftplib.FTP_TLS(timeout=30, source_address=self.source_address)
        try:
            ftp.connect(self.host, 21)
            try:
                ftp.auth()
            except ftplib.error_perm as err:
                if not str(err).startswith(("500", "502", "504")):
                    raise
                ftp.close()
                ftp = ftplib.FTP(timeout=30, source_address=self.source_address)
                ftp.connect(self.host, 21)
            ftp.login(self.username, self.password)
            if isinstance(ftp, ftplib.FTP_TLS):
                ftp.prot_p()
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


def install(client, directory, udp_port, select, stop: threading.Event):
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(directory, threading.Lock())
    if not lock.acquire(blocking=False):
        return {"state": "busy"}
    try:
        return _install(client, directory, udp_port, select, stop)
    finally:
        lock.release()


def _install(client, directory, udp_port, select, stop: threading.Event):
    """At most one activation attempt per source archive and UDP destination.

    A failed/uncertain activation stays blocked across HA restarts. A new program
    has a new hash and is evaluated again. No automatic rollback/restart loop.
    """
    name, original = client.current()
    _, xml = unpack(original)
    target = client.destination(udp_port)
    candidate, report = prepare(original, target, select(original, xml))
    report.update(source_sha256=digest(original), xml_sha256=digest(xml))
    if candidate == original:
        return dict(report, state="configured")
    backup_path = backup(directory, name, original)
    # Store next to the backup so integration removal/reinstallation preserves it.
    journal_path = Path(directory) / "activation.json"
    journal = json.loads(journal_path.read_text()) if journal_path.exists() else {}
    attempt = digest(original + target.encode())
    if journal.get("attempt") == attempt:
        return dict(report, state="blocked", backup=backup_path)
    if stop.is_set():
        return dict(report, state="stopped", backup=backup_path)
    _, expected_xml = unpack(candidate)
    journal = {"attempt": attempt, "backup": backup_path,
               "expected_xml_sha256": digest(expected_xml), "state": "pending"}
    _write_journal(journal_path, journal)
    temporary = "ha_udp_" + uuid.uuid4().hex + ".tmp"
    staged = False
    with client.ftp() as ftp:
        try:
            if any(Path(item).name.lower().startswith("sps_new.") for item in ftp.nlst()):
                raise OSError("Another program upload is pending; automatic setup blocked")
            ftp.storbinary("STOR " + temporary, io.BytesIO(candidate))
            received = bytearray()

            def receive(chunk):
                received.extend(chunk)
                if len(received) > len(candidate):
                    raise OSError("Uploaded archive exceeds expected size")

            ftp.retrbinary("RETR " + temporary, receive)
            if digest(bytes(received)) != digest(candidate):
                raise OSError("FTP read-back checksum mismatch")
            # Recheck the full source archive, not just its filename.
            current_name, current_raw = client.current()
            if current_name != name or current_raw != original:
                raise OSError("Program changed during setup; upload not activated")
            if stop.is_set():
                raise OSError("Integration unloading; upload not activated")
            if any(Path(item).name.lower().startswith("sps_new.") for item in ftp.nlst()):
                raise OSError("Another program upload is pending")
            ftp.rename(temporary, "sps_new.zip")
            staged = True
            answer = json.loads(client.get("/jdev/sps/restart"))
            if str(answer.get("LL", {}).get("Code")) != "200":
                raise OSError("Miniserver did not confirm program restart")
            staged = False  # Activation acknowledged; never delete somebody else's next upload.
            journal["state"] = "activation_requested"
            _write_journal(journal_path, journal)
        except BaseException as original_error:
            if staged:
                # An unactivated sps_new.zip would otherwise load on a later reboot.
                try:
                    pending = bytearray()
                    ftp.retrbinary("RETR sps_new.zip", pending.extend)
                    if bytes(pending) == candidate:
                        ftp.delete("sps_new.zip")
                except ftplib.error_perm as err:
                    if not str(err).startswith("550"):
                        raise ActivationUncertainError("Pending upload cleanup could not be verified") from original_error
                except Exception:
                    raise ActivationUncertainError("Pending upload cleanup could not be verified") from original_error
            raise
        finally:
            try:
                ftp.delete(temporary)
            except Exception:
                pass
    return dict(report, state="restarting", backup=backup_path)
