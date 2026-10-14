#!/usr/bin/env python3

"""
SvxLink-Dash-V3.1 node model.

This file defines the authoritative configuration model used by:
- Flask setup pages
- validation logic
- svxlink.conf renderers
- future dashboard editing
"""

from copy import deepcopy


SUPPORTED_NODE_TYPES = {"simplex", "repeater"}

SUPPORTED_IDENT_MODES = {
    "none",
    "cw",
    "voice",
    "both",
}

SUPPORTED_ROGER_MODES = {
    "none",
    "beep",
    "morse_t",
    "morse_k",
}
SUPPORTED_IDLE_TONES = {
    "chime",
    "pip",
    "silence",
}

SUPPORTED_DOWN_TONES = {
    "biboop",
    "va",
    "none",
}
SUPPORTED_SQUELCH_METHODS = [
    "vox",
    "hidraw",
    "gpiod",
    "ctcss",
    "serial",
]
SUPPORTED_INTERFACE_MODES = {
    "hidraw",
    "gpiod",
    "hybrid",
    "serial",
}
NANOPI_NEO_GPIO_DEFAULTS = {
    "sql": {
        "chip": "gpiochip0",
        "line": 203,
        "active": "high",
    },
    "ptt": {
        "chip": "gpiochip0",
        "line": 6,
    },
}
DEFAULT_MODEL = {
    "schema_version": 1,
        "build": {
        "intent": "single_channel",
    },

    "platform": {
        "id": None,
        "name": None,
        "supported": False,
    },

    "node": {
        "type": None,
        "callsign": None,
        "language": "en_US",
    },
    "interface": {
        "mode": "hidraw",
        "sql_source": "hidraw",
        "ptt_source": "hidraw",
    },
    "reflector": {
        "enabled": False,
        "name": None,
        "host": None,
        "port": None,
        "auth_key": None,
    },

        "ident": {
            "short": {
            "mode": "cw",
            "interval": 15,
        },
        "long": {
            "mode": "voice",
            "interval": 60,
        },
    },
    "gpio": {
        "sql": {
            "chip": "gpiochip0",
            "line": 23,
            "active": "high",
        },
        "ptt": {
            "chip": "gpiochip0",
            "line": 24,
        },
    },
    "hidraw": {
        "device": "/dev/hidraw0",
        "sql_pin": "VOL_DN",
        "ptt_pin": "GPIO3",
    },
    "serial": {
        "sql_port": "/dev/ttyS0",
        "sql_pin": "CTS",
        "sql_set_pins": "DTR!RTS",
        "ptt_port": "/dev/ttyS0",
        "ptt_pin": "DTRRTS",
    },
    "cw": {
        "amp": -10,
        "pitch": 650,
        "cpm": 95,
    },
    "audio": {
        "audio_dev": "alsa:plughw:0",
        "audio_channel": 0,
    },
    "time_format": "24",
    "fx_gain_normal": 0,
    "fx_gain_low": -12,
    "sql_hangtime": 20,
    "sql_tail_elim": 270,
    "tg_timeout": 60,
    "tx_ctcss_mode": "ALWAYS",
    "online_control": {
        "enabled": False,
        "command": None,
    },
    "courtesy": {
        "mode": "none",
    },
    "repeater": {
    "idle_tone": "chime",
    "down_tone": "biboop",
    "idle_timeout": 10,
    "sql_timeout": 180,
    },
    "squelch": {
        "method": "hidraw",
        "ctcss_freq": None,
        "ctcss_tx": False,
    },
    "echolink": {
        "enabled": False,
        "callsign": None,
        "password": None,
        "sysopname": None,
        "location": None,
    },
        "metar": {
            "enabled": False,
            "region": None,
            "startdefault": None,
            "airports": [],
            "custom_startdefault": None,
    },  
        "modules": {
            "enabled": [
            "ModuleHelp",
            "ModuleParrot",
        ],
    },
}

def new_node_model(platform=None):
    """
    Return a fresh node model.

    platform may be a dict from the platform detection layer.
    """

    model = deepcopy(DEFAULT_MODEL)

    if platform is not None:
        platform_id = platform.get("id")

        model["platform"] = {
            "id": platform_id,
            "name": platform.get("name"),
            "supported": bool(platform.get("supported")),
        }

        if platform_id == "nanopi_neo":
            model["gpio"] = deepcopy(NANOPI_NEO_GPIO_DEFAULTS)

    return model
def is_ics_multiport_model(model):
    hardware = model.get("hardware", {})
    enabled_ports = model.get("ports", {}).get("enabled", [])

    return (
        hardware.get("family") == "ics"
        and len(enabled_ports)
    )
