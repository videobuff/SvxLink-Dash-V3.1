#!/usr/bin/env python3

"""
Primary SvxLink configuration renderer for SvxLink-Dash-V3.1.
"""

from renderers.template_engine import render_config_template
import platform

# =========================================================
# System information
# =========================================================
import platform


def get_library_path():
    machine = platform.machine()

    if machine in ("armv7l", "armhf"):
        return "/usr/lib/arm-linux-gnueabihf/svxlink"

    if machine in ("aarch64", "arm64"):
        return "/usr/lib/aarch64-linux-gnu/svxlink"

    if machine in ("x86_64", "amd64"):
        return "/usr/lib/x86_64-linux-gnu/svxlink"

    return "/usr/lib/svxlink"

# =========================================================
# Module rendering
# =========================================================

def build_modules(model):
    """
    Render MODULES= line content.
    """

    enabled = model.get("modules", {}).get("enabled", [])

    return ",".join(enabled)

def build_modules_line(model):
    """
    Render the complete MODULES line for a single-node logic section.
    """

    enabled = model.get("modules", {}).get("enabled", [])

    if not enabled:
        return "#MODULES="

    return "MODULES=" + ",".join(enabled)


def build_modules_line_for_node(node):
    """
    Render the complete MODULES line for one multi-port node.
    """

    modules = node.get("modules", {})

    enabled = []

    if modules.get("echolink"):
        enabled.append("ModuleEchoLink")

    if modules.get("metar"):
        enabled.append("ModuleMetarInfo")

    if not enabled:
        return "#MODULES="

    return "MODULES=" + ",".join(enabled)
# =========================================================
# Language rendering
# =========================================================
def get_default_language(model):
    """
    Return selected default language.

    Set by /environment page.
    British Isles use en_GB.
    Australia/NZ use en_AU.
    North America uses en_US.
    """

    return (
        model.get("language", {}).get("default")
        or model.get("node", {}).get("language")
        or "en_GB"
    )
# =========================================================
# Module-specific renderers
# =========================================================

def render_echolink_module(model):
    """
    Render ModuleEchoLink section if enabled.
    """

    echolink = model.get("echolink", {})

    if not echolink.get("enabled"):
        return ""

    return render_config_template(
        "module_echolink.template",
        {
            "ECHOLINK_CALLSIGN": echolink.get("callsign", ""),
            "ECHOLINK_PASSWORD": echolink.get("password", ""),
            "ECHOLINK_SYSOPNAME": echolink.get("sysopname", ""),
            "ECHOLINK_LOCATION": echolink.get("location", ""),
            "DEFAULT_LANG": get_default_language(model),
        }
    )

# =========================================================
# METAR rendering
# =========================================================
def render_metar_module(model):
    """
    Render ModuleMetarInfo section if enabled.

    STARTDEFAULT must always contain a valid ICAO.
    AIRPORTS includes STARTDEFAULT first, followed by up to six extras.
    """

    metar = model.get("metar", {})

    if not metar.get("enabled"):
        return ""

    startdefault = metar.get("startdefault", "").strip().upper()
    extras = metar.get("airports", [])

    airports = []

    if startdefault:
        airports.append(startdefault)

    for airport in extras:
        airport = airport.strip().upper()
        if airport and airport not in airports:
            airports.append(airport)

    return render_config_template(
        "module_metar.template",
        {
            "METAR_STARTDEFAULT": startdefault,
            "METAR_AIRPORTS": ",".join(airports),
        }
    )
# =========================================================
# Ident rendering
# =========================================================

def ident_enabled(mode, ident_type):
    """
    Determine voice/cw enable flags.

    mode:
        none
        cw
        voice
        both

    ident_type:
        voice
        cw
    """

    if mode == "both":
        return 1

    if mode == ident_type:
        return 1

    return 0


# =========================================================
# Online control block
# =========================================================

def render_online_control(model):
    """
    Render ONLINE control block if enabled.
    """

    online = model.get("online_control", {})

    if not online.get("enabled"):
        return ""

    cmd = online.get("command")

    return (
        f"ONLINE_CMD={cmd}\n"
        "ONLINE=1"
    )


# =========================================================
# CTCSS helpers
# =========================================================

def render_report_ctcss(model):
    """
    Render REPORT_CTCSS line if required.
    """

    squelch = model.get("squelch", {})

    if squelch.get("method") != ("ctcss"):
        return ""

    freq = squelch.get("ctcss_freq")

    if not freq:
        return ""

    return f"REPORT_CTCSS={freq}"


