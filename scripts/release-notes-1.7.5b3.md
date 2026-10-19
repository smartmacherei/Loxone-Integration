Vorabversion zur Behebung eines FTP-Fehlers bei der automatischen UDP-Einrichtung. Baut auf 1.7.5b2 auf; die Einrichtungslogik ist unverändert.

Problem: Bei einem Miniserver mit Firmware 17.2.8.28 scheiterte die automatische UDP-Einrichtung und die Diagnose „Verbindung prüfen“ mit „FTP-Verschlüsselung: Fehlgeschlagen (FTP_LOGIN_REJECTED)“, obwohl FTP aktiv war. Gemessen wurde, dass dieser Miniserver jeden FTP-Befehl vor dem Login mit `530 Failed` beantwortet, auch `AUTH TLS`. Die Integration fiel bisher nur bei 500, 502 oder 504 auf Klartext-FTP zurück und brach bei 530 als „Login abgelehnt“ ab. Zugangsdaten wurden dabei nie gesendet.

Änderung: Antwortet der Server auf `AUTH TLS` vor dem Login mit 500, 502, 504, 530 oder 534, verbindet die Integration neu und meldet sich einmal per Klartext-FTP an. Ein abgelehnter Login wird nie wiederholt. Die Diagnose nennt `FTP_LOGIN_REJECTED` nur noch für einen echten Login-Versuch, ein 530 in anderen Schritten heißt `FTP_NOT_LOGGED_IN`.

Wichtig: Dabei gehen Benutzername und Passwort unverschlüsselt über das lokale Netz (die Integration schickt dieselben Zugangsdaten per HTTP-Basic-Auth ohnehin im Klartext). FTP am Miniserver nur für die Einrichtung aktivieren und danach wieder ausschalten.

Unverändert gegenüber 1.7.5b2: Die automatische Einrichtung prüft das Programm bei jedem Laden oder Neuladen der Integration und lädt ein angepasstes Programm hoch, wenn Logger-Referenzen fehlen (Sicherung vorher, Neustart der Miniserver-Logik). Läuft FTP erstmals durch, kann deshalb das erste Neuladen sofort das Programm ändern. Dafür einen passenden Zeitpunkt wählen und die Verteilung an alle Clients abwarten.

Nach dem Update Home Assistant neu starten. Der Integrationsbenutzer braucht in Loxone Config das Gruppenrecht „FTP“; fehlt es, endet die Prüfung nach dem Fallback mit `FTP_LOGIN_REJECTED` im Schritt „FTP-Anmeldung“.

Validierung: 242 Tests bestanden, 29 übersprungen. Neu sind Tests mit einem FTP-Server, der vor dem Login 530 und 534 liefert, für den Fallback, das Schließen der TLS-Verbindung vor dem Klartext-Aufbau, die ausbleibende Wiederholung eines abgelehnten Logins und die Übereinstimmung der Fallback-Codes in Installer und Diagnose. Noch nicht an einem echten Miniserver getestet; Schreibrechte in `/prog`, Passivmodus und die Aktivierung nach dem Upload sind unbestätigt.
