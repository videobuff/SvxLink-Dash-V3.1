import ast
import configparser
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class Pi3tweConfigurationTests(unittest.TestCase):
    def test_vox_overrides_hardware_squelch(self):
        from renderers.svxlink_renderer import render_rx_sql_block, render_tx_ptt_block
        for interface in ['hidraw', 'serial', 'hybrid']:
            model = {'interface': {'mode': interface}, 'squelch': {'method': 'vox'}}
            self.assertIn('SQL_DET=VOX', render_rx_sql_block(model))
            self.assertIn('VOX_THRESH=1000', render_rx_sql_block(model))
            self.assertIn('PTT_TYPE=PTY', render_tx_ptt_block(model))

    def test_module_paths_survive_runtime_relocation(self):
        tree = ast.parse((ROOT / 'install/pi3twe-svxlink-ptt').read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'runtime_config')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / 'original'
            original.mkdir()
            config = original / 'svxlink.conf'
            scope = {'Path': Path, 'configparser': configparser,
                     'PTY_LINK': root / 'ptt', 'standby_on': lambda: False, 'revd_interface': lambda: False}
            exec(compile(ast.Module(body=[fn], type_ignores=[]), 'runtime_config', 'exec'), scope)
            for path, expected in [('svxlink.d', str(original / 'svxlink.d')),
                                   ('/etc/custom/modules', '/etc/custom/modules')]:
                config.write_text('[GLOBAL]\nCFG_DIR=' + path + '\n[RepeaterLogic]\n[Tx1]\n')
                output = scope['runtime_config'](config_file=config)
                result = configparser.ConfigParser()
                result.read(output)
                self.assertEqual(result['GLOBAL']['CFG_DIR'], expected)
                self.assertEqual(result['Tx1']['PTT_TYPE'], 'PTY')


class MaintenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app
        cls.module = app
        app.app.config.update(TESTING=True)
        app.app.template_folder = str(ROOT / 'templates')

    def setUp(self):
        self.client = self.module.app.test_client()
        self.auth = patch.object(self.module, 'dashboard_auth_exists', return_value=True)
        self.auth.start()
        self.addCleanup(self.auth.stop)
        with self.client.session_transaction() as session:
            session['authorised'] = True

    def test_both_maintenance_paths(self):
        for path in ['/maintenance', '/maintenance/']:
            self.assertEqual(self.client.get(path).status_code, 200)

    def test_restart_only_restarts_svxlink(self):
        with patch.object(self.module, 'restart_svxlink') as restart, \
             patch.object(self.module, 'restart_services') as restart_all:
            for path in ['/maintenance/restart', '/maintenance/restart/']:
                self.assertEqual(self.client.post(path).status_code, 200)
            self.assertEqual(restart.call_count, 2)
            restart_all.assert_not_called()

    def test_restart_failure_is_visible(self):
        with patch.object(self.module, 'restart_svxlink', side_effect=RuntimeError('test')), \
             patch.object(self.module.app.logger, 'exception'):
            response = self.client.post('/maintenance/restart')
            self.assertEqual(response.status_code, 500)
            self.assertIn(b'Restart Failed', response.data)

    def test_restart_requires_login_and_post(self):
        with self.client.session_transaction() as session:
            session.clear()
        with patch.object(self.module, 'restart_svxlink') as restart:
            self.assertEqual(self.client.post('/maintenance/restart').status_code, 302)
            restart.assert_not_called()
        with self.client.session_transaction() as session:
            session['authorised'] = True
        self.assertEqual(self.client.get('/maintenance/restart').status_code, 405)
