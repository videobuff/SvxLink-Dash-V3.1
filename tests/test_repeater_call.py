from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from pi3twe.controller.svxlink import SvxLink, SvxLinkError


class RepeaterCallTest(TestCase):
    def test_call_uses_one_local_command_and_waits_for_completion(self):
        engine = SvxLink()
        with patch.object(engine, 'send_command') as send, \
             patch.object(engine, 'command_status', side_effect=[{'phase': 'call'}, {'phase': 'done'}]), \
             patch.object(engine, 'cleanup_status') as cleanup, \
             patch('pi3twe.controller.svxlink.time.sleep'), \
             patch.object(engine, 'control') as control:
            engine.test_repeater_call()
            self.assertEqual(send.call_count, 1)
            self.assertEqual(send.call_args.args[0], 'CALL')
            cleanup.assert_called_once_with(send.call_args.args[1])
            control.assert_not_called()

    def test_power_off_rejection_is_reported_without_service_restart(self):
        engine = SvxLink()
        with patch.object(engine, 'send_command'), \
             patch.object(engine, 'command_status', return_value={'phase': 'power_off'}), \
             patch.object(engine, 'cleanup_status'), \
             patch.object(engine, 'control') as control:
            with self.assertRaisesRegex(SvxLinkError, 'Power staat uit'):
                engine.test_repeater_call()
            control.assert_not_called()

    def test_timeout_cancels_only_the_call_job(self):
        engine = SvxLink()
        with patch.object(engine, 'send_command') as send, \
             patch.object(engine, 'command_status', return_value=None), \
             patch.object(engine, 'cleanup_status'), \
             patch('pi3twe.controller.svxlink.time.monotonic', side_effect=[0, 41]):
            with self.assertRaisesRegex(SvxLinkError, 'niet tijdig'):
                engine.test_repeater_call()
            self.assertEqual([call.args[0] for call in send.call_args_list], ['CALL', 'CANCEL'])
            self.assertEqual(send.call_args_list[0].args[1], send.call_args_list[1].args[1])
