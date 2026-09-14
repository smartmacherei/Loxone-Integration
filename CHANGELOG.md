# Changelog

Alle nennenswerten Änderungen an dieser Integration.
Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionierung nach [Semantic Versioning](https://semver.org/lang/de/).

## [Unveröffentlicht]

- Tür-, Fenster- und Toröffnungskontakte übernehmen die Statustexte aus Loxone: Steht dort
  1 = „Geschlossen“ und 0 = „Offen“ (auch „closed/open“, „zu/auf“), zeigt HA die Entität
  jetzt passend zur Klasse, also „geschlossen“ bei Wert 1. Erkannte Klemmen bringen ihre
  Statustexte aus Config mit; ohne Texte bleibt alles wie bisher.
- Weg 3, HA → Loxone: Entitäten mit dem Label „loxone“ werden per Knopf „HA-Werte ins
  Programm übernehmen“ als virtueller UDP-Eingang „HA Werte“ (Port 55556) mit einem
  Befehl je Wert ins Programm des Gateways bzw. des einzigen Miniservers geschrieben;
  Zustandsänderungen gehen als UDP-Pakete raus, alle Werte zusätzlich alle 5 Minuten und
  nach jedem Programmwechsel. Neuer Diagnose-Sensor „HA → Loxone“ mit den wartenden
  Änderungen. Ohne Knopfdruck ändert sich am Programm nichts. Weg 3 setzt Weg 2 voraus.
  Neuer Fehlercode `HA_VALUES_PORT_IN_USE`.
- Batterie und Geräteinterna (Online-Status, Schutzabschaltungen, Systemtemperatur)
  belegen keinen UDP-Platz mehr, auch nicht einen der 5 je Miniserver im
  Gateway/Client-Verbund. Die Plätze bleiben für Taster und Kontakte. Bestehende
  Einrichtungen ändern sich erst, wenn Loxone Config das nächste Mal speichert.
- Diese Klemmen werden, sobald in HA aktiviert, alle 4 Stunden per HTTP gelesen statt
  alle 30 Sekunden, und verfallen nicht als „nicht verfügbar“. Der Startwert kommt
  weiter beim Setup.

## [1.7.0b2] - 2026-09-14 (Vorabversion)

- Das Neuladen der Integration nach dem Speichern der Optionen schlug seit 1.6.0 fehl
  („a coroutine was expected“). Der Eintrag blieb in „Entladen fehlgeschlagen“, die
  Entitäten wurden nicht mehr versorgt und geänderte Optionen, auch die Beta-Option für
  den Gateway/Client-Verbund, kamen nie an. Behoben; Optionen wirken wieder sofort.
- Analoge Klemmen, für die der Miniserver keinen Wert liefert (NaN), melden sich als
  „nicht verfügbar“, statt bei jedem Update einen Fehler ins Protokoll zu schreiben.

## [1.7.0b1] - 2026-09-11 (Vorabversion)

- Beta: UDP-Einrichtung auch im Gateway/Client-Verbund, nur mit der neuen Option
  „Beta: UDP auch im Gateway/Client-Verbund einrichten“ (Vorgabe aus). Ohne die Option
  bleibt alles wie in 1.6.x: Verbund-Archive werden nicht angefasst.
- Mit der Option bekommt jeder Miniserver in seinem eigenen Programm einen eigenen Logger
  und eine Seite „HA UDP“, dazu ein eigenes Lebenszeichen, das unter der Miniserver-UUID
  gesendet wird. Fällt ein Client aus, wechseln nur dessen Klemmen auf Abfrage.
- Gesamtprojekt und alle Teilprogramme werden gleich geändert; das Archiv wird nur auf
  das Gateway gespielt, das die Teilprogramme nach dem Neustart an die Clients verteilt.
- Begrenzung für den ersten Feldtest: höchstens 5 Klemmen je Miniserver, nur solche, die
  in HA eingeschaltet starten. Die globale Höchstzahl gilt weiterhin zuerst.
- Programmformat 174 (Config 16.x) wird nur auf diesem Beta-Weg akzeptiert.
- Neuer Fehlercode `ARCHIVE_PROJECT_MISSING`; `ARCHIVE_MULTIPLE_PROGRAMS` verweist auf
  die Beta-Option. Diagnose zeigt je Miniserver, ob sein Lebenszeichen ankommt.
- Noch nicht an echter Hardware geprüft.

## [1.6.3] - 2026-09-11

- Die von der Integration angelegte Seite und der Logger im Miniserver-Programm
  heißen jetzt „HA UDP". Bestehende Anlagen mit dem Namen „HA UDP (smartmacherei)"
  werden weiter erkannt und nicht angefasst; der neue Name kommt erst, wenn die
  Seite ohnehin neu aufgebaut wird, etwa nach einer Programmänderung.

## [1.6.2] - 2026-09-11

- In Home Assistant deaktivierte Entitäten werden nicht mehr abgefragt. Die Auswahl,
  was der Miniserver beantworten muss, liegt damit beim Nutzer: Entität abschalten,
  Abfrage entfällt ab dem nächsten Zyklus; wieder einschalten, Abfrage läuft wieder.
- Geräteinterna werden als Diagnose deaktiviert angelegt: Online-Status je Gerät,
  Übertemperatur- und Unterspannungsabschaltung, interne Temperaturen und
  Rohformate. Sie belegen weder Entität noch Abfrage, bis jemand sie einschaltet.
  Batteriewerte bleiben aktiv, aber in der Diagnose-Kategorie. Bestehende
  Entitäten werden nicht verändert; die Vorgabe gilt nur für neu angelegte. Im
  Verbund des Testers betrifft das rund 340 von 1942 erkannten Klemmen.
- Kontrollabfrage bei gesundem UDP- oder WebSocket-Weg alle 30 statt 5 Minuten;
  den Ausfall des Weges meldet das Lebenszeichen ohnehin.

## [1.6.1] - 2026-09-11

- Die Höchstzahl gilt ausdrücklich für alle Wege und steht jetzt oben im Formular:
  zusätzlich erkannte Klemmen als Entitäten, ihre Abfrage, UDP-Logger und künftig
  Signale von Home Assistant nach Loxone. Schlüssel und gespeicherter Wert bleiben.
- Die Abfrage erkannter Klemmen ist unabhängig von der Anzahl gedeckelt: höchstens
  200 Anfragen je 30-Sekunden-Zyklus, höchstens zwei gleichzeitig je Miniserver.
  Große Anlagen werden im Umlauf abgefragt, die am längsten nicht abgefragte Klemme
  zuerst; das Protokoll nennt den daraus folgenden Abstand je Klemme. Werte, die nur
  auf ihre Runde warten, werden nicht als nicht verfügbar markiert.

## [1.6.0] - 2026-09-11

- Gateway/Client-Verbünde: Die Erkennung liest jetzt das Gesamtprojekt `sps.Loxone`
  aus dem Programmarchiv statt der ersten Programmdatei, die je nach Archiv ein
  zufälliger Miniserver war. Klemmen aller Miniserver werden gefunden und je
  Miniserver gruppiert; Klemmen eines Clients werden direkt am Client abgefragt
  (gleiche Zugangsdaten, Adresse aus dem Projekt). Der UDP-Empfänger akzeptiert
  Pakete von allen Miniserver-Adressen. Fehlt `sps.Loxone`, werden die
  Teilprogramme zusammengeführt. An einem Verbund mit vier Miniservern stieg die
  Zahl erkennbarer Klemmen von 306 auf 1942.
- Die Höchstzahl (Vorgabe 500) gilt jetzt für die zusätzlich erkannten Klemmen
  insgesamt: Entitäten, Abfrage und UDP-Logger, in Programmreihenfolge. Die Option
  steht im Formular unter Weg 1; der Schlüssel bleibt, gespeicherte Werte gelten
  weiter. Wird die Grenze erreicht, meldet das Protokoll die gefundene Anzahl.
- Diagnose-Download enthält die Miniserver des Projekts (Name, Rolle, Adresse) und
  die Zahl der direkt am Client abgefragten Klemmen.
- Die automatische UDP-Einrichtung bleibt für Verbünde gesperrt
  (`ARCHIVE_MULTIPLE_PROGRAMS`); die Vorarbeit dazu ist im Loxone-Skill dokumentiert.

## [1.5.0] - 2026-09-11

- Die Integration heißt jetzt schlicht „Loxone“ (Manifest, HACS, Dialogtitel).
  Bestehende Einträge werden beim Start umbenannt. Die Seite im Miniserver-Programm
  behält den Namen „HA UDP (smartmacherei)“, damit eingerichtete Anlagen erkannt bleiben.
- Einrichtungsdialog aufgeräumt: oben die Zugangsdaten, darunter die zwei Wege.
  Weg 1 (HA → Loxone) ist immer aktiv und bündelt Erkennung, Lichtkreise und
  Raumzuordnung. Weg 2 (Loxone → HA) ist die optionale UDP-Echtzeit mit Port und
  neuer Höchstzahl der Signale (Vorgabe 500, einstellbar 1–10000). Klemmen über
  der Grenze bleiben bei der 30-Sekunden-Abfrage; die Grenze schützt Miniserver,
  Netzwerk und HA bei sehr großen Anlagen. Diagnose zeigt Grenze und Anzahl.
- Szenen-Optionen entfernt. Lichtstimmungen bleiben als Effekte der Licht-Entität
  verfügbar (`light.turn_on` mit `effect`). Erzeugte Szenen-Entitäten werden beim
  Update aus dem Register entfernt (Konfigurationsversion 4).
- Weniger Miniserver-Traffic: Die 60-Sekunden-Prüfung liest nur noch das
  Verzeichnislisting; das Programm wird erst nach einem neuen Speichern aus
  Loxone Config erneut heruntergeladen. Bisher wurde das komplette Archiv jede
  Minute geladen, beim Tester 1,5 MB pro Minute über zwei Stunden. Ein
  gleichbleibender Fehler wird nur einmal als Warnung und danach im Debug-Log
  protokolliert.
- Zustandsupdates gehen über den internen Dispatcher statt über das Bus-Ereignis
  `loxone_event`. Damit verschwinden die Recorder-Warnungen „Event data exceed
  maximum size“ und die Datenbank wächst nicht mehr mit jedem Loxone-Wert.
  `loxone_event` wird nicht mehr ausgelöst; Automationen auf Entitätszustände
  umstellen. `loxone_send` und die Dienste sind unverändert.
- Home Assistant 2026.9: Registry-Zugriffe ohne die veraltete Mapping-API. Die
  Bereinigung gelöschter Geräte versteht `config_entry_id` und schützt Eltern von
  Child-Geräten; behebt „Loxone registry cleanup skipped (KeyError)“. Veraltete
  Konstante für ppm ersetzt.
- Gateway/Client-Anlagen: Ein Archiv mit mehreren Programmdateien wird weiterhin
  unverändert gelassen (`ARCHIVE_MULTIPLE_PROGRAMS`), jetzt ohne minütlichen
  Download. Alle übrigen Funktionen (WebSocket, Abfrage) laufen normal.
- README: Haftungsausschluss für die automatische Programmänderung, die zwei
  Wege im Einrichtungsdialog, aktualisierte Grenzen und Einstellungen.

## [1.4.6] - 2026-09-10

- „Diagnosedaten herunterladen“ enthält bei aktiver automatischer UDP-Einrichtung
  jetzt das vollständige Programmarchiv. Nach einem Fehler werden die originalen
  Bytes des fehlgeschlagenen Versuchs beigefügt, selbst bei ungültigem ZIP. So
  kann der Support die Archivprüfung lokal nachvollziehen.
- Ohne gespeicherten Fehlerstand wird das aktuelle Archiv ausschließlich lesend
  heruntergeladen und als neue Aufnahme gekennzeichnet. Größe, Zeitpunkt,
  SHA-256-Prüfsumme und Prüfergebnis stehen neben den Base64-kodierten Daten.
  Das bestehende Limit von 64 MiB bleibt erhalten; Abruffehler werden sicher
  gemeldet und verhindern den übrigen Diagnose-Download nicht.
- Dieser Support-Download enthält bewusst nicht anonymisierte Projektdaten und
  darf nur vertraulich weitergegeben werden. Logs und Statusattribute enthalten
  weiterhin keine Archivdaten. Keine zusätzlichen Uploads, Aktivierungen oder
  Entsperrungen. Nach erfolgreicher Einrichtung wird der Fehlerstand verworfen.
- Support-Werkzeug `scripts/extract_program_archive.py` stellt das Originalarchiv
  aus der Diagnose-JSON wieder her und prüft Größe sowie Prüfsumme.

## [1.4.5] - 2026-09-10

- Startfehler bei Loxone-Zählern behoben: Die gemeinsamen Geräteinformationen
  werden korrekt übernommen. Der Fehler konnte bisher die Einrichtung der
  gesamten Sensorplattform abbrechen.
- UDP-Fehler bei der Archivprüfung werden genauer erklärt: nicht lesbares ZIP,
  fehlende oder mehrere Programmdateien, doppelte Einträge, fehlende
  Begleitdateien, Größenlimit und fehlerhafte Prüfsumme haben eigene Fehlercodes.
  Diagnosedaten nennen sichere Dateizähler und fehlende bekannte Pflichtdateien,
  ohne Kundendateinamen oder Projektinhalte auszugeben.
- Der Diagnose-Download zeigt fehlgeschlagene Entitätsplattformen einzeln.
  Ein teilweise erfolgreicher Start wird als `partial` gekennzeichnet, auch wenn
  Home Assistant den Plattformfehler intern abfängt. Nach erfolgreicher
  Wiederherstellung wird dieser aktuelle Fehler bereinigt.
- Die Sicherheitsprüfung des Archivs bleibt unverändert streng. Es werden keine
  zusätzlichen Uploads oder Miniserver-Neustarts ausgelöst und keine gesperrten
  Versuche automatisch freigegeben. Ein abweichender Archivaufbau wird nicht
  pauschal als beschädigtes Kundenprojekt bezeichnet.

## [1.4.4] - 2026-09-10

- Startfehler aus Kundenlogs behoben: Die Raumzuordnung verwendet ausdrücklich
  Geräte- und Bereichs-IDs. HA-Versionen, deren Register beim Durchlaufen
  Geräteobjekte liefern, führen dadurch nicht mehr zum TypeError beim Start.
- Neuer Diagnoseknopf „Verbindung prüfen“ und Aktion `loxone.check_connection`:
  Prüft die konfigurierte Miniserver-Adresse, den Webport, Webzugriff, FTP-Port 21,
  TLS, FTP-Anmeldung und den lesenden FTP-Datenkanal. Kein Upload, Neustart oder
  automatisches Entsperren. Schreibrechte werden nicht getestet.
- Diagnose-Download enthält den Startverlauf mit letztem erfolgreichen Schritt,
  Fehlercode, sicherem Exception-Typ und Zeitpunkt. Letzte explizite
  Verbindungsprüfung und Startfehler bleiben nach HA-Neustart nachvollziehbar.
- WebSocket-Verbindung und bestätigte Anmeldung werden getrennt erfasst.
  UDP-Port, Listener, Paketzähler und Alter gültiger Daten helfen, Empfangsfehler
  von Einrichtungsfehlern zu unterscheiden. UDP-Setup-Schritte werden zusätzlich
  als begrenzter Verlauf und bei aktiviertem Debug-Logging protokolliert.
- Neue Diagnosemeldungen enthalten keine Passwörter, Tokens, Projektinhalte oder
  rohen Serverantworten. Timeouts werden nicht pauschal als Firewallfehler erklärt.

## [1.4.3] - 2026-09-10

- Die Raumzuordnung ist bei Einrichtung und Konfiguration standardmäßig
  eingeschaltet. Nach dem Verbindungsdialog öffnet sich die gemeinsame Raumliste.
  Zum Überspringen kann der Schalter ausgeschaltet werden. Bereiche werden
  weiterhin erst durch die bestätigte Auswahl zugeordnet.

## [1.4.2] - 2026-09-10

- Raumzuordnung als gemeinsame Liste: Alle Loxone-Räume erscheinen in einem
  Dialog mit jeweils einer HA-Bereichsauswahl. Bestehende Zuordnungen sind
  vorausgewählt. Änderungen werden gemeinsam gespeichert; das X entfernt eine
  Zuordnung. Der bisherige Ablauf mit wiederholter Raumauswahl entfällt.
- Gleichnamige Räume bleiben durch ihre IDs unterscheidbar. Manuelle
  Bereichszuordnungen und das Verhalten der UDP-Einrichtung bleiben unverändert.

## [1.4.1] - 2026-09-10

- Verständliche deutsche und englische Beschriftungen im Einrichtungsdialog:
  Jede Option erklärt jetzt direkt darunter, was sie bewirkt.
- Lichtstimmungen als HA-Szenen, einzelne Lichtkreise und Raumzuordnung werden
  ohne interne Fachbegriffe erklärt. Die Wartezeit betrifft nur das Anlegen der
  Szenen beim Start, nicht das spätere Schalten.
- UDP-Empfangsport und Miniserver-Webport sind klar unterscheidbar. Der Hinweis
  auf Programmänderung und kurzen Logik-Neustart bleibt bei der UDP-Einrichtung.
- Fehlerhafte Formatierung beim UDP-Port behoben (`UNCLOSED_TAG`).
  Nach dem Update HA neu starten und die Browserseite neu laden, damit keine
  alten Übersetzungen oder internen Feldnamen aus dem Cache angezeigt werden.
- Nur Oberflächentexte geändert; Schalt- und Einrichtungsverhalten unverändert.

## [1.4.0] - 2026-09-10

- Add optional Loxone room-to-Home Assistant area mapping during setup and in
  integration options. Store stable IDs, preserve manual assignments, and map
  shared multiroom hardware through entity areas. Removing a mapping retains
  the last placement. Room mapping does not modify the Miniserver program.
- Report automatic UDP setup failures by stage with stable error codes, safe
  German/English explanations and targeted checks. Expose current and historical
  errors in status attributes and diagnostics; retain original errors across
  blocked retries and clear current errors after verified recovery.
- Distinguish setup progress from UDP reception and planned from verified backups.
  Preserve all upload, activation and retry safeguards. Exclude raw project data
  and unsafe exception/server text from diagnostics.

## [1.3.6] - 2026-09-09

- Fix double removal of startup/shutdown event listeners during integration
  reload. Ignore queued events after unload and report normal WebSocket task
  cancellation at debug level instead of as an error.

## [1.3.5] - 2026-09-09

- Reconcile deleted project UUIDs on integration setup/reload. Back up affected
  registry records before removing stale entities and empty devices. Preserve
  offline, disabled, shared and still-loaded devices; skip cleanup when the full
  project cannot be verified or changes during the operation.
- Handle logger inputs disconnected by Loxone Config after deleting their source
  device. Remove only provably integration-generated references to absent signals;
  retain protection against overwriting user content and existing project backups.
- Release startup/shutdown listeners on unload and retain the WebSocket task for
  cleanup, avoiding callbacks to a removed config entry after repeated reloads.

## [1.3.4] - 2026-09-09

- Default new connections to HTTP port 80 instead of 8080. Existing explicitly
  configured ports are preserved. A fresh demo installation timed out on the old
  default; changing its port to 80 restored setup and healthy UDP reception.
- Update English/German setup instructions to match the corrected default.

## [1.3.3] - 2026-09-09

- Fix the live-detected ventilation entity collision: presence, humidity, air
  quality and outdoor temperature now use their proper HA sensor platforms.
  Presence retains its own state UUID while grouping under the ventilation device.
- Remove stale ventilation measurements previously registered as fans.
- Fix cleanup returning a router object during options reload, which HA attempted
  to await and rejected. Cleanup now returns nothing.
- Validated with regression tests and the installed HA 2026.7.2 runtime.
- Installed on demo HA; verified automatic program backup/activation, live UDP
  heartbeat and integration reload without duplicate entities. Physical device
  transition tests and backup restoration remain outstanding.

## [1.3.2] - 2026-09-09 (local test build)

- Resolve equivalent terminal/WebSocket states through explicit project wiring,
  including the supported Tree/Air Wallbox target-power API channel. Never add
  visualization flags or infer signal equivalence from names.
- Correct the verified Wallbox HTTP watts/kW mismatch; reject unresolved display
  placeholders and failed server responses instead of publishing false values.
- Keep quiet WebSocket signals healthy while connected, recover their cached state
  after UDP loss, and expire stale direct-terminal values after all paths fail.
- Reject ambiguous, inverted or scaled source aliases. Preserve verified project
  backups before automatic program changes.
- Live read checks: 1,129 of 1,213 terminal endpoints returned usable values;
  all 24 mapped WebSocket terminals received states, including both Wallboxes.
  Isolated HA runtime validation covers 1,213 terminals and 332 additional states.
  Physical transitions, activation/restart and restoration remain pending.

## [1.3.1] - 2026-09-09 (local test build)

- Extend direct discovery and grouping to Link/protocol terminals; retain generic
  signals, with corrected fire-alarm, motion and unlocked-state classification.
- Add current, voltage, pressure and battery classification, read-only special
  terminal values and supplementary WebSocket states for non-native controls.
- Add a system-second heartbeat, per-signal source selection, periodic verification,
  bounded polling, sender filtering and protection against late HTTP replies.
- Fix boolean U attributes being mistaken for duplicate UUIDs; preserve requested
  analog precision. Keep mandatory verified backups and activation safeguards.
- Fix shared structure mutation during platform setup and event listener cleanup.
- Isolated HA 2026.7.2 construction/event checks: 1,213 terminal entities and 332
  supplementary state sensors; offline patch is idempotent. Physical acceptance,
  program activation and restoration remain pending. No release has been published.

## [1.3.0] - 2026-09-09

### Added

- Optional automatic UDP logger setup during installation and after program changes.
  Existing installations opt in; the new-installation form enables the option by default
  and explains the program modification and brief Miniserver logic restart.
- Mandatory, verified full original ZIP and `.Loxone` project backups before every
  program modification, with SHA-256 metadata and English/German recovery instructions.
- Verified temporary FTP upload, source recheck, pending-upload detection and a
  persistent activation guard to prevent automatic restart loops.
- UDP status sensor and setup/receiver diagnostics.
- English and German customer documentation, including limitations and restoration.

### Validation

- Offline integrity and transaction tests; import and setup checks on HA 2026.7.2.
- Dry run against the demo Miniserver 17.2.8.28 program; no live program write performed.
- Live upload/restart/recovery acceptance testing remains outstanding.

## [1.2.1] – 2026-09-05

### Behoben

- **Der Sensor „Loxone Software Version" verdoppelte sich nach jedem Miniserver-Update.** Seine
  `unique_id` enthielt die Firmware-Version (`<Seriennummer>-17.1.6.30`). Nach einem Update legte
  Home Assistant deshalb einen neuen Sensor `sensor.loxone_software_version_2` an, der alte blieb
  für immer `unavailable` im Entitätsregister. Die `unique_id` ist jetzt fest
  (`<Seriennummer>-loxone_software_version`); beim Start werden vorhandene alte Einträge auf die
  neue ID umgezogen (Entity-ID und Verlauf bleiben) und Duplikate entfernt. Aufgefallen am
  Demo-Koffer beim Update 17.1.6.30 → 17.2.8.28.

## [1.2.0] – 2026-09-05

Echtzeit für auto-entdeckte Klemmen. Bisher wurden sie alle 30 s per HTTP nachgezogen, weil
der Miniserver über den WebSocket nur Bausteine mit Visu-Häkchen pusht. Jetzt gibt es einen
zweiten Weg, den der Miniserver selbst anbietet: ein **Logger-Objekt mit UDP-Adresse**.

### Hinzugefügt

- **UDP-Push-Kanal** (`udp_push.py`). Die Integration lauscht auf einem UDP-Port (Option
  *„UDP-Port für Echtzeitwerte"*, Vorgabe `55555`, `0` = aus) und speist jedes Datagramm
  `<Zeit>;<Logger>;<Klemmen-UUID>;<Wert>` in denselben Event-Bus, den der WebSocket-Stream
  nutzt. Die Entities merken keinen Unterschied. Angenommen werden nur UUIDs, die als
  Control bekannt sind; unveränderte Werte werden verworfen (analoge Eingänge melden auch
  Rauschen unterhalb der Anzeigeauflösung — ein unbelegter 0-10-V-Eingang lieferte ~1
  Datagramm je Sekunde).

  Gemessen am Demo-Koffer (Miniserver Gen 2, FW 17.1.6.30):

  | | |
  |---|---|
  | Latenz Schaltbefehl → Datagramm in HA | **12–20 ms** |
  | Impulse 20 ms und länger | vollständig (Ein und Aus) |
  | Impulse 10 ms (ein SPS-Zyklus) | teils verloren — SPS-Grenze, kein Logger-Problem |
  | Broadcast-Ziel (`192.168.0.255`, `255.255.255.255`) | funktioniert — der Miniserver muss die HA-Adresse nicht kennen |
  | SD-Karte | kein Schreibzugriff, `/log` bleibt unverändert |

- **Einrichtung im Miniserver-Programm** übernimmt das Skript `ha_udp_logger.py` aus dem
  [Loxone-Config-Skill](https://github.com/smartmacherei/loxone-skill): Es zieht das Programm
  aus dem Miniserver, legt ein Logger-Objekt `/dev/udp/<HA-IP>/<Port>` und eine Seite
  „HA UDP" mit einer Logger-Referenz je Klemme an und lädt das Programm zurück — genau so,
  wie Loxone Config speichert (`/prog/sps_new.zip` + `dev/sps/restart`). Wichtig: Die
  Zuweisung direkt an der Klemme (`<LoggerMailer>` im Klemmenobjekt) wertet der Miniserver
  **nicht** aus; nur die Referenz auf einer Seite (`OutputRefLM`) sendet.

- Tests für Parser und Protokoll (`tests/test_udp_push.py`, ohne Home Assistant lauffähig).

### Geändert

- Das 30-s-Polling bleibt als Rückfallebene bestehen: Es fängt verlorene Datagramme und
  Klemmen ohne Logger-Referenz (unverdrahtete Ausgänge haben keine Quelle, die man
  referenzieren könnte).

### Bekannte Grenzen

- Beim Programmstart schickt der Miniserver kein Gesamtabbild, nur Klemmen, deren Wert sich
  beim Start ändert. Die Startwerte kommen weiterhin per HTTP.
- Farbwerte (`<v.col>`) rendert der Logger als `0`; solche Ausgänge legt die Discovery ohnehin
  nicht an.

## [1.1.2] – 2026-08-28

Behebt zwei Fehler, die ein Code-Review an 1.1.0/1.1.1 gefunden hat.

### Behoben

- **Analoge Klemmen blieben ohne `device_class`, wenn sie nur über den Gerätenamen erkannt
  wurden.** Der Filter in `topology.classify_terminal()` gibt den Gerätenamen als Kategorie
  an `match_sensor_description()` — die Entity in `sensor.py` klassifizierte anschließend
  aber **erneut**, ohne diesen Kontext. Eine `%`-Klemme an einem „Feuchtesensor" kam damit
  zwar durch den Filter, landete in HA aber ohne `device_class`, ohne Einheiten-
  Normalisierung (`°`→`°C`, `Lx`→`lx`) und mit nacktem `MEASUREMENT`. Filter und Entity
  sehen jetzt dieselben Eingaben (`auto_category`).

- **Änderungen im Options-Dialog wirkten erst nach einem Neustart.** Die Integration
  registrierte keinen Update-Listener; `async_config_entry_updated` existierte, wurde aber
  nie angemeldet. Wer Auto-Discovery abschaltete, sah schlicht keine Wirkung. Jetzt lädt
  sich der Config-Entry bei jeder Optionsänderung selbst neu — verifiziert: Umschalten
  wirkt nach ~5 s ohne Neustart (50 → 22 Entities und zurück).

### Geändert

- `enumerate_discoverable()` nimmt die bereits gebaute `device_map` entgegen, statt das
  Programm-XML ein zweites Mal zu parsen und die Map neu aufzubauen. Bei großen Projekten
  spart das spürbar Zeit im Event-Loop.

- README: Hinweis ergänzt, dass auto-entdeckte Schalter **direkt auf die Klemme schreiben**
  — am Loxone-Programm vorbei. Ist derselbe Ausgang zusätzlich visualisiert, existieren
  zwei Schalter für dasselbe Relais.

- `_ALWAYS_KEEP_TYPES` enthält bewusst nur Miniserver-Klemmen und schaltbare Ausgänge,
  nicht die Eingänge von Tree-/Air-Geräten. Diese Asymmetrie ist jetzt im Code begründet.

## [1.1.1] – 2026-08-28

### Behoben

- **Physische Ein- und Ausgänge fehlten.** Der Relevanzfilter aus 1.1.0 hat auch die
  Miniserver-Klemmen verworfen (`Switch 1–7`, `LED 1–8`, `Voltage 2–4`, `Wheel 1`) sowie
  schaltbare Geräteausgänge wie das Klick-Signal einer Touch-Oberfläche. Deren Namen sind
  generisch („Switch 3", „Q1"), eine Bedeutung lässt sich daraus nicht ableiten — trotzdem
  gehören sie nach Home Assistant, es sind genau die Klemmen, die man am Verteiler anfasst.

  Neu: `_ALWAYS_KEEP_TYPES` legt physische I/O immer an, unabhängig von der Klassifikation —
  `DigitalIn`, `VoltageIn`, `Actor` (Miniserver-Klemmen) sowie `TreeActor` und `LoxAIRactor`
  (schaltbare Geräteausgänge). Alles Übrige braucht weiterhin eine erkennbare
  Gerätefunktion.

  Am Demo-Koffer: **54 statt 31** Klemmen. Draußen bleiben die 11 echten Parameter
  (`Overrun Time Presence`, `Time`, `Volume Minimum/Maximum`, `Fahrzeit`, `Stromfluss` …).

- Damit ist auch die Einschränkung aus 1.1.0 zurückgenommen, dass Discovery *nur* lesende
  Entities anlegt. Schaltbare Ausgänge werden wieder als Schalter erzeugt — sie sind der
  Grund, warum man Discovery überhaupt einschaltet. Wem das zu weit geht, schaltet
  Auto-Discovery per Option ab.

## [1.1.0] – 2026-08-28

### Hinzugefügt

- **Auto-Discovery klassifiziert jetzt nach Gerätefunktion.** Bisher wurde jede physische
  Klemme ohne Visu-Häkchen zu einer Entity — auch Konfigparameter („Overrun Time Presence",
  „Volume Maximum"), Anzeige-LEDs und Miniserver-Interna („Computing power throttling").
  Angelegt wird nur noch, was sich einer Gerätefunktion zuordnen lässt, orientiert an den
  Gerätetypen von Matter: Bewegung, Helligkeit, Temperatur, Leckmelder, Fensterkontakt,
  Batteriestand, Störungsmeldung, Erreichbarkeit.

  Der Filter ist keine zweite Namensliste, sondern nutzt dieselbe Klassifikation, die die
  Entity später ohnehin bekommt: Greift weder die Einheiten-Tabelle (`sensor.py`) noch die
  Namens-Tabelle (`binary_sensor.py`), ist es keine Gerätefunktion. Der Gerätename dient
  dabei als Kontext — „Eingang 1" allein sagt nichts, „Eingang 1" am „Wassersensor Air" ist
  ein Leckmelder.

  Am Demo-Koffer: **65 → 31 Klemmen**, jede mit passender `device_class`.

- **Auto-Discovery abschaltbar** über die neue Option *„Physische Klemmen automatisch
  entdecken"* in Einrichtung und Optionen (Vorgabe: an, also unverändertes Verhalten).
  Für Kundenprojekte, in denen auch die gefilterte Liste noch zu viel ist. Abgeschaltet
  entfällt auch das zyklische HTTP-Nachziehen.

- **Tree-Ausgänge werden erkannt** (`TreeActor`, `TreeAactor`). Bisher kannte die
  Topologie-Auswertung nur die Tree-*Eingänge*, wodurch Tree-Klemmen bei der
  Geräte-Gruppierung fehlten.

- **CHANGELOG.md** – diese Datei.

### Geändert

- **Discovery legt ausschließlich lesende Entities an.** Ausgänge werden nicht mehr als
  Schalter erzeugt. Ein auto-entdeckter Schalter ließe Home Assistant auf eine Klemme
  schreiben, die der Errichter bewusst nicht freigegeben hat. Wer eine Klemme bedienen
  will, setzt in Loxone Config das Visu-Häkchen — dann wird sie ohnehin ein regulärer
  Baustein und über den WebSocket gepusht.

### Behoben

- **Langsamer Start, wenn der Miniserver fehlt.** Der Erreichbarkeits-Probe beim Setup
  wartete die vollen `TIMEOUT`-Sekunden ab, obwohl Home Assistant über
  `ConfigEntryNotReady` ohnehin selbst im Hintergrund weiterversucht. Er gibt jetzt nach
  `SETUP_PROBE_TIMEOUT` (5 s) auf. Alle weiteren Anfragen — vor allem die unter Umständen
  große Strukturdatei — behalten das volle Timeout.

  Gemessen auf dem Demo-Koffer (HA 2026.7.2), Miniserver per Blackhole-IP unerreichbar:

  | Szenario | vorher | nachher |
  |---|---|---|
  | Miniserver erreichbar | 12 s | 11 s |
  | Miniserver unerreichbar | 42 s | 16 s |

### Hinweise zum Update

Bereits angelegte Entities für nun gefilterte Klemmen verschwinden nicht von selbst — sie
bleiben als `unavailable` in der Entity-Registry stehen und lassen sich dort löschen. Das
ist Home-Assistant-Standardverhalten; ein automatisches Aufräumen würde bei einem
versehentlich gesetzten Schalter Verlauf und Verknüpfungen vernichten.

## [1.0.0]

Erste Version dieses Forks von [PyLoxone](https://github.com/JoDehli/PyLoxone).
Geräte-Gruppierung über die Miniserver-Topologie, Auto-Discovery physischer Klemmen,
`device_class`-Ableitung, HTTP-Initialwerte.
