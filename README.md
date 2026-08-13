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
  ergänzt und korrekt dem Gerät zugeordnet.
- **Sinnvolle Symbole / `device_class`.** Ableitung aus Einheit (z. B. `Lx` → Helligkeit,
  `°` → Temperatur) und Namensschlüsselwörtern (Motion → Bewegung, Presence → Anwesenheit …).
- **HTTP-Initialwerte.** Werte, die der Miniserver nicht über den WebSocket-Stream
  pusht (z. B. Konfig-Analogwerte), werden per HTTP nachgeholt, damit Entities nicht
  „unavailable" bleiben.

## Dokumentation

Der Demo-Koffer, an dem diese Integration entwickelt und getestet wird, ist vollständig
dokumentiert — inklusive Zugängen, Netz-Aufbau und den Fallstricken, die dabei Zeit gekostet haben:

- **[`docs/STATUS.md`](docs/STATUS.md)** — hier anfangen: aktueller Stand, Blocker, offene Aufgaben
- [`docs/demokoffer.md`](docs/demokoffer.md) — Aufbau, Netz, Zugänge, was auf den Laptop muss
- [`docs/entwicklung.md`](docs/entwicklung.md) — Deploy-Weg, `.LoxCC`-Format, Messmethode, Fallen
- [`docs/zigbee2mqtt.md`](docs/zigbee2mqtt.md) — Zigbee-Stack und Demo-Automationen der Koffer-Box
- [`docs/simulation-testplan.md`](docs/simulation-testplan.md) — Control-Typen systematisch durchtesten
- [`addons/koffer_netz/`](addons/koffer_netz/) — Add-on, das den Miniserver per MAC findet und den
  Integrations-Host automatisch nachführt

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
