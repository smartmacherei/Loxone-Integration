# Changelog

Alle nennenswerten Änderungen an dieser Integration.
Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionierung nach [Semantic Versioning](https://semver.org/lang/de/).

## [1.1.2] – 2026-08-28

Behebt zwei Fehler, die ein Code-Review an 1.1.0/1.1.1 gefunden hat.

### Behoben

- **Analoge Klemmen blieben ohne `device_class`, wenn sie nur über den Gerätenamen erkannt
  wurden.** Der Filter in `topology.classify_terminal()` gibt den Gerätenamen als Kategorie
  an `match_sensor_description()` — die Entity in `sensor.py` klassifizierte anschließend
  aber **erneut**, ohne diesen Kontext. Eine `%`-Klemme an einem „Feuchtesensor" kam damit
  zwar durch den Filter, landete in HA aber ohne `device_class`, ohne Einheiten-
  Normalisierung (`°`→`°C`, `Lx`→`lx`) und mit nacktem `MEASUREMENT`. Filter und Entity
  sehen jetzt dieselben Eingaben (`auto_category`).

- **Änderungen im Options-Dialog wirkten erst nach einem Neustart.** Die Integration
  registrierte keinen Update-Listener; `async_config_entry_updated` existierte, wurde aber
  nie angemeldet. Wer Auto-Discovery abschaltete, sah schlicht keine Wirkung. Jetzt lädt
  sich der Config-Entry bei jeder Optionsänderung selbst neu — verifiziert: Umschalten
  wirkt nach ~5 s ohne Neustart (50 → 22 Entities und zurück).

### Geändert

- `enumerate_discoverable()` nimmt die bereits gebaute `device_map` entgegen, statt das
  Programm-XML ein zweites Mal zu parsen und die Map neu aufzubauen. Bei großen Projekten
  spart das spürbar Zeit im Event-Loop.

- README: Hinweis ergänzt, dass auto-entdeckte Schalter **direkt auf die Klemme schreiben**
  — am Loxone-Programm vorbei. Ist derselbe Ausgang zusätzlich visualisiert, existieren
  zwei Schalter für dasselbe Relais.

- `_ALWAYS_KEEP_TYPES` enthält bewusst nur Miniserver-Klemmen und schaltbare Ausgänge,
  nicht die Eingänge von Tree-/Air-Geräten. Diese Asymmetrie ist jetzt im Code begründet.

## [1.1.1] – 2026-08-28

### Behoben

- **Physische Ein- und Ausgänge fehlten.** Der Relevanzfilter aus 1.1.0 hat auch die
  Miniserver-Klemmen verworfen (`Switch 1–7`, `LED 1–8`, `Voltage 2–4`, `Wheel 1`) sowie
  schaltbare Geräteausgänge wie das Klick-Signal einer Touch-Oberfläche. Deren Namen sind
  generisch („Switch 3", „Q1"), eine Bedeutung lässt sich daraus nicht ableiten — trotzdem
  gehören sie nach Home Assistant, es sind genau die Klemmen, die man am Verteiler anfasst.

  Neu: `_ALWAYS_KEEP_TYPES` legt physische I/O immer an, unabhängig von der Klassifikation —
  `DigitalIn`, `VoltageIn`, `Actor` (Miniserver-Klemmen) sowie `TreeActor` und `LoxAIRactor`
  (schaltbare Geräteausgänge). Alles Übrige braucht weiterhin eine erkennbare
  Gerätefunktion.

  Am Demo-Koffer: **54 statt 31** Klemmen. Draußen bleiben die 11 echten Parameter
  (`Overrun Time Presence`, `Time`, `Volume Minimum/Maximum`, `Fahrzeit`, `Stromfluss` …).

- Damit ist auch die Einschränkung aus 1.1.0 zurückgenommen, dass Discovery *nur* lesende
  Entities anlegt. Schaltbare Ausgänge werden wieder als Schalter erzeugt — sie sind der
  Grund, warum man Discovery überhaupt einschaltet. Wem das zu weit geht, schaltet
  Auto-Discovery per Option ab.

## [1.1.0] – 2026-08-28

### Hinzugefügt

- **Auto-Discovery klassifiziert jetzt nach Gerätefunktion.** Bisher wurde jede physische
  Klemme ohne Visu-Häkchen zu einer Entity — auch Konfigparameter („Overrun Time Presence",
  „Volume Maximum"), Anzeige-LEDs und Miniserver-Interna („Computing power throttling").
  Angelegt wird nur noch, was sich einer Gerätefunktion zuordnen lässt, orientiert an den
  Gerätetypen von Matter: Bewegung, Helligkeit, Temperatur, Leckmelder, Fensterkontakt,
  Batteriestand, Störungsmeldung, Erreichbarkeit.

  Der Filter ist keine zweite Namensliste, sondern nutzt dieselbe Klassifikation, die die
  Entity später ohnehin bekommt: Greift weder die Einheiten-Tabelle (`sensor.py`) noch die
  Namens-Tabelle (`binary_sensor.py`), ist es keine Gerätefunktion. Der Gerätename dient
  dabei als Kontext — „Eingang 1" allein sagt nichts, „Eingang 1" am „Wassersensor Air" ist
  ein Leckmelder.

  Am Demo-Koffer: **65 → 31 Klemmen**, jede mit passender `device_class`.

- **Auto-Discovery abschaltbar** über die neue Option *„Physische Klemmen automatisch
  entdecken"* in Einrichtung und Optionen (Vorgabe: an, also unverändertes Verhalten).
  Für Kundenprojekte, in denen auch die gefilterte Liste noch zu viel ist. Abgeschaltet
  entfällt auch das zyklische HTTP-Nachziehen.

- **Tree-Ausgänge werden erkannt** (`TreeActor`, `TreeAactor`). Bisher kannte die
  Topologie-Auswertung nur die Tree-*Eingänge*, wodurch Tree-Klemmen bei der
  Geräte-Gruppierung fehlten.

- **CHANGELOG.md** – diese Datei.

### Geändert

- **Discovery legt ausschließlich lesende Entities an.** Ausgänge werden nicht mehr als
  Schalter erzeugt. Ein auto-entdeckter Schalter ließe Home Assistant auf eine Klemme
  schreiben, die der Errichter bewusst nicht freigegeben hat. Wer eine Klemme bedienen
  will, setzt in Loxone Config das Visu-Häkchen — dann wird sie ohnehin ein regulärer
  Baustein und über den WebSocket gepusht.

### Behoben

- **Langsamer Start, wenn der Miniserver fehlt.** Der Erreichbarkeits-Probe beim Setup
  wartete die vollen `TIMEOUT`-Sekunden ab, obwohl Home Assistant über
  `ConfigEntryNotReady` ohnehin selbst im Hintergrund weiterversucht. Er gibt jetzt nach
  `SETUP_PROBE_TIMEOUT` (5 s) auf. Alle weiteren Anfragen — vor allem die unter Umständen
  große Strukturdatei — behalten das volle Timeout.

  Gemessen auf dem Demo-Koffer (HA 2026.7.2), Miniserver per Blackhole-IP unerreichbar:

  | Szenario | vorher | nachher |
  |---|---|---|
  | Miniserver erreichbar | 12 s | 11 s |
  | Miniserver unerreichbar | 42 s | 16 s |

### Hinweise zum Update

Bereits angelegte Entities für nun gefilterte Klemmen verschwinden nicht von selbst — sie
bleiben als `unavailable` in der Entity-Registry stehen und lassen sich dort löschen. Das
ist Home-Assistant-Standardverhalten; ein automatisches Aufräumen würde bei einem
versehentlich gesetzten Schalter Verlauf und Verknüpfungen vernichten.

## [1.0.0]

Erste Version dieses Forks von [PyLoxone](https://github.com/JoDehli/PyLoxone).
Geräte-Gruppierung über die Miniserver-Topologie, Auto-Discovery physischer Klemmen,
`device_class`-Ableitung, HTTP-Initialwerte.