def render_tx_ctcss_logic(model):
    """
    Render TX_CTCSS logic line if TX CTCSS enabled.
    """

    squelch = model.get("squelch", {})

    if not squelch.get("ctcss_tx"):
        return ""

    mode = model.get("tx_ctcss_mode", "ALWAYS")

    return f"TX_CTCSS={mode}"

def render_open_on_ctcss_line(model):
    """
    Render OPEN_ON_CTCSS for repeater logic only when CTCSS is used.

    For non-CTCSS squelch methods, leave it commented.
    """

    node_type = model.get("node", {}).get("type")
    squelch = model.get("squelch", {})

    if node_type != "repeater":
        return "#OPEN_ON_CTCSS=1000"

    if squelch.get("method") != ("ctcss"):
        return "#OPEN_ON_CTCSS=1000"

    if not squelch.get("ctcss_freq"):
        return "#OPEN_ON_CTCSS=1000"

    return "OPEN_ON_CTCSS=600"

# =========================================================
# RX rendering
# =========================================================

def render_rx_sql_block(model):
    """
    Render SQL_DET line.
    """

    interface = model.get("interface", {})
    squelch = model.get("squelch", {})

    interface_mode = interface.get("mode")
    squelch_method = squelch.get("method")

    if squelch_method == "vox":
        return "SQL_DET=VOX\nVOX_FILTER_DEPTH=20\nVOX_THRESH=1000"

    if interface_mode == "hidraw":
        return "SQL_DET=HIDRAW"

    if interface_mode == "hybrid":
        if squelch_method == "ctcss":
            return "SQL_DET=CTCSS"

        return "SQL_DET=GPIOD"
#    if squelch_method == "gpiod_ctcss":
#        return "\n".join([
#            "SQL_DET=COMBINE",
#            "SQL_COMBINE=(Rx1:CTCSS)&(Rx1:GPIOD)",
#        ])
    if squelch_method == "ctcss":
        return "SQL_DET=CTCSS"
    if squelch_method == "serial":
        return "SQL_DET=SERIAL"
#    if squelch_method == "serial_ctcss":
#        return "\n".join([
#        "SQL_DET=COMBINE",
#        "SQL_COMBINE=(Rx1:CTCSS)&(Rx1:SERIAL)",
#        ])
    return "SQL_DET=GPIOD"


def render_rx_ctcss_block(model):
    """
    Render CTCSS RX block.
    """

    squelch = model.get("squelch", {})

    if squelch.get("method") != ("ctcss"):
        return ""

    freq = squelch.get("ctcss_freq")

    if not freq:
        return ""

    return "\n".join([
        "CTCSS_MODE=4",
        f"CTCSS_FQ={freq}",
        "CTCSS_SNR_OFFSET=0",
        "#CTCSS_SNR_OFFSETS=88.5:-1.0,136.5:-0.5",
        "CTCSS_OPEN_THRESH=15",
        "CTCSS_CLOSE_THRESH=9",
        "CTCSS_BPF_LOW=60",
        "CTCSS_BPF_HIGH=270",
        "CTCSS_EMIT_TONE_DETECTED=0",
    ])


def render_rx_gpiod_block(model):
    """
    Render RX GPIOD block.

    Active-high COS uses PULLDOWN.
    Active-low COS uses PULLUP.

    Do not render RX GPIOD when CTCSS is selected.
    PTT GPIOD is rendered separately.
    """

    interface = model.get("interface", {})
    squelch_method = model.get("squelch", {}).get("method")

    if squelch_method == "ctcss":
        return ""

    if interface.get("mode") == "hidraw":
        return ""

    if interface.get("sql_source") != "gpiod":
        return ""

    gpio = model.get("gpio", {}).get("sql", {})

    chip = gpio.get("chip", "gpiochip0")
    line = str(gpio.get("line", 203))
    inverted = bool(gpio.get("invert", False))

    if inverted:
        line = f"!{line}"
        bias = "PULLUP"
    else:
        bias = "PULLDOWN"

    return "\n".join([
        f"SQL_GPIOD_CHIP={chip}",
        f"SQL_GPIOD_LINE={line}",
        f"SQL_GPIOD_BIAS={bias}",
    ])

