Release 1.7.0 macht die UDP-Einrichtung im Gateway/Client-Verbund regulär und bringt den dritten Weg: Werte aus Home Assistant nach Loxone.

**Gateway/Client ohne Beta.** Die Einrichtung wurde an einer Anlage mit vier Miniservern bestätigt: Seite „HA UDP“ auf jedem Miniserver, Lebenszeichen von allen, kein erneuter Upload nach einem HA-Neustart. Die Option heißt jetzt „UDP auch im Gateway/Client-Verbund einrichten“, gespeicherte Einstellungen bleiben gültig.

**Weg 3: HA → Loxone.** Entitäten in Home Assistant mit dem Label „loxone“ versehen, dann den Knopf „HA-Werte ins Programm übernehmen“ drücken. Die Integration holt das Programm frisch vom Miniserver, sichert es, legt unter den virtuellen Eingängen des Gateways (oder des einzigen Miniservers) einen virtuellen UDP-Eingang „HA Werte“ (Port 55556) mit einem Befehl je Wert an, lädt hoch und startet neu. Danach gehen Zustandsänderungen als UDP-Pakete an den Miniserver, alle Werte zusätzlich alle 5 Minuten. Thermostate liefern Modus, Ist-, Solltemperatur und Aktion; Sensoren, Schalter und Auswahlen je einen Wert. Der Diagnose-Sensor „HA → Loxone“ zeigt, was ein Knopfdruck ändern würde. Ohne Knopfdruck ändert sich am Programm nichts. Weg 3 setzt Weg 2 voraus. In Loxone Config danach „Vom Miniserver laden“ und die Befehle aus der Peripherie auf die Seiten ziehen.

**Batterie und Geräteinterna** belegen keinen UDP-Platz mehr, auch nicht einen der 5 je Miniserver. Sie werden alle 4 Stunden per HTTP gelesen und verfallen nicht als „nicht verfügbar“. Bei bestehenden Einrichtungen entfällt die Batterie-Logger-Referenz erst beim nächsten Speichern aus Loxone Config (ein Upload, ein Neustart).

**Kontakte folgen den Loxone-Statustexten.** Steht in Config 0 = „Offen“ und 1 = „Geschlossen“ (auch open/closed, auf/zu), zeigt HA Tür-, Fenster- und Torkontakte jetzt richtig herum.

**Weniger Last beim Start.** Startwerte zählen als Abfrage; Klemmen mit UDP-Pfad bekommen ihre erste Kontrollabfrage erst nach 30 Minuten.

Nach dem Update: Home Assistant neu starten und die Browserseite neu laden.

Validierung: Offline-Tests und Tests in einer isolierten HA-Instanz (2026.9) bestanden; Weg 3 zusätzlich am Programmarchiv einer Vier-Miniserver-Anlage geprüft (Projekt und Gateway-Teilprogramm identisch, Clients unverändert). Weg 3 ist noch nicht an echter Hardware gelaufen. Nutzung auf eigene Verantwortung, siehe Haftungsausschluss.
