# Geräteabdeckung und Abnahme

[English](device-coverage.md)

Prüfumfang für Version 1.3.3: Geräteerkennung, lesbare Zustände und
vollständige Bedienbarkeit sind unterschiedliche Fähigkeiten.

## Darstellung

- Air-, Tree- und Link-Klemmen werden ihren Gerätecontainern zugeordnet, auch bei
  unterstützten untergeordneten DALI-, Modbus-, EnOcean- und Internorm-Geräten.
- Unbekannte Namen verhindern die Erkennung numerischer und digitaler Werte nicht
  mehr. Strom, Spannung, Druck und Batterieladestand erhalten passende Klassen.
- RGBW-, T5-, API- und Textformate erscheinen als lesende Rohwert-Sensoren. Liefert
  der Miniserver keinen gültigen Wert, bleibt die Entity unbekannt. Ein T5-Sammelwert
  wird dadurch nicht zu fünf Tasterereignissen, ein Farbwert nicht zur Lichtsteuerung.
- Bisher nicht nativ unterstützte Visu-Controls erhalten Sensoren für ihre benannten
  WebSocket-Zustände. Das ermöglicht keine vollständige native Bedienung etwa von
  Wallbox, Touch Display, Pool oder Zutrittssteuerung. Befehle werden nicht geraten.
- Neue protokollspezifische Ausgänge bleiben lesend. Bereits unterstützte physische
  Schalter behalten ihre Funktion; ihre Verwendung muss zum Loxone-Programm passen.
- Leere 1-Wire-/M-Bus-Extensions belegen keine Messwertunterstützung. Dafür sind
  konfigurierte Sensorobjekte und angeschlossene Geräte erforderlich.

Die Erkennung kann viele Entities erzeugen. Nicht benötigte Entities lassen sich
in HA deaktivieren; alternativ die automatische Klemmen-Erkennung abschalten.

## Echtzeit und Rückfall

Ein zusätzlicher Logger-Verweis nutzt den vorhandenen System-Sekundenausgang als
Lebenszeichen pro Sekunde. Es entstehen keine neuen Visu-Freigaben. Fehlt dieser
Ausgang, bleiben regelmäßige Abfragen aktiv.

Für dieselbe Signal-UUID gilt bei frischem Lebenszeichen UDP vor WebSocket.
Zusätzlich werden gleichwertige Zustände anhand eindeutiger Programmverbindungen
zugeordnet, einschließlich des Ziel-Leistungskanals der unterstützten Tree-/Air-
Wallbox. Namen reichen nicht aus; invertierte, skalierte oder mehrdeutige Zuordnungen
werden abgelehnt. Direkt erkannte Klemmen erhalten Startwerte und nötigenfalls
Abfragen alle 30 Sekunden, begrenzt auf 200 Anfragen je Zyklus und zwei gleichzeitige je
Miniserver (große Anlagen im Umlauf); bei gesundem UDP-Kanal alle 30 Minuten eine
Kontrollabfrage. Das Lebenszeichen läuft nach fünf Sekunden ab; der nächste
Abfragezyklus übernimmt, bei Bedarf mit dem gespeicherten WebSocket-Zustand.
Unveränderte Einzelwerte dürfen still bleiben. Bei bestehender WebSocket-Verbindung
reichen ebenfalls Kontrollabfragen alle 30 Minuten. In Home Assistant deaktivierte
Entitäten werden nicht abgefragt; Geräteinterna (Online-Status, Schutzabschaltungen,
interne Temperatur, Rohformate) werden deaktiviert angelegt. Batterie und Geräteinterna
bekommen keine UDP-Logger-Referenz; einmal aktiviert werden sie alle 4 Stunden gelesen
und verfallen nicht als „nicht verfügbar“. Fehlen alle nutzbaren Wege
und frische Werte seit 90 Sekunden, markiert der nächste abgeschlossene Abfragezyklus
die direkt erkannten Klemmen unbekannt beziehungsweise unverfügbar.

