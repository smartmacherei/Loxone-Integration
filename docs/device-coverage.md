# Device coverage and acceptance testing

[Deutsch](device-coverage.de.md)

Validation scope for version 1.3.3: device presence, readable states and full native
control are separate capabilities. A device listed in Config is not proof of live
hardware or of support for every command.

## Supported representations

- Air, Tree and Link extension terminals are grouped by their physical containers,
  including supported nested DALI, Modbus, EnOcean and Internorm devices.
- Generic numeric and digital signals remain discoverable without recognized names.
  Current, voltage, pressure and battery percentages receive appropriate classes.
- RGBW, T5, API and text formats use read-only raw sensors. An invalid/unavailable
  server value remains unknown. These sensors are not native light controls or
  button events; a composite T5 terminal does not simulate five button presses.
- Existing native HA platforms remain responsible for supported visualization
  controls. Other control types expose their named WebSocket states as read-only
  sensors, including structured values. No control commands or units are guessed.
- These additional sensors do not provide complete native Wallbox, Touch Display,
  pool or access-control user interfaces. Existing supported Loxone controls may
  provide part of the device's functionality.
- New protocol-specific outputs are read-only. Previously supported physical
  switches retain their behavior. Review exposed output switches before using them.
- Empty 1-Wire/M-Bus extensions cannot demonstrate sensor support; actual configured
  sensor objects and live hardware are required.

Discovery can create many entities. Disable unwanted entities in HA, or disable
automatic terminal discovery. Unknown units/meanings are preserved without assigning
an invented device class.

## Source selection

Automatic provisioning adds a logger reference to the existing system-second
output when available. This provides a one-second heartbeat without new Visu flags.
If that output is absent, the integration keeps conservative polling.

For an identical signal UUID, UDP takes priority while the heartbeat is fresh;
WebSocket is next when it provides that UUID or an equivalent state proven by
explicit project wiring. Transparent references and the supported Tree/Air Wallbox
target-power API channel can provide this mapping. Inverted, scaled or ambiguous
aliases are rejected. Names are never used to equate signals. Direct-discovery HTTP values
provide initial state and fallback, normally every 30 seconds, bounded to 200 requests
per cycle and two concurrent requests per Miniserver (large installations are polled in
rotation). Healthy UDP signals receive a verification query every 30 minutes. Heartbeat
expiry is five seconds; the next scheduled polling cycle supplies fallback values. A
silent, unchanged signal does not by itself indicate failure. Quiet WebSocket states
remain healthy while connected; verification is every 30 minutes. Entities that are
disabled in Home Assistant are not polled; device internals (online state, protective
shutdowns, internal temperature, raw formats) are created disabled. Battery levels and
device internals get no UDP logger reference; once enabled they are read every 4 hours
and never expire as unavailable. Cached WebSocket values can
take over on the next poll cycle after UDP loss. Direct-terminal values become
unknown/unavailable after 90 seconds without a usable source or fresh read, checked
at the end of each polling cycle.

Polling is limited to eight concurrent requests and a 30-second batch budget.
Overlapping batches are prevented. A push received during a request supersedes its
later HTTP reply. The heartbeat proves the channel is alive, not that every logger
is correct; periodic verification remains necessary. Raw formats can use a proven
WebSocket alias or a readable HTTP value. Unresolved placeholders such as `<v.col>`
remain unknown. DALI requires suitable configured source connections; discovery
alone cannot make an unconnected channel publish meaningful real-time values.

Only datagrams from the configured Miniserver IPv4 address and known signal IDs are
accepted. Diagnostics report heartbeat health and observed source counts. Existing
visualization state sensors use WebSocket; no unsupported state-UUID HTTP endpoint
is assumed as a fallback.

## Validation performed

The supplied September 9 test project contains 58 Air and 37 Tree devices plus Link
products. Source code was imported in an isolated process using the installed HA
2026.7.2 runtime. Construction and synthetic event processing succeeded for 1,213
direct terminal entities and 332 supplementary state sensors. Offline patching
produced 820 signal references and one heartbeat; 393 selected terminals were not
eligible for numeric UDP. Applying the patch twice made no further changes.

Read-only checks against Miniserver 17.2.8.28 returned usable HTTP values for 1,129
of 1,213 terminals. All 24 mapped terminal WebSocket states arrived; 883 of 886
declared states arrived during the short observation window. Both Wallbox target
channels matched their corresponding WebSocket values after correcting the HTTP
watts/kW mismatch (14.296 kW Tree; 7.4 kW Air). The correction is limited to the
structurally identified supported Wallbox channel; other firmware remains untested.
HTTP readability and initial WebSocket snapshots do not prove physical transitions.

The automated suite covers discovery boundaries, classification, raw formats,
heartbeat failure/recovery, periodic verification, late HTTP replies, UUID
validation, precision, original backups and activation failures.

Version 1.3.3 was installed on the demo HA server. Automatic provisioning completed
with a verified original-project backup, also copied to the laptop. The active
program matched the expected checksum and required no further patch. Live LAN
capture confirmed one heartbeat datagram per second, and HA reported healthy UDP.
An integration reload recovered without changing the 1,644 registry entries.
The 203 HA devices include both physical-device containers and logical controls;
these counts are not hardware counts. Of 1,590 loaded entities, 64 raw-value
entities remained unavailable. The 11 unknown scene states were not activated.

These checks do not replace physical acceptance testing. The observed heartbeat
proves the transport, not every device's state transitions or end-to-end latency.
Physical actuation and restoration from backup remain untested.

## On-site acceptance sequence

1. Keep the verified original ZIP and matching `.Loxone` backup outside HA as well.
2. Install the test package, restart HA, and review its entities and setup status.
3. If automatic setup is enabled, wait for its backup, activation and reconnection;
   load the current project from the Miniserver before further Config edits.
4. Operate actual inputs and compare measurements with Config. Verify raw formats
   and supported native controls separately; record unavailable values.
5. Verify loss/recovery of reception, HA restart and a replacement Config program
   on the demo installation. Check for duplicate entities and repeated restarts.
6. Verify restoration using the saved original project before customer rollout.

Do not publish original project archives, credentials or raw customer structures
with an issue report.
