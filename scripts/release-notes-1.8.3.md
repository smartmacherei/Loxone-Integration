Host-Bereinigung, Vorauswahl gleichnamiger Bereiche, alte Tor-Bausteine als Beschattung.

Problem: Mit `http://192.168.178.123/` im Feld **Host** schlug die Einrichtung fehl. Die Verbindung fragte `//jdev/cfg/apiKey` an, der Miniserver antwortete 404 „There seems to be no Webinterface available on your Miniserver“, die Integration zeigte „Unrecognized command“. Programm-Download, Absenderfilter für UDP-Pakete und der Sender für Weg 3 nutzen den Host ebenfalls direkt und hätten mit so einer Adresse auch nicht funktioniert.

**Korrektur (mit 1.8.4):** Diese Notes führten den an der Anlage beobachteten Abbruch `PROGRAM_DOWNLOAD_FAILED` (OSError) auf den Host zurück. Das war falsch: Der Host war zu dem Zeitpunkt schon sauber, der Miniserver hat den Programm-Download mit HTTP 403 abgelehnt, weil dem Benutzer die Rechte fehlten. Seit 1.8.4 heißt dieser Fall `MINISERVER_ACCESS_DENIED` und nennt die nötigen Rechte.

Änderung:

- **Host wird bereinigt:** beim Speichern im Dialog und einmal beim Laden bestehender Einträge. `http://`, Schrägstrich am Ende und Leerzeichen fallen weg, ein Port in der Adresse geht ins Feld **Port**. `https://` mit Port 443 wird zu Host + Port 443; mit anderem Port bleibt `https://` stehen. Ein sauberer Host bleibt unverändert (der Sicherungsordner hängt am Host).
- **Vorauswahl gleichnamiger Bereiche:** Die Raumzuordnung wählt für Räume ohne Zuordnung den HA-Bereich mit gleichem Namen vor. Leer gelassene Räume werden gemerkt (`room_area_unmapped`) und nicht wieder vorausgewählt. Vor 1.8.3 gespeicherte Zuordnungen bekommen keine Namens-Vorauswahl, bis einmal mit 1.8.3 gespeichert wurde.
- **Alte Tor-Bausteine als Beschattung:** Ein `Gate` in einer Loxone-Kategorie vom Typ Beschattung erscheint als Jalousie statt als Garagentor. Anlass: An einer echten Anlage fahren sechs Torsteuerungen V1 die Raffstores im Wohnzimmer.

Wichtig:

- Bei einem Eintrag mit Browser-Adresse ändert sich durch die Bereinigung der Sicherungsordner unter `/config/loxone_backups/` (er wird aus dem Host abgeleitet). Ein dort bereits angelegter alter Ordner bleibt liegen.

Validierung: 313 Tests bestanden (davon die HA-Tests gegen Home Assistant 2026.10.2), 1 fehlgeschlagen: `test_actual_registries_persist_mapping_and_protect_user_edit` scheitert dort mit „Frame helper not set up“ an einer Veralterungsmeldung von HA 2026.10. Der Test schlägt mit dem unveränderten Code von 1.8.2 genauso fehl, er hängt nicht an dieser Version. Neu: Bereinigung von Browser-Adressen, unveränderter sauberer Host, Speichern des bereinigten Hosts im Einrichtungsdialog, Vorauswahl gleichnamiger Bereiche, kein erneutes Vorauswählen leer gelassener Räume, keine Namens-Vorauswahl bei Zuordnungen vor 1.8.3, Tor in Beschattungs-Kategorie als Jalousie. Offline gegen die Strukturdatei und das Programm einer echten Anlage geprüft (sechs Torsteuerungen V1 in der Kategorie Beschattung). In einer laufenden Anlage ist 1.8.3 noch nicht gelaufen.
