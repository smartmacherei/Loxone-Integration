# Automatische Echtzeiteinrichtung: Technik und Wiederherstellung

[English](automatic-udp.md) · [Übersicht](../README.de.md)

Diese technische Anleitung erklärt, wie geeignete Signale ohne zusätzliche Einträge
in der Kundenvisualisierung in Echtzeit verfügbar werden. Bereits visualisierte
Bausteine nutzen weiter WebSocket. Für geeignete zusätzlich entdeckte Klemmen wird
ein UDP-Logger im Miniserver-Programm eingerichtet.

## Einstellungen und Voraussetzungen

| Einstellung | Vorgabe bei neuer Installation | Zweck |
|---|---|---|
| Physische Klemmen automatisch entdecken | Ein | Geeignete Klemmen außerhalb der Visualisierung ergänzen |
| UDP-Echtzeit automatisch einrichten | Ein | Programm sichern und Logger automatisch einrichten |
| UDP-Port | `55555` | `0` deaktiviert UDP und automatische Programmänderungen |
| Höchstzahl zusätzlicher Signale | `500` | Eine Grenze für alle Wege: erkannte Entitäten, ihre Abfrage, Logger-Referenzen und künftig Signale nach Loxone; Programmreihenfolge. Die Abfrage ist zusätzlich auf 200 Anfragen je 30 s und 2 gleichzeitige je Miniserver begrenzt |
| LightControllerV2-Unterkanäle | Aus | Einzelne Lichtkanäle standardmäßig aktivieren |
| UDP auch im Gateway/Client-Verbund | Aus | Verbund-Archive (ein Programm je Miniserver) ebenfalls einrichten: je Miniserver eigener Logger, eigene Seite, höchstens 5 Klemmen, eigenes Lebenszeichen. Upload nur auf das Gateway, das verteilt an die Clients. Ausgeschaltet bleiben Verbund-Archive unverändert |

Lichtstimmungen sind immer als Effekte der Licht-Entität verfügbar. Die Szenen-Optionen
früherer Versionen wurden in 1.5.0 entfernt.

Nach der Einrichtung liest die 60-Sekunden-Prüfung nur noch das Verzeichnislisting
des Miniserver-Programms. Das Programmarchiv selbst wird erst nach einem neuen
Speichern aus Loxone Config erneut heruntergeladen; eine ruhende Anlage erzeugt
keine wiederholten Downloads.

Voraussetzungen sind ein vollständiges aktuelles Programm-ZIP, geeignete Lese-,
Upload- und Aktivierungsberechtigungen, FTP/FTPS auf Port 21, eine IPv4-Verbindung
und ein freier UDP-Port auf HA. Automatische Bearbeitung ist auf die geprüften
Objektformate `175` und `178` begrenzt. Router und Firewall werden nicht umkonfiguriert.

## Ablauf

Ab Version 1.3.1 ist die automatische Einrichtung für neue Installationen im Formular
eingeschaltet. Bestehende Einträge bleiben unverändert, bis die Option ausdrücklich
aktiviert wird. Deaktivierte Klemmenerkennung oder UDP-Port `0` verhindern ebenfalls
automatische Programmänderungen. Bereits angelegte Logger bleiben beim Ausschalten erhalten.

Die Integration prüft das aktuelle Programm alle 60 Sekunden. Fehlende Referenzen
werden für geeignete entdeckte Klemmen ergänzt. Passende vorhandene Logger werden
weiterverwendet. Eigene Objekte haben feste Kennungen; ihre Seite heißt
**HA UDP** (Anlagen aus früheren Versionen behalten den Seitennamen **HA UDP (smartmacherei)**,
bis die Seite neu aufgebaut wird). Dort keine eigene Kundenlogik ergänzen.

**Die Einrichtung ändert das Miniserver-Programm und startet seine Logik kurz neu.**
Das kann auch nach einem neuen Upload aus Loxone Config geschehen. Während der
Einrichtung nicht gleichzeitig aus Config speichern. Vor späteren Änderungen das
aktuelle Programm aus dem Miniserver laden.

## Ohne überprüfte Sicherung kein Upload

Unter `/config/loxone_backups/<server-id>/` entstehen vor jeder Änderung:

- die vollständige, unveränderte Original-ZIP-Datei vom Miniserver;
- eine `.Loxone`-Datei zum direkten Öffnen in Loxone Config;
- eine JSON-Datei mit Quelldateiname, Größe, SHA-256-Prüfsumme und Sicherungszeit;
- `RESTORE.txt` mit deutscher und englischer Wiederherstellungsanleitung.

Originalpaket, LoxCC-Prüfsumme und gespeicherte Dateien werden geprüft. Die Dateien
werden auf den Datenträger geschrieben und zur Kontrolle erneut gelesen. Scheitert
das, erfolgt weder FTP-Upload noch Neustart. Verschiedene Projektstände überschreiben
sich nicht. Die Sicherungen bleiben bei Deinstallation erhalten, liegen außerhalb
des öffentlich erreichbaren `www`-Ordners und werden nicht automatisch gelöscht.

