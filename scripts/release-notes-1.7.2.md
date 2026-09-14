Zwei Korrekturen aus dem Feldtest im Gateway/Client-Verbund.

**Bestehende UDP-Befehle bleiben unverändert.** Beim erneuten Drücken von „HA-Werte ins Programm übernehmen“ werden neue Entitäten angehängt und abgewählte entfernt; vorhandene Befehle behalten Titel, Skalierung, analog/digital, Kennung und Kürzel. In Config gemachte Änderungen und Verdrahtungen bleiben damit gültig. Bisher wurde der ganze Eingang neu geschrieben.

**Clients vor dem Upload prüfen.** Im Gateway/Client-Verbund prüft die Integration vor jedem Upload, ob alle Client-Miniserver antworten. Antwortet einer nicht, bleibt das Programm unverändert (Fehlercode CLIENT_UNREACHABLE, Schritt „Clients prüfen“). So bleibt kein Client mit veraltetem Programm zurück. Ein späterer Versuch ist nicht gesperrt.

Nach dem Update: Home Assistant neu starten, Browserseite neu laden. Wer mit 1.7.0 angelegte Eingänge hat, drückt einmal den Knopf; nur fehlende Analog-Merkmale werden ergänzt, sonst bleibt alles wie es ist.

Validierung: Offline-Tests bestanden, Ablauf „Knopf, Änderung in Config, Knopf mit weiterer Entität“ am Programmarchiv einer Vier-Miniserver-Anlage geprüft. Nutzung auf eigene Verantwortung, siehe Haftungsausschluss.
