"""Safe UDP setup diagnostics. Never interpolate exception or server text."""
from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timezone
import errno

# Each tuple contains the German/English step label and targeted next check.
STEPS = {
    "program_download": ("Programm herunterladen", "Download program", "Erreichbarkeit und HTTP-Zugriff des Integrationsbenutzers auf den Miniserver prüfen.", "Check Miniserver reachability and the integration user's HTTP access."),
    "archive_check": ("Archiv prüfen", "Check archive", "Prüfen, ob ein vollständiges, lesbares Projektarchiv aus Loxone Config vorliegt.", "Check that a complete, readable project archive from Loxone Config is available."),
    "program_format": ("Programmformat prüfen", "Check program format", "Projektformat und unterstützte Loxone-Config-Version prüfen; das Originalprojekt erhalten.", "Check the project format and supported Loxone Config version; retain the original project."),
    "udp_destination": ("UDP-Ziel ermitteln", "Determine UDP destination", "IPv4-Adresse und Route von Home Assistant zum Miniserver prüfen.", "Check Home Assistant's IPv4 address and route to the Miniserver."),
    "program_prepare": ("Programm vorbereiten", "Prepare program", "Projektstruktur und Änderungen an der verwalteten HA-UDP-Seite im Originalprojekt prüfen.", "Check the project structure and changes to the managed HA UDP page in the original project."),
    "backup_write": ("Sicherung schreiben", "Write backup", "Schreibrechte und freien Speicher am vorgesehenen Sicherungsort prüfen.", "Check write permissions and free space at the intended backup location."),
    "backup_verify": ("Sicherung verifizieren", "Verify backup", "Lesbarkeit und Integrität der Sicherungsdateien prüfen; bis dahin nicht manuell hochladen.", "Check readability and integrity of the backup files before any manual upload."),
    "clients_check": ("Clients prüfen", "Check clients", "Alle Client-Miniserver müssen erreichbar sein, sonst behält ein Client das alte Programm. Client einschalten oder neu starten, dann erneut versuchen.", "Every client Miniserver must be reachable, otherwise a client keeps the old program. Power the client on or restart it, then retry."),
    "ftp_connect": ("FTP verbinden", "Connect FTP", "Erreichbarkeit des FTP-Dienstes am Miniserver auf Port 21 prüfen.", "Check reachability of the Miniserver FTP service on port 21."),
    "ftp_tls": ("TLS aushandeln", "Negotiate TLS", "FTPS-Unterstützung und TLS-Verbindung zum Miniserver prüfen.", "Check FTPS support and the TLS connection to the Miniserver."),
    "ftp_login": ("FTP-Anmeldung", "FTP login", "Bitte prüfen, ob der in der Integration hinterlegte Benutzer FTP-Zugriff besitzt und die Zugangsdaten stimmen.", "Check that the user configured in the integration has FTP access and that the credentials are correct."),
    "upload": ("Upload durchführen", "Upload program", "FTP-Schreibzugriff auf /prog, freien Speicher und bereits vorgemerkte Programmuploads prüfen.", "Check FTP write access to /prog, free space and any already staged program uploads."),
    "upload_verify": ("Upload verifizieren", "Verify upload", "FTP-Lesezugriff und Integrität des hochgeladenen Archivs prüfen; keinen weiteren Upload erzwingen.", "Check FTP read access and the uploaded archive's integrity; do not force another upload."),
    "program_activate": ("Programm aktivieren", "Activate program", "Miniserver-Zustand und vorgemerkte Programme mit dem Errichter prüfen, bevor erneut aktiviert wird.", "Check Miniserver state and staged programs with the installer before another activation."),
    "activation_verify": ("Aktivierung kontrollieren", "Check activation", "Aktives Projekt und Aktivierungszustand prüfen. Eine gesperrte Wiederholung nicht ungeprüft freigeben.", "Check the active project and activation state. Do not release a blocked retry without verification."),
}

