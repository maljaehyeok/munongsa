"""Offline checkout checks: no credentials, corpus, service control or API calls."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import stage_host_release as release
import render_units

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads((ROOT/'deploy/chatbot/source-manifest.json').read_text(encoding='utf-8'))
PINNED = ('assets/amount-display.js','assets/ux-first.css','assets/personalization.js',
          'assets/notice-review.js','assets/support-details.js','scripts/rag_nlu.py',
          'scripts/rag_catalogue.py','scripts/support_notice_review.py')

class CheckoutTests(unittest.TestCase):
    def test_eight_reviewed_hashes_and_attributes(self):
        attrs=(ROOT/'.gitattributes').read_text().splitlines()
        for name in PINNED:
            with self.subTest(name=name):
                self.assertIn(name+' -text',attrs)
                self.assertEqual(release.digest(ROOT/name),(MANIFEST['web']|MANIFEST['runtime'])[name])

    def test_all_runtime_sources_are_byte_exact(self):
        for name,digest in MANIFEST['runtime'].items():
            with self.subTest(name=name):
                self.assertEqual(release.digest(release.source_path(name)),digest)

    def test_notice_review_is_a_source_module_not_entrypoint(self):
        self.assertEqual(release.source_path('scripts/support_notice_review.py'),ROOT/'scripts/support_notice_review.py')
        self.assertEqual(release.source_path('scripts/chat_wsgi.py'),ROOT/'deploy/chatbot/chat_wsgi.py')

    def test_path_escape_rejected(self):
        for value in ('../secrets','/etc/passwd','scripts/../secret','scripts/nested/file.py'):
            with self.subTest(path=value),self.assertRaises(ValueError):release.source_path(value)

    def test_missing_private_corpus_creates_no_release(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'output'
            with self.assertRaisesRegex(ValueError,'private corpus unavailable'):
                release.stage(Path(folder)/'absent',output)
            self.assertFalse(output.exists())

    def test_tampered_runtime_creates_no_release(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);(base/'scripts').mkdir();(base/'corpus').mkdir()
            (base/'scripts/rag_search.py').write_bytes(b'synthetic tampered source')
            with patch.object(release,'ROOT',base),self.assertRaisesRegex(ValueError,'runtime differs'):
                release.stage(base/'corpus',base.parent/(base.name+'-unused-output'))
            self.assertFalse((base.parent/(base.name+'-unused-output')).exists())

    def test_candidate_units_preserve_limits(self):
        values=dict(RELEASE_DIR='/opt/example-release',VENV_DIR='/opt/example-venv',
                    SERVICE_USER='example_chat',BRIDGE_GATEWAY='172.18.0.1',
                    NGINX_PEER='172.18.0.2',BRIDGE_INTERFACE='docker0')
        units=render_units.render(values)
        service=units['munongsa-chat-api.service']
        self.assertIn('MemoryMax=128M',service)
        self.assertIn('MemorySwapMax=0',service)
        self.assertIn('PrivateNetwork=yes',service)

if __name__=='__main__':unittest.main()
