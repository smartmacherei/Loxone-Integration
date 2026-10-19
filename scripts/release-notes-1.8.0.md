Stabile Version, fasst die Vorabversionen 1.7.5b1 bis 1.8.0b1 zusammen. Am Code gegenüber 1.8.0b1 keine Änderung.

Was neu ist gegenüber 1.7.4:

- **UDP-Einrichtung nur beim Laden:** Die automatische UDP-Einrichtung prüft das Programm einmal beim Laden oder Neuladen der Integration. Die zyklische Abfrage und die Reaktion auf spätere Config-Speichervorgänge entfallen.
- **FTP-Fallback:** Beantwortet der Miniserver `AUTH TLS` vor dem Login mit 500, 502, 504, 530 oder 534, verbindet die Integration neu und meldet sich einmal per Klartext-FTP an. Vorher brach die Einrichtung bei 530 als „Login abgelehnt“ ab, ohne dass Zugangsdaten gesendet wurden. Die Diagnose nennt `FTP_LOGIN_REJECTED` nur noch für einen echten Login-Versuch.
- **Home Assistant verbunden:** Das Loxone-Gerät hat eine neue Entität, die immer an ist. Eine Neuinstallation legt das Label **loxone** (Symbol `mdi:alpha-l-box`, grün) selbst an, gibt es dieser Entität und setzt sie auf die Wunschliste für Weg 3 (HA → Loxone). Weitere Entitäten mit dem Label kommen weiterhin erst per Knopf „HA-Werte ins Programm übernehmen“ ins Programm.
- **Behoben:** Der Sensor „UDP-Status“ trug nach der Einrichtung die vollständige UUID-Liste aller Klemmen als Attribut. Bei mehreren hundert Klemmen überschritt das die 16384 Byte der HA-Datenbank, HA warnte alle 30 Sekunden und speicherte die Attribute nicht. Der Sensor zeigt jetzt nur noch Zähler (`scope_signals`).

Wichtig beim Update einer bestehenden Installation:

- Das Update legt die neue Entität an, aber **ohne Label und ohne Programmänderung**. Am Miniserver-Programm ändert sich nur etwas, wenn die automatische Einrichtung ohnehin fehlende Logger ergänzt oder wenn der Knopf gedrückt wird.
- Die automatische Einrichtung prüft das Programm bei **jedem Laden oder Neuladen** der Integration und lädt ein angepasstes Programm hoch, wenn Logger-Referenzen fehlen (Sicherung vorher, kurzer Neustart der Miniserver-Logik). Läuft FTP erstmals durch, kann deshalb schon das erste Neuladen das Programm ändern. Einen passenden Zeitpunkt wählen und die Verteilung an alle Clients abwarten.
- Beim FTP-Fallback gehen Benutzername und Passwort im Klartext über das lokale Netz. FTP am Miniserver nur für die Einrichtung aktivieren. Der Integrationsbenutzer braucht in Loxone Config das Gruppenrecht „FTP“.

Validierung: 256 Tests bestanden, 29 übersprungen. An einem echten Miniserver (Firmware 17.2.8.28, 826 Klemmen, 391 mit Echtzeit) bestätigt: der FTP-Fallback samt Programmupload und Aktivierung, UDP-Empfang, das Update von 1.7.5b3 auf 1.8.0b1 ohne Programmänderung, die neue Entität ohne Label und das Verschwinden der Recorder-Warnung.

Nicht an einer echten Installation geprüft: der Neuinstallations-Pfad (Label und Wunschliste werden automatisch gesetzt). Er ist nur mit simulierten Registern getestet, Home Assistant selbst war offline nicht installierbar. Bei einer Neuinstallation also die Entität, das Label und die Wunschliste kontrollieren.
