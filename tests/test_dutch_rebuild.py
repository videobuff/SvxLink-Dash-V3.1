"""Rebuilds retain the selected voice and accept the bundled Dutch pack."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from services import build_svxlink
from renderers.svxlink_renderer import get_default_language, render_echolink_module

ROOT = Path(__file__).resolve().parents[1]


class DutchRebuildTests(unittest.TestCase):
    def test_existing_dutch_pack_does_not_need_an_external_repository(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'nl_NL').mkdir()
            with patch.object(build_svxlink, 'SOUND_BASE_DIR', Path(folder)), \
                 patch.object(build_svxlink.subprocess, 'run') as run:
                result = build_svxlink.ensure_language_pack({'language': {'default': 'nl_NL'}})
                self.assertEqual(result, str(Path(folder) / 'nl_NL'))
                run.assert_not_called()

    def test_clean_example_validates_and_renders_dutch(self):
        model = json.loads((ROOT / 'config/node_model.pi3twe.example.json').read_text())
        validation = build_svxlink.validate_build(model)
        self.assertEqual(validation['validation_errors'], [])
        self.assertEqual(validation['platform_errors'], [])
        self.assertEqual(get_default_language(model), 'nl_NL')
        self.assertIn('DEFAULT_LANG=nl_NL', build_svxlink.render_all(model)['svxlink.conf'])
        model['echolink'] = {'enabled': True}
        self.assertIn('DEFAULT_LANG=nl_NL', render_echolink_module(model))
        self.assertNotIn('dashboard_auth', model)

    def test_environment_change_preserves_dutch(self):
        import app
        client = app.app.test_client()
        model = {'language': {'default': 'nl_NL'}}
        with client.session_transaction() as session:
            session['authorised'] = True
        with patch.object(app, 'load_node_model', return_value=model), \
             patch.object(app, 'save_node_model') as save, \
             patch.object(app, 'dashboard_auth_exists', return_value=True):
            response = client.post('/environment', data={'environment': 'british_isles'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(model['language']['default'], 'nl_NL')
        save.assert_called_once()