# Explicit internal conditions, never inferred by matching an exception message.
REASONS = {
    "ARCHIVE_INVALID_ZIP": ("Die heruntergeladene Datei ist kein lesbares ZIP-Archiv.", "The downloaded file is not a readable ZIP archive."),
    "ARCHIVE_DUPLICATE_ENTRIES": ("Das ZIP enthält mehrfach vorhandene Dateieinträge; eine sichere Zuordnung ist nicht möglich.", "The ZIP contains duplicate file entries; safe selection is not possible."),
    "ARCHIVE_PROGRAM_MISSING": ("Im ZIP wurde keine erwartete sps-Programmdatei gefunden.", "The ZIP contains no expected sps program file."),
    "ARCHIVE_MULTIPLE_PROGRAMS": ("Das ZIP enthält mehrere sps-Programmdateien (Gateway/Client-Verbund). Die automatische Einrichtung ist dafür nur mit der Beta-Option „UDP auch im Gateway/Client-Verbund“ freigegeben; ohne sie bleibt das Programm unverändert.", "The ZIP contains multiple sps program files (Gateway/Client system). Automatic setup is only enabled for it with the beta option “UDP also in a Gateway/Client system”; without it the program stays unchanged."),
    "ARCHIVE_PROJECT_MISSING": ("Das Verbund-Archiv enthält kein Gesamtprojekt sps.Loxone; ohne Gesamtprojekt lassen sich die Programme nicht konsistent ändern.", "The gateway archive lacks the full project sps.Loxone; without it the programs cannot be changed consistently."),
    "ARCHIVE_REQUIRED_FILES_MISSING": ("Im ZIP fehlen Begleitdateien, die unsere Sicherheitsprüfung voraussetzt. Das beweist kein beschädigtes Kundenprojekt; der Archivaufbau kann abweichen.", "The ZIP lacks companion files required by our safety check. This does not prove project corruption; the archive layout may differ."),
    "ARCHIVE_SIZE_LIMIT": ("Die entpackte Gesamtgröße überschreitet das Sicherheitslimit von 64 MiB.", "The total uncompressed size exceeds the 64 MiB safety limit."),
    "ARCHIVE_CHECKSUM_MISMATCH": ("Die ZIP-Integritätsprüfung meldet einen beschädigten Dateieintrag.", "The ZIP integrity check reports a corrupt file entry."),
    "HA_VALUES_PORT_IN_USE": ("Der UDP-Port 55556 für HA-Werte wird im Programm bereits von einem anderen virtuellen UDP-Eingang benutzt.", "UDP port 55556 for HA values is already used by another virtual UDP input in the program."),
    "PROGRAM_FORMAT_UNSUPPORTED": ("Das Programmformat ist für automatische Bearbeitung nicht freigegeben.", "The program format is not approved for automatic editing."),
    "UPLOAD_SIZE_MISMATCH": ("Das zurückgelesene Archiv überschreitet die erwartete Größe.", "The archive read back exceeds the expected size."),
    "UPLOAD_CHECKSUM_MISMATCH": ("Die Prüfsumme des zurückgelesenen Uploads stimmt nicht überein.", "The uploaded archive's read-back checksum does not match."),
    "BACKUP_CHECKSUM_MISMATCH": ("Die Überprüfung einer Sicherungsdatei ist fehlgeschlagen.", "Verification of a backup file failed."),
    "SOURCE_PROGRAM_CHANGED": ("Das Quellprogramm hat sich während der Einrichtung geändert; dieser Upload wurde nicht aktiviert.", "The source program changed during setup; this upload was not activated."),
    "CLIENT_UNREACHABLE": ("Ein Client-Miniserver antwortet nicht. Der Upload wurde nicht gestartet, damit kein Client mit veraltetem Programm zurückbleibt.", "A client Miniserver does not answer. The upload was not started so that no client is left with an outdated program."),
    "PROGRAM_UPLOAD_PENDING": ("Ein anderes Programm ist bereits zur Aktivierung vorgemerkt.", "Another program is already staged for activation."),
    "SETUP_STOPPED": ("Die Integration wird beendet; der Upload wurde nicht aktiviert.", "The integration is unloading; the upload was not activated."),
    "ACTIVATION_REJECTED": ("Der Miniserver hat den angeforderten Programmneustart nicht bestätigt.", "The Miniserver did not acknowledge the requested program restart."),
    "ACTIVATION_UNCONFIRMED": ("Die Aktivierung wurde noch nicht anhand des aktiven Programms bestätigt.", "Activation has not yet been confirmed against the active program."),
    "ACTIVATION_CLEANUP_UNCONFIRMED": ("Aktivierung und Bereinigung sind unbestätigt.", "Activation and cleanup are unconfirmed."),
    "PREVIOUS_ATTEMPT_BLOCKED": ("Ein früherer Versuch sperrt die Wiederholung; dessen Fehlerdetails sind nicht verfügbar.", "An earlier attempt blocks repetition; its error details are unavailable."),
    "TEMPORARY_CLEANUP_UNCONFIRMED": ("Die Bereinigung der temporären Upload-Datei ist unbestätigt. Temporäre ha_udp_*.tmp-Dateien in /prog durch den Errichter prüfen lassen.", "Cleanup of the temporary upload file is unconfirmed. Have the installer check temporary ha_udp_*.tmp files in /prog."),
}
SAFE_TYPES = frozenset({"Exception", "OSError", "ValueError", "RuntimeError", "TimeoutError", "ConnectionError", "ConnectionRefusedError", "ConnectionResetError", "ConnectionAbortedError", "BrokenPipeError", "PermissionError", "FileNotFoundError", "IsADirectoryError", "NotADirectoryError", "UnicodeDecodeError", "UnicodeEncodeError", "KeyError", "IndexError", "AttributeError", "TypeError", "JSONDecodeError", "BadZipFile", "LargeZipFile", "ParseError", "error_perm", "error_temp", "error_reply", "error_proto", "SSLError", "SSLCertVerificationError", "SSLEOFError", "gaierror", "RemoteDisconnected", "IncompleteRead", "ActivationUncertainError"})


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def coded_error(code, message, kind=OSError):
    error = kind(message)  # Only fixed internal messages; never a server response.
    error.udp_code = code
    return error


