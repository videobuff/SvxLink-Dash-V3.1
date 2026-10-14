#!/usr/bin/env python3

import subprocess
from typing import Any, Dict, List
from pathlib import Path
import os
import shlex
import signal
import stat

DEVCAL_LOG = Path("/tmp/svxlink-devcal.log")
DEVCAL_PID = Path("/tmp/svxlink-devcal.pid")
DEVCAL_MODE = Path("/tmp/svxlink-devcal.mode")
DEVCAL_INPUT = Path("/tmp/svxlink-devcal.in")
DEVCAL_TX_STATE = Path("/tmp/svxlink-devcal.tx")


SVXLINK_SERVICE = "pi3twe-svxlink.service"

def prepare_devcal_input_pipe() -> None:
    if DEVCAL_INPUT.exists():
        try:
            mode = DEVCAL_INPUT.stat().st_mode
            if stat.S_ISFIFO(mode):
                return

            DEVCAL_INPUT.unlink()

        except FileNotFoundError:
            pass

    os.mkfifo(DEVCAL_INPUT, 0o666)
    os.chmod(DEVCAL_INPUT, 0o666)
    
def run_cmd(cmd: List[str], timeout: int = 30) -> Dict[str, Any]:
    result = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )

    return {
        "command": " ".join(cmd),
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }

def get_svxlink_service_state() -> Dict[str, Any]:
    return run_cmd(["/usr/bin/systemctl", "is-active", SVXLINK_SERVICE], timeout=10)


def stop_svxlink_for_calibration() -> Dict[str, Any]:
    return run_cmd(["sudo", "/usr/local/sbin/pi3twe-svxlink-control", "stop"], timeout=20)

def kill_devcal_processes() -> Dict[str, Any]:
    """
    Force-clear any devcal process before SvxLink is started/restarted.

    This is a safety net for cases where devcal survives page refreshes,
    navigation, or stale PID files and continues holding audio, GPIO, or HID
    resources.
    """
    result = run_cmd(
        ["sudo", "/usr/bin/pkill", "-x", "devcal"],
        timeout=10,
    )

    # pkill return codes:
    #   0 = one or more matching processes were killed
    #   1 = no matching process found
    # Both are acceptable for this cleanup step.
    if result["returncode"] in (0, 1):
        DEVCAL_PID.unlink(missing_ok=True)
        DEVCAL_MODE.unlink(missing_ok=True)
        DEVCAL_TX_STATE.unlink(missing_ok=True)
        DEVCAL_INPUT.unlink(missing_ok=True)

        if result["returncode"] == 0:
            result["stdout"] = result["stdout"] or "Cleared devcal process."
        else:
            result["stdout"] = "No devcal process was running."

        result["returncode"] = 0
        return result

    return result

def restart_svxlink_after_calibration() -> Dict[str, Any]:
    kill_result = kill_devcal_processes()

    if kill_result["returncode"] != 0:
        return {
            "command": kill_result["command"],
            "returncode": kill_result["returncode"],
            "stdout": kill_result["stdout"],
            "stderr": kill_result["stderr"] or "Unable to clear devcal before restarting SvxLink.",
        }

    return run_cmd(
        ["sudo", "/usr/local/sbin/pi3twe-svxlink-control", "restart"],
        timeout=30,
    )
    
def run_devcal(
    config_file: str,
    section: str,
    mode: str,
    modfqs: str,
    caldev: str,
    maxdev: str,
    headroom: str,
    audiodev: str = "",
    flat: bool = False,
    wide: bool = False,
) -> Dict[str, Any]:
    config_file = (config_file or "/etc/pi3twe/svxlink/svxlink.conf").strip()
    section = (section or "").strip()
    mode = (mode or "").strip()

    if not section:
        raise ValueError("No SvxLink Tx/Rx section selected.")

    cmd = [
        "sudo",
        "/usr/bin/devcal",
        config_file,
        section,
    ]

    if mode == "txcal":
        cmd.append("--txcal")
    elif mode == "rxcal":
        cmd.append("--rxcal")
    elif mode == "measure":
        cmd.append("--measure")
    else:
        raise ValueError("Invalid devcal mode selected.")

    if modfqs:
        cmd.extend(["--modfqs", str(modfqs)])

    if caldev:
        cmd.extend(["--caldev", str(caldev)])

    if maxdev:
        cmd.extend(["--maxdev", str(maxdev)])

    if headroom:
        cmd.extend(["--headroom", str(headroom)])

    if audiodev:
        cmd.extend(["--audiodev", audiodev])

    if flat:
        cmd.append("--flat")

    if wide:
        cmd.append("--wide")

    return run_cmd(cmd, timeout=180)

def build_devcal_command(
    config_file: str,
    section: str,
    mode: str,
    modfqs: str,
    caldev: str,
    maxdev: str,
    headroom: str,
    audiodev: str = "",
    flat: bool = False,
    wide: bool = False,
) -> List[str]:
    config_file = (config_file or "/etc/pi3twe/svxlink/svxlink.conf").strip()
    section = (section or "").strip()
    mode = (mode or "").strip()

    if not section:
        raise ValueError("No SvxLink Tx/Rx section selected.")

    cmd = [
        "sudo",
        "/usr/bin/devcal",
    ]

    if mode == "txcal":
        cmd.append("-t")

    elif mode == "rxcal":
        cmd.append("-r")

    elif mode == "measure":
        cmd.append("-M")

    else:
        raise ValueError("Invalid devcal mode selected.")

    if modfqs:
        cmd.extend(["-f", str(modfqs)])

    if caldev:
        cmd.extend(["-d", str(caldev)])

    if maxdev:
        cmd.extend(["-m", str(maxdev)])

    if headroom:
        cmd.extend(["-H", str(headroom)])

    if audiodev:
        cmd.extend(["-a", audiodev])

    if flat:
        cmd.append("-F")

    if wide:
        cmd.append("-w")

    cmd.extend([
        config_file,
        section,
    ])

    return cmd
