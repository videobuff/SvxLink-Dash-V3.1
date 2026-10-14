"""Small, restricted wrapper around the ALSA audio controls."""

from __future__ import annotations

import re
import subprocess


class AudioMixerError(RuntimeError):
    """Raised when ALSA cannot read or update a mixer control."""


class AudioMixer:
    def __init__(self, card: int = 1) -> None:
        self.card = card

    def state(self) -> dict[str, int | bool]:
        output = self._get("Loopback Mixing")
        match = re.search(r"Item\d+:\s*'(Enabled|Disabled)'", output)
        if not match:
            raise AudioMixerError("Stand van Loopback Mixing kon niet worden gelezen")
        enabled = match.group(1) == "Enabled"
        return {
            "enabled": enabled,
            "output_mode": "monitor" if enabled else "transmit",
            "input_percent": self._percent(self._get("Capture"), "Capture"),
            "monitor_percent": self._percent(self._get("Mic"), "Mic"),
            "master_percent": self._percent(self._get("Master"), "Master"),
        }

    def update(
        self,
        *,
        enabled: bool,
        input_percent: int,
        monitor_percent: int,
        master_percent: int,
    ) -> dict[str, int | bool]:
        input_gain = self._validate_percent(input_percent)
        monitor = self._validate_percent(monitor_percent)
        master = self._validate_percent(master_percent)
        self._set("Capture", f"{input_gain}%", "cap")
        if enabled:
            self._set("Mic", f"{monitor}%", "unmute")
            self._set("Loopback Mixing", "Enabled")
        else:
            # Fail-safe order: break the feedback path before enabling any
            # news/EchoLink playback on the analog output.
            self._set("Loopback Mixing", "Disabled")
            self._set("Mic", f"{monitor}%", "mute")
        self._set("Master", f"{master}%", "unmute")
        return self.state()

    def _get(self, control: str) -> str:
        return self._run("sget", control)

    def _set(self, control: str, *values: str) -> str:
        return self._run("sset", control, *values)

    def _run(self, action: str, control: str, *values: str) -> str:
        try:
            result = subprocess.run(
                ["/usr/bin/amixer", "-c", str(self.card), action, control, *values],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise AudioMixerError(f"ALSA-regelaar '{control}' is niet beschikbaar") from error
        return result.stdout

    @staticmethod
    def _percent(output: str, control: str) -> int:
        match = re.search(r"\[(\d{1,3})%\]", output)
        if not match:
            raise AudioMixerError(f"Volume van '{control}' kon niet worden gelezen")
        return int(match.group(1))

    @staticmethod
    def _validate_percent(value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
            raise ValueError("Volume moet een geheel getal van 0 tot en met 100 zijn")
        return value
