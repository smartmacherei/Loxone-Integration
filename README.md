# Loxone for Home Assistant — smartmacherei

[Deutsch](README.de.md) · [Changelog](CHANGELOG.md) · [Support](https://github.com/smartmacherei/Loxone-Integration/issues)

**Real-time updates in Home Assistant, without adding extra controls to your Loxone visualization.**

Bring supported Loxone devices and signals into Home Assistant, grouped by physical
device. Eligible inputs and outputs can be discovered without enabling each one in
the Loxone visualization. Your existing visualization stays focused on what you use.

Based on [PyLoxone](https://github.com/JoDehli/PyLoxone), with additional device discovery
and automatic setup by smartmacherei.

[See 20 devices in Home Assistant](docs/screenshots/1.3.3/README.md) — original
German and English screenshots from the demo installation.

## What you get

- **More signals, less configuration.** Discover supported physical inputs and outputs
  without adding visualization controls just to use them in Home Assistant.
- **Devices that belong together.** Group physical channels under their actual device
  where the Miniserver program provides the required topology.
- **Real-time updates for eligible signals.** Receive changes directly, including
  supported signals outside the visualization.
- **A verified project backup before changes.** Keep the complete original program
  and a project file that can be opened in Loxone Config.

**Current release: 1.5.0.** Project backup, automatic upload/restart, UDP heartbeat reception and
integration reload were verified on the demo installation. Physical device
transitions and restoration from backup still require acceptance testing.
Gateway/Client installations (several Miniservers, several program files in one
archive) are detected and left unchanged; automatic UDP setup for them is not yet supported.

## Install with HACS

1. In HACS, open **Custom repositories** from the menu.
2. Add `https://github.com/smartmacherei/Loxone-Integration` as an **Integration**.
3. Download **Loxone** and restart Home Assistant.
4. Open **Settings → Devices & services → Add integration → Loxone**.
5. Enter the Miniserver address, HTTP port, username and password. The form defaults
   to `80`. If your Miniserver uses another HTTP port, enter that port explicitly.
6. Below the connection data the form shows two ways. **Way 1 (HA → Loxone)** is always
   active: Home Assistant reads controls and terminals from the Miniserver; its options
   only decide what gets created. **Way 2 (Loxone → HA)** is optional: the Miniserver
   pushes real-time values over UDP. It changes the Miniserver program, see the
   [disclaimer](#disclaimer) before enabling it.

HACS offers the published GitHub releases for this custom repository.
This fork uses the same `loxone` domain as PyLoxone. Install only one of them.
Use a non-default Miniserver password and an account allowed to read the program.
Home Assistant must be able to reach the Miniserver on the local network.

## Automatic real-time setup (UDP)

For new installations, the setup form offers automatic real-time configuration for
eligible discovered terminals. Existing installations keep their current behavior
until you explicitly enable the option.

The number of real-time signals is limited (default 500, adjustable in the form) so a
very large installation cannot flood the Miniserver, the network or Home Assistant.
Terminals above the limit keep the 30-second polling. Once configured, the integration
only reads the Miniserver's program directory listing every 60 seconds; the program
itself is downloaded again only after Loxone Config saved a new one.

**Automatic setup changes the Miniserver program and briefly restarts its logic.**
It needs permission to upload and activate the program. Before any change, the
integration saves and verifies the complete original archive and an openable
`.Loxone` project. **If the backup fails, no upload or restart takes place.**

The integration also checks replacement programs and can configure real-time updates
again when needed. This may cause another backup and brief restart. Avoid simultaneous
saves from Loxone Config while setup is running. Load the current program
**from the Miniserver** before editing it.

See [setup requirements, technical details and recovery](docs/automatic-udp.md)
for the full procedure and the exact settings.

## Scope and limitations

See [device coverage and the acceptance checklist](docs/device-coverage.md) for
native controls, read-only states, special formats and the tested project coverage.

- Real-time support applies to eligible signals, not every terminal. Unwired outputs
  and unsupported value formats may still update at 30-second intervals.
- Existing visualization controls continue to use their established live connection.
  No additional visualization entries are needed for supported discovered terminals.
- Automatic editing currently supports the tested Loxone Config 17.1/17.2 program
  formats. Unsupported formats are left unchanged.
- Physical output switches write directly to terminals. Review their use if the
  Loxone program also controls those outputs; disable unwanted entities or discovery.
- The integration does not automatically discover a changed Miniserver IP address.
  Use a stable address or update the host option.
- Gateway/Client installations: the program archive of a Gateway contains one program
  per Miniserver. Automatic UDP setup stops before any change with the error code
  `ARCHIVE_MULTIPLE_PROGRAMS`. Everything else (WebSocket, polling) works as usual.
- State updates reach the entities through an internal dispatcher. The former bus
  event `loxone_event` is no longer fired, which keeps the recorder database small.
  Automations should use entity states; `loxone_send` for commands is unchanged.
- Lighting moods are available as effects of the light entity. Generated scene
  entities were removed in 1.5.0; their registry entries are cleaned up automatically.

Installing updated integration code requires restarting Home Assistant.

After deleting devices in Loxone Config, save the program to the Miniserver and
reload the Loxone integration in HA. Deleted UUIDs are reconciled against the
verified full project; offline devices remain. Automatic setup checks program
changes every 60 seconds when enabled and reloads after successful configuration.
If automatic setup is disabled or blocked, reload manually. Registry records are
backed up under `/config/loxone_registry_backups/<entry-id>/` before removal.
Cleanup is skipped if the project cannot be verified. Custom entity identifiers
that cannot be matched safely may still need manual review.

## Backups and support

On a standard HA installation, project backups are stored under
`/config/loxone_backups/<server-id>/`. They survive removing and reinstalling the
integration. Copy them to a separate computer for recovery if the HA server or its
storage fails. [Restore your original project](docs/automatic-udp.md#restore-the-original-project).

If setup fails, check the HA notification and integration diagnostics. The diagnostic
status distinguishes setup progress from actual reception of live data. Quiet inputs
may not send updates until their value changes.

For support, include integration, HA and Miniserver versions and the observed error.
**Do not attach project backups or credentials to public issues.**

## Disclaimer

This integration is an independent project by smartmacherei e.U. It is not affiliated
with, endorsed by or supported by Loxone Electronics GmbH. "Loxone" and "Miniserver"
are trademarks of their respective owners.

**Automatic real-time setup (Way 2) downloads the Miniserver program, adds a page with
logger objects, uploads the changed program and restarts the Miniserver logic.** The
integration saves and verifies a complete backup first and stops whenever a check fails.
You nevertheless use this feature at your own risk. The software is provided "as is"
without warranty of any kind, as stated in the Apache License 2.0. To the extent
permitted by law, smartmacherei e.U. and the contributors accept no liability for damage
of any kind resulting from the use of this integration, including but not limited to
loss or corruption of Miniserver programs, malfunction or downtime of building services
(heating, lighting, shading, access control, alarm systems), data loss, or the cost of
restoring a project. Before enabling automatic setup, keep your own current project
backup in Loxone Config, review the changed program afterwards, and enable it only on
installations you are authorised to change.

## License

Apache License 2.0: [LICENSE](LICENSE) and [NOTICE](NOTICE).
Based on PyLoxone by JoDehli and contributors, with modifications by smartmacherei.

## Room mapping / Raumzuordnung

[Optional room mapping during setup and in integration options / Optionale Raumzuordnung](docs/room-mapping.md).
[UDP setup diagnostics / UDP-Einrichtungsdiagnose](docs/udp-setup-diagnostics.md).

[Connection checks and diagnostic downloads / Verbindungspruefung und Diagnosedaten](docs/connection-diagnostics.md).