def is_multiport_model(model):
    enabled_ports = model.get("ports", {}).get("enabled", [])

    return (
        is_ics_multiport_model(model)
        or len(enabled_ports) > 1
    )
def validate_model(model):
    """
    Validate high-level model consistency.

    Returns:
        list[str]: validation error messages.
    """

    errors = []
    
    multiport = is_multiport_model(model)

    node_type = model.get("node", {}).get("type")
    callsign = model.get("node", {}).get("callsign")

    if multiport:
        nodes = model.get("nodes", {})
        enabled_ports = model.get("ports", {}).get("enabled", [])

        if not enabled_ports:
            errors.append("At least one port must be enabled.")

        if not nodes:
            errors.append("Port configuration is required.")

        for port in enabled_ports:
            port_id = str(port)
            node = nodes.get(port_id, {})

            if node.get("role") not in ("simplex", "repeater"):
                errors.append(
                    f"Port {port_id} type must be simplex or repeater."
                )

            if not node.get("callsign"):
                errors.append(
                    f"Port {port_id} callsign is required."
                )

    else:
        if node_type not in SUPPORTED_NODE_TYPES:
            errors.append("Node type must be simplex or repeater.")

        if not callsign:
            errors.append("Callsign is required.")

    short_ident = model.get("ident", {}).get("short", {})
    long_ident = model.get("ident", {}).get("long", {})

    if short_ident.get("mode") not in SUPPORTED_IDENT_MODES:
        errors.append("Short ident mode is invalid.")

    if long_ident.get("mode") not in SUPPORTED_IDENT_MODES:
        errors.append("Long ident mode is invalid.")

    for ident_name, ident_data in (
        ("Short", short_ident),
        ("Long", long_ident),
    ):
        interval = ident_data.get("interval")

        if not isinstance(interval, int):
            errors.append(f"{ident_name} ident interval must be a number.")
        elif interval < 1:
            errors.append(f"{ident_name} ident interval must be at least 1 minute.")

    enabled_ports = [
        str(port)
        for port in model.get("ports", {}).get("enabled", [])
    ]

    is_multiport = multiport
    
    if is_multiport:
        nodes = model.get("nodes", {})

        for port_id in enabled_ports:
            port_node = nodes.get(port_id, {})
            role = port_node.get("role", "simplex")
            courtesy = port_node.get("courtesy", {})
            roger_mode = courtesy.get("mode", "none")

            if roger_mode not in SUPPORTED_ROGER_MODES:
                errors.append(
                    f"Port {port_id}: roger tone mode is invalid."
                )

            if role == "repeater" and roger_mode == "none":
                errors.append(
                    f"Port {port_id}: repeater mode requires a roger tone."
                )

            if role == "repeater":
                idle_tone = courtesy.get("idle_tone", "none")
                down_tone = courtesy.get("down_tone", "none")

                if idle_tone not in SUPPORTED_IDLE_TONES:
                    errors.append(
                        f"Port {port_id}: idle tone mode is invalid."
                    )

                if down_tone not in SUPPORTED_DOWN_TONES:
                    errors.append(
                        f"Port {port_id}: close-down tone mode is invalid."
                    )

    else:
        roger_mode = model.get("courtesy", {}).get("mode")

        if roger_mode not in SUPPORTED_ROGER_MODES:
            errors.append("Roger tone mode is invalid.")

        if node_type == "repeater" and roger_mode == "none":
            errors.append("Repeater mode requires a roger tone.")

        if node_type == "repeater":
            idle_tone = model.get("repeater", {}).get("idle_tone")
            down_tone = model.get("repeater", {}).get("down_tone")

            if idle_tone not in SUPPORTED_IDLE_TONES:
                errors.append("Idle tone mode is invalid.")

            if down_tone not in SUPPORTED_DOWN_TONES:
                errors.append("Close-down tone mode is invalid.")
    
    if not multiport:            
        interface_mode = model.get("interface", {}).get("mode")

        if interface_mode not in SUPPORTED_INTERFACE_MODES:
            errors.append("Interface mode is invalid.")

        squelch_method = model.get("squelch", {}).get("method")

        if squelch_method not in SUPPORTED_SQUELCH_METHODS:
            errors.append("Squelch method is invalid.")

    reflector = model.get("reflector", {})

    if reflector.get("enabled"):
        if not reflector.get("host"):
            errors.append("Reflector host is required.")
        if not reflector.get("port"):
            errors.append("Reflector port is required.")
        if not reflector.get("auth_key"):
            errors.append("Reflector authentication key is required.")
        elif len(str(reflector.get("auth_key"))) != 16:
            errors.append("Reflector authentication key must be 16 characters.")
 
    echolink = model.get("echolink", {})

    if echolink.get("enabled"):
        echolink_callsign = echolink.get("callsign")

        if not echolink_callsign:
            errors.append("EchoLink callsign is required.")
        elif not (
            echolink_callsign.endswith("-L")
            or echolink_callsign.endswith("-R")
        ):
            errors.append("EchoLink callsign must end in -L or -R.")

        if not echolink.get("password"):
            errors.append("EchoLink password is required.")

        if not echolink.get("sysopname"):
            errors.append("EchoLink sysop name is required.")

        location = echolink.get("location")

        if not location:
            errors.append("EchoLink location is required.")
        elif not location.startswith("[Svx] "):
            errors.append("EchoLink location must start with [Svx].")
        elif len(location.replace("[Svx] ", "", 1)) > 12:
            errors.append("EchoLink location text must be 12 characters or fewer.")
    
    return errors


