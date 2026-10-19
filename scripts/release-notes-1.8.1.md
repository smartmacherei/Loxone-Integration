Fehlerkorrektur für Weg 3 (HA → Loxone). Gegenüber 1.8.0 ändert sich nur die Erzeugung der Befehle im Eingang „HA Werte“.

Problem: Digitale HA-Werte (Schalter, Binärsensoren, `input_boolean`, `light` u. Ä.) kamen im Miniserver nicht an. Der Befehl hatte die Erkennung `<schlüssel>=\v`, aber der Platzhalter `\v` wirkt nur an analogen Befehlen. An einem echten Miniserver (Firmware 17.2.8.28) gemessen: Das UDP-Paket `input_boolean.turklingel_haustur=1` kam an und wurde dem Eingang „HA Werte“ zugeordnet, der digitale Befehl löste aber nicht aus. Mit der Erkennung `input_boolean.turklingel_haustur=1` kam der Impuls an.

Änderung:

- **Erkennung nach HA-Typ:** Digitale Werte bekommen die exakte Erkennung `<schlüssel>=1` (Impuls bei 1), Zahlenwerte bleiben analog mit `<schlüssel>=\v`.
- **Migration:** Digitale Befehle aus 1.8.0 mit `=\v` werden beim nächsten Programmupdate auf `=1` umgestellt. UUID, Kurzname und Titel bleiben, die Verdrahtung in Config bleibt gültig.
- **Änderungen in Config bleiben:** Befehle werden über den Schlüssel der Entität gefunden, nicht mehr über den Erkennungstext. Wer die Erkennung in Config ändert, wird nicht mehr zurückgesetzt.

Wichtig:

- Für den Zustand 0 gibt es bei digitalen Werten weiterhin keinen Befehl. Wer den Zustand braucht, stellt den Befehl in Config auf analog (`<schlüssel>=\v`), das bleibt erhalten.
- Die Umstellung bestehender Befehle ist eine Programmänderung. Sie passiert, wie jede andere, beim nächsten Laden der Integration (Sicherung vorher, kurzer Neustart der Miniserver-Logik) oder beim Knopf „HA-Werte ins Programm übernehmen“. Hast du die Erkennung in Config schon auf `=1` gestellt, ändert sich nichts.

Validierung: 260 Tests bestanden, 29 übersprungen. Neu: Erkennung nach Typ, Migration eines `=\v`-Befehls mit gleicher UUID, geänderte Erkennung bleibt erhalten und löst keinen Neuaufbau aus, von Config entfernte Standardattribute lösen keinen Neuaufbau aus. Am Miniserver bestätigt ist die Erkennung `=1` an einem digitalen Befehl (Türklingel). Die automatische Umstellung durch die Integration ist noch nicht an einer echten Anlage gelaufen.
