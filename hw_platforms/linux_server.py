#!/usr/bin/env python3

"""
Generic Linux server platform profile for SvxLink-Dash-V3.1.
"""

PROFILE = {
    "id": "linux_server",
    "name": "Generic Linux Server",
    "supported": True,

    "allowed_node_types": [
        "simplex",
        "repeater",
    ],

    "allowed_interface_modes": [
        "hidraw",
        "serial",
    ],

    "allowed_squelch_modes": [
        "vox",
        "hidraw",
        "serial",
        "ctcss",
    ],

    "default_interface_mode": "hidraw",

    "gpio": {
        "sql": None,
        "ptt": None,
    },

    "audio": {
        "audio_dev": "alsa:plughw:0",
        "audio_channel": 0,
    },

    "notes": [
        "Generic Linux servers support HIDRAW and serial hardware control.",
        "Native Raspberry Pi and NanoPi GPIOD pin profiles are unavailable.",
        "HIDRAW requires a supported CM108/CM119 or TOADS interface.",
        "Serial control requires a suitable physical or USB serial interface.",
    ],
}