def set_node_identity(model, node_type, callsign):
    """
    Set basic node identity.
    """

    model["node"]["type"] = node_type
    model["node"]["callsign"] = callsign.strip().upper()
    return model


def set_ident(model, short_mode, short_interval, long_mode, long_interval):
    """
    Set short and long identification behaviour.
    """

    model["ident"]["short"]["mode"] = short_mode
    model["ident"]["short"]["interval"] = int(short_interval)

    model["ident"]["long"]["mode"] = long_mode
    model["ident"]["long"]["interval"] = int(long_interval)

    return model


def set_roger(model, roger_mode):
    """
    Set roger tone mode.

    Repeater enforcement is validated separately.
    """

    model["courtesy"]["mode"] = roger_mode
    return model

def set_interface_mode(model, mode):
    """
    Set physical SQL/PTT control interface.

    gpiod:
        SQL = GPIOD
        PTT = GPIOD

    hidraw:
        SQL = HIDRAW
        PTT = HIDRAW

    hybrid:
        SQL = GPIOD
        PTT = HIDRAW
    """

    if mode == "gpiod":
        model["interface"] = {
            "mode": "gpiod",
            "sql_source": "gpiod",
            "ptt_source": "gpiod",
        }

    elif mode == "hidraw":
        model["interface"] = {
            "mode": "hidraw",
            "sql_source": "hidraw",
            "ptt_source": "hidraw",
        }

    elif mode == "hybrid":
        model["interface"] = {
            "mode": "hybrid",
            "sql_source": "gpiod",
            "ptt_source": "hidraw",
        }

    else:
        raise ValueError(f"Unsupported interface mode: {mode}")

    return model

def set_squelch(model, method, ctcss_freq=None, ctcss_tx=False):
    """
    Set squelch configuration.
    """

    model["squelch"]["method"] = method
    model["squelch"]["ctcss_freq"] = ctcss_freq
    model["squelch"]["ctcss_tx"] = bool(ctcss_tx)

    return model


def enable_reflector(model, name, host, port, auth_key):
    """
    Enable reflector configuration.
    """

    model["reflector"] = {
        "enabled": True,
        "name": name,
        "host": host,
        "port": int(port),
        "auth_key": auth_key,
    }

    return model


def disable_reflector(model):
    """
    Disable reflector configuration.
    """

    model["reflector"] = {
        "enabled": False,
        "name": None,
        "host": None,
        "port": None,
        "auth_key": None,
    }

    return model
    
def set_echolink(
    model,
    enabled,
    callsign=None,
    password=None,
    sysopname=None,
    location=None,
):
    """
    Set EchoLink module configuration.

    EchoLink LOCATION is built as:
        [Svx] Fq, Location

    The final LOCATION field must not exceed 17 characters.
    """

    if not enabled:
        model["echolink"] = {
            "enabled": False,
            "callsign": None,
            "password": None,
            "sysopname": None,           
            "location": None,
        }
        return model

    callsign = callsign.strip().upper()
    password = password.strip()
    sysopname = sysopname.strip()
    location_text = location.strip()

    location = f"[Svx] {location_text}"

    model["echolink"] = {
        "enabled": True,
        "callsign": callsign,
        "password": password,
        "sysopname": sysopname,
        "location": location,
    }

    return model

def enable_module(model, module_name):
    """
    Enable a SvxLink module by name.
    """

    modules = model["modules"]["enabled"]

    if module_name not in modules:
        modules.append(module_name)

    return model


def disable_module(model, module_name):
    """
    Disable a SvxLink module by name.
    """

    modules = model["modules"]["enabled"]

    if module_name in modules:
        modules.remove(module_name)

    return model