def failure(step, error=None, *, code=None, timestamp=None):
    """Create only allowlisted data; the raw exception is never stringified."""
    step = step if step in STEPS else "program_download"
    code = code or getattr(error, "udp_code", None)
    if code not in REASONS:
        suffix = "TIMEOUT" if isinstance(error, TimeoutError) else "FAILED"
        if isinstance(error, OSError) and error.errno == errno.ENOSPC:
            suffix = "NO_SPACE"
        code = step.upper() + "_" + suffix
    name = type(error).__name__ if error is not None else "Exception"
    data = {"code": code, "step": step, "exception_type": name if name in SAFE_TYPES else "Exception", "timestamp": timestamp or utc_now()}
    extra = safe_archive_details(getattr(error, "archive_details", None))
    if extra:
        data["archive_details"] = extra
    description, check = details(data, "en")
    return dict(data, description=description, next_check=check)


def details(data, language):
    de = language == "de"
    code, step = data["code"], data["step"]
    if code in REASONS:
        description = REASONS[code][0 if de else 1]
    elif code.endswith("_TIMEOUT"):
        description = "Der Schritt wurde nicht innerhalb des Zeitlimits abgeschlossen; die Ursache ist nicht bestätigt." if de else "The step did not complete within the timeout; the cause is unconfirmed."
    elif code.endswith("_NO_SPACE"):
        description = "Das Betriebssystem meldet keinen verfügbaren Speicherplatz." if de else "The operating system reports no space left."
    else:
        description = "Der Schritt ist fehlgeschlagen; eine genauere Ursache ist nicht bestätigt." if de else "The step failed; a more specific cause is unconfirmed."
    if step == "archive_check" and code.startswith("ARCHIVE_"):
        extra = safe_archive_details(data.get("archive_details"))
        missing = extra.get("missing_required_files", [])
        if missing:
            description += (" Fehlende Pflichtdateien: " if de else " Missing required files: ") + ", ".join(missing) + "."
        return description, ("Archivaufbau anhand der Diagnosedaten prüfen; bei Master-/Client-Verbund die Programmzuordnung klären. Schutzprüfung nicht umgehen." if de else "Check archive layout using diagnostics; clarify program ownership in a master/client installation. Do not bypass the safety check.")
    return description, STEPS[step][2 if de else 3]