def render_rx_hidraw_block(model):
    """
    Render RX HIDRAW block.
    """

    interface = model.get("interface", {})

    if interface.get("sql_source") != "hidraw":
        return ""

    hid = model.get("hidraw", {})

    device = hid.get("device", "/dev/hidraw0")
    pin = hid.get("sql_pin", "VOL_DN")
    if hid.get("sql_invert"):
        pin = f"!{pin}"

    return "\n".join([
        f"HID_DEVICE={device}",
        f"HID_SQL_PIN={pin}",
    ])
def render_rx_combine_sections(model):
    """
    Render COMBINE detector subsections.
    """

    squelch = model.get("squelch", {})

    if squelch.get("method") == "gpiod_ctcss":
        return "\n\n".join([
            render_rx_ctcss_combine_block(model),
            render_rx_gpiod_combine_block(model),
        ])

    if squelch.get("method") == "serial_ctcss":
        return "\n\n".join([
            render_rx_ctcss_combine_block(model),
            render_rx_serial_combine_block(model),
        ])
    return ""


def render_rx_ctcss_combine_block(model):
    squelch = model.get("squelch", {})
    freq = squelch.get("ctcss_freq")

    if not freq:
        return ""

    return "\n".join([
        "[Rx1:CTCSS]",
        "SQL_DET=CTCSS",
        "CTCSS_MODE=4",
        f"CTCSS_FQ={freq}",
        "#CTCSS_SNR_OFFSET=0",
        "#CTCSS_SNR_OFFSETS=88.5:-1.0,136.5:-0.5",
        "#CTCSS_OPEN_THRESH=15",
        "#CTCSS_CLOSE_THRESH=9",
        "#CTCSS_BPF_LOW=60",
        "#CTCSS_BPF_HIGH=270",
        "#CTCSS_EMIT_TONE_DETECTED=0",
    ])
def render_rx_gpiod_combine_block(model):
    gpio = model.get("gpio", {}).get("sql", {})

    chip = gpio.get("chip", "gpiochip0")
    line = gpio.get("line", 203)

    return "\n".join([
        "[Rx1:GPIOD]",
        "SQL_DET=GPIOD",
        f"SQL_GPIOD_CHIP={chip}",
        f"SQL_GPIOD_LINE={line}",
    ])
def render_rx_serial_block(model):
    """
    Render RX SERIAL squelch block.
    """

    if model.get("squelch", {}).get("method") != "serial":
        return ""

    serial = model.get("serial", {})

    return "\n".join([
        "SERIAL_PORT=" + serial.get("sql_port", "/dev/ttyS0"),
        "SERIAL_PIN=" + serial.get("sql_pin", "CTS"),
        "SERIAL_SET_PINS=" + serial.get("sql_set_pins", "DTR!RTS"),
    ])
def render_rx_serial_combine_block(model):
    """
    Render RX SERIAL subsection for COMBINE squelch.
    """

    serial = model.get("serial", {})

    return "\n".join([
        "[Rx1:SERIAL]",
        "SQL_DET=SERIAL",
        "SERIAL_PORT=" + serial.get("sql_port", "/dev/ttyS0"),
        "SERIAL_PIN=" + serial.get("sql_pin", "CTS"),
        "SERIAL_SET_PINS=" + serial.get("sql_set_pins", "DTR!RTS"),
    ])
# =========================================================
# TX rendering
# =========================================================

def render_tx_ptt_block(model):
    """
    SvxLink PTT is deliberately routed through the PI3TWE USB-relay bridge.
    The bridge owns BASE (QAAMZ_2), audio PTT (QAAMZ_3) and TX (QAAMZ_4).
    Never let generated dashboard settings key a GPIO or radio port directly.
    """
    return "\n".join([
        "PTT_TYPE=PTY",
        "PTT_PTY=/run/pi3twe-svxlink/ptt",
    ])


def render_tx_ctcss_block(model):
    """
    Render TX-side CTCSS block.
    """

    squelch = model.get("squelch", {})

    if not squelch.get("ctcss_tx"):
        return ""

    freq = squelch.get("ctcss_freq")

    if not freq:
        return ""

    return "\n".join([
        f"CTCSS_FQ={freq}",
        "CTCSS_LEVEL=-24",
    ])


# =========================================================
# Macros
# =========================================================

def render_macros(model):
    """
    Render reflector macro section.
    """

    reflector = model.get("reflector", {})

    if not reflector.get("enabled"):
        return "[Macros]"

    host = reflector.get("host", "")

    if "uk.wide" in host or "yorkshire" in host:

        macro_lines = "\n".join([
            "1=::91235#",
            "2=::912350#",
            "6=::9123561#",
            "9=::910#",
        ])

    elif "australia" in host:

        macro_lines = "\n".join([
            "1=::9505#",
            "9=::910#",
        ])

    elif "north.america" in host:

        macro_lines = "\n".join([
            "1=::93100#",
            "9=::910#",
        ])

    else:
        macro_lines = ""

    return render_config_template(
        "macros.template",
        {
            "MACRO_LINES": macro_lines,
        }
    )


