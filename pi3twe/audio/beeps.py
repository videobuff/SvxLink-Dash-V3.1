"""Generate a short, bounded announcement signal as a PCM WAV file."""
import math
import struct
import wave
from pathlib import Path


def write_beeps(path: Path, settings: dict, *, sample_rate=48000):
    rate = sample_rate
    tone_samples = round(rate * settings["beep_duration_ms"] / 1000)
    gap_samples = round(rate * settings["beep_gap_ms"] / 1000)
    ramp = min(round(rate * .005), tone_samples // 2)
    tone = bytearray()
    for index in range(tone_samples):
        envelope = min(1, index / max(1, ramp), (tone_samples - 1 - index) / max(1, ramp))
        sample = round(7000 * envelope * math.sin(2 * math.pi * settings["beep_frequency_hz"] * index / rate))
        tone.extend(struct.pack("<h", sample))
    silence = bytes(gap_samples * 2)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        for index in range(settings["beep_count"]):
            output.writeframes(tone)
            if index < settings["beep_count"] - 1:
                output.writeframes(silence)
