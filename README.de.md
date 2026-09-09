# Loxone für Home Assistant — smartmacherei

[English](README.md) · [Änderungen](CHANGELOG.md) · [Support](https://github.com/smartmacherei/Loxone-Integration/issues)

**Echtzeitwerte in Home Assistant, ohne zusätzliche Einträge in deiner Loxone-Visualisierung.**

Binde unterstützte Loxone-Geräte und Signale in Home Assistant ein, nach physischen
Geräten gruppiert. Geeignete Ein- und Ausgänge werden erkannt, ohne für jede Klemme
„In Visualisierung verwenden“ aktivieren zu müssen. Deine bestehende Visualisierung
bleibt auf die Funktionen konzentriert, die du dort tatsächlich brauchst.

Die Integration basiert auf [PyLoxone](https://github.com/JoDehli/PyLoxone), erweitert
um Geräteerkennung und automatische Einrichtung von smartmacherei.

[20 Ger?te in Home Assistant ansehen](docs/screenshots/1.3.3/README.md) ? echte
Ger?teansichten auf Deutsch und Englisch aus der Demo-Installation.

## Was du bekommst

- **Mehr Signale mit weniger Einrichtung.** Unterstützte physische Ein- und Ausgänge
  entdecken, ohne dafür zusätzliche Bedienelemente in der Visualisierung anzulegen.
- **Zusammengehörige Kanäle unter einem Gerät.** Die physische Gerätezuordnung wird
  aus dem Miniserver-Programm übernommen, soweit dort verfügbar.
- **Echtzeitwerte für geeignete Signale.** Änderungen direkt empfangen, auch für
  unterstützte Signale außerhalb der Visualisierung.
- **Geprüfte Projektsicherung vor Änderungen.** Vollständiges Originalprogramm und
  eine Projektdatei zum Öffnen in Loxone Config aufbewahren.

**Aktuelle Veröffentlichung: 1.3.5.** Projektsicherung, automatischer Upload/Neustart, UDP-
Lebenszeichen und erneutes Laden wurden am Demokoffer geprüft. Physische
Zustandswechsel und Wiederherstellung aus der Sicherung müssen noch abgenommen werden.

## Installation mit HACS

1. HACS → Menü → **Benutzerdefinierte Repositories**.
2. `https://github.com/smartmacherei/Loxone-Integration` als **Integration** hinzufügen.
3. **Loxone (smartmacherei)** herunterladen und Home Assistant neu starten.
4. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Loxone**.
5. Adresse, HTTP-Port und Zugangsdaten des Miniservers eingeben. Die Vorgabe ist
   `80`. Falls der Miniserver einen anderen HTTP-Port nutzt, diesen ausdrücklich eintragen.

HACS bietet die GitHub-Veröffentlichungen dieses benutzerdefinierten Repositorys an.
PyLoxone und dieser Fork verwenden dieselbe Domain `loxone`; nur eine Variante
installieren. Ein vom Werkszustand abweichendes Passwort und Leseberechtigungen für
das Programm sind erforderlich. HA muss den Miniserver im lokalen Netz erreichen können.

## Automatische Echtzeiteinrichtung in 1.3.3

Bei neuen Installationen bietet das Formular die automatische Echtzeiteinrichtung
für geeignete entdeckte Klemmen an. Bestehende Installationen behalten ihr Verhalten,
bis du die Option ausdrücklich einschaltest.

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

## Lizenz

Apache License 2.0 — [LICENSE](LICENSE), [NOTICE](NOTICE).
Basierend auf PyLoxone von JoDehli und Mitwirkenden, erweitert von smartmacherei.
