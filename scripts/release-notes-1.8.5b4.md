Vorabversion mit der Freigabe für Loxone Config 17.3, Sensoren mit Einheit für den Energieflussmonitor und einem Szenen-Fix für Farblichter aus der Community. Enthält alle Änderungen aus 1.8.5b1 bis 1.8.5b3.

Neu:

- **Loxone Config 17.3 (#23):** Config 17.3 speichert das Programm im Objektformat 179. Die automatische UDP-Einrichtung brach deshalb bei jedem mit 17.3 gespeicherten Projekt mit `PROGRAM_FORMAT_UNSUPPORTED` ab. 179 ist jetzt freigegeben, für Einzelanlagen und Gateway/Client.
- **Energieflussmonitor (#22):** Netz-, Produktions- und Speicherleistung und die Leistung jedes Knotens erscheinen als Leistungssensoren in kW, mit Geräte- und Zustandsklasse. Die Knotenwerte heißen nach dem Knoten. Dazu der CO2-Faktor in kg/kWh und Import- und Exportpreis als Zahl.

Behoben:

- **Farblichter und Szenen (#24, Beitrag von BlackEntrance in #13):** Eine Szene mit Farbe oder Farbtemperatur und Helligkeit schaltet ein ausgeschaltetes Licht jetzt ein. Einfaches Einschalten stellt die letzte Helligkeit und Farbe wieder her. Betrifft RGB-, LumiTech- und Tunable-White-Lichter.
- **Gerätenamen:** Bausteine ohne eigene Umsetzung heißen in HA nach dem Baustein, nicht mehr nach ihrem ersten Zustand („Energieflussmonitor: jLocked“). Selbst vergebene Gerätenamen bleiben.
- **Fehlermeldung bei unbekanntem Programmformat:** Sie nennt jetzt das gefundene Format, die Config-Version und die freigegebenen Formate, mit dem passenden nächsten Schritt für ältere und neuere Projekte.

Wichtig:

- **Config 17.3:** Offline mit einem echten 17.3-Projekt geprüft (Gateway und 3 Clients). Die Einrichtung findet alle Objekte und ändert nichts. Das Neuanlegen an einem Miniserver mit 17.3 ist noch nicht an Hardware geprüft.
- **Energieflussmonitor:** Bestehende Entitäten behalten Entity-ID und Verlauf. Nicht dokumentierte Werte (Eigenverbrauch, Speicherladung aus Produktion und deren Summen) bleiben Rohwerte ohne Einheit, bis ihre Bedeutung belegt ist.
- **Gen1-Miniserver:** Wie er den SPS-Zustand während der Verteilung meldet, ist weiter nicht an Hardware geprüft (#17).

Validierung:

- **Tests:** ohne HA 397 bestanden (118 übersprungen), mit HA 2026.11.2 515 bestanden (dazu 50 Teiltests), in GitHub Actions. Die Fixes für #22 und #23 wurden zuerst mit einem roten Test belegt, alle Änderungen vor dem Mergen unabhängig geprüft.
- **Mit echten Kundendaten (offline):** das 17.3-Programm aus #23 und vier Energieflussmonitore aus derselben Anlage sowie der Energieflussmonitor des Demo-Koffers.
- **Nicht an Hardware geprüft:** Neuanlage mit Config 17.3, Energieflussmonitor-Sensoren im Live-Betrieb, Farblicht-Fix in der finalen Fassung (eine frühere Fassung wurde vom Autor an einer LED Ceiling Light RGBW Air getestet).
