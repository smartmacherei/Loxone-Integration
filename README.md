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

**Current release: 1.3.3.** Project backup, automatic upload/restart, UDP heartbeat reception and
integration reload were verified on the demo installation. Physical device
transitions and restoration from backup still require acceptance testing.

## Install with HACS

1. In HACS, open **Custom repositories** from the menu.
2. Add `https://github.com/smartmacherei/Loxone-Integration` as an **Integration**.
3. Download **Loxone (smartmacherei)** and restart Home Assistant.
4. Open **Settings → Devices & services → Add integration → Loxone**.
5. Enter the Miniserver address, HTTP port, username and password. The form defaults
   to `8080`; many installations use `80`. Use your Miniserver's actual port.

HACS offers the published GitHub releases for this custom repository.
This fork uses the same `loxone` domain as PyLoxone. Install only one of them.
Use a non-default Miniserver password and an account allowed to read the program.
Home Assistant must be able to reach the Miniserver on the local network.

## Automatic real-time setup in 1.3.3

For new installations, the setup form offers automatic real-time configuration for
eligible discovered terminals. Existing installations keep their current behavior
until you explicitly enable the option.

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

Installing updated integration code requires restarting Home Assistant.

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

## License

Apache License 2.0: [LICENSE](LICENSE) and [NOTICE](NOTICE).
Based on PyLoxone by JoDehli and contributors, with modifications by smartmacherei.
