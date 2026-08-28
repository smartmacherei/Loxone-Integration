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

> **Live oder Polling?** Der Miniserver pusht ausschließlich Bausteine mit Visu-Häkchen —
> gemessen kam über den WebSocket keine einzige nicht-visualisierte Klemme an. Diese
> Bausteine sind also live (Millisekunden). Auto-entdeckte Klemmen werden stattdessen alle
> 30 s per HTTP nachgezogen; kurze Impulse (Tasterdrücke) liegen dabei prinzipbedingt
> zwischen zwei Abfragen. Wer eine Klemme in Echtzeit braucht, setzt in Loxone Config ihr
> Visu-Häkchen — dann pusht der Miniserver sie von selbst.

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

## Lizenz & Attribution

Apache License 2.0 — siehe [`LICENSE`](LICENSE) und [`NOTICE`](NOTICE).
Basiert auf [PyLoxone](https://github.com/JoDehli/PyLoxone) von JoDehli und
Mitwirkenden. Änderungen von smartmacherei sind in der Git-Historie und in `NOTICE`
dokumentiert.