def safe_archive_details(value):
    """Only counts and known required names, never customer filenames/content."""
    if not isinstance(value, dict):
        return {}
    result = {k: value[k] for k in ("entry_count", "program_file_count")
              if type(value.get(k)) is int and 0 <= value[k] <= 1000000}
    missing = value.get("missing_required_files")
    if isinstance(missing, list):
        result["missing_required_files"] = sorted({n for n in missing if isinstance(n, str) and n in {"LoxAPP3.json", "permissions.bin", "Emergency.LoxCC", "Music.json", "sps.Loxone"}})
    return result


def restore_failure(value):
    """Validate persisted fields and regenerate prose; never trust journal text."""
    if not isinstance(value, dict) or not isinstance(value.get("step"), str) or value["step"] not in STEPS:
        return None
    step, code = value["step"], value.get("code")
    if not isinstance(code, str):
        return None
    if code not in REASONS and code not in {step.upper() + "_" + s for s in ("FAILED", "TIMEOUT", "NO_SPACE")}:
        return None
    timestamp = value.get("timestamp")
    if timestamp is not None:
        try:
            parsed = datetime.fromisoformat(timestamp)
            if parsed.tzinfo is None:
                return None
            timestamp = parsed.isoformat()
        except (ValueError, TypeError):
            return None
    name = value.get("exception_type")
    data = {"code": code, "step": step, "timestamp": timestamp, "exception_type": name if isinstance(name, str) and name in SAFE_TYPES else "Exception"}
    extra = safe_archive_details(value.get("archive_details"))
    if extra:
        data["archive_details"] = extra
    description, check = details(data, "en")
    return dict(data, description=description, next_check=check)


class SetupTrace:
    """One executor-local observation, with no provisioning decisions."""
    def __init__(self, progress=None):
        self.step = "program_download"
        self.progress = progress
        self.backup = None
        self.journal_path = None
        self.journal = None
        self.attempt = None
        self.cleanup_warning = None
        self.activation_error = None
        self.source_program = None

    def mark(self, step):
        self.step = step
        if self.progress:
            self.progress({"step": step, "backup_verified": self.backup is not None, **({"backup": self.backup} if self.backup else {})})


TRACE = ContextVar("loxone_udp_setup_trace", default=None)


def mark(step):
    trace = TRACE.get()
    if trace:
        trace.mark(step)


def notification(data, language="en", blocked=False):
    data = restore_failure(data)
    de = language.startswith("de")
    if data is None:
        data = failure("activation_verify", code="PREVIOUS_ATTEMPT_BLOCKED")
    description, check = details(data, "de" if de else "en")
    title = ("Automatische UDP-Einrichtung gesperrt. Ursprünglicher Fehler:" if blocked else "Automatische UDP-Einrichtung fehlgeschlagen.") if de else ("Automatic UDP setup is blocked. Original error:" if blocked else "Automatic UDP setup failed.")
    result = f"{title}\n\n{'Schritt' if de else 'Step'}: {STEPS[data['step']][0 if de else 1]}\n\n{'Fehler' if de else 'Error'}: {data['code']}\n\n{'Ausnahmetyp' if de else 'Exception type'}: {data['exception_type']}\n\n{description}\n\n{check}"
    if data["code"] == "ACTIVATION_CLEANUP_UNCONFIRMED":
        result += ("\n\nAuf dem Miniserver kann /prog/sps_new.zip liegen und beim nächsten Neustart geladen werden. Vor einem Neustart durch den Errichter prüfen lassen." if de else "\n\n/prog/sps_new.zip may remain on the Miniserver and load on its next restart. Have the installer check this before restarting.")
    return result + ("\n\nFehlgeschlagene Aktivierungsversuche bleiben für automatische Wiederholungen gesperrt." if de else "\n\nFailed activation attempts remain blocked from automatic repetition.")
