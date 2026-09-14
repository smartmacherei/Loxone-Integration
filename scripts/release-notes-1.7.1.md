Korrekturen für Weg 3 (HA → Loxone) nach dem ersten Feldtest an einer Vier-Miniserver-Anlage.

**Analoge Eingänge.** Zahlenwerte werden im Loxone-Programm jetzt als analoge UDP-Befehle angelegt. Bisher fehlte das Merkmal, Loxone Config legte sie als Digitaleingänge an. Ein/Aus-Werte bleiben digital. Bestehende Einträge aus 1.7.0 werden beim nächsten Druck auf „HA-Werte ins Programm übernehmen“ neu geschrieben.

**Von Config neu angelegter Eingang.** Hat Loxone Config den Eingang „HA Werte“ nach einer Bearbeitung mit neuen Kennungen neu angelegt, bricht die Einrichtung nicht mehr mit PROGRAM_PREPARE_FAILED ab, sondern übernimmt ihn anhand von Titel oder Kürzel. Vom Anwender geänderte Befehlstitel bleiben erhalten.

**Zustand unbekannt beim Knopfdruck.** Dann entscheidet die Domäne der Entität über analog oder digital.

Nach dem Update: Home Assistant neu starten, Browserseite neu laden, einmal „HA-Werte ins Programm übernehmen“ drücken. Der Miniserver startet dabei kurz neu.

Validierung: Offline-Tests und Tests in einer isolierten HA-Instanz bestanden; zweifacher Einrichtungslauf am Programmarchiv der Vier-Miniserver-Anlage geprüft. Nutzung auf eigene Verantwortung, siehe Haftungsausschluss.
