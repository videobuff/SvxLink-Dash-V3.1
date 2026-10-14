"""Restricted remote control of the RF monitor receiver."""

from __future__ import annotations

import re
import subprocess
import os
import fcntl
from pathlib import Path


class RfMonitorError(RuntimeError):
    """Raised when the RF monitor configuration cannot be read or changed."""


class RfMonitor:
    DEFAULT_SQUELCH_LEVEL = 9
    MIN_SQUELCH_LEVEL = 0
    MAX_SQUELCH_LEVEL = 20
    DEFAULT_OPENWEBRX_SQUELCH_LEVEL = -35
    MIN_OPENWEBRX_SQUELCH_LEVEL = -60
    MAX_OPENWEBRX_SQUELCH_LEVEL = 0
    DEFAULT_STREAM_LEVEL_PERCENT = 50
    MIN_STREAM_LEVEL_PERCENT = 10
    MAX_STREAM_LEVEL_PERCENT = 100
    FREQUENCIES = {
        145600000: "145,600 MHz — repeateruitgang",
        145000000: "145,000 MHz — repeateringang",
        430275000: "430,275 MHz — testfrequentie",
    }
    MIN_FREQUENCY_OFFSET_HZ = -10000
    MAX_FREQUENCY_OFFSET_HZ = 10000
    FREQUENCY_STEP_HZ = 1000

    def __init__(
        self,
        config_file: Path = Path("/etc/pi3twe/pi3twe-rf-monitor.conf"),
        restart_command: tuple[str, ...] = (),
    ) -> None:
        self.config_file = config_file
        self.restart_command = restart_command

    def state(self) -> dict[str, object]:
        try:
            config = self.config_file.read_text(encoding="utf-8")
        except OSError as error:
            raise RfMonitorError("RF-monitorconfiguratie is niet leesbaar") from error
        match = re.search(r"^RF_MONITOR_FREQUENCY=(\d+)$", config, re.MULTILINE)
        if not match:
            raise RfMonitorError("RF-monitorfrequentie ontbreekt in de configuratie")
        frequency = int(match.group(1))
        base_frequency = self._base_frequency(frequency)
        frequency_offset = frequency - base_frequency
        source_match = re.search(r"^RF_MONITOR_SOURCE=(\w+)$", config, re.MULTILINE)
        source = source_match.group(1) if source_match else "rtlsdr"
        openwebrx = source == "openwebrx"
        squelch_key = "RF_MONITOR_OPENWEBRX_SQUELCH" if openwebrx else "RF_MONITOR_SQUELCH"
        squelch_match = re.search(
            rf"^{squelch_key}=(-?\d+)$", config, re.MULTILINE
        )
        squelch_default = (
            self.DEFAULT_OPENWEBRX_SQUELCH_LEVEL if openwebrx else self.DEFAULT_SQUELCH_LEVEL
        )
        squelch_level = (
            int(squelch_match.group(1)) if squelch_match else squelch_default
        )
        stream_level_match = re.search(
            r"^RF_MONITOR_STREAM_LEVEL_PERCENT=(\d+)$", config, re.MULTILINE
        )
        stream_level_percent = (
            int(stream_level_match.group(1))
            if stream_level_match
            else self.DEFAULT_STREAM_LEVEL_PERCENT
        )
        return {
            "frequency_hz": frequency,
            "base_frequency_hz": base_frequency,
            "frequency_offset_hz": frequency_offset,
            "frequency_offset_min_hz": self.MIN_FREQUENCY_OFFSET_HZ,
            "frequency_offset_max_hz": self.MAX_FREQUENCY_OFFSET_HZ,
            "frequency_step_hz": self.FREQUENCY_STEP_HZ,
            "frequency_label": self._frequency_label(base_frequency, frequency_offset),
            "receiver_source": source,
            "receiver_label": "OpenWebRX" if openwebrx else "RTL-SDR (rtl_fm)",
            "squelch_level": squelch_level,
            "squelch_level_min": (
                self.MIN_OPENWEBRX_SQUELCH_LEVEL if openwebrx else self.MIN_SQUELCH_LEVEL
            ),
            "squelch_level_max": (
                self.MAX_OPENWEBRX_SQUELCH_LEVEL if openwebrx else self.MAX_SQUELCH_LEVEL
            ),
            "squelch_level_step": 1,
            "squelch_unit": "dB" if openwebrx else "",
            "stream_level_percent": stream_level_percent,
            "stream_level_min_percent": self.MIN_STREAM_LEVEL_PERCENT,
            "stream_level_max_percent": self.MAX_STREAM_LEVEL_PERCENT,
            "stream_level_step_percent": 5,
            "options": [
                {"frequency_hz": value, "label": label}
                for value, label in self.FREQUENCIES.items()
            ],
        }

    def update(
        self,
        frequency_hz: int,
        squelch_level: int | None = None,
        stream_level_percent: int | None = None,
    ) -> dict[str, object]:
        if isinstance(frequency_hz, bool) or not isinstance(frequency_hz, int):
            raise ValueError("Kies een geldige RF-monitorfrequentie")
        self._base_frequency(frequency_hz)
        try:
            with self.config_file.open("r+", encoding="utf-8") as config_file:
                fcntl.flock(config_file, fcntl.LOCK_EX)
                config = config_file.read()
                source_match = re.search(r"^RF_MONITOR_SOURCE=(\w+)$", config, re.MULTILINE)
                source = source_match.group(1) if source_match else "rtlsdr"
                openwebrx = source == "openwebrx"
                squelch_min = (
                    self.MIN_OPENWEBRX_SQUELCH_LEVEL if openwebrx else self.MIN_SQUELCH_LEVEL
                )
                squelch_max = (
                    self.MAX_OPENWEBRX_SQUELCH_LEVEL if openwebrx else self.MAX_SQUELCH_LEVEL
                )
                if squelch_level is not None and (
                    isinstance(squelch_level, bool)
                    or not isinstance(squelch_level, int)
                    or not squelch_min <= squelch_level <= squelch_max
                ):
                    unit = " dB" if openwebrx else ""
                    raise ValueError(
                        f"Squelch moet een geheel getal tussen {squelch_min} en {squelch_max}{unit} zijn"
                    )
                if stream_level_percent is not None and (
                    isinstance(stream_level_percent, bool)
                    or not isinstance(stream_level_percent, int)
                    or not self.MIN_STREAM_LEVEL_PERCENT
                    <= stream_level_percent
                    <= self.MAX_STREAM_LEVEL_PERCENT
                ):
                    raise ValueError("Streamniveau moet een geheel getal tussen 10 en 100% zijn")
                config, changed = re.subn(
                    r"^RF_MONITOR_FREQUENCY=\d+$",
                    f"RF_MONITOR_FREQUENCY={frequency_hz}",
                    config,
                    count=1,
                    flags=re.MULTILINE,
                )
                if not changed:
                    raise RfMonitorError("RF-monitorfrequentie ontbreekt in de configuratie")
                # Auto-gain raises the noise floor after startup and defeats a
                # stable RF squelch. Preserve manually tuned fixed gains.
                config = re.sub(
                    r"^RF_MONITOR_GAIN=auto$",
                    "RF_MONITOR_GAIN=35",
                    config,
                    count=1,
                    flags=re.MULTILINE,
                )
                if squelch_level is not None:
                    squelch_key = (
                        "RF_MONITOR_OPENWEBRX_SQUELCH" if openwebrx else "RF_MONITOR_SQUELCH"
                    )
                    squelch_line = f"{squelch_key}={squelch_level}"
                    config, changed = re.subn(
                        rf"^{squelch_key}=-?\d+$",
                        squelch_line,
                        config,
                        count=1,
                        flags=re.MULTILINE,
                    )
                    if not changed:
                        config = f"{config.rstrip()}\n{squelch_line}\n"
                if stream_level_percent is not None:
                    stream_level_line = (
                        f"RF_MONITOR_STREAM_LEVEL_PERCENT={stream_level_percent}"
                    )
                    config, changed = re.subn(
                        r"^RF_MONITOR_STREAM_LEVEL_PERCENT=\d+$",
                        stream_level_line,
                        config,
                        count=1,
                        flags=re.MULTILINE,
                    )
                    if not changed:
                        config = f"{config.rstrip()}\n{stream_level_line}\n"
                config_file.seek(0)
                config_file.write(config)
                config_file.truncate()
                config_file.flush()
                os.fsync(config_file.fileno())
            if self.restart_command:
                subprocess.run(
                    list(self.restart_command),
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
        except (OSError, subprocess.SubprocessError) as error:
            raise RfMonitorError("RF-monitor kon niet worden omgeschakeld") from error
        return self.state()

    @classmethod
    def _base_frequency(cls, frequency_hz: int) -> int:
        for base_frequency in cls.FREQUENCIES:
            offset = frequency_hz - base_frequency
            if (
                cls.MIN_FREQUENCY_OFFSET_HZ <= offset <= cls.MAX_FREQUENCY_OFFSET_HZ
                and offset % cls.FREQUENCY_STEP_HZ == 0
            ):
                return base_frequency
        raise ValueError("Fijnafstemming moet in stappen van 1 kHz tussen -10 en +10 kHz liggen")

    @classmethod
    def _frequency_label(cls, base_frequency: int, offset_hz: int) -> str:
        frequency_mhz = (base_frequency + offset_hz) / 1_000_000
        offset_khz = offset_hz // 1000
        return f"{frequency_mhz:.3f} MHz ({offset_khz:+d} kHz)"
