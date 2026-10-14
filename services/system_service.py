#!/usr/bin/env python3

"""
System maintenance helpers for SvxLink-Dash-V3.1.
"""

import subprocess


def restart_services():
    """
    Restart SvxLink and dashboard services.
    """

    subprocess.Popen(
        [
            "sudo",
            "/usr/local/sbin/pi3twe-dashboard-control",
            "restart-all",
        ]
    )


def reboot_device():
    """
    Reboot the device.
    """

    subprocess.Popen(
        [
            "sudo",
            "/usr/local/sbin/pi3twe-dashboard-control",
            "reboot",
        ]
    )

def schedule_reboot(delay_seconds=3):
    return subprocess.run(
        [
            "sudo",
            "-n",
            "/usr/local/sbin/pi3twe-dashboard-control",
            "reboot",
        ],
        text=True,
        capture_output=True,
    )

def shutdown_device():
    """
    Shut down the device.
    """

    subprocess.Popen(
        [
            "sudo",
            "/usr/local/sbin/pi3twe-dashboard-control",
            "shutdown",
        ]
    )
