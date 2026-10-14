"""DCTTECH USB relay backend using Debian's maintained usbrelay utility."""

from __future__ import annotations

import re
import subprocess
import time
from collections.abc import Callable, Sequence
from threading import RLock

CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


class UsbRelayError(RuntimeError):
    """The physical relay could not be queried or controlled."""


class UsbRelayHardware:
    def __init__(
        self,
        module_id: str,
        *,
        relay_channels: tuple[int, int] = (1, 2),
        executable: str = "/usr/bin/usbrelay",
        runner: CommandRunner | None = None,
        cache_seconds: float = 0.2,
    ) -> None:
        normalized_id = module_id.strip()
        if not re.fullmatch(r"[A-Za-z0-9]{1,5}", normalized_id):
            raise ValueError("USB relay module ID must contain 1-5 letters or digits")
        if len(set(relay_channels)) != 2 or any(
            channel not in range(1, 5) for channel in relay_channels
        ):
            raise ValueError("USB relay channels must be two unique values from 1 to 4")
        self._module_id = normalized_id
        self._relay_channels = dict(enumerate(relay_channels, start=1))
        self._executable = executable
        self._runner = runner or self._run_command
        self._cache_seconds = max(0.0, cache_seconds)
        self._states = {1: False, 2: False}
        self._last_read = float("-inf")
        self._connected = False
        self._last_error: str | None = "USB relay has not been queried yet"
        self._lock = RLock()

    def count(self) -> int:
        return 2

    def get_state(self, relay_id: int) -> bool:
        self._validate_relay(relay_id)
        with self._lock:
            try:
                self._refresh()
            except UsbRelayError:
                # State pages remain available during a temporary disconnect.
                pass
            return self._states[relay_id]

    def set_state(self, relay_id: int, enabled: bool) -> None:
        self._validate_relay(relay_id)
        with self._lock:
            channel = self._relay_channels[relay_id]
            action = f"{self._module_id}_{channel}={int(bool(enabled))}"
            result = self._runner([self._executable, action])
            if result.returncode != 0:
                self._record_failure(result.stderr or result.stdout or "usbrelay failed")
                raise UsbRelayError(self._last_error)

            self._last_read = float("-inf")
            self._refresh(force=True)
            if self._states[relay_id] is not bool(enabled):
                self._record_failure(
                    f"Relay {relay_id} did not reach requested state {int(bool(enabled))}"
                )
                raise UsbRelayError(self._last_error)

    def health(self) -> dict[str, object]:
        with self._lock:
            try:
                self._refresh()
            except UsbRelayError:
                pass
            return {
                "backend": "usbrelay",
                "connected": self._connected,
                "module_id": self._module_id,
                "channels": 2,
                "physical_channels": dict(self._relay_channels),
                "message": (
                    "DCTTECH USB relay connected"
                    if self._connected
                    else self._last_error or "USB relay unavailable"
                ),
            }

    def _refresh(self, *, force: bool = False) -> None:
        if not force and time.monotonic() - self._last_read <= self._cache_seconds:
            return

        result = self._runner([self._executable])
        if result.returncode != 0:
            self._record_failure(result.stderr or result.stdout or "usbrelay failed")
            raise UsbRelayError(self._last_error)

        states = self._parse_states(result.stdout)
        missing = [
            channel
            for channel in self._relay_channels.values()
            if channel not in states
        ]
        if missing:
            self._record_failure(
                f"USB relay {self._module_id} missing channel(s): {missing}"
            )
            raise UsbRelayError(self._last_error)

        self._states.update(
            {
                relay_id: states[channel]
                for relay_id, channel in self._relay_channels.items()
            }
        )
        self._last_read = time.monotonic()
        self._connected = True
        self._last_error = None

    def _parse_states(self, output: str) -> dict[int, bool]:
        pattern = re.compile(
            rf"^{re.escape(self._module_id)}_([1-4])=([01])$", re.MULTILINE
        )
        return {
            int(channel): state == "1"
            for channel, state in pattern.findall(output)
        }

    def _record_failure(self, message: str) -> None:
        self._connected = False
        self._last_error = " ".join(message.strip().split())

    @staticmethod
    def _run_command(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise UsbRelayError(f"Could not execute usbrelay: {error}") from error

    @staticmethod
    def _validate_relay(relay_id: int) -> None:
        if relay_id not in (1, 2):
            raise ValueError(f"Unknown relay: {relay_id}")
