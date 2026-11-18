Vorabversion mit einer weiteren Fehlerkorrektur für Gateway/Client-Anlagen. Enthält auch die Änderung aus 1.8.5b1 (Ein/Aus-Werte halten ihren Zustand in Loxone).

Problem: Beim Speichern aus Loxone Config blieb eine Anlage bei „Verteilung an Clients“ hängen, auch nach 30 Minuten. Mit ausgeschalteter UDP-Einrichtung lief die Verteilung durch. Der Code zeigt einen Weg, auf dem das passieren kann: Das Speichern unterbricht die Verbindung, die Integration lädt nach einer Sekunde neu und prüft kurz darauf das Programm. Fehlt dort etwas, lädt sie hoch und startet die Logik neu, während das Gateway noch verteilt. Eine Abweichung entsteht zum Beispiel, wenn Config ein älteres lokales Projekt speichert, in dem Ein/Aus-Werte noch digital sind.

Änderung:

- **Kein Upload nach einem Verbindungsverlust:** Lädt die Integration deshalb neu, liest sie das Programm nur. Weicht es ab, schreibt sie weder Sicherung noch Programm und startet nichts neu. Der UDP-Status zeigt **Anpassung offen, nichts hochgeladen**, dazu kommt eine Benachrichtigung.
- **Ausdrückliche Wege bleiben:** Neu laden der Integration, ein HA-Neustart und der Knopf „HA-Werte ins Programm übernehmen“ passen das Programm weiter an.
- **Unverändertes Programm:** Es wird wie bisher als eingerichtet bestätigt.

Wichtig:

- **Vor Änderungen in Config das Projekt aus dem Miniserver laden.** Sonst stehen die von der Integration umgestellten Befehle im nächsten Speichervorgang wieder im alten Zustand.
- **Grenzen:** Neu laden oder ein HA-Neustart während der Verteilung kann weiter hochladen, deshalb die Verteilung vorher abwarten. Die Integration liest das Programm beim Neuladen auch weiterhin. Ob schon das Lesen die Verteilung stört, ist nicht ausgeschlossen.

Validierung: 290 Tests bestanden, 35 übersprungen (Home Assistant ist offline nicht installiert). Neu: kein Upload nach Verbindungsverlust, auch im Gateway/Client-Fall und mit einem älteren Projekt aus Config, keine Sicherung und kein Journal dabei, Bestätigung bei unverändertem Programm, normaler Upload beim Laden ohne Verbindungsverlust und per ausdrücklicher Prüfung. Die Verdrahtung in `__init__.py` läuft nur in Home Assistant und ist offline nicht ausgeführt worden. Der Ablauf ist noch nicht an einer echten Anlage gelaufen, die Ursache dort noch nicht bestätigt; das soll diese Vorabversion klären.
