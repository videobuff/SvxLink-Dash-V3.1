# PI3TWE fork

Based on https://github.com/f5vmr/SvxLink-Dash-V3.1 at commit
01816f4. The upstream history and attribution are retained.

This commit preserves the working Debian NUC installation of 14 October 2026:
SvxLink 26.05.2, EchoLink PI3TWE-R, the dashboard on port 5001, analogue audio
through the NUC sound card, and a supervised four-channel USB relay interface.
Local settings and credentials are deliberately excluded; retain the existing
`/opt/dashboard/config/node_model.json` and `/etc/pi3twe/svxlink` on deployment.

## Changes

- Configuration is deployed to `/etc/pi3twe/svxlink` and controls
  `pi3twe-svxlink.service` using restricted service helpers.
- VOX is selectable for a single receiver without a connected COR input.
- Maintenance accepts both `/maintenance` and `/maintenance/`. Restart only
  restarts SvxLink, with an error response when the command fails.
- PTT is controlled by the supervisor using a PTY. The supervisor owns relay
  sequencing, standby checks, the shared transmitter lock and timeout handling.
- The runtime config resolves its module directory against the original config
  path, preventing stale `/run` module settings and EchoLink remote-script errors.
- The custom event wrapper loads the standard repeater handlers for Pi3tweLogic.
- Configuration builds no longer replace the system login banner.

## Installation boundary

`install/install-pi3twe-nuc.sh` captures the installation procedure for the
existing PI3TWE host. It requires root, the existing controller and audio
services, a staged SvxLink 26.05.2 installation, and an ABI-matched
`Pi3tweLogic.so`. Supply the staged install directory and plugin as arguments.
The generic upstream installer is not the migration procedure for this host.
Never overwrite local configuration with an example model during an update.

This is a snapshot of the working integration, not a completed removal of the
old controller. The following dependencies must be migrated before stopping it:

- `pi3twe.service`, `pi3twe-audio-init.service` and their runtime directories;
- `/run/pi3twe-transmitter/route.lock`;
- controller standby and news spool files;
- the SDR stream-source setting checked before starting SvxLink;
- the custom native Pi3tweLogic plugin and its ABI manifest.

Future control pages can live inside SvxDash and reuse its templates, navigation
and authentication. Move the controller's functions and state to that interface
before decommissioning the old web service.

## Verification

Run `python3 -m unittest discover -s tests -v` and `git diff --check`.
The tests mock service commands; they never transmit or restart the host.
The running host was also checked by a successful incoming iPhone EchoLink QSO.
