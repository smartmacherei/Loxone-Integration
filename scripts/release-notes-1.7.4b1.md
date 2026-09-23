Vorabversion für den Feldtest im Gateway/Client-Verbund. Eine Korrektur, sonst gleich 1.7.3.

**„Client-Programm veraltet“ nach Programmänderungen durch die Integration.** Loxone Config gibt dem Gesamtprojekt `sps.Loxone` und allen Teilprogrammen `sps0…spsN` dasselbe Programmdatum (`Date`/`DateS`). Die Integration dagegen hat jedes geänderte Teilprogramm mit der eigenen Uhrzeit gestempelt, unveränderte Teile behielten ihr altes Datum. Das Gateway sah bei den betroffenen Clients ein abweichendes Programm und meldete sie als veraltet. Neustart oder Stromlosmachen half nicht, weil das Datum in den Programmdateien selbst steht. Jetzt tragen alle Programme eines Uploads dasselbe Datum, auch unveränderte Teile.

Nach dem Update: Home Assistant neu starten. Danach einmal in Loxone Config das Projekt aus dem Miniserver laden und wieder in den Miniserver speichern. Damit bekommen alle Programme wieder ein gemeinsames Datum und die Meldung verschwindet. Weitere Uploads der Integration halten das Datum gleich.

Validierung: Offline-Tests bestanden. Der Fehler wurde mit einem neuen Test nachgestellt: vorher drei verschiedene Daten in einem Archiv, jetzt eines. Am Programmarchiv des Testers (vier Miniserver) offline geprüft: alle fünf Programme mit gleichem `Date`/`DateS`, `NumO` stimmt. Noch nicht an der Anlage bestätigt. Nutzung auf eigene Verantwortung, siehe Haftungsausschluss.