# =========================================================
# Logic rendering
# =========================================================

def render_active_logic(model):
    """
    Render SimplexLogic or RepeaterLogic.
    """

    node_type = model.get("node", {}).get("type")
    logic_name = (
    "RepeaterLogic"
    if node_type == "repeater"
    else "SimplexLogic"
    )
    short_ident = model.get("ident", {}).get("short", {})
    long_ident = model.get("ident", {}).get("long", {})

    values = {
        "LOGIC_NAME": logic_name,
        "RX_NAME": "Rx1",
        "TX_NAME": "Tx1",
        "MODULES_LINE": build_modules_line(model),
        "CALLSIGN": model["node"]["callsign"],

        "SHORT_IDENT_INTERVAL": short_ident.get("interval", 15),
        "SHORT_VOICE_ID_ENABLE": ident_enabled(
            short_ident.get("mode"),
            "voice"
        ),
        "SHORT_CW_ID_ENABLE": ident_enabled(
            short_ident.get("mode"),
            "cw"
        ),
        "SHORT_ANNOUNCE_ENABLE": 1 if short_ident.get("announce_enable", False) else 0,
        "SHORT_ANNOUNCE_FILE": short_ident.get("announce_file", ""),

        "LONG_IDENT_INTERVAL": long_ident.get("interval", 60),
        "LONG_VOICE_ID_ENABLE": ident_enabled(
            long_ident.get("mode"),
            "voice"
        ),
        "LONG_CW_ID_ENABLE": ident_enabled(
            long_ident.get("mode"),
            "cw"
        ),
        "LONG_ANNOUNCE_ENABLE": 1 if long_ident.get("announce_enable", False) else 0,
        "LONG_ANNOUNCE_FILE": long_ident.get("announce_file", ""),
        "TIME_FORMAT": model.get("time_format", "24"),

        "CW_AMP": model.get("cw", {}).get("amp", -10),
        "CW_PITCH": model.get("cw", {}).get("pitch", 650),
        "CW_CPM": model.get("cw", {}).get("cpm", 95),

        "DEFAULT_LANG": get_default_language(model),

        "RGR_SOUND_ALWAYS": model.get("courtesy", {}).get("mode") != "none" and 1 or 0,

        "REPORT_CTCSS_LINE": render_report_ctcss(model),
        "TX_CTCSS_LINE": render_tx_ctcss_logic(model),

        "FX_GAIN_NORMAL": model.get("fx_gain_normal", 0),
        "FX_GAIN_LOW": model.get("fx_gain_low", -12),

        "ONLINE_CONTROL_BLOCK": render_online_control(model),
        "DTMF_CTRL_PTY": get_dtmf_ctrl_pty(model),
        "IDLE_TIMEOUT": model.get("idle_timeout", 10),
        "OPEN_ON_CTCSS_LINE": render_open_on_ctcss_line(model),
        "REPEATER_SQL_TIMEOUT": model.get("sql_timeout", 180),
    }

    if node_type == "repeater":
        return render_config_template(
            "repeater_logic.template",
            values
        )

    return render_config_template(
        "simplex_logic.template",
        values
    )
