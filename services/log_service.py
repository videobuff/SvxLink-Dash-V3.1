#!/usr/bin/env python3

"""
SvxLink log path resolver.

Prefers the PI3TWE controller log, then the standard SvxLink configuration.
"""

from pathlib import Path
import shlex


DEFAULT_FILE = Path("/etc/default/svxlink")

PREFERRED_LOG = Path("/var/log/pi3twe-svxlink/svxlink.log")
LEGACY_LOG = Path("/var/log/svxlink.log")


def get_svxlink_log_path():
    """
    Determine active SvxLink log path.

    Prefer the existing PI3TWE controller log. Otherwise use LOGFILE from
    /etc/default/svxlink, falling back to /var/log/svxlink.log.
    """

    if PREFERRED_LOG.exists():
        return PREFERRED_LOG

    if DEFAULT_FILE.exists():

        try:
            for line in DEFAULT_FILE.read_text(
                encoding="utf-8",
                errors="ignore",
            ).splitlines():

                line = line.strip()

                if not line or line.startswith("#"):
                    continue

                if line.startswith("LOGFILE="):

                    value = line.split("=", 1)[1].strip()

                    if value:
                        value = shlex.split(value)[0]
                        return Path(value)

        except Exception:
            pass

    return LEGACY_LOG
