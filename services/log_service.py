#!/usr/bin/env python3

"""
SvxLink log path resolver.

Determines the active SvxLink log file from /etc/default/svxlink.
"""

from pathlib import Path
import shlex


DEFAULT_FILE = Path("/etc/default/svxlink")

PREFERRED_LOG = Path("/var/log/pi3twe-svxlink/svxlink.log")
LEGACY_LOG = Path("/var/log/svxlink.log")


def get_svxlink_log_path():
    """
    Determine active SvxLink log path.

    Preferred source:
    - LOGFILE from /etc/default/svxlink

    Fallback:
    - /var/log/svxlink.log
    - /var/log/svxlink
    """

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

    if PREFERRED_LOG.exists():
        return PREFERRED_LOG

    return LEGACY_LOG
