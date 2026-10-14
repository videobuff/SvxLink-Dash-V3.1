# SvxLink-Dash PI3TWE fork

PI3TWE adaptations of [f5vmr/SvxLink-Dash-V3.1](https://github.com/f5vmr/SvxLink-Dash-V3.1).
See [PI3TWE setup and migration notes](docs/PI3TWE.md) for the working NUC configuration,
installation prerequisites, changes and remaining controller dependencies.

---

# SvxLink-Dash-V3.1

A modern Flask-based configuration and runtime dashboard for SvxLink systems.

SvxLink-Dash-V3.1 provides:

- Guided SvxLink configuration using SvxLink V26.05.1 from Tobias Blomberg SM0SVX
- Runtime operational dashboard
- Reflector management
- EchoLink and METAR module configuration
- Live reflector activity monitoring
- DTMF talkgroup control
- Protected runtime editing environment
- Hardware and system telemetry
- Live log viewer
- Node information generation
- Multi-platform deployment support

The project is intended for both:

1. Existing SvxLink users wanting a modern configuration/dashboard layer

2. Complete appliance-style SvxLink images for Raspberry Pi, NanoPi-Neo, and a build structure for Linux PC and similar systems.
NB the current structure is in English only and presented for the https://ukwide.svxlink.net, https://north.america.svxlink.net and the https://au.svxlink.net Svxreflectors

---

# Features

## Configuration Builder

- Guided SvxLink configuration workflow
- Simplex and repeater node support on multiple ports
- Reflector support
- EchoLink support
- METAR module support
- Courtesy tone / roger tone support
- GPIO and audio configuration
- Node information generation
- Configuration review before deployment

## Runtime Dashboard

- Live node status
- Service monitoring
- Reflector connection state
- Squelch state
- EchoLink activity
- Monitored talkgroups display
- Live reflector activity feed
- DTMF talkgroup buttons
- Manual DTMF command entry
- Hardware telemetry
- Live system log viewer

## Operational Editing

Protected editing environment with authentication:

- Talkgroup buttons
- Monitoring talkgroups
- EchoLink module
- METAR module
- Node information

## Deployment Features

- Automatic configuration rendering
- Automatic SvxLink restart
- Backup-aware deployment
- Systemd service support
- Automatic permission correction
- Portable log-path detection

---

# Supported Platforms

Tested platforms currently include:

Raspberry Pi / Raspberry Pi OS Bookworm / Raspberry Pi OS Trixie
NanoPi Neo / Armbian Bookworm
Linux PC Bookworm LTS

Other Debian-based systems may also function correctly.


---

# Browser Support

Tested with:

- Chromium
- Chrome
- Firefox

---

# Installation

## Quick Install

The installer automatically:

- Downloads SvxLink-Dash-V3.1 into `/opt/dashboard`
- Installs required Python packages
- Configures permissions
- Installs the systemd service
- Configures restricted sudo permissions
- Enables and starts the dashboard service

Run:

```bash
cd /tmp
wget https://raw.githubusercontent.com/f5vmr/SvxLink-Dash-V3.1/main/install/install-dashboard.sh
chmod +x install-dashboard.sh
sudo ./install-dashboard.sh
```

After installation:

```text
http://svxlink.local:5000/
```

---

# Existing SvxLink Requirements

SvxLink must already be operational.

Expected components:

```text
SvxLink Version 26.05.1 in this case 
```

The dashboard assumes:

- SvxLink already functions correctly
- `/etc/svxlink` is present
- DTMF PTY control is enabled
- `/dev/shm/....Logic` exists..

---

# Python Dependencies

Installed automatically by the installer.

Equivalent packages:

```bash
python3
python3-flask
python3-jinja2
python3-werkzeug
python3-psutil
```

---

# Log File Detection

The dashboard automatically determines the active SvxLink log file.

Priority:

1. `LOGFILE=` from `/etc/default/svxlink`
2. `/var/log/svxlink.log`
3. `/var/log/svxlink`

This allows compatibility with:

- Standard SvxLink installations
- Appliance-style images
- Custom deployments

---

# Authentication

Runtime editing functions are protected by dashboard authentication.

Public runtime monitoring remains accessible.

Protected pages include:

- Talkgroups
- Monitoring TGs
- EchoLink editing
- METAR editing
- Node information editing
- Log viewer

Dashboard credentials are configured during initial setup.

---

# Forgotten Credentials

Dashboard credentials can be reset locally on the Linux console.

Run:

```bash
sudo /opt/dashboard/tools/reset_dashboard_auth.py
```

---

# Systemd Service

Installed service:

```text
svxlink-dash.service
```

Service user:

```text
svxlink:svxlink
```

The dashboard intentionally runs as the SvxLink user to allow:

- PTY DTMF control
- Configuration deployment
- Runtime management

---

# Restricted sudo Permissions

The installer configures restricted sudo access for:

```text
systemctl restart svxlink
systemctl is-active svxlink
and a number of other functions
```

via:

```text
/etc/sudoers.d/svxlink-dash
```

---

# Runtime Dashboard Overview

The dashboard provides:

## Left Column Operational State

- Node
- Service
- Reflector
- Modules
- Radio Status
- Squelch State
- Monitoring TGs
- Active TGs
- EchoLink Activity
- Uptime

## Main Operational Area

- Live reflector activity feed
- Talkgroup controls
- Manual DTMF command entry

## System Footer

- Hostname
- IP address
- OS information
- Kernel version
- CPU temperature
- Disk usage
- Memory usage

---

# Manual DTMF Commands

## Talkgroups

Prefix TG numbers with:

```text
91
```

Terminate with:

```text
#
```

Example:

```text
91235#
```

## EchoLink

Open module:

```text
2#
```

Then send:

```text
<node>#
```

Exit EchoLink:

```text
##
```

## METAR

Open module:

```text
5#
```

Airport selection examples:

```text
1#
2#
3#
```

Exit METAR:

```text
#
```

---

# Node Information

The dashboard generates:

```text
/etc/svxlink/node_info.json
```

The setup workflow supports:

- Decimal latitude/longitude
- Maidenhead locator
- DMS coordinate formats
- RF information
- Antenna information

Useful locator resource:

https://www.levinecentral.com/ham/grid_square.php

---

# Repository Layout

```text
/opt/dashboard
├── app.py
├── templates/
├── static/
├── services/
├── renderers/
├── install/
├── config/
├── backups/
└── tools/
```

---

# Service Management

## Restart Dashboard

```bash
sudo systemctl restart svxlink-dash
```

## View Dashboard Status

```bash
sudo systemctl status svxlink-dash
```

## Restart SvxLink

```bash
sudo systemctl restart svxlink
```

---

# Troubleshooting

## Dashboard Does Not Start

Check:

```bash
sudo systemctl status svxlink-dash
```

## Live Log Viewer

The dashboard includes a protected live log viewer.

Alternatively:

```bash
tail -f /var/log/svxlink.log
```

or the configured log file from:

```text
/etc/default/svxlink
```

## DTMF Buttons Not Working

Verify:

```text
/dev/shm/simplex_dtmf_ctrl or /dev/shm/repeater_dtmf_ctrl
```

exists and is writable by user `svxlink`.

---

# Reflector Protocol Notice

SvxLink-Dash-V3.1 is written primarily for the following SvxReflector Protocol 2 networks running SvxLink Version 25:

- UKWide
- North America
- Australia
- Other SvxReflectors can be considered, but method of user verification and entry of a password will need to be discussed with the prospective SvxReflector Manager.

The generated `[ReflectorLogic]` section includes the required base elements for SvxReflector Protocol 3 support, however Protocol 3-specific configuration currently requires manual modification by the system operator.

Important:

If manual Protocol 3 modifications have been applied to:

```text
/etc/svxlink/svxlink.conf
```

then using the dashboard `Rebuild` function may overwrite those manual changes.

In Protocol 3 environments it is therefore recommended that operators avoid using the full rebuild function unless they are prepared to reapply their custom reflector configuration afterwards.

---

# Current Limitations

Currently not implemented:

- Browser audio streaming

This may be added in future versions.

---

# Credits

SvxLink Software: Version 26.05

Tobias Blömberg SM0SVX

Version 3.1

was developed by Chris Jackson, G4NAB.
Additional assistance with Python, Flask, configuration rendering,
debugging and documentation was provided through ChatGPT by OpenAI.

---

# License

This project is distributed as useful to the amateur radio community.
