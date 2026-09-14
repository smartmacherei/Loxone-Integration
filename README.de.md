# Loxone für Home Assistant — smartmacherei

[English](README.md) · [Änderungen](CHANGELOG.md) · [Support](https://github.com/smartmacherei/Loxone-Integration/issues)

**Echtzeitwerte in Home Assistant, ohne zusätzliche Einträge in deiner Loxone-Visualisierung.**

Binde unterstützte Loxone-Geräte und Signale in Home Assistant ein, nach physischen
Geräten gruppiert. Geeignete Ein- und Ausgänge werden erkannt, ohne für jede Klemme
„In Visualisierung verwenden“ aktivieren zu müssen. Deine bestehende Visualisierung
bleibt auf die Funktionen konzentriert, die du dort tatsächlich brauchst.

Die Integration basiert auf [PyLoxone](https://github.com/JoDehli/PyLoxone), erweitert
um Geräteerkennung und automatische Einrichtung von smartmacherei.

[20 Geräte in Home Assistant ansehen](docs/screenshots/1.3.3/README.md) — echte
Geräteansichten auf Deutsch und Englisch aus der Demo-Installation.

## Was du bekommst

- **Mehr Signale mit weniger Einrichtung.** Unterstützte physische Ein- und Ausgänge
  entdecken, ohne dafür zusätzliche Bedienelemente in der Visualisierung anzulegen.
- **Zusammengehörige Kanäle unter einem Gerät.** Die physische Gerätezuordnung wird
  aus dem Miniserver-Programm übernommen, soweit dort verfügbar.
- **Echtzeitwerte für geeignete Signale.** Änderungen direkt empfangen, auch für
  unterstützte Signale außerhalb der Visualisierung.
- **Geprüfte Projektsicherung vor Änderungen.** Vollständiges Originalprogramm und
  eine Projektdatei zum Öffnen in Loxone Config aufbewahren.

**Aktuelle Veröffentlichung: 1.7.0.** Projektsicherung, automatischer Upload/Neustart, UDP-
Lebenszeichen und erneutes Laden wurden am Demokoffer geprüft. Physische
Zustandswechsel und Wiederherstellung aus der Sicherung müssen noch abgenommen werden.
Die UDP-Einrichtung im Gateway/Client-Verbund wurde an einer Anlage mit vier Miniservern
bestätigt. Gateway/Client-Anlagen: Alle Miniserver werden erkannt und gelesen; die
automatische UDP-Einrichtung lässt die Programme unverändert, solange die Option
„UDP auch im Gateway/Client-Verbund einrichten“ nicht eingeschaltet ist (siehe unten).
Weg 3 (HA → Loxone) ist neu in 1.7.0 und noch nicht an echter Hardware geprüft.

## Installation mit HACS

1. HACS → Menü → **Benutzerdefinierte Repositories**.
2. `https://github.com/smartmacherei/Loxone-Integration` als **Integration** hinzufügen.
3. **Loxone** herunterladen und Home Assistant neu starten.
4. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Loxone**.
5. Adresse, HTTP-Port und Zugangsdaten des Miniservers eingeben. Die Vorgabe ist
   `80`. Falls der Miniserver einen anderen HTTP-Port nutzt, diesen ausdrücklich eintragen.
6. Unter den Zugangsdaten zeigt das Formular die zwei Wege. **Weg 1 (HA → Loxone)** ist
   immer aktiv: Home Assistant liest Bausteine und Klemmen vom Miniserver; die Optionen
   dazu bestimmen nur, was angelegt wird. **Weg 2 (Loxone → HA)** ist optional: Der
   Miniserver sendet Echtzeitwerte per UDP. Dafür wird das Miniserver-Programm geändert,
   vor dem Einschalten den [Haftungsausschluss](#haftungsausschluss) lesen.

HACS bietet die GitHub-Veröffentlichungen dieses benutzerdefinierten Repositorys an.
PyLoxone und dieser Fork verwenden dieselbe Domain `loxone`; nur eine Variante
installieren. Ein vom Werkszustand abweichendes Passwort und Leseberechtigungen für
das Programm sind erforderlich. HA muss den Miniserver im lokalen Netz erreichen können.

## Automatische Echtzeiteinrichtung (UDP)

Bei neuen Installationen bietet das Formular die automatische Echtzeiteinrichtung
für geeignete entdeckte Klemmen an. Bestehende Installationen behalten ihr Verhalten,
bis du die Option ausdrücklich einschaltest.

Eine Grenze gilt für alle Wege (Vorgabe 500, oben im Formular einstellbar): So viele
zusätzlich erkannte Klemmen werden zu Entitäten, abgefragt und mit UDP-Loggern versehen;
später begrenzt sie auch Signale von Home Assistant nach Loxone. Die Abfrage selbst ist auf
200 Anfragen je 30 Sekunden und zwei gleichzeitige je Miniserver gedeckelt, damit eine sehr
große Anlage, etwa ein Gateway/Client-Verbund mit vielen Miniservern, im Umlauf abgefragt
wird statt Miniserver oder Netzwerk zu überlasten. In Home Assistant deaktivierte
Entitäten werden gar nicht abgefragt, und Geräteinterna (Online-Status,
Schutzabschaltungen, interne Temperatur, Rohformate) werden deaktiviert angelegt. Der
Miniserver antwortet so nur für das, was du wirklich nutzt. Nach der
Einrichtung liest die Integration alle 60 Sekunden nur das Verzeichnislisting des
Miniserver-Programms; das Programm selbst wird erst nach einem neuen Speichern aus
Loxone Config erneut heruntergeladen.

**Die automatische Einrichtung ändert das Miniserver-Programm und startet seine
Logik kurz neu.** Dafür werden Berechtigungen zum Hochladen und Aktivieren benötigt.
Vor jeder Änderung sichert und prüft die Integration das vollständige Originalpaket
und ein in Config öffenbares `.Loxone`-Projekt.
**Scheitert die Sicherung, gibt es weder Upload noch Neustart.**

Auch nach einem neuen Miniserver-Programm prüft die Integration die Einrichtung und
ergänzt sie bei Bedarf. Dabei können erneut eine Sicherung und ein kurzer Neustart
erfolgen. Währenddessen nicht gleichzeitig aus Loxone Config speichern. Vor eigenen
Änderungen das aktuelle Programm **aus dem Miniserver laden**.

[Voraussetzungen, technische Details und Wiederherstellung](docs/automatic-udp.de.md)

## HA → Loxone (Weg 3, Label und Knopf)

Werte aus Home Assistant (Thermostat, Sensoren, Schalter) werden Eingänge im
Loxone-Programm, ohne in Loxone Config Objekte anzulegen:

1. In Home Assistant jeder Entität, die nach Loxone soll, das Label **loxone** geben.
2. Der Diagnose-Sensor **HA → Loxone** zeigt die Zahl der Werte im Programm und als
   Attribute `pending_add` / `pending_remove` (Entitäten, die seit dem letzten Knopfdruck
   das Label bekamen oder verloren), `unsupported` (Textzustände) und `beyond_limit`.
3. **HA-Werte ins Programm übernehmen** drücken. Die Integration lädt das aktuelle Programm
   vom Miniserver, sichert es, legt unter den virtuellen Eingängen des Gateways (bzw. des
   einzigen Miniservers) einen virtuellen UDP-Eingang „HA Werte“ (Port 55556) mit einem
   Befehl je Wert an, lädt hoch und startet neu. Ohne Knopfdruck ändert sich nichts, auch
   wenn Labels kommen oder gehen.
4. Ab dann geht jede Zustandsänderung als `<schlüssel>=<zahl>` raus, dazu alle Werte alle
   5 Minuten und nach jedem Programmwechsel. In Loxone Config das Projekt vom Miniserver
   laden und die Befehle aus der Peripherie auf die Seiten ziehen; Clients erreichen sie wie
   jeden Gateway-Eingang.

Werte sind immer Zahlen: Zahlenzustände unverändert; on/off, open/closed und ähnliche als
1/0; Entitäten mit Attribut `options` als Index des Zustands; `climate` liefert Modus-Index
(`hvac_modes`), Ist-Temperatur, Solltemperatur und Aktions-Index (off, heating, cooling,
drying, idle, fan, preheating, defrosting). Textzustände stehen unter „unsupported“. Weg 3
setzt Weg 2 (automatische UDP-Einrichtung) voraus, weil er dieselbe Kette aus Sicherung,
Upload und Neustart nutzt. `udp_max_signals` begrenzt die Zahl der Werte.

## Umfang und Grenzen

[Geräteabdeckung und Abnahme](docs/device-coverage.de.md) unterscheiden native
Bedienfunktionen, lesende Zustände und Sonderformate mit dem aktuellen Prüfstand.

- Echtzeit gilt für geeignete Signale, nicht für jede Klemme. Unverdrahtete Ausgänge
  und nicht unterstützte Wertformate können weiterhin nur alle 30 Sekunden aktualisiert werden.
- Bereits visualisierte Bausteine nutzen weiterhin ihre bestehende Live-Verbindung.
  Für unterstützte entdeckte Klemmen sind keine zusätzlichen Visu-Einträge nötig.
- Automatische Programmanpassungen sind derzeit auf die geprüften Programmformate
  von Loxone Config 17.1/17.2 begrenzt. Andere Formate bleiben unverändert.
- Entdeckte Ausgangsschalter schreiben direkt auf die Klemme. Wenn das Loxone-Programm
  diese ebenfalls steuert, die gewünschten Entities prüfen oder Discovery abschalten.
- Die Miniserver-IP wird nicht automatisch nachgeführt. Eine stabile Adresse nutzen
  oder die Host-Einstellung anpassen.
- Gateway/Client-Anlagen: Die Erkennung liest das Gesamtprojekt, findet die Klemmen aller
  Miniserver und gruppiert sie je Miniserver; Klemmen eines Clients werden direkt am
  Client abgefragt. Die automatische UDP-Einrichtung bricht ohne die Option vor jeder
  Änderung mit dem Fehlercode `ARCHIVE_MULTIPLE_PROGRAMS` ab. WebSocket, Befehle und
  Räume laufen über das Gateway.
- Gateway/Client (1.7.0): Mit der Option „UDP auch im Gateway/Client-Verbund einrichten“ bekommt
  jeder Miniserver in seinem eigenen Programm einen eigenen Logger und eine Seite „HA UDP“,
  begrenzt auf 5 Klemmen je Miniserver, plus ein Lebenszeichen je Miniserver. Batterie
  und Geräteinterna belegen keinen Platz; sie werden stattdessen alle 4 Stunden per HTTP
  gelesen. Gesamtprojekt und alle Teilprogramme werden gleich geändert;
  das Archiv wird nur auf das Gateway gespielt, das die Teilprogramme nach dem Neustart an
  die Clients verteilt. Programmformat 174 (Config 16.x) wird nur auf diesem Weg akzeptiert.
  Noch nicht an echter Hardware geprüft; Sicherung kontrollieren, Nutzung auf eigene
  Verantwortung.
- Zustandsupdates erreichen die Entitäten über einen internen Dispatcher. Das frühere
  Bus-Ereignis `loxone_event` wird nicht mehr ausgelöst; das hält die Recorder-Datenbank
  klein. Automationen sollten Entitätszustände nutzen; `loxone_send` für Befehle bleibt.
- Lichtstimmungen stehen als Effekte der Licht-Entität bereit. Erzeugte Szenen-Entitäten
  wurden in 1.5.0 entfernt; ihre Registereinträge werden automatisch bereinigt.

Nach Installation einer neuen Integrationsversion Home Assistant neu starten.

Nach dem Löschen von Geräten in Loxone Config das Programm auf dem Miniserver
speichern und die Loxone-Integration in HA neu laden. Gelöschte UUIDs werden mit
dem geprüften vollständigen Projekt abgeglichen; Offline-Geräte bleiben erhalten.
Die aktivierte automatische Einrichtung prüft Programmänderungen alle 60 Sekunden
und lädt nach erfolgreicher Konfiguration neu. Ist sie abgeschaltet oder blockiert,
manuell neu laden. Vor dem Entfernen werden die Registereinträge unter
`/config/loxone_registry_backups/<entry-id>/` gesichert. Ohne prüfbares Projekt
wird nichts bereinigt. Nicht eindeutig zuordenbare Entity-Kennungen können eine
manuelle Prüfung erfordern.

## Sicherungen und Hilfe

Die Projektsicherungen liegen bei einer Standardinstallation unter
`/config/loxone_backups/<server-id>/` und bleiben nach Deinstallation erhalten.
Zusätzlich auf einen separaten Rechner kopieren, damit sie auch bei Ausfall des
HA-Servers oder seines Datenträgers verfügbar sind.
[Original wiederherstellen](docs/automatic-udp.de.md#original-wiederherstellen).

Bei Problemen die HA-Meldung und Integrationsdiagnose prüfen. Der Diagnosestatus
unterscheidet die Einrichtung vom tatsächlichen Empfang aktueller Werte. Unveränderte
Eingänge senden möglicherweise erst bei der nächsten Änderung.

Für Support Versionsnummern und Fehlerbild angeben.
**Keine Zugangsdaten oder Projektsicherungen öffentlich hochladen.**

## Haftungsausschluss

Diese Integration ist ein unabhängiges Projekt der smartmacherei e.U. Sie steht in
keiner Verbindung zur Loxone Electronics GmbH und wird von dieser weder unterstützt
noch freigegeben. „Loxone“ und „Miniserver“ sind Marken der jeweiligen Inhaber.

**Die automatische Echtzeiteinrichtung (Weg 2) lädt das Miniserver-Programm herunter,
ergänzt eine Seite mit Logger-Objekten, lädt das geänderte Programm hoch und startet
die Miniserver-Logik neu.** Die Integration sichert und prüft vorher das vollständige
Original und bricht bei jeder fehlgeschlagenen Prüfung ab. Die Nutzung erfolgt dennoch
auf eigene Gefahr. Die Software wird gemäß Apache License 2.0 „wie besehen“ ohne jede
Gewährleistung bereitgestellt. Soweit gesetzlich zulässig, übernehmen die smartmacherei
e.U. und die Mitwirkenden keine Haftung für Schäden jeder Art aus der Nutzung dieser
Integration, insbesondere nicht für Verlust oder Beschädigung von Miniserver-Programmen,
Fehlfunktion oder Ausfall gebäudetechnischer Anlagen (Heizung, Beleuchtung, Beschattung,
Zutritt, Alarmanlage), Datenverlust oder Kosten einer Wiederherstellung. Erstelle vor
dem Einschalten eine eigene aktuelle Projektsicherung in Loxone Config, prüfe danach das
geänderte Programm und aktiviere die automatische Einrichtung nur auf Anlagen, die du
ändern darfst.

## Lizenz

Apache License 2.0 — [LICENSE](LICENSE), [NOTICE](NOTICE).
Basierend auf PyLoxone von JoDehli und Mitwirkenden, erweitert von smartmacherei.

## Room mapping / Raumzuordnung

[Optional room mapping during setup and in integration options / Optionale Raumzuordnung](docs/room-mapping.md).
[UDP setup diagnostics / UDP-Einrichtungsdiagnose](docs/udp-setup-diagnostics.md).

[Connection checks and diagnostic downloads / Verbindungspruefung und Diagnosedaten](docs/connection-diagnostics.md).