# =========================================================
# ICS port logic rendering
# =========================================================
def render_port_logic(model, port_id, node):
    """
    Render one SimplexLogic or RepeaterLogic section for an ICS port.
    """

    role = node.get("role", "simplex")
    logic_name = f"Port{port_id}Logic"

    ident = node.get("ident", {})
    short_ident = ident.get("short", {})
    long_ident = ident.get("long", {})

    cw = node.get("cw", {})
    courtesy = node.get("courtesy", {})
    repeater = node.get("repeater", {})

    values = {
        "LOGIC_NAME": logic_name,
        "RX_NAME": f"Rx{port_id}",
        "TX_NAME": f"Tx{port_id}",

        "MODULES_LINE": build_modules_line_for_node(node),
        "CALLSIGN": node.get("callsign", model.get("node", {}).get("callsign", "")),

        "SHORT_IDENT_INTERVAL": short_ident.get("interval", 15),
        "SHORT_VOICE_ID_ENABLE": 1 if short_ident.get("voice_enable", False) else 0,
        "SHORT_CW_ID_ENABLE": 1 if short_ident.get("cw_enable", True) else 0,
        "SHORT_ANNOUNCE_ENABLE": 1 if short_ident.get("announce_enable", False) else 0,
        "SHORT_ANNOUNCE_FILE": short_ident.get("announce_file", ""),

        "LONG_IDENT_INTERVAL": long_ident.get("interval", 60),
        "LONG_VOICE_ID_ENABLE": 1 if long_ident.get("voice_enable", True) else 0,
        "LONG_CW_ID_ENABLE": 1 if long_ident.get("cw_enable", False) else 0,
        "LONG_ANNOUNCE_ENABLE": 1 if long_ident.get("announce_enable", False) else 0,
        "LONG_ANNOUNCE_FILE": long_ident.get("announce_file", ""),

        "TIME_FORMAT": model.get("time_format", "24"),

        "CW_AMP": cw.get("amp", -10),
        "CW_PITCH": cw.get("pitch", 650),
        "CW_CPM": cw.get("cpm", 95),

        "DEFAULT_LANG": get_default_language(model),

        "RGR_SOUND_ALWAYS": 1 if courtesy.get("mode", "none") != "none" else 0,

        "REPORT_CTCSS_LINE": render_port_report_ctcss(node),
        "TX_CTCSS_LINE": render_port_tx_ctcss_logic(node),

        "FX_GAIN_NORMAL": model.get("fx_gain_normal", 0),
        "FX_GAIN_LOW": model.get("fx_gain_low", -12),

        "ONLINE_CONTROL_BLOCK": "",
        "DTMF_CTRL_PTY": f"/dev/shm/port{port_id}_dtmf_ctrl",

        "IDLE_TIMEOUT": repeater.get("idle_timeout", 10),
        "OPEN_ON_CTCSS_LINE": "",
        "REPEATER_SQL_TIMEOUT": repeater.get("sql_timeout", 180),
    }

    if role == "repeater":
        return render_config_template(
            "repeater_logic.template",
            values
        )

    return render_config_template(
        "simplex_logic.template",
        values
    )
def build_modules_for_node(node):
    """
    Build the MODULES line for one multi-port node.
    """

    modules = node.get("modules", {})

    enabled = []

    if modules.get("echolink"):
        enabled.append("ModuleEchoLink")

    if modules.get("metar"):
        enabled.append("ModuleMetarInfo")

    return ",".join(enabled)


def render_port_report_ctcss(node):
    """
    Render REPORT_CTCSS for one port.
    """

    squelch = node.get("squelch", {})

    if squelch.get("ctcss_mode") in ("rx", "rx_tx"):
        return "REPORT_CTCSS=1"

    return "#REPORT_CTCSS=1"

def render_port_tx_ctcss_logic(node):
    """
    Render TX_CTCSS for one multi-port node.
    """

    squelch = node.get("squelch", {})

    if squelch.get("ctcss_mode") == "rx_tx":
        return "TX_CTCSS=always"

    return "#TX_CTCSS=always"

def resolve_gpiod_line(model, node, label):
    """
    Resolve a stable GPIO line name to chip/line details.

    Prefer per-node data created during ICS GPIOD discovery.
    Fall back to the top-level discovered line map.
    Finally fall back to the stable line name itself.
    """

    gpio = node.get("gpio", {})

    if label.startswith("RX_"):
        chip = gpio.get("cos_chip", "")
        line = (
            gpio.get("cos_line")
            or gpio.get("cos")
            or label
        )
        offset = gpio.get("cos_offset")

    elif label.startswith("TX_"):
        chip = gpio.get("ptt_chip", "")
        line = (
            gpio.get("ptt_line")
            or gpio.get("ptt")
            or label
        )
        offset = gpio.get("ptt_offset")

    else:
        chip = ""
        line = label
        offset = None

    if chip:
        return {
            "chip": chip,
            "line": line,
            "offset": offset,
        }

    resolved = (
        model.get("gpiod", {})
        .get("resolved_lines", {})
        .get(label, {})
    )

    return {
        "chip": resolved.get("chip", ""),
        "line": resolved.get("line", line),
        "offset": resolved.get("offset", offset),
    }

