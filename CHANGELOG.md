# Changelog

Alle nennenswerten Änderungen an dieser Integration.
Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionierung nach [Semantic Versioning](https://semver.org/lang/de/).

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
