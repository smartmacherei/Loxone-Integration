# Weg 3: HA → Loxone per Label und Knopfdruck

Stand 2026-09-14, freigegeben vom User im Gespräch.

## Ziel

Werte aus Home Assistant (Thermostat-Ist/Soll/Modus, Sensoren, Schalter) im Loxone-Programm
als Eingänge verfügbar machen, ohne dass der Anwender in Config Objekte anlegt. Bedienung
so einfach wie bei Matterbridge: Entität in HA mit dem Label „loxone“ versehen, Knopf drücken.

## Bedienung

1. In HA bekommt jede Entität, die nach Loxone soll, das Label **loxone** (Name, Groß/klein egal).
2. Der Diagnose-Sensor **„HA → Loxone“** zeigt die Zahl der eingetragenen Werte und als
   Attribute `pending_add` / `pending_remove` (Entitäten, die seit dem letzten Knopfdruck
   dazukamen oder ihr Label verloren) sowie den UDP-Port.
3. Der Knopf **„HA-Werte ins Programm übernehmen“** liest das aktuelle Programm frisch vom
   Miniserver, sichert es, trägt die gewünschten Werte als virtuellen UDP-Eingang mit
   Befehlen ein, lädt hoch und startet den Miniserver neu. Ohne Knopfdruck ändert sich am
   Programm nichts, auch wenn Labels kommen oder gehen.
4. Ab dann sendet die Integration bei jeder Zustandsänderung ein UDP-Paket an den
   Miniserver, dazu alle 5 Minuten alle Werte erneut (nach Miniserver-Neustart stehen die
   Eingänge sonst auf 0) und einmal nach jedem erfolgreichen Programmwechsel.
5. In Loxone Config liegen die Befehle in der Peripherie unter „Virtuelle Eingänge“ des
   Gateways bzw. des einzigen Miniservers, Eingang „HA Werte“. Der Anwender zieht sie auf
   seine Seiten; Clients erreichen sie wie jeden Gateway-Eingang (Config legt die
   Memory-Proxys selbst an). Nach dem Knopfdruck in Config „Vom Miniserver laden“.

Voraussetzung: Weg 2 („Echtzeitwerte per UDP automatisch einrichten“) ist eingeschaltet,
weil Weg 3 dieselbe Kette aus Download, Sicherung, Aktivierungssperre, Upload und
Neustart benutzt. Ist Weg 2 aus, meldet der Knopf das als Benachrichtigung.

## Wertregeln

Jede Entität ergibt einen oder mehrere Werte, Schlüssel = `entity_id` bzw.
`entity_id.attribut`. Jeder Wert ist eine Zahl; Loxone kennt keine Texte.

| Fall | Wert |
|---|---|
| Zustand ist eine Zahl | die Zahl |
| Zustand on/off, true/false, open/closed, locked/unlocked, home/not_home, wet/dry, detected/clear | 1 / 0 |
| Entität hat Attribut `options` (select, Aufzählungs-Sensor) | Index des Zustands in `options` |
| `climate` | `entity_id` = Index des Modus in `hvac_modes`; `.current_temperature`; `.temperature`; `.hvac_action` = Index in off, heating, cooling, drying, idle, fan, preheating, defrosting |
| unknown / unavailable | wird nicht gesendet, Loxone behält den letzten Wert |
| alles andere | nicht exportierbar, steht im Sensor-Attribut `unsupported` |

Die Grenze `udp_max_signals` gilt auch hier: mehr Werte als die Grenze werden nicht
eingetragen (Warnung im Protokoll, Rest im Attribut `beyond_limit`).

Titel in Loxone: Anzeigename der Entität, bei Attributen mit Zusatz (de: Ist-Temperatur,
Solltemperatur, Aktion; en: current temperature, target temperature, action), Sprache nach
HA-Einstellung. Vom Anwender in Config geänderte Titel bleiben beim nächsten Umbau erhalten
(gleicher Schlüssel = gleiche UUID, Titel wird übernommen).

## Programmänderung

Neues Modul `ha_values_program.py`, aufgerufen aus `udp_program.prepare()` nach `patch_xml`,
für das Gesamtprojekt und im Verbund für das Teilprogramm des Gateways (das Teilprogramm,
dessen `Program/@Ref` auf den LoxLIVE mit dem `Gateway`-Objekt zeigt; ohne Verbund der
einzige LoxLIVE).

- Elternobjekt: `VirtualInCaption` dieses LoxLIVE (in Olivers Projekt und Teilprogramm
  gleichermaßen vorhanden, dort liegen bereits 16 `VirtualUdpIn`).