def render_multiport_logic_sections(model):
    """
    Render all SimplexLogic/RepeaterLogic sections for enabled ICS ports.
    """

    nodes = model.get("nodes", {})
    enabled_ports = model.get("ports", {}).get("enabled", [])

    logic_names = []
    logic_sections = []

    for port in enabled_ports:
        port_id = str(port)
        node = nodes.get(port_id, {})

        if not node:
            continue

        logic_name = f"Port{port_id}Logic"

        logic_names.append(logic_name)
        logic_sections.append(
            render_port_logic(model, port_id, node)
        )

    return {
        "logics": ",".join(logic_names),
        "sections": "\n\n".join(logic_sections),
    }
def render_port_rx_section(model, port_id, node):
    """
    Render one Rx section for a multi-port node.
    """

    audio = node.get("audio", {})
    squelch = node.get("squelch", {})

    rx_name = f"Rx{port_id}"
    rx_label = f"RX_{port_id}"

    audio_dev = audio.get("rx_audio", f"alsa:rx{port_id}")

    method = squelch.get("method", "gpiod")
    ctcss_mode = squelch.get("ctcss_mode", "radio")
    ctcss_freq = squelch.get("ctcss_freq")

    lines = [
        f"[{rx_name}]",
        "TYPE=Local",
        f"AUDIO_DEV={audio_dev}",
        "AUDIO_CHANNEL=0",
    ]

    if method == "hidraw":
        hidraw = node.get("hidraw", {})

        try:
            hidraw_index = int(port_id) - 1
        except ValueError:
            hidraw_index = 0

        device = hidraw.get("device", f"/dev/hidraw{hidraw_index}")
        pin = hidraw.get("sql_pin", "VOL_DN")

        if hidraw.get("sql_invert"):
            pin = f"!{pin}"

        lines.extend([
            "SQL_DET=HIDRAW",
            f"HID_DEVICE={device}",
            f"HID_SQL_PIN={pin}",
        ])
    elif method == "serial":
        serial = node.get("serial", {})

        lines.extend([
            "SQL_DET=SERIAL",
            "SERIAL_PORT=" + serial.get("sql_port", "/dev/ttyS0"),
            "SERIAL_PIN=" + serial.get("sql_pin", "CTS"),
            "SERIAL_SET_PINS=" + serial.get("sql_set_pins", "DTR!RTS"),
        ])

    elif method == "ctcss":
        lines.append("SQL_DET=CTCSS")

    else:
        resolved = resolve_gpiod_line(
            model,
            node,
            rx_label,
        )

        sql_line = resolved.get("line", rx_label)

        if node.get("gpio", {}).get("cos_invert"):
            # External COS is active-low.
            sql_line = f"!{sql_line}"
            sql_bias = "PULLUP"
        else:
            # External COS is active-high.
            sql_bias = "PULLDOWN"

        lines.extend([
            "SQL_DET=GPIOD",
            f"SQL_GPIOD_CHIP={resolved.get('chip', '')}",
            f"SQL_GPIOD_LINE={sql_line}",
            f"SQL_GPIOD_BIAS={sql_bias}",
        ])

    lines.extend([
        f"SQL_HANGTIME={model.get('sql_hangtime', 20)}",
        f"SQL_TAIL_ELIM={model.get('sql_tail_elim', 270)}",
    ])

    if method == "ctcss" and ctcss_mode in ("rx", "rx_tx") and ctcss_freq:
        lines.extend([
            "CTCSS_MODE=4",
            f"CTCSS_FQ={ctcss_freq}",
            "CTCSS_SNR_OFFSET=0",
            "CTCSS_OPEN_THRESH=15",
            "CTCSS_CLOSE_THRESH=9",
            "CTCSS_BPF_LOW=60",
            "CTCSS_BPF_HIGH=270",
            "CTCSS_EMIT_TONE_DETECTED=0",
        ])

    return "\n".join(lines)

