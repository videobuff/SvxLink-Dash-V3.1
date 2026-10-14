#!/usr/bin/env python3

"""
SvxLink service and file deployment helpers for SvxLink-Dash-V3.1.

This module owns:
- svxlink service status
- svxlink service restart
- volatile config backups
- safe file writes

It does NOT generate svxlink.conf.
Rendering belongs in /renderers.
"""
import shutil
import subprocess
import os
import pwd
import grp
import re
from pathlib import Path
from datetime import datetime



# =========================================================
# Paths
# =========================================================

APP_ROOT = Path("/opt/dashboard")

SVXLINK_CONF = Path("/etc/pi3twe/svxlink/svxlink.conf")
MODULE_DIR = Path("/etc/pi3twe/svxlink/svxlink.d")

LOGIC_DIR_SRC = Path("/usr/share/svxlink/events.d")
LOGIC_DIR_DST = Path("/usr/share/svxlink/events.d/local")

BACKUP_DIR = APP_ROOT / "backups"



# =========================================================
# Service control
# =========================================================

def svxlink_status():
    """
    Return systemd active state for svxlink.

    Typical results:
    - active
    - inactive
    - failed
    - unknown
    """

    result = subprocess.run(
        ["/usr/bin/systemctl", "is-active", "pi3twe-svxlink.service"],
        text=True,
        capture_output=True,
    )

    status = result.stdout.strip()

    if not status:
        return "unknown"

    return status


def restart_svxlink():
    """
    Restart SvxLink using sudoers.d permission.

    The dashboard is expected to run as user svxlink.
    """

    subprocess.run(
        ["sudo", "/usr/local/sbin/pi3twe-svxlink-control", "restart"],
        check=True,
    )


# =========================================================
# Backup helpers
# =========================================================

def timestamp():
    """
    Return filesystem-safe timestamp.
    """

    return datetime.now().strftime("%Y%m%d-%H%M%S")


def ensure_backup_dir():
    """
    Ensure backup directory exists.
    """

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def backup_file(path):
    """
    Back up a single file if it exists.

    Returns:
        Path | None
    """

    path = Path(path)

    if not path.exists() or not path.is_file():
        return None

    ensure_backup_dir()

    backup_name = f"{path.name}.{timestamp()}.bak"
    backup_path = BACKUP_DIR / backup_name

    shutil.copy2(path, backup_path)

    return backup_path


def backup_active_config():
    """
    Back up volatile active SvxLink config files.

    Backed up:
    - /etc/svxlink/svxlink.conf
    - /etc/svxlink/svxlink.d/*.conf

    Not backed up:
    - /usr/share/svxlink/events.d/local/*
      because this is V3-managed generated output.
    """

    backups = []

    svxlink_backup = backup_file(SVXLINK_CONF)
    if svxlink_backup:
        backups.append(svxlink_backup)

    if MODULE_DIR.exists():
        for conf_file in sorted(MODULE_DIR.glob("*.conf")):
            backup = backup_file(conf_file)
            if backup:
                backups.append(backup)

    return backups


# =========================================================
# Safe write helpers
# =========================================================
def ensure_logic_dir():
    LOGIC_DIR_DST.mkdir(parents=True, exist_ok=True)
    if not os.access(LOGIC_DIR_DST, os.W_OK):
        raise PermissionError(f"Dashboard cannot write {LOGIC_DIR_DST}")
def write_text_file(path, content):
    """
    Write text content to a file.

    Parent directory is created if required.
    """

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(content, encoding="utf-8")


def copy_file(src, dst):
    """
    Copy a file, preserving metadata where possible.

    Ensures:
    - destination directory exists
    - directory ownership = svxlink:svxlink
    - directory mode = 775
    - copied file ownership = svxlink:svxlink
    - copied file mode = 664
    """

    src = Path(src)
    dst = Path(dst)

    if not src.exists():
        raise FileNotFoundError(f"Source file does not exist: {src}")

    uid = pwd.getpwnam("svxlink").pw_uid
    gid = grp.getgrnam("svxlink").gr_gid

    if dst.parent == LOGIC_DIR_DST:
        ensure_logic_dir()
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)

    # enforce directory ownership/mode
    os.chown(dst.parent, uid, gid)
    os.chmod(dst.parent, 0o775)

    shutil.copy2(src, dst)

    # enforce file ownership/mode
    os.chown(dst, uid, gid)
    os.chmod(dst, 0o664)

    return dst

def deploy_logic_file(filename):
    """
    Copy a logic/event file from LOGIC_DIR_SRC to LOGIC_DIR_DST.

    This intentionally overwrites the destination every time.
    """

    src = LOGIC_DIR_SRC / filename
    dst = LOGIC_DIR_DST / filename

    return copy_file(src, dst)


def deploy_required_logic_files():
    """
    Deploy known local override logic files.

    These are managed outputs and are not backed up.
    """

    deployed = []

    for filename in (
        "Logic.tcl",
        "RepeaterLogicType.tcl",
        "CW.tcl",
    ):
        deployed.append(deploy_logic_file(filename))

    return deployed
