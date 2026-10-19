Fehlerkorrektur für Weg 3 (HA → Loxone). Gegenüber 1.8.0 ändert sich die Erzeugung der Befehle im Eingang „HA Werte“ und das Senden digitaler Werte.

Problem: Digitale HA-Werte (Schalter, Binärsensoren, `input_boolean`, `light` u. Ä.) kamen im Miniserver nicht an. Der Befehl hatte die Erkennung `<schlüssel>=\v`, aber der Platzhalter `\v` wirkt nur an analogen Befehlen. An einem echten Miniserver (Firmware 17.2.8.28) gemessen: Das UDP-Paket `input_boolean.turklingel_haustur=1` kam an und wurde dem Eingang „HA Werte“ zugeordnet, der digitale Befehl löste aber nicht aus. Mit der Erkennung `input_boolean.turklingel_haustur=1` kam der Impuls an.

Änderung:

- **Erkennung nach HA-Typ:** Digitale Werte bekommen die exakte Erkennung `<schlüssel>=1` (Impuls bei 1), Zahlenwerte bleiben analog mit `<schlüssel>=\v`.
- **Digitale Werte nur bei Zustandswechsel:** Weil ein digitaler Befehl jetzt auslöst, sendet HA `<schlüssel>=1` nur noch bei einem echten Zustandswechsel, nicht bei Attributänderungen, nicht alle 5 Minuten, nicht beim Start und nicht nach einem Programmwechsel. Zahlenwerte senden wie bisher.
- **Migration:** Digitale Befehle aus 1.8.0 mit `=\v` werden beim nächsten Laden der Integration auf `=1` umgestellt. UUID, Kurzname und Titel bleiben, die Verdrahtung in Config bleibt gültig.
- **Änderungen in Config bleiben:** Befehle werden über den Schlüssel der Entität gefunden, nicht über den Erkennungstext. Auf analog gestellte Befehle, zusätzliche Befehle zum selben Schlüssel (z. B. `<schlüssel>=0`) und Befehle mit anderer Erkennung bleiben beim Neuaufbau erhalten.

Wichtig:

- **Ein reines Update ändert das Programm,** wenn bestehende digitale Befehle `=\v` haben: Beim ersten Laden der Integration folgen Sicherung, Upload und ein kurzer Neustart der Miniserver-Logik. Das ist bewusst so, weil diese Befehle nie funktioniert haben. Hast du die Erkennung in Config schon auf `=1` gestellt, ändert sich nichts. Bei Gateway-Anlagen danach die Verteilung abwarten und die Integration neu laden.
- Ist ein Versuch unter 1.8.0 für dasselbe Ausgangsprogramm gescheitert, bleibt er über das Aktivierungsjournal gesperrt, auch für diese Umstellung. Dann hilft der Weg aus der Doku (automatische Einrichtung ausschalten, `activation.json` umbenennen).
- Für den Zustand 0 gibt es bei digitalen Werten weiterhin keinen Befehl. Wer ihn braucht, legt in Config einen zweiten Befehl mit `<schlüssel>=0` an oder stellt den Befehl auf analog.

Validierung: 268 Tests bestanden, 29 übersprungen. Neu: Erkennung nach Typ, Migration eines `=\v`-Befehls mit gleicher UUID (auch mit zusätzlichem Befehl davor), geänderte Erkennung bleibt erhalten und löst keinen Neuaufbau aus, zusätzliche und fremde Befehle überleben einen Neuaufbau, Analog-Umstellung setzt `\v`, digitale Werte gehen nur bei echtem Zustandswechsel raus. Am Miniserver bestätigt ist die Erkennung `=1` an einem digitalen Befehl (Türklingel). Die automatische Umstellung durch die Integration und das neue Sendeverhalten sind noch nicht an einer echten Anlage gelaufen.
