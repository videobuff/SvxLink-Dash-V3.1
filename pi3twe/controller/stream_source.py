"""Persist the exclusive source for the single public audio stream."""

from pathlib import Path


class StreamSourceError(RuntimeError):
    pass


class StreamSource:
    SOURCES = {"analog", "sdr"}

    def __init__(self, state_file: Path = Path("/etc/pi3twe/pi3twe-stream-source")) -> None:
        self.state_file = state_file

    def state(self) -> dict[str, str]:
        try:
            source = self.state_file.read_text(encoding="ascii").strip()
        except OSError as error:
            raise StreamSourceError("Streambron kon niet worden gelezen") from error
        if source not in self.SOURCES:
            raise StreamSourceError("Streambronconfiguratie is ongeldig")
        return {"stream_source": source}

    def update(self, source: str) -> dict[str, str]:
        if source not in self.SOURCES:
            raise ValueError("Kies de microfooningang of OpenWebRX als streambron")
        try:
            self.state_file.write_text(f"{source}\n", encoding="ascii")
        except OSError as error:
            raise StreamSourceError("Streambron kon niet worden omgeschakeld") from error
        return self.state()
