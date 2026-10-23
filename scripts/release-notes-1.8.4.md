Klare Meldung, wenn der Miniserver dem Benutzer den Zugriff verweigert.

Problem: An einer echten Anlage brach die automatische UDP-Einrichtung mit `PROGRAM_DOWNLOAD_FAILED` (OSError) ab, „eine genauere Ursache ist nicht bestätigt“. Tatsächlich hatte der Miniserver `/dev/fslist/prog` mit HTTP 403 abgelehnt: Die Anmeldung war gültig, aber dem HA-Benutzer fehlten die Rechte für das Programm. Die Meldung empfahl nur, Erreichbarkeit und HTTP-Zugriff zu prüfen.

Änderung:

- **HTTP 403** beim Lesen des Programms ergibt `MINISERVER_ACCESS_DENIED` mit Ausnahmetyp `PermissionError`. Die Meldung sagt, dass die Anmeldung gültig ist und Rechte fehlen, und nennt sie: in Loxone Config der Benutzergruppe „Web-Interface / Apps“, „FTP“ und „Loxone Config“ geben (geprüft: Gruppe „Vollzugriff“), in den Miniserver speichern, Integration neu laden.
- **HTTP 401** ergibt `MINISERVER_LOGIN_REJECTED`: Benutzername und Passwort abgleichen.
- Andere HTTP-Fehler behalten den bisherigen Code. Serverantworten landen weiterhin nicht in der Meldung.
- **Korrektur der Notes zu 1.8.3:** Dort war der Abbruch `PROGRAM_DOWNLOAD_FAILED` dem Host zugeschrieben. Der Host war zu dem Zeitpunkt schon sauber; Ursache war der 403.

Wichtig:

- Die Meldung behebt das Rechteproblem nicht, sie benennt es. Die Rechte vergibt man in Loxone Config.

Validierung: 316 Tests bestanden (davon die HA-Tests gegen Home Assistant 2026.10.2), 1 fehlgeschlagen: `test_actual_registries_persist_mapping_and_protect_user_edit` scheitert dort seit 1.8.2 unverändert an einer Veralterungsmeldung von HA 2026.10 („Frame helper not set up“). Neu: HTTP 403 und 401 beim Programm-Download ergeben eigene Codes mit passender Empfehlung, beide überstehen den Neustart im Journal, andere HTTP-Fehler behalten den bisherigen Code, keine Serverantwort in der Meldung.
