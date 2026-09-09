# Air-/Tree-Testraum aus dem lokalen Config-Katalog

Das Skript `scripts/create_device_test_room.py` erzeugt eine separate
**Projektplanung (`.LxPlan`)**, keine direkt hochladbare Miniserver-Programmdatei.
Die vollständigen Geräte und Klemmen erzeugt anschließend Loxone Config selbst.
Dadurch müssen wir unbekannte Geräte-XML und Konnektoren nicht erfinden.

## Erzeugen

```powershell
py -3 scripts/create_device_test_room.py --output dist/air-tree-test
```

Das Skript verwendet standardmäßig den neuesten lokal installierten Planungskatalog.
Für einen reproduzierbaren Stand und einen Abgleich mit der Gerätedokumentation:

```powershell
py -3 scripts/create_device_test_room.py `
  --config-data "C:\ProgramData\Loxone\Loxone Config 17.2.8.28" `
  --techdoc "C:\Program Files (x86)\Loxone\LoxoneConfigAlpha\tdd_ENG.LxRes" `
  --room "HA Air Tree Test" `
  --output dist/air-tree-test
```

Ein vorhandener Ausgabeordner wird nicht überschrieben. Für einen erneuten Lauf
einen neuen Ordner wählen. `--unique-types` reduziert gleiche bekannte Modellkennungen
auf einen Artikel; ohne diese Option werden auch Farb-/Artikelvarianten eingeplant.

Die Ausgabe enthält:

- `Air-Tree-Test.LxPlan`: alle ausgewählten Artikel im Raum **HA Air Tree Test**;
- `devices.csv`: Artikelnummern, Namen und Modellkennungen;
- `catalog.json`: Katalogstand, Prüfsumme und bekannte Abdeckungslücken;
- `README.txt`: Anleitung zum weiteren Ablauf.

Eine Air Base und eine Tree Extension werden zentral eingeplant. Ihre tatsächliche
Dimensionierung und Verteilung auf Schnittstellen muss Config beim Übernehmen prüfen.
Es werden keine Seriennummern, Pairing-Schlüssel oder Live-Geräte erfunden.

## In Config übernehmen

1. Eine separate Projektplanung in der passenden Loxone Config öffnen und die
   erzeugte `.LxPlan` laden. Nicht in einem Kundenprojekt arbeiten.
2. Artikelliste und Testraum kontrollieren. Die Planung in ein Programm übernehmen.
   Die optionale Auto-Konfiguration von Bedienbausteinen zunächst überspringen:
   Für diesen Test wollen wir Geräte/Klemmen, keine automatisch erzeugte Visu.
3. Das Ergebnis separat als `Air-Tree-Test.Loxone` speichern.
4. Mit dem Skript prüfen, welche Geräte und Klemmen tatsächlich entstanden sind:

```powershell
py -3 scripts/create_device_test_room.py `
  --verify-project "dist/air-tree-test/Air-Tree-Test.Loxone" `
  --manifest "dist/air-tree-test/catalog.json"
```

Die Prüfung liest nur. Sie kontrolliert Modellanzahl, Raumzuordnung und vorhandene
Klemmen. Sie meldet außerdem bereits visualisierte Klemmen. Fehlende oder nicht
auflösbare Modelle führen zum Rückgabecode `2`; erfolgreiche Katalogprüfung zu `0`.
Farbvarianten und sämtliche gerätespezifischen Konnektoren sind damit noch nicht einzeln validiert.

## Was aktuell abgedeckt ist

Der korrigierte Abgleich des lokalen Katalogs 17.2.8.28 umfasst **94 Air- und
66 Tree-Artikel**, inklusive Power Supply & Backup aus der Kategorie PowerSupply.
Sieben Artikel haben keine Modellkennung in den Erzeugungsdaten. Es verbleiben
**37 nicht zugeordnete Modellkennungen** aus der technischen Dokumentation.
Das bedeutet nicht, dass 37 Produkte fehlen: Touch Pure Flex ist beispielsweise
bereits mit anderen Modellkennungen enthalten. Andere Eintraege betreffen alte
Generationen, Partnerprodukte oder Artikel ohne Erzeugungsdaten.

`coverage-details.md` nennt alle nicht zugeordneten Kennungen samt Bezeichnungen
aus der lokalen Dokumentation sowie die sieben Artikel ohne Modellkennung.
Die aktuelle Ausgabe liegt unter `dist/air-tree-test-reviewed/`.

Das ist **noch kein verifiziertes Projekt aller in Config enthaltenen Geraete**.
Erst die Uebernahme in Config zeigt die tatsaechlich erzeugten Geraete. Fuer danach
noch fehlende Modelle brauchen wir passende, aus Config exportierte Vorlagen.

Die erzeugte Planung und der Prüfer wurden automatisiert getestet. Das Öffnen und
Übernehmen dieser konkreten Planung durch die Config-Oberfläche ist noch nicht geprüft.
Loxone beschreibt den grundsätzlichen Ablauf in der
[offiziellen Projektplanungsanleitung](https://www.loxone.com/enen/kb/project-planning/).

Ohne angeschlossene Hardware lässt sich damit zunächst Struktur und Erkennung testen.
Echte Air-/Tree-Werte, Funkverhalten und die Echtzeitübertragung werden dadurch nicht
simuliert. Das Skript hat keinen Netzwerkzugriff und schreibt nichts auf den Miniserver.
