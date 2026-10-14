#!/usr/bin/python3
"""Build the native plugin against the exact installed SvxLink 26.05.2 ABI."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--headers', type=Path, required=True, help='Extracted sigc++-3.0 development package root')
parser.add_argument('--build-config', type=Path, required=True, help='Directory with the SvxLink build config.h')
args = parser.parse_args()
version = subprocess.check_output(['git', '-C', str(args.source), 'describe', '--tags', '--always'], text=True).strip()
if version != '26.05.2':
    raise SystemExit('Use the exact SvxLink 26.05.2 source tree')
build = ROOT / '.native-build'
include = build / 'include'
include.mkdir(parents=True, exist_ok=True)
source = args.source / 'src'
logic = source / 'svxlink/svxlink'
header = (logic / 'Logic.h').read_text()
if 'pi3tweLiveAudio' not in header:
    header = header.replace('  protected:\n', '  protected:\n    Async::AudioSelector* pi3tweLiveAudio() const { return tx_audio_selector; }\n    void pi3tweEndAnnouncement() { updateTxCtcss(false, TX_CTCSS_ANNOUNCEMENT); checkIdle(); }\n    void pi3tweCallsign(const std::string& value) { m_callsign = value; setEventVariable("mycall", value); }\n', 1)
(include / 'Logic.h').write_text(header)
(include / 'RepeaterLogic.h').write_text((logic / 'RepeaterLogic.h').read_text())
paths = [include, args.build_config, args.build_config / "include", source / "misc", args.headers / 'usr/include/sigc++-3.0',
         args.headers / 'usr/lib/x86_64-linux-gnu/sigc++-3.0/include']
paths += [source / relative for relative in ['svxlink/svxlink','svxlink/trx','async/core','async/audio','locationinfo','echolib','svxlink/svxmisc']]
flags = (args.build_config / 'svxlink/svxlink/CMakeFiles/svxlink.dir/flags.make').read_text()
if '-DINTERNAL_SAMPLE_RATE=16000' not in flags:
    raise SystemExit('This news pipeline requires the installed 16 kHz internal SvxLink build')
command = ['g++', '-DINTERNAL_SAMPLE_RATE=16000', '-std=c++17', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Wno-unused-parameter']
for path in paths:
    command.extend(['-I',str(path)])
command += [str(ROOT / 'native/Pi3tweLogic.cpp'), '-L/usr/local/lib/svxlink', '-L/usr/local/lib',
            '-Wl,-rpath,/usr/local/lib/svxlink:/usr/local/lib', '-Wl,--no-as-needed',
            '-l:RepeaterLogic.so', '-l:libasyncaudio.so.1.9', '-l:libasynccore.so.1.9',
            '-l:libsigc-3.0.so.0', '-o', str(build / 'Pi3tweLogic.so')]
subprocess.run(command, check=True)
manifest = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [
    Path('/usr/local/bin/svxlink'), Path('/usr/local/lib/svxlink/RepeaterLogic.so')]}
(build / 'abi-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
print('Built:',build/'Pi3tweLogic.so')
