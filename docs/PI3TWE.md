# PI3TWE in SvxDash

This fork extends [f5vmr/SvxLink-Dash-V3.1](https://github.com/f5vmr/SvxLink-Dash-V3.1)
and retains the original Git history and attribution. The PI3TWE backend was
migrated from the user's PI3TWE-Controller_new project into the `pi3twe` package.
It does not import or call the old controller installation.

## Dashboard

The real SvxDash runs on port **5000**. `/` opens its status dashboard.
The **PI3TWE** navigation entry uses the existing SvxDash login and visual style.

The page provides:

- Physical Icom Power on/off, with persistent desired state and relay monitoring.
- SvxLink AAN, STANDBY and UIT. Standby preserves EchoLink registration; UIT
  stops the engine and remains off across service restarts and reboots.
- Bulletin uploads (MP3, WAV, OGG, FLAC, M4A), browser-only audio previews,
  validity periods, enabling/disabling the hourly schedule, manual broadcasts,
  and deletion. New uploads are disabled until activated.
- News enable/disable, callsign, identification interval and announcement beeps.
- Analogue NUC audio levels, stream-source selection and SDR/RF monitor tuning.
- The existing durable event log and host uptime.

All PI3TWE APIs require authentication. Mutating requests additionally require
an unpredictable session token. Bulletin and event text is rendered as text.

## Existing-host migration

Run the following from the checked-out fork after tests pass:

```sh
sudo python3 install/migrate-pi3twe-dashboard.py
```

The installer targets the existing Debian NUC, USB relay **QAAMZ** and SvxLink
26.05.2 installation. It checks prerequisites and tests before stopping services.
It backs up the dashboard, service/helper configuration and original ownership
under `/var/backups/pi3twe-svxdash`, then migrates the SQLite database, news files
and standby setting to `/var/lib/pi3twe-svxdash` without removing the originals.
Local SvxDash configuration and credentials remain in `/opt/dashboard/config`.

SvxLink and SvxDash run as `svxlink`, with audio and USB relay access. The shared
transmitter lock is created independently through systemd-tmpfiles. SvxLink's
service no longer depends on `pi3twe.service` or files in the old checkout.
The existing independent ALSA initialization service remains in use.

The installer stops/disables the old system controller and the user dashboard
that previously occupied port 5000. It disables the obsolete microphone-gain
unit that enabled analogue loopback. Apache's PI3TWE proxy is updated to port
5000; the Grafana proxy remains available. The Prometheus target is moved to
5000 and the existing metric names remain available at `/metrics`. A read-only authenticated check of
PI3TWE state and native-engine readiness must succeed before completion.
An installation failure restores the previous files, ownership and services.
No Power or news transmission command is issued as a deployment check.

`install/install-pi3twe-nuc.sh` also requires a staged SvxLink installation and an
ABI-matched Pi3tweLogic plugin; it prepares those and invokes this migration.
The upstream generic installer is not the PI3TWE migration procedure.

## Persistent state and scheduling

Use one dashboard process. A process lock rejects a second scheduler or relay
reconciler. The persistent database stores Power state, news metadata, hourly
claims, event history and audio policy. After a SvxLink restart, the policy
monitor reapplies the saved identification settings through its command PTY.

The news scheduler runs in the first five minutes of each hour and claims each
active, valid bulletin at most once per UTC hour. Power, normal engine operation,
and enabled news are required for playback. A skipped or failed slot is logged;
it is not replayed later in the same hour. Manual broadcasts bypass the schedule
and validity period but still require Power, AAN and news permission.

Power off remains available during playback. TX/PTT relays are owned exclusively
by the SvxLink supervisor, never by dashboard buttons. News playback uses the
running native engine with beeps before and after; it does not restart SvxLink
or change ALSA routing. Analogue loopback/streaming is rejected while SvxLink
owns the microphone path. Browser audio preview never broadcasts to the radio.

## Validation

```sh
python3 -W error::ResourceWarning -m unittest discover -s tests -v
git diff --check
systemd-analyze verify install/svxlink-dash.service install/pi3twe-svxlink.service
```

Tests use dummy relays and engine commands, covering Power persistence, immediate
off, no direct TX, standby, authentication, news uploads/cleanup, scheduling,
playback lifecycle, policy rollback and analogue feedback prevention.
