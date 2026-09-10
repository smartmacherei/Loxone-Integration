# Diagnose der automatischen UDP-Einrichtung

Die Diagnose ergänzt den bestehenden Einrichtungsablauf. Die Anzahl und Reihenfolge
der Uploads, Aktivierungsaufrufe, Wiederholungen und Bereinigungsversuche bleiben
unverändert. Es gibt keine automatische Freigabe einer Aktivierungssperre.

## Schritte und Fehlerdaten

Die Schritte sind `program_download`, `archive_check`, `program_format`,
`udp_destination`, `program_prepare`, `backup_write`, `backup_verify`,
`ftp_connect`, `ftp_tls`, `ftp_login`, `upload`, `upload_verify`,
`program_activate` und `activation_verify`.

`udp_errors.py` erzeugt ausschließlich kontrollierte Meldungen. Jeder Fehler enthält
`code`, `step`, `exception_type`, `timestamp`, `description` und `next_check`.
Unbekannte Ursachen erhalten einen schrittbezogenen `*_FAILED`-Code. Zeitüberschreitungen
erhalten `*_TIMEOUT`; daraus wird keine Firewall- oder Berechtigungsursache abgeleitet.
Exception-Texte, Serverantworten und Tracebacks werden nicht in die Meldungen übernommen.
Nicht freigegebene Exception-Klassennamen werden als `Exception` ausgegeben.

Der UDP-Status und die Integrationsdiagnose enthalten `error_code`, `error_step`,
`error_timestamp` und die strukturierten Daten unter `error`. Die Uhrzeit ist UTC.
Nach bestätigter Wiederherstellung verschwinden die aktuellen Fehlerattribute.
Ein im Speicher erhaltener früherer Fehler steht ausschließlich als
`last_error` mit `historical: true` zur Verfügung.
Entsprechend werden frühere Zusatzmeldungen als `last_cleanup_warning` bzw.
`last_activation_error` gekennzeichnet. Ein Fehler während der Aktivierung bleibt
unter `activation_error` erhalten, wenn zusätzlich die Bereinigung scheitert.

Ein bereits angelegtes Aktivierungsjournal wird um sichere Fehlerdaten ergänzt.
Ein blockierter Versuch kann damit auch nach einem HA-Neustart seine ursprüngliche
Ursache anzeigen. Bei älteren Journalen ohne Fehlerdetails ist der ursprüngliche
Fehlerzeitpunkt unbekannt (`null`). Kann die Ergänzung nicht gespeichert werden,
wird dies gemeldet; die bestehende Sperre bleibt erhalten.

`backup_location` bezeichnet zunächst nur den vorgesehenen Speicherort.
Erst nach vollständiger Überprüfung der Sicherung wird `backup_verified: true`
gesetzt und `backup` als verifizierte Datei angezeigt. Während der Einrichtung
bleibt der Status `checking`; Datenempfang allein bestätigt keine Einrichtung.
Der Sensor weist den Einrichtungszustand zusätzlich unter `setup_state` aus.

Unbestätigte Bereinigung einer temporären Upload-Datei wird separat als
`cleanup_warning` gemeldet. Bei unbestätigter Aktivierung und Bereinigung bleibt
der Hinweis auf eine möglicherweise vorhandene `/prog/sps_new.zip` erhalten.
Auch eine FTP-Antwort 550 bestätigt deren Abwesenheit nicht eindeutig; die
Diagnose meldet in diesem Fall Unsicherheit, ohne zusätzliche Fernzugriffe.
Die Integrationsdiagnose enthält kein ungefiltertes `LoxAPP3.json` mehr, da dieses
private Projektinformationen enthalten kann.

## Meldungsbeispiele

Die Sprache richtet sich nach der HA-Konfigurationssprache (Deutsch, sonst Englisch).

> Automatische UDP-Einrichtung fehlgeschlagen.\
> Schritt: FTP-Anmeldung\
> Fehler: FTP_LOGIN_FAILED\
> Ausnahmetyp: error_perm\
> Der Schritt ist fehlgeschlagen; eine genauere Ursache ist nicht bestätigt.\
> Bitte prüfen, ob der in der Integration hinterlegte Benutzer FTP-Zugriff besitzt
> und die Zugangsdaten stimmen.

> Automatische UDP-Einrichtung fehlgeschlagen.\
> Schritt: Programm herunterladen\
> Fehler: PROGRAM_DOWNLOAD_TIMEOUT\
> Ausnahmetyp: TimeoutError\
> Der Schritt wurde nicht innerhalb des Zeitlimits abgeschlossen; die Ursache ist
> nicht bestätigt.\
> Erreichbarkeit und HTTP-Zugriff des Integrationsbenutzers auf den Miniserver prüfen.

> Automatic UDP setup is blocked. Original error:\
> Step: Verify upload\
> Error: UPLOAD_CHECKSUM_MISMATCH\
> Exception type: OSError\
> The uploaded archive's read-back checksum does not match.\
> Check FTP read access and the uploaded archive's integrity; do not force another upload.

## Lokale Prüfung

Ab Version 1.4.5 unterscheidet die Archivprüfung folgende Fehler:

| Fehlercode | Bestätigte Feststellung |
| --- | --- |
| `ARCHIVE_INVALID_ZIP` | Die heruntergeladene Datei lässt sich nicht als ZIP öffnen. |
| `ARCHIVE_PROGRAM_MISSING` | Keine erwartete sps-Programmdatei gefunden. |
| `ARCHIVE_MULTIPLE_PROGRAMS` | Mehrere sps-Programmdateien gefunden; automatische Auswahl nicht unterstützt. |
| `ARCHIVE_DUPLICATE_ENTRIES` | Dateieinträge kommen mehrfach vor. |
| `ARCHIVE_REQUIRED_FILES_MISSING` | Von der Sicherheitsprüfung geforderte Begleitdateien fehlen. |
| `ARCHIVE_SIZE_LIMIT` | Entpackte Gesamtgröße überschreitet 64 MiB. |
| `ARCHIVE_CHECKSUM_MISMATCH` | Die ZIP-Integritätsprüfung hat einen beschädigten Eintrag gefunden. |

`archive_details` enthält nur Dateizähler und gegebenenfalls fehlende Namen aus
der festen Liste `LoxAPP3.json`, `permissions.bin`, `Emergency.LoxCC`, `Music.json`.
Andere Dateinamen und Inhalte werden nicht übernommen. Fehlende Begleitdateien
beweisen kein beschädigtes Kundenprojekt: Der Archivaufbau kann abweichen.
Diese Fehler entstehen vor Sicherung, FTP-Anmeldung und Upload.

Beispiel: **Schritt: Archiv prüfen · Fehler: ARCHIVE_REQUIRED_FILES_MISSING ·
Fehlende Pflichtdateien: Music.json.**

English: **Step: Check archive · Error: ARCHIVE_MULTIPLE_PROGRAMS · The ZIP
contains multiple sps program files. Automatic setup currently requires exactly
one; master/client ownership is unconfirmed.**

### Tests

`python -m pytest tests -q`

Die Tests verwenden künstliche Projektarchive und simulierte Netzwerkgrenzen.
Sie greifen nicht auf einen Live-Miniserver oder eine HA-Installation zu.
