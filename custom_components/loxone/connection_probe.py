"""Explicit, read-only checks of configured ports. No provisioning operations."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import ftplib
import http.client
import json
import logging
import socket
import ssl
from urllib.parse import urlparse

_LOGGER = logging.getLogger(__name__)
TIMEOUT = 8
MAX_BODY = 32 * 1024 * 1024
LABELS = {
    "web_connect": ("Webport erreichbar", "Web port reachable"),
    "web_login": ("Web-Anmeldung", "Web login"),
    "miniserver": ("Miniserver erkannt", "Miniserver identified"),
    "ftp_connect": ("FTP-Port 21 erreichbar", "FTP port 21 reachable"),
    "ftp_tls": ("FTP-Verschlüsselung", "FTP encryption"),
    "ftp_login": ("FTP-Anmeldung", "FTP login"),
    "ftp_directory": ("FTP-Datenkanal / Programmverzeichnis lesbar", "FTP data channel / program directory readable"),
}
HINTS = {
    "web_connect": ("Miniserver-Adresse, Webport und Netzwerkroute prüfen.", "Check Miniserver address, web port and network route."),
    "web_login": ("Miniserver-Benutzer und Web-Zugriffsrechte prüfen; nicht den HA-Benutzer verwenden.", "Check the Miniserver user and web access rights; do not use the HA user."),
    "miniserver": ("Prüfen, ob diese Adresse den erwarteten Miniserver und eine gültige LoxAPP3-Struktur liefert.", "Check that this address returns the expected Miniserver and valid LoxAPP3 structure."),
    "ftp_connect": ("FTP-Dienst auf Port 21 und Erreichbarkeit von HA aus prüfen.", "Check the FTP service on port 21 and reachability from HA."),
    "ftp_tls": ("FTPS-Unterstützung und TLS-Verbindung prüfen.", "Check FTPS support and TLS connectivity."),
    "ftp_login": ("Miniserver-Zugangsdaten und FTP-Rechte des Benutzers prüfen.", "Check Miniserver credentials and the user's FTP permissions."),
    "ftp_directory": ("FTP-Leserechte für /prog sowie passive FTP-Datenverbindungen prüfen. Schreibrechte wurden nicht getestet.", "Check FTP read permissions for /prog and passive FTP data connections. Write permissions were not tested."),
}


def now():
    return datetime.now(timezone.utc).isoformat()


def error_code(step, error):
    if isinstance(error, TimeoutError):
        return "TIMEOUT"
    if isinstance(error, ConnectionRefusedError):
        return "CONNECTION_REFUSED"
    if isinstance(error, socket.gaierror):
        return "DNS_FAILED"
    if isinstance(error, ssl.SSLError):
        return "TLS_FAILED"
    if isinstance(error, ftplib.error_perm):
        # Read only the protocol's numeric code; never expose server text.
        code = str(error)[:3]
        if code == "530":
            return "FTP_LOGIN_REJECTED"
        if code == "550":
            return "FTP_PATH_OR_PERMISSION_REJECTED"
    return "CHECK_FAILED"


def probe(options, progress=None):
    """Probe only the configured HTTP(S) port and FTP 21, without retries."""
    report = {"started_at": now(), "state": "running", "checks": {},
              "write_access_tested": False, "provisioning_performed": False}

    def record(step, state, code, **safe):
        item = {"state": state, "code": code, "timestamp": now(), **safe}
        report["checks"][step] = item
        _LOGGER.info("Loxone connection check: %s %s %s", step, state, code)
        if progress:
            progress(step, dict(item))

    def failed(step, error):
        safe_types = {"TimeoutError", "ConnectionRefusedError", "ConnectionResetError", "ConnectionError", "OSError", "ValueError", "JSONDecodeError", "UnicodeEncodeError", "gaierror", "SSLError", "SSLCertVerificationError", "error_perm", "error_temp", "error_proto", "error_reply"}
        name = type(error).__name__
        record(step, "failed", error_code(step, error), exception_type=name if name in safe_types else "Exception")

    try:
        parsed = urlparse(str(options["host"]) if "://" in str(options["host"]) else "//" + str(options["host"]))
        port = int(options["port"])
        host = parsed.hostname
        scheme = parsed.scheme or ("https" if port == 443 else "http")
        if not host or scheme not in {"http", "https"} or not 1 <= port <= 65535:
            raise ValueError()
        report.update(target_host=host, web_port=port, web_scheme=scheme, ftp_port=21)
    except Exception:
        record("web_connect", "failed", "INVALID_CONNECTION_SETTINGS")
        report.update(state="failed", completed_at=now())
        return report

    conn = None
    step = "web_connect"
    try:
        cls = http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection
        conn = cls(host, port, timeout=TIMEOUT)
        conn.connect()
        record(step, "ok", "WEB_CONNECTED")
        step = "web_login"
        auth = base64.b64encode(f"{options['username']}:{options['password']}".encode("latin-1")).decode()
        conn.request("GET", (parsed.path.rstrip("/") if parsed.path else "") + "/data/LoxAPP3.json",
                     headers={"Authorization": "Basic " + auth})
        response = conn.getresponse()
        if response.status != 200:
            code = {401: "HTTP_LOGIN_REJECTED", 403: "HTTP_ACCESS_FORBIDDEN", 404: "HTTP_PATH_NOT_FOUND"}.get(response.status, "HTTP_ERROR")
            record(step, "failed", code, http_status=response.status)
        else:
            record(step, "ok", "WEB_ACCESS_ACCEPTED", http_status=200)
            step = "miniserver"
            raw = response.read(MAX_BODY + 1)
            if len(raw) > MAX_BODY:
                raise ValueError()
            data = json.loads(raw)
            if not isinstance(data, dict) or not isinstance(data.get("msInfo"), dict) or not isinstance(data.get("controls"), dict):
                record(step, "failed", "MINISERVER_STRUCTURE_INVALID")
            else:
                record(step, "ok", "MINISERVER_IDENTIFIED")
    except Exception as error:
        failed(step, error)
    finally:
        if conn:
            conn.close()

    ftp = None
    step = "ftp_connect"
    try:
        ftp = ftplib.FTP_TLS(timeout=TIMEOUT)
        ftp.connect(host, 21)
        record(step, "ok", "FTP_CONNECTED")
        step = "ftp_tls"
        try:
            ftp.auth()
        except ftplib.error_perm as error:
            if str(error)[:3] not in {"500", "502", "504"}:
                raise
            # Match the existing installer's fallback, never retry rejected logins.
            ftp.close()
            ftp = None
            record(step, "unsupported", "FTP_TLS_UNSUPPORTED")
            step = "ftp_connect"
            ftp = ftplib.FTP(timeout=TIMEOUT)
            ftp.connect(host, 21)
        else:
            record(step, "ok", "FTP_TLS_NEGOTIATED")
        step = "ftp_login"
        ftp.login(options["username"], options["password"])
        record(step, "ok", "FTP_LOGIN_ACCEPTED")
        if isinstance(ftp, ftplib.FTP_TLS):
            step = "ftp_tls"
            ftp.prot_p()
            record(step, "ok", "FTP_DATA_TLS_ENABLED")
        step = "ftp_directory"
        ftp.cwd("/prog")
        # No names/content retained. This tests the passive data channel as well.
        ftp.retrlines("NLST", lambda line: None)
        record(step, "ok", "FTP_DIRECTORY_READABLE")
    except Exception as error:
        failed(step, error)
    finally:
        if ftp:
            ftp.close()
    for key in LABELS:
        if key not in report["checks"]:
            record(key, "not_tested", "PREVIOUS_CHECK_FAILED")
    report.update(completed_at=now(), state="failed" if any(c["state"] == "failed" for c in report["checks"].values()) else "completed")
    return report


def describe(report, language):
    de = language == "de"
    lines = []
    for key, item in report.get("checks", {}).items():
        if key not in LABELS:
            continue
        states = {"ok": "OK", "failed": "Fehlgeschlagen" if de else "Failed", "unsupported": "Nicht unterstützt; unverschlüsseltes FTP" if de else "Unsupported; plain FTP", "not_tested": "Nicht geprüft" if de else "Not tested"}
        lines.append(f"{LABELS[key][0 if de else 1]}: {states.get(item['state'], item['state'])} ({item['code']})")
        if item["state"] == "failed":
            lines.append(HINTS[key][0 if de else 1])
            if item["code"] == "TIMEOUT":
                lines.append("Zeitlimit erreicht; Ursache nicht bestätigt." if de else "Timeout; cause unconfirmed.")
    return "\n\n".join(lines)