def render_port_tx_section(model, port_id, node):
    """
    Render one Tx section for a multi-port node.
    """

    audio = node.get("audio", {})
    squelch = node.get("squelch", {})

    tx_name = f"Tx{port_id}"
    tx_label = f"TX_{port_id}"

    audio_dev = audio.get("tx_audio", f"alsa:tx{port_id}")

    method = squelch.get("method", "gpiod")
    ctcss_mode = squelch.get("ctcss_mode", "radio")
    ctcss_freq = squelch.get("ctcss_freq")

    lines = [
        f"[{tx_name}]",
        "TYPE=Local",
        f"AUDIO_DEV={audio_dev}",
        "AUDIO_CHANNEL=0",
    ]

    if method == "hidraw":
        hidraw = node.get("hidraw", {})

        try:
            hidraw_index = int(port_id) - 1
        except ValueError:
            hidraw_index = 0

        device = hidraw.get("device", f"/dev/hidraw{hidraw_index}")
        pin = hidraw.get("ptt_pin", "GPIO3")

        if hidraw.get("ptt_invert"):
            pin = f"!{pin}"

        lines.extend([
            "PTT_TYPE=Hidraw",
            f"HID_DEVICE={device}",
            f"HID_PTT_PIN={pin}",
        ])

    else:
        resolved = resolve_gpiod_line(
            model,
            node,
            tx_label,
        )

        ptt_line = resolved.get("line", tx_label)

        if not node.get("gpio", {}).get("ptt_invert"):
            ptt_line = f"!{ptt_line}"

        lines.extend([
            "PTT_TYPE=GPIOD",
            f"PTT_GPIOD_CHIP={resolved.get('chip', '')}",
            f"PTT_GPIOD_LINE={ptt_line}",
        ])

    if ctcss_mode == "rx_tx" and ctcss_freq:
        lines.extend([
            f"CTCSS_FQ={ctcss_freq}",
            "CTCSS_LEVEL=9",
        ])

    return "\n".join(lines)

def render_multiport_rx_tx_sections(model):
    """
    Render all Rx and Tx sections for enabled ICS ports.
    """

    nodes = model.get("nodes", {})
    enabled_ports = model.get("ports", {}).get("enabled", [])

    rx_sections = []
    tx_sections = []

    for port in enabled_ports:
        port_id = str(port)
        node = nodes.get(port_id, {})

        if not node:
            continue

        rx_sections.append(
            render_port_rx_section(model, port_id, node)
        )

        tx_sections.append(
            render_port_tx_section(model, port_id, node)
        )

    return {
        "rx_sections": "\n\n".join(rx_sections),
        "tx_sections": "\n\n".join(tx_sections),
    }

# =========================================================
# DTMF Sender Renderer
# =========================================================
def get_dtmf_ctrl_pty(model):
    node_type = model.get("node", {}).get("type")

    if node_type == "repeater":
        return "/dev/shm/repeater_dtmf_ctrl"

    return "/dev/shm/simplex_dtmf_ctrl"
# =========================================================
# Reflector rendering
# =========================================================
def get_primary_callsign(model):
    """
    Return the best callsign for shared/global config sections.
    For multi-port builds, use the first enabled port callsign.
    """

    enabled_ports = model.get("ports", {}).get("enabled", [])
    nodes = model.get("nodes", {})

    for port in enabled_ports:
        node = nodes.get(str(port), {})
        callsign = node.get("callsign")
        if callsign:
            return callsign

    return (
        model.get("node", {}).get("callsign")
        or model.get("ident", {}).get("callsign")
        or "NOCALL"
    )
def render_reflector_logic(model):
    """
    Render ReflectorLogic section if enabled.
    """

    reflector = model.get("reflector", {})

    if not reflector.get("enabled"):
        return ""

    host = reflector.get("host", "")

    monitor_tgs = reflector.get(
        "monitor_tgs",
        []
)

    if isinstance(monitor_tgs, list):
        monitor_tgs = ",".join(
            str(x) for x in monitor_tgs
    )

    if not monitor_tgs:
        monitor_tgs = "0"

    return render_config_template(
        "reflector_logic.template",
        {
            "REFLECTOR_HOST": reflector["host"],
            "REFLECTOR_PORT": reflector["port"],
            "CALLSIGN": get_primary_callsign(model),
            "REFLECTOR_AUTH_KEY": reflector["auth_key"],
            "MONITOR_TGS": monitor_tgs,
            "TG_SELECT_TIMEOUT": model.get("tg_timeout", 60),
            "DEFAULT_LANG": get_default_language(model),
        }
    )


def render_link_to_reflector(model):
    """
    Render LinkToReflector section if reflector is enabled.
    """

    if not model.get("reflector", {}).get("enabled"):
        return ""

    node_type = model.get("node", {}).get("type")

    active_logic_name = (
        "RepeaterLogic"
        if node_type == "repeater"
        else "SimplexLogic"
    )

    values = {
        "CONNECT_LOGICS": f"{active_logic_name}:9,ReflectorLogic",
        "ACTIVATE_ON_ACTIVITY": active_logic_name,
    }

    return render_config_template(
        "link_to_reflector.template",
        values
    )