def devcal_is_running() -> bool:
    if not DEVCAL_PID.exists():
        return False

    try:
        pid = int(DEVCAL_PID.read_text().strip())
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def start_devcal_session(
    config_file: str,
    section: str,
    mode: str,
    modfqs: str = "1000.0",
    caldev: str = "2404.8",
    maxdev: str = "5000",
    headroom: str = "6",
    audiodev: str = "",
    flat: bool = False,
    wide: bool = False,
) -> Dict[str, Any]:

    if devcal_is_running():
        raise RuntimeError("devcal is already running.")

    prepare_devcal_input_pipe()

    cmd = build_devcal_command(
        config_file=config_file,
        section=section,
        mode=mode,
        modfqs=modfqs,
        caldev=caldev,
        maxdev=maxdev,
        headroom=headroom,
        audiodev=audiodev,
        flat=flat,
        wide=wide,
    )

    quoted_cmd = " ".join(shlex.quote(part) for part in cmd)

    quoted_fifo = shlex.quote(str(DEVCAL_INPUT))

    shell_command = (
        f"while true; do "
        f"/bin/cat {quoted_fifo}; "
        f"done | {quoted_cmd}"
    )

    DEVCAL_LOG.write_text(
        "Starting devcal:\n"
        + shell_command
        + "\n\n",
        encoding="utf-8",
    )

    log_handle = DEVCAL_LOG.open("a", encoding="utf-8")

    process = subprocess.Popen(
        ["/bin/bash", "-lc", shell_command],
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )

    DEVCAL_PID.write_text(str(process.pid), encoding="utf-8")
    DEVCAL_MODE.write_text(mode, encoding="utf-8")
    set_devcal_tx_state("off")

    return {
        "command": shell_command,
        "returncode": 0,
        "stdout": f"devcal started with PID {process.pid}",
        "stderr": "",
    }
def get_devcal_mode() -> str:
    if not DEVCAL_MODE.exists():
        return ""

    try:
        return DEVCAL_MODE.read_text(
            encoding="utf-8",
            errors="ignore"
        ).strip()

    except Exception:
        return ""
def get_devcal_tx_state() -> str:
    if not DEVCAL_TX_STATE.exists():
        return "off"

    try:
        state = DEVCAL_TX_STATE.read_text(
            encoding="utf-8",
            errors="ignore",
        ).strip().lower()

    except Exception:
        return "off"

    if state == "on":
        return "on"

    return "off"


def set_devcal_tx_state(state: str) -> None:
    state = "on" if state == "on" else "off"
    DEVCAL_TX_STATE.write_text(state, encoding="utf-8")


def toggle_devcal_tx_state() -> str:
    current = get_devcal_tx_state()
    new_state = "off" if current == "on" else "on"
    set_devcal_tx_state(new_state)
    return new_state

def toggle_devcal_tx() -> Dict[str, Any]:
    if not devcal_is_running():
        raise RuntimeError("devcal is not running.")

    mode = get_devcal_mode()

    if mode != "txcal":
        raise RuntimeError("TX toggle is only available during TX calibration.")

    if not DEVCAL_INPUT.exists():
        raise RuntimeError("devcal input pipe is not available.")

    with DEVCAL_INPUT.open("w", encoding="utf-8") as fh:
        fh.write("T\n")
        fh.flush()

    new_state = toggle_devcal_tx_state()

    return {
        "command": "send T to devcal",
        "returncode": 0,
        "stdout": f"TX tone toggled {new_state.upper()}",
        "stderr": "",
    }
    
def stop_devcal_session() -> Dict[str, Any]:
    if not DEVCAL_PID.exists():
        return {
            "command": "stop devcal",
            "returncode": 0,
            "stdout": "No devcal PID file found.",
            "stderr": "",
        }

    try:
        pid = int(DEVCAL_PID.read_text().strip())

        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

        DEVCAL_PID.unlink(missing_ok=True)
        DEVCAL_MODE.unlink(missing_ok=True)
        DEVCAL_TX_STATE.unlink(missing_ok=True)
        DEVCAL_INPUT.unlink(missing_ok=True)

        return {
            "command": "stop devcal",
            "returncode": 0,
            "stdout": f"Stopped devcal PID {pid}",
            "stderr": "",
        }

    except Exception as exc:
        return {
            "command": "stop devcal",
            "returncode": 1,
            "stdout": "",
            "stderr": str(exc),
        }


def get_devcal_output(limit: int = 120) -> List[str]:
    if not DEVCAL_LOG.exists():
        return ["No devcal output yet."]

    try:
        lines = DEVCAL_LOG.read_text(
            encoding="utf-8",
            errors="ignore",
        ).splitlines()

    except Exception as exc:
        return [f"Unable to read devcal output: {exc}"]

    return lines[-limit:]