Über den vorhandenen administrativen Dateizugriff, etwa Samba oder File editor,
zusätzlich auf einen separaten Rechner kopieren. Nur auf dem HA-Datenträger liegende
Sicherungen schützen nicht vor dessen Ausfall. Den Konfigurationsordner in die
HA-Sicherung aufnehmen. Projektsicherungen enthalten sensible Daten und dürfen
nicht in öffentlichen GitHub-Issues landen.

## Upload und Kontrolle

Das geänderte Paket wird zunächst unter einem temporären Namen hochgeladen und zur
Prüfsummenkontrolle erneut heruntergeladen. Vor der Aktivierung werden das Originalpaket
und ausstehende Uploads nochmals geprüft. Bei verändertem Programm oder vorhandenem
`sps_new.*` wird die Aktivierung abgebrochen. Danach erfolgen Umbenennung zu
`sps_new.zip` und Programmneustart.

FTPS wird bevorzugt. Nur wenn der Server AUTH TLS ausdrücklich nicht unterstützt,
wird normales FTP verwendet. Diese Funktion ist für eine vertrauenswürdige lokale
Verbindung vorgesehen. Der Miniserver bietet keine Transaktionssperre zwischen
verschiedenen Clients; daher nicht gleichzeitig aus Config speichern.

Bei einer Folgeprüfung müssen passende funktionale Logger-Referenzen vorhanden sein,
bevor die Einrichtung als konfiguriert gilt. Bei erkannten Programmänderungen lädt HA
die Integration neu, um die Entities zu aktualisieren.

Der Sensor **UDP-Status** zeigt Einrichtung, Fehler/Sperren und tatsächlichen Empfang.
„Warte auf UDP-Daten“ bedeutet noch keinen Fehler: Unveränderte Klemmen senden
möglicherweise nichts. Startwerte und nicht per Logger meldbare Klemmen kommen weiter
per HTTP. Polling alle 30 Sekunden bleibt als Rückfallebene erhalten.

## Original wiederherstellen

1. Automatische Echtzeiteinrichtung deaktivieren oder HA stoppen, damit sie die
   Wiederherstellung nicht gleich wieder verändert.
2. Gewünschte `.Loxone`-Sicherung auf den PC kopieren und in passender Loxone Config öffnen.
   Die JSON-Datei nennt Quelldateiname und Sicherungszeit; das ZIP enthält das Originalpaket.
3. Mit dem richtigen Miniserver verbinden und **In Miniserver speichern** wählen.
   Das ersetzt das laufende Programm und startet die Logik kurz neu. Ergebnis prüfen.
4. HA wieder verbinden und die automatische Einrichtung während der Fehlersuche ausgeschaltet lassen.

Bei ausgefallenem HA eine bereits heruntergeladene Kopie nutzen oder den Ordner aus
einer HA-Sicherung wiederherstellen. Die Wiederherstellung über Config benötigt diese
Integration nicht.

## Fehler und erneuter Versuch

`activation.json` merkt sich bereits versuchte Aktivierungen auch über HA-Neustarts
und Neuinstallationen hinweg. Dadurch gibt es keine automatische Neustartschleife.
Ein neues Miniserver-Programm wird gesondert geprüft.

Zuerst Ursache beheben: Speicherplatz, Berechtigungen, Format, FTP, UDP-Port oder
paralleler Config-Upload. Bei unbestätigter Bereinigung vor weiteren Neustarts durch
den Errichter `/prog/sps_new.zip` prüfen lassen. Eine dort verbliebene Datei kann beim
nächsten Neustart geladen werden. Keine fremden Uploads löschen.

Für einen bewussten erneuten Versuch desselben Programms: automatische Einrichtung
ausschalten, Entladen abwarten und `activation.json` im Sicherungsordner in einen freien
Archivnamen wie `activation.previous.json` umbenennen. Originalsicherungen behalten.
Erst nach Ursachenklärung wieder einschalten. Dies ist eine administrative Maßnahme;
es gibt keine automatische Wiederherstellungs- und Neustartschleife.

## Teststand

Version 1.3.1 ergänzt Lebenszeichen, Empfangsüberwachung und Kontrollabfragen.
[Geräteabdeckung und Abnahme](device-coverage.de.md) beschreiben den Rückfall
auf Abfragen sowie die Grenzen lesender Sonderwerte.

Automatische Fehlerfalltests und Prüfung unter HA 2026.7.2 sind vorhanden.
Mit Version 1.3.3 wurden Sicherung, Upload/Neustart und das aktive Programm am
Demo-Miniserver 17.2.8.28 geprüft. UDP-Lebenszeichen und erneutes Laden sind bestätigt.
Physische Zustandswechsel und Wiederherstellung sind weiterhin nicht abgenommen.