def render_multiport_link_to_reflector(model, active_logics):
    """
    Render LinkToReflector section for ICS multi-port builds.
    """

    if not model.get("reflector", {}).get("enabled"):
        return ""

    connect_logics = [
        f"{logic}:9"
        for logic in active_logics
        if logic
    ]

    connect_logics.append("ReflectorLogic")

    activate_on_activity = (
        active_logics[0]
        if active_logics
        else "SimplexLogic"
    )

    values = {
        "CONNECT_LOGICS": ",".join(connect_logics),
        "ACTIVATE_ON_ACTIVITY": activate_on_activity,
    }

    return render_config_template(
        "link_to_reflector.template",
        values
    )
def render_multiport_svxlink_config(model):
    """
    Render final svxlink.conf text for ICS multi-port builds.
    """

    logic_result = render_multiport_logic_sections(model)
    audio_result = render_multiport_rx_tx_sections(model)

    reflector_enabled = bool(
        model.get("reflector", {}).get("enabled")
    )

    active_logics = [
        logic.strip()
        for logic in logic_result["logics"].split(",")
        if logic.strip()
    ]

    global_logics = list(active_logics)

    if reflector_enabled and "ReflectorLogic" not in global_logics:
        global_logics.append("ReflectorLogic")

    links_line = (
        "LINKS=LinkToReflector"
        if reflector_enabled
        else "#LINKS=LinkToReflector"
    )

    values = {
        "LOGIC_CORE_PATH": get_library_path(),
        "LOGICS": ",".join(global_logics),
        "LINKS_LINE": links_line,

        "ACTIVE_LOGIC_SECTION": logic_result["sections"],

        "REFLECTOR_LOGIC_SECTION": (
            render_reflector_logic(model)
            if reflector_enabled
            else ""
        ),

        "LINK_TO_REFLECTOR_SECTION": (
            render_multiport_link_to_reflector(model, active_logics)
            if reflector_enabled
            else ""
        ),

        "RX_SECTIONS": audio_result["rx_sections"],
        "TX_SECTIONS": audio_result["tx_sections"],

        "MACROS_SECTION": render_macros(model),
    }

    return render_config_template(
        "svxlink_multiport.conf.template",
        values
    )

# =========================================================
# Final configuration renderer
# =========================================================

def render_svxlink_config(model):
    """
    Render final svxlink.conf text.
    """
    hardware = model.get("hardware", {})

    profile_id = (
        model.get("hardware_profile_id")
        or hardware.get("profile_id")
        or hardware.get("id")
        or hardware.get("profile")
        or ""
    )

    if hardware.get("family") == "ics" or str(profile_id).startswith("ics_"):
        return render_multiport_svxlink_config(model)

    node_type = model.get("node", {}).get("type")

    logic_name = (
        "RepeaterLogic"
        if node_type == "repeater"
        else "SimplexLogic"
    )
    logics = logic_name

    if model.get("reflector", {}).get("enabled"):
        logics = f"{logic_name},ReflectorLogic"
        
    reflector_enabled = model.get("reflector", {}).get("enabled")

    links_line = (
        "LINKS=LinkToReflector"
        if reflector_enabled
        else "#LINKS=LinkToReflector"
    )

    values = {
        "LOGIC_CORE_PATH": get_library_path(),
        "LOGICS": logics,
        "LINKS_LINE": links_line,

        "ACTIVE_LOGIC_SECTION": render_active_logic(model),

        "REFLECTOR_LOGIC_SECTION": render_reflector_logic(model),

        "LINK_TO_REFLECTOR_SECTION": render_link_to_reflector(model),
        "AUDIO_DEV": (
            model.get("audio", {}).get("audio_dev")
            or "alsa:plughw:0"
        ),
        "RX_SQL_BLOCK": render_rx_sql_block(model),
        "RX_CTCSS_BLOCK": render_rx_ctcss_block(model),
        "RX_GPIOD_BLOCK": render_rx_gpiod_block(model),
        "RX_HIDRAW_BLOCK": render_rx_hidraw_block(model),
        "RX_SERIAL_BLOCK": render_rx_serial_block(model),
        "RX_COMBINE_SECTIONS": render_rx_combine_sections(model),

        "TX_PTT_BLOCK": render_tx_ptt_block(model),
        "TX_CTCSS_BLOCK": render_tx_ctcss_block(model),
        "SQL_HANGTIME": model.get("sql_hangtime", 20),
        "SQL_TAIL_ELIM": model.get("sql_tail_elim", 270),

        "MACROS_SECTION": render_macros(model),
    }

    return render_config_template(
        "svxlink.conf.template",
        values
    )
