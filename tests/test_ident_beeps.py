from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
import ctypes
import ctypes.util
import struct
import wave
from pi3twe.audio.beeps import write_beeps

ROOT = Path(__file__).resolve().parents[1]


class IdentificationTest(TestCase):
    def test_both_repeater_identifications_use_plain_callsign(self):
        source = (ROOT / 'install/pi3twe-svxlink-events/events.tcl').read_text()
        override = source[source.index('# A repeater identification'):]
        harness = '''set logic_name RepeaterLogic
set mycall PI3TWE
set played {}
proc printInfo {text} {}
namespace eval RepeaterLogic::Logic {
    namespace eval CW {
        proc play {text} { lappend ::played $text }
    }
    proc send_short_cw_ident {hour minute} { error "old suffix handler" }
    proc send_long_cw_ident {hour minute} { error "old suffix handler" }
    namespace export *
}
namespace eval RepeaterLogic { namespace import Logic::* }
'''
        harness += override
        harness += '''
RepeaterLogic::send_short_cw_ident 0 0
RepeaterLogic::send_long_cw_ident 0 0
puts $played
'''
        harness = harness.replace('puts $played', 'set played')
        library = ctypes.CDLL(ctypes.util.find_library('tcl8.6'))
        library.Tcl_CreateInterp.restype = ctypes.c_void_p
        library.Tcl_Eval.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        library.Tcl_GetStringResult.argtypes = [ctypes.c_void_p]
        library.Tcl_GetStringResult.restype = ctypes.c_char_p
        library.Tcl_DeleteInterp.argtypes = [ctypes.c_void_p]
        interpreter = library.Tcl_CreateInterp()
        try:
            result = library.Tcl_Eval(interpreter, harness.encode())
            output = library.Tcl_GetStringResult(interpreter).decode()
            self.assertEqual(result, 0, output)
            self.assertEqual(output, 'PI3TWE PI3TWE')
        finally:
            library.Tcl_DeleteInterp(interpreter)

    def test_five_beeps_start_one_second_apart_at_600_hz(self):
        settings = {'beep_count': 5, 'beep_frequency_hz': 600, 'beep_duration_ms': 250, 'beep_gap_ms': 750}
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'beeps.wav'
            write_beeps(path, settings, sample_rate=16000)
            with wave.open(str(path)) as audio:
                self.assertEqual(audio.getnframes(), 68000)
                raw = audio.readframes(audio.getnframes())
            samples = struct.unpack('<2000h', raw[1000:5000])
            crossings = sum(a <= 0 < b for a, b in zip(samples, samples[1:]))
            self.assertTrue(73 <= crossings <= 77, crossings)  # 600 Hz across 0.125 s.
            for index in range(5):
                start = index * 16000 * 2
                self.assertNotEqual(raw[start:start + 4000 * 2], bytes(4000 * 2))
                if index < 4:
                    self.assertEqual(raw[start + 4000 * 2:start + 16000 * 2], bytes(12000 * 2))