- Ein `VirtualUdpIn` „HA Werte“, `Port` 55556 (fest, Konstante; ist der Port im Programm
  schon von einem fremden `VirtualUdpIn` belegt: Fehlercode `HA_VALUES_PORT_IN_USE`),
  `IName` „HAV“, `Address=""`, `WF="16384"`, `V` wie das Programm.
- Je Wert ein `VirtualUdpInCmd` mit `Check="<schlüssel>=\v"`, `Title`, `IName` „HAV<n>“
  (n = Position in der sortierten Schlüsselliste), `Nio="2"`, `Signed="true"`,
  `SourceValHigh="100" DestValHigh="100"` (keine Skalierung), `MinVal="-1000000000"
  MaxVal="1000000000"`, `MinChange="0" MinTime="0"`, Konnektoren `AQ` und `Q`,
  `Display Unit="<v.2>"` (Digitalwerte `<v>`).
- UUIDs deterministisch: `uuid5(doc_id + "/smartmacherei/havalues/" + schlüssel)`, Suffix
  wie bei Weg 2 die Document-Kennung; Konnektoren nach demselben Muster wie `OutputRefLM`.
- Vergleich vor dem Umbau: (Port, Menge aus (UUID, Check)). Gleich → keine Änderung.
  Sonst wird der ganze `VirtualUdpIn` ersetzt, bestehende Titel je UUID übernommen.
- Ein fremdes Objekt mit unserer UUID oder ein `IName` „HAV…“, der nicht uns gehört →
  `ValueError`, kein Upload (wie „Managed object was modified“ bei Weg 2).
- Document-Stempel (`Date`, `DateS`, `NumO`) und Duplikatprüfung: aus `patch_xml`
  in eine Hilfsfunktion gezogen, von beiden benutzt.
- Leere Wunschliste entfernt den `VirtualUdpIn` samt Befehlen wieder.

Datagramm je Wert: `<schlüssel>=<zahl>` als UTF-8, ohne Zeilenende, Zahl mit Punkt.
Ziel: Host aus den Optionen (Gateway oder einziger Miniserver), Port 55556.

## HA-Seite

Neues Modul `ha_values.py`:

- `desired(hass, limit)` → sortierte Liste `{key, entity_id, attribute, title}` aus allen
  Registry-Entitäten mit dem Label; `values(hass, entries)` → `{key: zahl}` nach den
  Wertregeln; beide ohne HA-Import testbar (Zustände als einfache Objekte).
- Gespeicherte Wunschliste in `Store(hass, 1, "loxone.ha_values.<entry_id>")`
  (`{"entries": [...]}`); nur der Knopf schreibt sie. Kein Options-Update, damit kein
  Reload.
- `UdpSetup` bekommt `self.ha_values` (Liste oder `None`) und reicht sie an `install` →
  `_install` → `prepare` weiter. `check(force=True)` überspringt den Listing-Kurzschluss.
- Sender: bei Setup Wunschliste laden, `async_track_state_change_event` für die
  Entitäten, UDP-Socket (`SOCK_DGRAM`, `sendto` im Event-Loop, ungeblockt), alle 5 Minuten
  Vollsendung, Vollsendung nach `configured` (Manager ruft einen Callback).
- Knopf `HaValuesApplyButton` (`translation_key` `ha_values_apply`): Wunschliste neu
  berechnen, speichern, Manager setzen, `check(force=True)`; ohne Manager
  Benachrichtigung „Weg 2 einschalten“.
- Sensor `HaValuesSensor` (`translation_key` `ha_values`, Diagnose, `should_poll`):
  Wert = Anzahl gespeicherter Einträge; Attribute `pending_add`, `pending_remove`,
  `unsupported`, `beyond_limit`, `port`, `label`.

## Nicht enthalten

Automatische Programmänderung ohne Knopf; Attribute außer den Climate-Werten; Labels auf
Geräten statt Entitäten; Rückweg für Befehle (Loxone → HA-Aktion, das gibt es schon über
die Entitäten); eine eigene Seite im Programm.

## Tests

Offline (`py -3.12 -m pytest tests -q`): Programmänderung auf synthetischem Einzel- und
Verbund-XML (Anlage, Idempotenz, Ersetzen bei Änderung, Titel bleibt, Entfernen bei leerer
Liste, Port belegt, fremdes Objekt), `prepare()` mit Wunschliste (Projekt und Gateway-Teil
gleich, Client-Teil unverändert), Wertregeln mit einfachen Zustandsobjekten, Grenze.
Im HA-Container: Knopf, Sensor, Store, Sender.
