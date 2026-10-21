Fehlerkorrektur und neue Namen im Loxone-Programm.

Problem: Nach jedem Speichern aus Loxone Config hat die Integration das Programm beim nächsten Laden noch einmal hochgeladen, mit Sicherung, Upload und Neustart der Miniserver-Logik, obwohl sich an ihren Objekten nichts geändert hatte. Ursache: Config setzt beim Speichern das Kennzeichen `Analog` an den Logger-Referenzen der verwalteten Seite neu, nach Art des Quell-Konnektors. An einer echten Anlage waren es 259 von 501 Referenzen. Der Vergleich hat dieses Kennzeichen mitgezählt und die Seite deshalb für geändert gehalten.

Änderung:

- **Kein Upload mehr nach einem Speichern aus Config:** Der Vergleich lässt das Kennzeichen `Analog` aus. Was der Logger sendet, bestimmt das Meldungsformat (`<v>` / `<v.n>`).
- **Neue Namen:** Seite und Logger heißen **Home Assistant - Loxone nach HA (UDP)**, der virtuelle UDP-Eingang für Weg 3 heißt **Home Assistant - HA nach Loxone (UDP)**. Beides beginnt mit „Home Assistant“, die Richtung steht im Namen.
- **Migration:** Die bisherigen Namen (`HA UDP`, `HA UDP (smartmacherei)`, `HA Werte`) werden erkannt und einmal umbenannt. UUIDs, Kurznamen und Befehle bleiben, die Verdrahtung in Config bleibt gültig. Einen selbst vergebenen Namen am Eingang fasst die Integration nicht an.

Wichtig:

- **Ein reines Update ändert das Programm einmal** (Umbenennung): Beim ersten Laden folgen Sicherung, Upload und ein kurzer Neustart der Miniserver-Logik. Danach in Loxone Config das Projekt **aus dem Miniserver laden**, sonst stehen dort noch die alten Namen und das nächste Speichern löst wieder eine Umbenennung aus.

Validierung: 271 Tests bestanden, 29 übersprungen. Neu: geändertes `Analog`-Kennzeichen löst keinen Neuaufbau aus, alte Namen von Seite, Logger und Eingang werden einmal umbenannt und bleiben danach ruhig, ein eigener Name am Eingang bleibt. Zusätzlich offline am Programm einer echten Anlage nachgestellt: Das aus Config gespeicherte Projekt wurde mit 1.8.1 als geändert erkannt, mit 1.8.2 (nach der Umbenennung) nicht mehr. Die Umbenennung durch die Integration ist noch nicht an einer echten Anlage gelaufen.