def apply_courtesy_tone(model):
    """
    Modify local Logic.tcl according to selected courtesy tone.

    Uses:
    - model["courtesy"]["mode"]
    - model["courtesy"]["frequency"]
    - model["cw"]["amp"]
    - model["cw"]["pitch"]
    - model["cw"]["cpm"]

    The local Logic.tcl file is managed output, so no backup is made here.
    """

    logic_tcl = LOGIC_DIR_DST / "Logic.tcl"

    if not logic_tcl.exists():
        raise FileNotFoundError(f"Logic.tcl not found: {logic_tcl}")

    courtesy = model.get("courtesy", {})
    #cw = model.get("cw", {})

    mode = courtesy.get("mode", "none")
    tone_freq = courtesy.get("frequency", 800)

    # cw_amp = cw.get("amp", -10)
    # cw_pitch = cw.get("pitch", 650)
    # cw_cpm = cw.get("cpm", 95)

    content = logic_tcl.read_text(encoding="utf-8")

    # Disable the stock CW squelch tail marker if present.
    content = content.replace(
        "CW::play $sql_rx_id 200 1000 -10",
        "# CW::play $sql_rx_id 200 1000 -10"
    )

    # Replace the stock courtesy tone line.
    if mode == "none":
        replacement = "# playTone 440 500 100"

    elif mode == "beep":
        replacement = f"playTone {tone_freq} 800 60"

    elif mode == "morse_t":
        replacement = f'CW::play "T"'

    elif mode == "morse_k":
        replacement = f'CW::play "K"'

    else:
        replacement = "# playTone 440 500 100"

    content = content.replace(
        "playTone 440 500 100",
        replacement
    )

    logic_tcl.write_text(content, encoding="utf-8")

    return logic_tcl

def apply_repeater_event_customisations(model):
    """
    Modify local RepeaterLogicType.tcl according to repeater tone choices.
    """

    repeater = model.get("repeater", {})

    idle_tone = repeater.get("idle_tone", "chime")
    down_tone = repeater.get("down_tone", "biboop")

    logic_tcl = LOGIC_DIR_DST / "RepeaterLogicType.tcl"

    if not logic_tcl.exists():
        raise FileNotFoundError(
            f"RepeaterLogicType.tcl not found: {logic_tcl}"
        )

    content = logic_tcl.read_text(encoding="utf-8")

    idle_original = """    playTone 1100 [expr {round(pow($base, $i) * 150 / $max)}] 100;
    playTone 1200 [expr {round(pow($base, $i) * 150 / $max)}] 100;"""

    idle_chime = """    playTone 1190 [expr {round(pow($base, $i) * 150 / $max)}] 100;
    playTone 1200 [expr {round(pow($base, $i) * 150 / $max)}] 100;"""

    idle_commented = """    # playTone 1100 [expr {round(pow($base, $i) * 150 / $max)}] 100;
    # playTone 1200 [expr {round(pow($base, $i) * 150 / $max)}] 100;"""

    if idle_tone == "chime":
        content = content.replace(idle_original, idle_chime, 1)

    elif idle_tone == "pip":
        start = content.find("proc repeater_idle {} {")
        end = content.find("\n\n\n#\n# Executed if the repeater opens", start)

        if start == -1 or end == -1:
            raise RuntimeError("Could not locate repeater_idle procedure")

        proc = content[start:end]

        proc = proc.replace(
            "playTone 1100",
            "# playTone 1100",
            1,
        )

        proc = proc.replace(
            "playTone 1200",
            "# playTone 1200",
            1,
        )

        if 'CW::play "E";' not in proc:
            last_brace = proc.rfind("}")
            proc = (
                proc[:last_brace]
                + '  CW::play "E";\n'
                + proc[last_brace:]
            )

        content = content[:start] + proc + content[end:]

    elif idle_tone == "silence":
        content = content.replace(idle_original, idle_commented, 1)

    down_original = """    playTone 400 900 50
    playSilence 100
    playTone 360 900 50
    playSilence 500"""

    down_commented = """    # playTone 400 900 50
    # playSilence 100
    # playTone 360 900 50
    playSilence 500"""

    down_va = """    CW::play "-"
    playSilence 500"""

    if down_tone == "none":
        content = content.replace(down_original, down_commented, 1)

    elif down_tone == "va":
        content = content.replace(down_original, down_va, 1)

    logic_tcl.write_text(content, encoding="utf-8")
    os.chmod(logic_tcl, 0o664)

    return logic_tcl
def apply_va_barred_cw_symbol():
    """
    Add '-' as VA barred (...-.-) to local CW.tcl.
    """

    cw_tcl = LOGIC_DIR_DST / "CW.tcl"

    if not cw_tcl.exists():
        raise FileNotFoundError(
            f"CW.tcl not found: {cw_tcl}"
        )

    content = cw_tcl.read_text(encoding="utf-8")

    if '  "-" "...-.-"' not in content:
        content = content.replace(
            '  "=" "-...-"',
            '  "=" "-...-"\n  "-" "...-.-"',
            1,
        )

    cw_tcl.write_text(content, encoding="utf-8")
    os.chmod(cw_tcl, 0o664)

    return cw_tcl
