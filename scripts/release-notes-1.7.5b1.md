Vorabversion für den Feldtest der UDP-Einrichtung im Gateway/Client-Verbund.

Beim Speichern aus Loxone Config blieb eine Anlage bei „Verteilen an die Clients“ hängen. Nach Abschalten der automatischen UDP-Einrichtung lief die Verteilung durch. Eine mögliche Ursache ist die bisherige 60-Sekunden-Prüfung: Fehlen im neuen Programm UDP-Einträge, kann HA während der Verteilung selbst ein angepasstes Programm hochladen und die Logik neu starten. Dieser Zusammenhang ist an der betroffenen Anlage noch nicht bestätigt.

Die automatische UDP-Einrichtung prüft das Programm jetzt einmal beim Laden oder Neuladen der Integration. Die regelmäßige Verzeichnisabfrage und automatische Reaktion auf spätere Config-Speichervorgänge entfallen. Der ausdrücklich ausgelöste Knopf „HA-Werte ins Programm übernehmen“ bleibt erhalten.

Nach einer Programmanpassung durch HA zeigt der UDP-Status „Integration nach Programmstart neu laden“. Die Aktivierung wird erst bei diesem Neuladen geprüft; es gibt keine automatische Folgeprüfung. UDP-Empfang und die bestehenden Zustandsabfragen bleiben erhalten.

Nach dem Update Home Assistant neu starten. Bei späteren Änderungen aus Loxone Config zuerst die Verteilung an alle Clients abschließen lassen, dann die Loxone-Integration in HA neu laden. Falls HA dabei das Programm anpasst, erneut Programmstart und Client-Verteilung abwarten und danach zur Kontrolle neu laden.

Validierung: 229 Tests bestanden, 29 übersprungen. Die Tests prüfen unter anderem die einmalige Einrichtung, ausbleibende Folgeuploads nach einem Config-Speichervorgang, Aktivierungskontrolle beim Neuladen und das Entladen während der Startverzögerung. Noch nicht an der betroffenen Anlage getestet.