Maximal acht Anfragen laufen gleichzeitig, ein Durchlauf dauert höchstens
30 Sekunden. Überlappende Durchläufe und das Überschreiben neuer Push-Werte durch
ältere HTTP-Antworten werden verhindert. Das Lebenszeichen bestätigt den Kanal,
nicht jeden einzelnen Logger. Rohformate nutzen belegte WebSocket-Zuordnungen oder
lesbare HTTP-Werte. Platzhalter wie `<v.col>` gelten nicht als Werte. DALI benötigt
passende programmierte Quellverbindungen; reine Erkennung genügt nicht für Echtzeit.
Visu-Zustände nutzen WebSocket; nicht belegte HTTP-Endpunkte
für deren Zustands-UUIDs werden nicht vorausgesetzt.

## Geprüfter Stand

Am übergebenen Testprojekt wurden mit der installierten HA-Laufzeit 2026.7.2 in
einem isolierten Prüfprozess 1.213 Klemmen-Entities und 332 zusätzliche
Zustands-Sensoren erzeugt und mit synthetischen Ereignissen verarbeitet, ohne
Fehler. Der Offline-Entwurf erzeugt 820 Signalreferenzen plus Lebenszeichen;
393 Klemmen sind nicht für numerisches UDP geeignet. Ein zweiter Patch ändert
nichts mehr. Automatisierte Tests prüfen unter anderem Ausfall/Wiederkehr,
Zuordnung, Klassifikation, Sicherungen und Fehler während der Aktivierung.

Lesender Live-Test mit Miniserver 17.2.8.28: 1.129 von 1.213 Klemmen lieferten
gültige HTTP-Werte. Alle 24 zugeordneten Klemmenzustände kamen per WebSocket an;
883 von 886 deklarierten Zuständen erschienen im kurzen Beobachtungsfenster.
Die korrigierte Watt/kW-Behandlung der beiden Wallbox-Zielkanäle stimmt mit
WebSocket überein: 14,296 kW Tree und 7,4 kW Air. Diese Korrektur gilt nur für
den strukturell erkannten unterstützten Wallbox-Kanal; andere Firmwarestände
sind ungeprüft. Startwerte beweisen noch keine physischen Zustandswechsel.

Version 1.3.3 wurde auf dem Demo-HA installiert und die automatische Einrichtung
am Miniserver durchgeführt. Die geprüfte Original-Projektsicherung liegt auch auf
dem Laptop. Das aktive Programm stimmt mit der erwarteten Prüfsumme überein und
benötigt keinen weiteren Patch. Ein LAN-Mitschnitt bestätigt ein Lebenszeichen
pro Sekunde; HA meldet gesunden UDP-Empfang. Erneutes Laden der Integration
funktioniert mit unverändert 1.644 Registereinträgen. Die 203 HA-Geräte umfassen
physische Gerätecontainer und logische Controls, nicht 203 angeschlossene Geräte.
Von 1.590 geladenen Entities bleiben 64 Rohwert-Entities unverfügbar. Die elf
Szenen mit unbekanntem Zustand wurden nicht betätigt.

Das Lebenszeichen beweist den Transport, nicht sämtliche physischen Zustandswechsel
oder deren Latenz. Physische Betätigung und echte Wiederherstellung bleiben offen.

## Abnahme am Demokoffer

1. Geprüfte Original-ZIP und `.Loxone` zusätzlich außerhalb von HA aufbewahren.
2. Testpaket installieren, HA neu starten, Entities und Einrichtungsstatus prüfen.
3. Bei automatischer Einrichtung Sicherung, Aktivierung und Wiederverbindung
   abwarten. Vor Config-Änderungen den aktuellen Stand aus dem Miniserver laden.
4. Physische Eingänge und Messwerte mit Config vergleichen. Rohwerte und native
   Bedienfunktionen getrennt prüfen; unbekannte Werte protokollieren.
5. Empfangsausfall und Wiederkehr, HA-Neustart sowie ein neues Config-Programm
   prüfen. Auf doppelte Entities und wiederholte Neustarts achten.
6. Wiederherstellung des Originalprojekts vor dem Kundeneinsatz durchführen.

Projektarchive, Zugangsdaten und vollständige Kundenstrukturen nicht veröffentlichen.
