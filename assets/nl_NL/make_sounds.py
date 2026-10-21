#!/usr/bin/env python3
"""Maak SvxLink-geluidsclips met de Microsoft neural stemmen via edge-tts.

Leest nl_NL.tsv (pad<TAB>modus<TAB>tekst), synthetiseert elke clip,
bewerkt hem na met sox (stilte trimmen / normaliseren) en schrijft een
SvxLink-taalmap met events.d erbij.

Synthese-resultaten worden gecachet in <cache>/; alleen gewijzigde
teksten of een andere stem leiden tot een nieuwe API-aanroep.

Voorbeelden:
    ./make_sounds.py --list-voices
    ./make_sounds.py --only Core/online,Default/21
    ./make_sounds.py
"""

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLE_RATE = 16000
# Zelfde nabewerking als svxlink-google-tts (scripts/filter_sounds.cfg)
DEFAULT_EFFECT = "bass -10 200 compand 0.01,0.1 3:-55,-25,-5 -15 -50 0.01"
SILENCE_LEVEL = "-50d"


def read_tsv(path):
    clips = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 3 or parts[1] not in ("trim", "max", "link"):
            sys.exit(f"{path}:{lineno}: verwacht pad<TAB>trim|max|link<TAB>tekst")
        clips.append(tuple(parts))
    return clips


def list_voices(lang):
    import edge_tts
    for v in asyncio.run(edge_tts.list_voices()):
        if v["Locale"].startswith(lang):
            print(f"{v['ShortName']:32} {v['Gender']}")


def synthesize(text, dst, args):
    import edge_tts
    asyncio.run(edge_tts.Communicate(text, args.voice, rate=args.rate, pitch=args.pitch).save(str(dst)))


def sox_process(src, dst, mode, effect, pad):
    cmd = ["sox", str(src), "-r", str(SAMPLE_RATE), "-c", "1", "-b", "16", str(dst)]
    if mode == "trim":
        cmd += ["silence", "1", "0.01", SILENCE_LEVEL, "reverse",
                "silence", "1", "0.01", SILENCE_LEVEL, "reverse"]
    cmd += effect.split() + ["norm", "-3"]
    if mode == "trim" and pad > 0:
        cmd += ["pad", "0", str(pad)]
    subprocess.run(cmd, check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tsv", type=Path, default=HERE / "nl_NL.tsv")
    p.add_argument("--out", type=Path, default=HERE / "build" / "nl_NL")
    p.add_argument("--cache", type=Path, default=HERE / "build" / "cache")
    p.add_argument("--lang", default="nl-NL")
    p.add_argument("--voice", default="nl-NL-MaartenNeural", help="stemnaam, zie --list-voices")
    p.add_argument("--rate", default="-10%", help="spreeksnelheid, bijv. -10%% of +5%%")
    p.add_argument("--pitch", default="+0Hz", help="toonhoogte, bijv. -5Hz")
    p.add_argument("--pad", type=float, default=0.12, help="stilte (s) na elke getrimde clip")
    p.add_argument("--effect", default=DEFAULT_EFFECT, help="extra sox-effecten ('' = geen)")
    p.add_argument("--only", help="komma-gescheiden clippaden, bijv. Core/online,Default/21")
    p.add_argument("--list-voices", action="store_true")
    p.add_argument("--no-tar", action="store_true")
    args = p.parse_args()

    if args.list_voices:
        list_voices(args.lang)
        return

    clips = read_tsv(args.tsv)
    if args.only:
        wanted = set(args.only.split(","))
        clips = [c for c in clips if c[0] in wanted]
        missing = wanted - {c[0] for c in clips}
        if missing:
            sys.exit(f"Onbekende clips: {', '.join(sorted(missing))}")

    calls = 0
    for path, mode, text in clips:
        dst = args.out / f"{path}.wav"
        dst.parent.mkdir(parents=True, exist_ok=True)
        if mode == "link":
            if dst.is_symlink() or dst.exists():
                dst.unlink()
            dst.symlink_to(f"{text}.wav")
            continue

        key = hashlib.sha256(json.dumps([text, args.lang, args.voice, args.rate, args.pitch]).encode()).hexdigest()[:16]
        raw = args.cache / f"{key}.mp3"
        if not raw.exists():
            raw.parent.mkdir(parents=True, exist_ok=True)
            synthesize(text, raw, args)
            calls += 1
            print(f"  TTS  {path}: {text}")
        sox_process(raw, dst, mode, args.effect, args.pad)

    events = HERE / "events.d"
    if events.is_dir() and not args.only:
        shutil.copytree(events, args.out / "events.d", dirs_exist_ok=True)

    print(f"{len(clips)} clips in {args.out} ({calls} nieuw gesynthetiseerd)")

    if not args.no_tar and not args.only:
        tar = args.out.parent / f"{args.out.name}.tar.bz2"
        with tarfile.open(tar, "w:bz2") as t:
            t.add(args.out, arcname=args.out.name)
        print(f"Archief: {tar}")


if __name__ == "__main__":
    main()
