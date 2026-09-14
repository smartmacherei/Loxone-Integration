Korrektur der Client-Prüfung aus 1.7.2.

Die Prüfung, ob alle Client-Miniserver vor dem Upload erreichbar sind, akzeptierte nur bestimmte HTTP-Antworten und meldete laufende Clients als nicht erreichbar (CLIENT_UNREACHABLE). Jetzt zählt jede HTTP-Antwort des Clients, notfalls ein offener HTTPS-Port; nur eine fehlgeschlagene Verbindung gilt als Ausfall. Der Antwortstatus jedes Clients steht im Protokoll (Stufe Debug).

Nach dem Update: Home Assistant neu starten, den Knopf „HA-Werte ins Programm übernehmen“ erneut drücken. Eine Aktivierungssperre entsteht durch die fehlgeschlagene Prüfung nicht.

Validierung: Offline-Tests bestanden. Die Prüfung selbst konnte nicht an echten Clients gegengeprüft werden; bitte Rückmeldung mit Protokollauszug, falls sie erneut anschlägt.
