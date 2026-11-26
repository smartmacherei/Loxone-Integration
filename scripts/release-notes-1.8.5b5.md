Vorabversion mit einem Fix für Gateway/Client-Anlagen, deren Client nicht auf Port 80 läuft. Enthält alle Änderungen aus 1.8.5b1 bis 1.8.5b4.

Behoben:

- **Client auf eigenem Port (#28):** Lief ein Client-Miniserver auf einem anderen Port als 80, startete der UDP-Empfang nicht. Damit fehlten die automatische UDP-Einrichtung und „HA-Werte ins Programm übernehmen“, und auch die Abfrage der Client-Klemmen und die SPS-Zustandsprüfung vor einem Upload scheiterten. Mit Config 17.3 hatte das nichts zu tun.
- **UDP-Empfang:** Eine nicht auflösbare Miniserver-Adresse stoppt ihn nicht mehr. Nur dieser Absender wird übersprungen, mit einer Warnung im Log. Löst keine Adresse auf, startet er wie bisher nicht; das Log nennt jetzt den Grund.

Verbessert:

- **Klare Meldung:** Ist die automatische UDP-Einrichtung eingeschaltet, läuft aber kein UDP-Empfang, nennen Knopf, UDP-Status und Diagnose die Ursache, statt das Einschalten der Option zu verlangen.

Wichtig:

- **Gateway/Client:** Für die automatische Einrichtung und HA-Werte im Verbund müssen „Echtzeitwerte per UDP automatisch einrichten“ und „UDP auch im Gateway/Client-Verbund einrichten“ eingeschaltet sein.
- **Config 17.3.11.23:** Die offizielle 17.3 ist noch nicht mit einem eigenen Programm geprüft; geprüft wurde 17.3.11.12 (Format 179). Meldet die Einrichtung ein anderes Format, nennt sie es.

Validierung:

- **Tests:** ohne HA 400 bestanden (119 übersprungen), mit HA 2026.11.2 519 bestanden (dazu 50 Teiltests), in GitHub Actions. Jeder Fix wurde zuerst mit einem roten Test belegt und vor dem Mergen unabhängig geprüft.
- **Nachgestellt:** Mit einem Absender `<IP>:88` scheiterte der UDP-Empfang mit `gaierror`; jetzt startet er.
- **Nicht an Hardware geprüft:** Gateway/Client mit einem Client auf Port 88.
