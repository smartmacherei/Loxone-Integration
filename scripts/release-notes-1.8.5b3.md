Vorabversion mit der Upload-Sperre für Gateway/Client-Anlagen, den Bausteinparametern und vielen Fehlerkorrekturen aus einem vollständigen Code-Review. Enthält alle Änderungen aus 1.8.5b1 und 1.8.5b2.

Neu:

- **Upload nur im Normalbetrieb (#17):** Vor jedem Programm-Upload fragt die Integration den SPS-Zustand des Miniservers und aller Clients ab. Meldet einer nicht „läuft“, etwa während der Verteilung an die Clients, wird nichts hochgeladen und nichts neu gestartet. Der UDP-Status zeigt den Zustand je Miniserver.
- **Bausteinparameter:** Die Parameter der Funktionsbausteine erscheinen als Zahl-Entitäten. Mit dem Label `loxone` lassen sie sich über Weg 3 aus HA verstellen, nur bei Einzelanlagen.
- **Tests in der CI:** Bei jedem Push laufen die Tests ohne HA und mit HA 2026.11.2.

Behoben (Auswahl, vollständig im CHANGELOG):

- **UDP-Einrichtung:** Bei Projekten mit Anlagenschema brach sie mit `PROGRAM_PREPARE_FAILED` ab (#14, sehr wahrscheinlich auch #6).
- **Raumregler:**
  - Heizen und Kühlen aus der App erscheinen in HA richtig und lassen sich richtig schalten (#16).
  - Alte Raumregler zeigen ihre Modi richtig an und senden die dokumentierten Befehle.
- **Sicherheit:** Farb- und Stimmungszustände werden nicht mehr mit `eval()` ausgewertet.
- **Geräte:**
  - Brandmelder melden einen laufenden Alarm.
  - Komfortschalter schalten beim Einschalten nicht mehr aus.
  - Texteingaben zeigen ihren Text.
  - Lüftungen bekommen gültige Befehle.
  - Dimmer am Minimum gelten als an.
- **Verbindung:**
  - Ein fehlerhaftes Paket beendet den Empfang nicht mehr.
  - Ein abgelehnter Token führt zu einem neuen Verbindungsaufbau, mit wachsender Wartezeit.
  - Fernzugriff über die Loxone-Cloud verbindet mit `wss://`.
  - Gesicherte Befehle gehen nicht mehr verloren.
- **Neuladen:**
  - Das Stoppen von HA löst kein Neuladen mehr aus.
  - Nach einem unerwarteten Verbindungsfehler lädt die Integration markiert neu, statt einzufrieren.
  - Die Dienste bleiben während eines Neuladens verfügbar.
- **Zwei Miniserver als getrennte Einträge:** Befehle gehen an den richtigen.
- **HA 2026.11:** keine Warnungen über veraltete Schnittstellen mehr (Klima-Temperaturen, Raumzuordnung, `aiohttp.BasicAuth`).

Wichtig:

- **Erstes Laden:** Ist die automatische UDP-Einrichtung eingeschaltet, prüft die Integration beim ersten Laden das Programm. Fehlt etwas, sichert sie es, lädt es angepasst hoch und startet die Logik kurz neu.
- **Alte Raumregler:** „Aus“ schaltet jetzt über den Servicemodus „Heizen und Kühlen aus“. „Heizen“ und „Kühlen“ wählen die Automatik-Varianten.
- **Gen1-Miniserver:** Wie er den SPS-Zustand meldet, ist noch nicht an Hardware geprüft.

Validierung:

- **Tests:** ohne HA 387 bestanden (104 übersprungen), mit HA 2026.11.2 491 bestanden. Dieselben Tests laufen jetzt in GitHub Actions.
- **Demo-Koffer** (HA 2026.10.1, Miniserver 17.2.8.28, Einzelanlage, Update von 1.7.4):
  - Nach erfolgreicher Prüfung des SPS-Zustands hat die Integration das Programm gesichert, angepasst und aktiviert.
  - Nach dem Neustart des Miniservers hat sie markiert neu geladen und das Programm danach als eingerichtet bestätigt.
  - Der WebSocket ist angemeldet, UDP-Werte kommen an, und im Log stehen keine Fehler der Integration.
- **Nicht an Hardware geprüft:** Gateway/Client-Verbund, Bausteinparameter über Weg 3, Fernzugriff.
