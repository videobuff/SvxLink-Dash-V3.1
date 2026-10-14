"""Restricted status and service control for the PI3TWE SvxLink instance."""

from __future__ import annotations

import json
import logging
import os
import re
import stat
import time
import uuid
import configparser
import subprocess
from pathlib import Path
from typing import Sequence


class SvxLinkError(RuntimeError):
    pass


class SvxLink:
    ACTIONS = {"start", "stop", "restart"}

    def __init__(
        self,
        *,
        config_file: Path = Path("/etc/pi3twe/svxlink/svxlink.conf"),
        echolink_file: Path = Path("/etc/pi3twe/svxlink/svxlink.d/ModuleEchoLink.conf"),
        echolink_ready_file: Path = Path("/etc/pi3twe/svxlink/echolink.configured"),
        executable: Path = Path("/usr/local/bin/svxlink"),
        command_pty: Path = Path("/run/pi3twe-svxlink/command"),
        status_directory: Path = Path("/run/pi3twe-svxlink/status"),
        control_command: Sequence[str] = (
            "/usr/local/sbin/pi3twe-svxlink-control",
        ),
    ) -> None:
        self.config_file = config_file
        self.echolink_file = echolink_file
        self.echolink_ready_file = echolink_ready_file
        self.executable = executable
        self.control_command = tuple(control_command)
        self.command_pty = command_pty
        self.status_directory = status_directory

    def state(self) -> dict[str, object]:
        service = self._service_properties()
        return {
            "installed": self.executable.is_file(),
            "configured": self.config_file.is_file(),
            "echolink_configured": self._echolink_configured(),
            "active": service.get("ActiveState") == "active",
            "native_ready": self.command_pty.exists() and (self.status_directory / "ready").is_file(),
            "enabled": service.get("UnitFileState") == "enabled",
            "service_state": service.get("ActiveState", "unknown"),
            "service_detail": service.get("SubState", "unknown"),
            "callsign": self._callsign(),
        }

    def control(self, action: str) -> dict[str, object]:
        if action not in self.ACTIONS:
            raise ValueError("Kies starten, stoppen of herstarten")
        if not self.executable.is_file():
            raise SvxLinkError("SvxLink is nog niet geïnstalleerd")
        if not self.config_file.is_file():
            raise SvxLinkError("SvxLink is nog niet geconfigureerd")
        try:
            subprocess.run(
                [*self.control_command, action],
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except (OSError, subprocess.SubprocessError) as error:
            message = "SvxLink kon niet worden bediend"
            if isinstance(error, subprocess.CalledProcessError):
                detail = " ".join((error.stderr or error.stdout or "").split())
                if detail:
                    message = detail
            raise SvxLinkError(message) from error
        return self.state()

    def send_command(self, command: str, token: str, arguments: str = "") -> None:
        if command not in {"NEWS", "CANCEL", "RADIO", "POLICY", "STATUS"} or not re.fullmatch(r"[a-f0-9]{32}", token):
            raise ValueError("Ongeldige SvxLink-opdracht")
        if not re.fullmatch(r"[A-Z0-9/ ]*", arguments):
            raise ValueError("Ongeldige SvxLink-argumenten")
        fd = None
        try:
            fd = os.open(self.command_pty, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            if not stat.S_ISCHR(os.fstat(fd).st_mode):
                raise OSError("SvxLink-commandopoort is geen PTY")
            payload = f"{command} {token} {arguments}".rstrip().encode("ascii") + b"\n"
            if os.write(fd, payload) != len(payload):
                raise OSError("SvxLink-opdracht is niet volledig geschreven")
        except OSError as error:
            raise SvxLinkError("SvxLink-commandopoort is niet beschikbaar: " + str(error)) from error
        finally:
            if fd is not None:
                os.close(fd)

    def command_status(self, token: str) -> dict | None:
        if not re.fullmatch(r"[a-f0-9]{32}", token):
            raise ValueError("Ongeldig opdrachtnummer")
        try:
            data = json.loads((self.status_directory / f"{token}.json").read_text())
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as error:
            raise SvxLinkError("SvxLink-status kon niet worden gelezen") from error
        if data.get("job") != token:
            raise SvxLinkError("SvxLink-status hoort bij een andere opdracht")
        return data

    def cleanup_status(self, token):
        """Cleanup must never turn a confirmed command into a failed command."""
        if not re.fullmatch(r"[a-f0-9]{32}", token):
            raise ValueError("Ongeldig opdrachtnummer")
        try:
            (self.status_directory / f"{token}.json").unlink(missing_ok=True)
        except OSError as error:
            logging.getLogger(__name__).warning("SvxLink-bevestiging kon niet worden opgeruimd: %s", error)

    def _execute(self, command, arguments):
        token = uuid.uuid4().hex
        self.send_command(command, token, arguments)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = self.command_status(token)
            if state:
                self.cleanup_status(token)
                if state["phase"] == "done":
                    return
                raise SvxLinkError("SvxLink heeft de opdracht geweigerd: " + state["phase"])
            time.sleep(.05)
        raise SvxLinkError("SvxLink heeft de opdracht niet bevestigd")

    def apply_policy(self, settings):
        self._execute("POLICY", f"{settings['callsign']} {settings['id_interval_minutes']}")

    def radio_power(self, enabled):
        self._execute("RADIO", str(int(bool(enabled))))

    @staticmethod
    def _service_properties() -> dict[str, str]:
        try:
            result = subprocess.run(
                [
                    "/usr/bin/systemctl",
                    "show",
                    "pi3twe-svxlink.service",
                    "--property=ActiveState,SubState,UnitFileState",
                    "--no-pager",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return {}
        return dict(
            line.split("=", 1)
            for line in result.stdout.splitlines()
            if "=" in line
        )

    def _callsign(self) -> str:
        config = self._read_config(self.config_file)
        section = "RepeaterLogic" if config.has_section("RepeaterLogic") else "SimplexLogic"
        return config.get(section, "CALLSIGN", fallback="PI3TWE")

    def _echolink_configured(self) -> bool:
        runtime = self.command_pty.parent
        if self.echolink_file == Path("/etc/pi3twe/svxlink/svxlink.d/ModuleEchoLink.conf") and (runtime / "applied-config").is_file():
            main = self._read_config(runtime / "svxlink.conf")
            modules = main.get("RepeaterLogic", "MODULES", fallback="").split(",")
            if "ModuleEchoLink" not in modules:
                return False
            module_dir = Path(main.get("GLOBAL", "CFG_DIR", fallback=str(self.echolink_file.parent)))
            if not module_dir.is_absolute():
                module_dir = runtime / module_dir
            config = self._read_config(module_dir / "ModuleEchoLink.conf")
        else:
            if self.echolink_ready_file.is_file():
                return True
            config = self._read_config(self.echolink_file)
        if not config.has_section("ModuleEchoLink"):
            return False
        values = {
            key: config.get("ModuleEchoLink", key, fallback="").strip()
            for key in ("CALLSIGN", "PASSWORD", "SYSOPNAME", "LOCATION")
        }
        return all(value and value != "CHANGE_ME" for value in values.values())

    @staticmethod
    def _read_config(path: Path) -> configparser.ConfigParser:
        config = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            with path.open(encoding="utf-8") as config_file:
                config.read_file(config_file)
        except (OSError, configparser.Error):
            pass
        return config
