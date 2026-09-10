# Verbindung prüfen und Diagnosedaten herunterladen

1. Nach dem Update HA neu starten.
2. **Einstellungen → Geräte & Dienste → Loxone → Miniserver-Gerät** öffnen.
3. Unter Diagnose **Verbindung prüfen** drücken. Während einer laufenden
   automatischen UDP-Einrichtung wartet man deren Abschluss ab.
4. Die Ergebnisse stehen anschließend in einer HA-Benachrichtigung.
5. Im Menü der Integration **Diagnosedaten herunterladen** wählen und die Datei
   zusammen mit HA-Version und ungefährer Fehlerzeit weitergeben.

Wenn die Integration nicht vollständig startet, ist die Prüfung auch über
**Entwicklerwerkzeuge → Aktionen → Loxone: Miniserver-Verbindung prüfen** möglich.
Dort den vorhandenen Loxone-Konfigurationseintrag auswählen.

Der Download selbst führt keine Netzwerkprüfung durch. Er enthält den aktuellen
Zustand und die letzte ausdrücklich gestartete Prüfung mit deren Zeitpunkt.

## Was geprüft wird

| Ergebnis | Aussage |
| --- | --- |
| `WEB_CONNECTED` | Der konfigurierte HTTP-/HTTPS-Port ist erreichbar. |
| `WEB_ACCESS_ACCEPTED` | Der Abruf mit dem konfigurierten Benutzer wurde mit HTTP 200 beantwortet. |
| `HTTP_LOGIN_REJECTED` | HTTP 401: Die Anmeldung wurde abgelehnt. Miniserver-Zugang statt HA-Zugang verwenden. |
| `MINISERVER_IDENTIFIED` | Die Antwort enthält eine Loxone-Struktur mit Miniserver-Informationen. |
| `FTP_CONNECTED` | Der FTP-Dienst auf Port 21 antwortet. |
| `FTP_LOGIN_ACCEPTED` | Der FTP-Server hat die Anmeldung akzeptiert. |
| `FTP_LOGIN_REJECTED` | FTP 530: Anmeldung/Zugriff wurde abgelehnt. |
| `FTP_DIRECTORY_READABLE` | Verzeichnisabfrage von `/prog` und passiver FTP-Datenkanal funktionieren. |
| `CONNECTION_REFUSED` | Die Verbindung wurde abgewiesen; Dienst/Port prüfen. |
| `TIMEOUT` | Zeitlimit erreicht. Eine konkrete Netzwerk- oder Firewallursache ist nicht bestätigt. |

Eine erfolgreiche Leseprüfung beweist keine FTP-Schreibrechte. Es werden keine
Testdateien hochgeladen, keine Programme geändert und keine Neustarts ausgelöst.
Die Prüfung verwendet den eingestellten Webport und FTP 21; sie durchsucht nicht
alle Ports und ändert keine Zugangsdaten oder Wiederholungssperren.

Für UDP werden vorhandener Listener, konfigurierter Empfangsport, Paketanzahl und
Alter des letzten gültigen Pakets erfasst. Ohne Daten lässt sich allein daraus
nicht entscheiden, ob Sender, Zieladresse, Route oder Firewall verantwortlich ist.
Es wird kein zweiter UDP-Listener geöffnet und kein Testpaket gesendet.

## Start- und Fehlerverlauf

`integration_startup` enthält den letzten Startversuch, beispielsweise
`http_structure`, `websocket_connect`, `area_mapping` oder `entity_platforms`.
Bei einem Abbruch bleiben Schritt, Fehlercode, sicherer Exception-Typ und Zeitpunkt
gespeichert. Ein erfolgreich abgeschlossener neuer Start ersetzt den aktuellen
Fehler. Aus dem Speicher geladene ältere Startdaten tragen `historical: true`.

`connection.current` zeigt den aktuellen WebSocket- und UDP-Zustand.
Ab Version 1.4.5 enthält `integration_startup.platforms` zusätzlich den Status
der einzelnen Entitätsplattformen, zum Beispiel `sensor`. Ein abgefangener
Plattformfehler führt zu `state: partial`, `ENTITY_PLATFORMS_FAILED` und einer
Liste `failed_platforms`. Der Plattformdatensatz nennt Fehlercode, sicheren
Exception-Typ und Zeitpunkt. Ein erfolgreicher erneuter Plattformstart bereinigt
diesen aktuellen Fehler. Das bestätigt die Einrichtung der Plattform, nicht die
Erreichbarkeit jedes angeschlossenen Geräts.

`connection.last_explicit_check` enthält die letzte bewusste Verbindungsprüfung;
deren Resultat kann älter als der aktuelle Zustand sein. `udp_setup.step_history`
enthält bis zu 50 Schrittwechsel des aktuellen UDP-Einrichtungsversuchs.

Für zusätzliche Schrittprotokolle unter **Entwicklerwerkzeuge → Aktionen** nur
die neuen Diagnose-Logger aktivieren:

```yaml
action: logger.set_level
data:
  custom_components.loxone.udp_setup: debug
  custom_components.loxone.connection_probe: debug
  custom_components.loxone.startup_trace: debug
```

Nach der Aufzeichnung die drei Werte wieder auf `info` setzen. Damit werden
gezielt die sicheren Diagnosemeldungen erfasst, ohne vollständige
Protokollnachrichten der älteren API-Bibliothek einzuschalten.
Der Diagnose-Download ist für die erste Analyse vorzuziehen: Er enthält keine
vollständigen Projektdateien, Passwörter, Tokens oder rohen Serverantworten.

## English

Use the Miniserver device's **Check connection** diagnostic button or the
`loxone.check_connection` action with an existing Loxone config entry. Results
appear in a notification and the integration diagnostics download. The download
itself does not run tests. Checks are read-only: configured HTTP(S) port, web
access, Loxone structure, FTP 21, TLS, login and directory listing/data channel.
No write-permission test, uploads, restarts or retry unlocks are performed.
UDP status is observed from the existing receiver. Missing packets do not prove
a firewall failure. Startup history and the last explicit check survive restart;
the current WebSocket/UDP status is reported separately.
