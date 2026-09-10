# Room mapping / Raumzuordnung

## Deutsch

Unter **Einstellungen → Geräte & Dienste → Loxone → Konfigurieren** die Option
**Loxone-Räume bestehenden HA-Bereichen zuordnen** aktivieren. Der zusätzliche
Dialog ist auch bei der ersten Einrichtung verfügbar.

1. Gewünschte Bereiche zunächst in Home Assistant anlegen.
2. Einen Loxone-Raum und einen vorhandenen HA-Bereich auswählen.
3. Für mehrere Zuordnungen **Weiteren Raum zuordnen** aktivieren.
4. Zum Abschluss ohne diese Option absenden. Leere Felder überspringen den Schritt.

Gespeichert werden Raum-UUID und Bereichs-ID. Umbenennungen ändern die Zuordnung
nicht. Geräte mit mehreren Räumen erhalten bei Bedarf Bereichszuordnungen an
ihren einzelnen Entitäten. Manuelle Zuordnungen haben Vorrang. Bereits vorhandene
Gerätebereiche ohne Eigentumsnachweis gelten ebenfalls als manuell: Bei Bedarf
den Gerätebereich in HA selbst ändern oder vor dem Zuordnen leeren.

Eine manuelle Änderung nach einer verwalteten Zuordnung wird auch nach einem
Neustart respektiert. Zum erneuten Verwalten die betreffende Raumzuordnung
entfernen, speichern, den bisherigen Geräte-/Entitätsbereich in HA leeren und
anschließend erneut einrichten. **Entfernen** behält die
letzte Platzierung bei; es löscht weder Bereiche noch Geräte. Gelöschte Zielbereiche
werden nicht automatisch neu angelegt.

Die Raumzuordnung liest Rauminformationen und aktualisiert ausschließlich
HA-Register. Sie ändert keine Loxone-Signale oder Miniserver-Programme. Beim
Speichern gelten weiterhin die übrigen Integrationsoptionen, insbesondere die
separate automatische UDP-Einrichtung.

## English

Open **Settings → Devices & services → Loxone → Configure** and enable the optional
room mapping checkbox. The same extra dialog is available during initial setup.
Create the desired HA areas first, choose a Loxone room and an existing HA area,
and select **Map another room** to continue. Submit without that option to finish;
empty selections skip the step.

Mappings use stable room UUIDs and area IDs. Manual assignments take precedence,
including existing device areas without a recorded integration owner. Change or
clear those areas in HA yourself if needed. Multiroom devices use entity areas.
Removing a mapping retains its last placement and releases integration ownership.
To resume managing a manually overridden mapping, remove it, save, then add it
again, clearing the existing device/entity area in HA before adding it back.
Deleted target areas are not recreated. Mapping changes HA registries only;
other saved integration settings, including automatic UDP setup, still apply.
