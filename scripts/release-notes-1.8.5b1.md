Vorabversion mit einer Fehlerkorrektur für Weg 3 (HA → Loxone): Ein/Aus-Werte halten in Loxone ihren Zustand.

Problem: An einer echten Anlage zeigten Licht und drei Pumpen eines Whirlpools in Loxone „Aus“, obwohl sie in HA „Ein“ waren. Seit 1.8.1 legt die Integration Ein/Aus-Werte als digitale Befehle mit der Erkennung `<schlüssel>=1` an und sendet sie nur beim Zustandswechsel. Ein digitaler Befehl löst bei `=1` aber nur einen Impuls aus; danach steht der Eingang wieder auf „Aus“, und für den Zustand 0 gab es keinen Befehl. Für eine Klingel reichte das, für einen Zustand wie Licht, Pumpe oder Schalter nicht. Zahlenwerte (analog mit `<schlüssel>=\v`) waren nicht betroffen.

Änderung:

- **Ein/Aus-Werte sind analoge Befehle** mit `<schlüssel>=\v`. Sie kommen als 1 oder 0 an `AQ` an und bleiben stehen, bis HA einen neuen Wert schickt.
- **Senden wie bei Zahlen:** bei jeder Änderung, alle 5 Minuten, beim Start und nach jedem Programmwechsel. Nach einem Neustart des Miniservers ist der Zustand spätestens nach 5 Minuten wieder richtig.
- **Migration:** Digitale Befehle, die die Integration angelegt hat (`=1` aus 1.8.1 bis 1.8.4, `=\v` aus 1.8.0), werden beim nächsten Laden auf analog mit `=\v` umgestellt. UUID, Kurzname und Titel bleiben.
- **Eigene Befehle bleiben**, wie sie sind, auch digitale (z. B. `<schlüssel>=0`) und Befehle, deren Erkennung nicht mit `<schlüssel>=` beginnt.

Wichtig:

- **Ein reines Update ändert das Programm**, wenn es digitale Befehle aus 1.8.0 bis 1.8.4 gibt: Beim ersten Laden folgen Sicherung, Upload und ein kurzer Neustart der Miniserver-Logik. Bei Gateway-Anlagen danach die Verteilung abwarten und die Integration neu laden.
- Ein eigener digitaler Befehl `<schlüssel>=0` (in 1.8.1 als Behelf empfohlen) löst durch das Wiederholen jetzt alle 5 Minuten aus, solange der Zustand 0 ist. Er wird nicht mehr gebraucht und kann weg.
- Die Integration stellt nur den Befehl selbst um, nicht die Referenzen auf den Seiten (`InputRef`). Bitte nach dem Update in Loxone Config prüfen, ob verdrahtete Ein/Aus-Werte weiterhin richtig ankommen.
- Ist ein früherer Versuch für dasselbe Ausgangsprogramm gescheitert, bleibt er über das Aktivierungsjournal gesperrt, auch für diese Umstellung. Dann hilft der Weg aus der Doku (automatische Einrichtung ausschalten, `activation.json` umbenennen).

Validierung: 283 Tests bestanden, 35 übersprungen (Home Assistant ist offline nicht installiert). Neu bzw. angepasst: Ein/Aus-Werte werden analog mit `\v` angelegt, digitale Befehle aus 1.8.0 und 1.8.1 bis 1.8.4 werden mit gleicher UUID umgestellt (auch mit einem eigenen Befehl davor), eigene digitale Befehle bleiben digital, Ein/Aus-Werte gehen bei jeder Änderung und beim Wiederholen raus. Gegen das Programm der meldenden Anlage geprüft: Genau die vier digitalen Befehle werden analog, die übrigen 39 bleiben unverändert, ein zweiter Lauf ändert nichts. Upload, Neustart und die Anzeige in Loxone sind noch nicht an einer echten Anlage gelaufen; das soll diese Vorabversion klären.
