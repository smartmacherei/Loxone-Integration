# Automatic UDP setup and project recovery

[Deutsch](automatic-udp.de.md) · [Main guide](../README.md)

This technical guide explains how real-time updates for eligible signals work without
adding controls to the customer's visualization. Existing visualization controls keep
using WebSocket; discovered terminals with usable sources use the additional UDP path.

Version 1.3.1 adds heartbeat monitoring and periodic verification. See
[device coverage and source selection](device-coverage.md) for the exact fallback
behavior and the limitations of read-only special values.

## Settings

| Setting | Default for new installations | Purpose |
|---|---|---|
| Auto-discover physical terminals | On | Add eligible terminals outside the visualization |
| Automatically set up real-time UDP | On | Back up and configure the logger program automatically |
| UDP port | `55555` | Receive logger packets; `0` disables UDP and automatic program changes |
| Maximum number of additionally discovered terminals | `500` | One bound for discovered entities, their polling and logger references, in program order |
| LightControllerV2 subcontrols | Off | Enable individual light-controller channels by default |

Lighting moods are always available as effects of the light entity. The scene options
of earlier versions were removed in 1.5.0.

Once configured, the periodic check (every 60 seconds) only reads the Miniserver's
program directory listing. The program archive itself is downloaded again only after
Loxone Config saved a new one, so an idle installation causes no repeated downloads.

Automatic setup requires a complete current program ZIP, permission to read/upload
and activate the program, local FTP/FTPS on port 21, an IPv4 route to the Miniserver,
and a free UDP port on HA. Automatic editing currently accepts object formats `175`
and `178`. Other formats remain unchanged. No router or firewall settings are changed.

## Before enabling automatic setup

Automatic setup is offered during new installation and can be changed in the
integration options. Existing entries without this option remain read-only with
respect to the Miniserver program. Disabling terminal discovery or setting the UDP
port to `0` also disables automatic program changes. Disabling setup does not remove
loggers already written to the Miniserver.

When enabled, the integration reads the current complete program ZIP. It creates
references only for discovered terminals with usable signal sources. Matching manual
loggers are reused. Objects owned by this integration use deterministic identifiers;
its own page is called **HA UDP (smartmacherei)**. Do not add customer logic to that page.
Existing application logic, permissions and other archive files are preserved.

## Backup is mandatory

Before uploading any changed program, the integration:

1. Validates the ZIP contents and the LoxCC program checksum.
2. Saves the **complete, unmodified original ZIP** to
   `/config/loxone_backups/<server-id>/<sha256>.zip`.
3. Saves the decoded original project as `<sha256>.Loxone`, for opening in Loxone Config.
4. Flushes both files to storage, reads them back and checks their contents.
5. Saves and verifies a JSON record with source filename, size, SHA-256 and UTC time.

Any failure stops the operation before FTP is opened. Different project versions
have different filenames and never overwrite one another. No automatic backup
pruning is performed. The directory is outside `www`, uses restrictive permissions
on HA, and remains after integration removal. It contains sensitive project data.

Use File editor, Studio Code Server, Samba or your existing administrator file access
to copy the files to a separate computer. Include the configuration directory in your
HA backup plan. A backup only on the HA disk cannot protect against that disk failing.
The UDP status attributes/notification identify the backup folder.

## Upload and verification

The prepared ZIP is uploaded under a temporary filename and downloaded again to
verify its SHA-256. Before activation the original program is fetched again and
compared byte for byte. If a program changed or another `sps_new.*` upload is pending,
automatic activation stops. The verified ZIP is then renamed to `sps_new.zip` and the
Miniserver is asked to restart its program. This briefly interrupts the logic.

FTPS is preferred; plain FTP is used only when the server explicitly reports that
AUTH TLS is unsupported. Use this feature on a trusted local connection.
Do not save from Loxone Config concurrently: the Miniserver has no cross-client
transaction lock, so the final check cannot eliminate every possible race.

On a later check, the running program must contain the expected functional logger
references before setup reports configured. HA reloads after detected program changes
to refresh the entities. **Receiving UDP data** means known terminal packets have
actually arrived. **Waiting for UDP data** and **No recent UDP data** are not proof
of a fault, because unchanged values may not emit packets.

## Restore the original project

1. Disable automatic UDP setup in Home Assistant, or stop HA, to prevent automatic
   reapplication after restoration.
2. Copy the desired `.Loxone` backup to your computer. The matching `.json` gives its
   original filename and backup time; the `.zip` contains the full original archive.
3. Open the `.Loxone` file in a compatible Loxone Config version.
4. Connect to the intended Miniserver and select **Save in Miniserver**. This replaces
   the running program and briefly restarts the logic. Confirm the result in Config.
5. Reconnect HA. Keep automatic setup disabled while investigating the original fault.

If HA is unavailable, use an already downloaded copy, or recover this backup folder
from your HA backup. Recovery through Loxone Config does not depend on this integration.
Do not upload project archives to public GitHub issues.

## Failed setup and deliberate retry

The `activation.json` file remembers attempted source-program/destination combinations.
An unsuccessful or uncertain activation is not repeated automatically, including after
HA restarts or reinstallation. A genuinely new program is evaluated separately.

Check the cause first: backup storage, supported program format, credentials, FTP access,
UDP port or a concurrent Config upload. If cleanup could not be verified, inspect
`/prog/sps_new.zip` on the Miniserver with your installer before restarting it: a pending
file can be loaded on a future restart. Do not remove another person's pending upload.

For an intentional retry of the same program, disable automatic setup and wait for the
integration to unload. Retain the original backup, then rename `activation.json` in
that server's backup folder to `activation.previous.json` (use a unique filename if
needed). Re-enable setup after resolving the cause. This is an administrator action,
not a routine installation step. There is no automatic restore/restart loop.

## Validation of version 1.3.3

Offline tests cover archive integrity, project preservation, repeat runs, mandatory
backup verification, interrupted uploads and the activation guard. Import/setup-form
checks also run in HA 2026.7.2. Backup, upload/restart and the resulting active program
were verified on the demo Miniserver 17.2.8.28. Live UDP heartbeat reception and
integration reload were confirmed. Physical device transitions and restoration
remain untested; see [device coverage and acceptance](device-coverage.md).
