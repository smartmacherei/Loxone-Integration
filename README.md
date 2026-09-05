# Loxone-Integration (smartmacherei)

Home-Assistant-Integration für den Loxone Miniserver.

Dies ist ein **Fork von [PyLoxone](https://github.com/JoDehli/PyLoxone)** (Apache-2.0)
mit Erweiterungen, die den Miniserver deutlich „plug & play" in Home Assistant bringen.

## Was diese Version zusätzlich kann

- **Echte Geräte-Gruppierung.** Statt für jeden Ein-/Ausgang ein eigenes HA-Gerät zu
  erzeugen, wird das komplette Miniserver-Programm (`sps*.LoxCC`) geladen, dekodiert
  und die physische Hardware-Topologie (TreeDevice) ausgewertet. Alle Kanäle eines
  physischen Loxone-Geräts landen unter **einem** HA-Gerät mit dem echten Gerätenamen.
- **Auto-Discovery ohne Visu-Klicken.** Physische Klemmen, die (noch) nicht in der
  Loxone-Visualisierung sichtbar gemacht wurden, werden automatisch als Entities
  ergänzt und korrekt dem Gerät zugeordnet. Angelegt wird dabei nur, was eine echte
  Gerätefunktion ist — Bewegung, Helligkeit, Temperatur, Leckmelder, Fensterkontakt,
  Batteriestand, Störung, Erreichbarkeit —, nicht jeder Konfigparameter und jede
  Status-LED. Die physischen Ein-/Ausgänge des Miniservers (`I`, `AI`, `Q`) und die
  schaltbaren Geräteausgänge kommen dagegen immer mit — auch ohne sprechenden Namen,
  denn genau die fasst man am Verteiler an. Ganz abschaltbar über die Option
  **„Physische Klemmen automatisch entdecken“**.
- **Sinnvolle Symbole / `device_class`.** Ableitung aus Einheit (z. B. `Lx` → Helligkeit,
  `°` → Temperatur) und Namensschlüsselwörtern (Motion → Bewegung, Presence → Anwesenheit …).
- **HTTP-Initialwerte.** Werte, die der Miniserver nicht über den WebSocket-Stream
  pusht (z. B. Konfig-Analogwerte), werden per HTTP nachgeholt, damit Entities nicht
  „unavailable" bleiben.

- **Echtzeit für entdeckte Klemmen per UDP.** Der Miniserver pusht über den WebSocket
  ausschließlich Bausteine mit Visu-Häkchen — gemessen kam keine einzige nicht-visualisierte
  Klemme an. Deshalb lauscht die Integration zusätzlich auf einem UDP-Port (Option
  **„UDP-Port für Echtzeitwerte"**, Vorgabe `55555`), auf den ein Logger-Objekt im
  Miniserver-Programm jede Änderung sofort meldet: **12–20 ms** statt 30 s, Impulse ab 20 ms
  vollständig. Ohne Logger im Programm bleibt es beim 30-s-Polling.

> **Logger einrichten.** Das Skript `ha_udp_logger.py` aus dem
> [Loxone-Config-Skill](https://github.com/smartmacherei/loxone-skill) zieht das Programm aus
> dem Miniserver, legt das Logger-Objekt (`/dev/udp/<HA-IP>/<Port>`) und eine Programmseite
> „HA UDP" mit einer Logger-Referenz je Klemme an und lädt das Programm zurück:
>
> ```
> set LOX_PW=…
> py -3 ha_udp_logger.py --from-miniserver 192.168.0.186 --target 192.168.0.223:55555 -o sps_new.zip --upload --restart
> ```
>
> Statt der HA-Adresse geht auch eine Broadcast-Adresse (`255.255.255.255:55555`) — dann muss
> der Miniserver die Adresse von Home Assistant nicht kennen. Danach das Projekt in Loxone
> Config **aus dem Miniserver laden**, sonst überschreibt der nächste Config-Upload die Seite.
> Die Zuweisung direkt an der Klemme („Logging/Mail/Call/Track") sendet übrigens nichts — nur
> die Logger-Referenz auf einer Seite tut es; das Skript macht es richtig.

> **Achtung bei auto-entdeckten Schaltern.** Schaltbare Ausgänge werden als HA-`switch`
> angelegt und schreiben **direkt auf die Klemme** — am Loxone-Programm vorbei. Ist derselbe
> Ausgang zusätzlich über einen Baustein visualisiert, gibt es zwei Schalter für dasselbe
> Relais, die voneinander nichts wissen. Wo das stört: Auto-Discovery abschalten oder die
> betreffenden Entities in HA deaktivieren.

## Installation (HACS)

1. HACS → drei Punkte → **Benutzerdefinierte Repositories**
2. Repository `https://github.com/smartmacherei/Loxone-Integration`, Kategorie **Integration**
3. „Loxone (smartmacherei)" installieren, Home Assistant neu starten
4. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Loxone**
   (Benutzer, Passwort, Host-IP, Port des Miniservers)

## Konfiguration

Beim Einrichten werden Benutzername, Passwort, Host und Port des Miniservers
abgefragt. Für die Geräte-Topologie und Auto-Discovery greift die Integration lesend
auf das Programm des Miniservers zu (`/dev/fslist`, `/dev/fsget`) — dafür ist ein
**nicht-Default-Passwort** am Miniserver nötig (das Werks-`admin/admin` sperrt den
Zugriff).

| Option | Vorgabe | Wirkung |
|---|---|---|
| Physische Klemmen automatisch entdecken | an | Klemmen ohne Visu-Häkchen als Entities anlegen |
| UDP-Port für Echtzeitwerte | `55555` | Port für die Logger-Datagramme des Miniservers; `0` schaltet den Kanal ab. Der Port muss auf dem HA-Host frei sein (HAOS: Host-Netzwerk, kein Port-Mapping nötig) |

## Lizenz & Attribution

Apache License 2.0 — siehe [`LICENSE`](LICENSE) und [`NOTICE`](NOTICE).
Basiert auf [PyLoxone](https://github.com/JoDehli/PyLoxone) von JoDehli und
Mitwirkenden. Änderungen von smartmacherei sind in der Git-Historie und in `NOTICE`
dokumentiert.
