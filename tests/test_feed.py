"""Legacy command must delegate to the same permission/schema checks as refresh."""
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import build_feed


class FeedTests(unittest.TestCase):
    def test_legacy_command_uses_reviewed_config_and_canonical_schema(self):
        expected = {'state': 'not_configured', 'updated_variants': 0}
        with patch('scripts.build_feed.refresh', return_value=expected) as refresh:
            self.assertEqual(build_feed.build(), expected)
        kwargs = refresh.call_args.kwargs
        self.assertEqual(kwargs['config_path'], build_feed.ROOT / 'config/sources.json')
        self.assertEqual(kwargs['data_path'], build_feed.ROOT / 'data/phones.json')
        self.assertEqual(kwargs['report_path'], build_feed.ROOT / 'data/status.json')
        self.assertTrue(all(Path(path).is_absolute() for path in kwargs.values()))

    def test_review_candidates_are_disabled(self):
        import json
        stores = json.loads((build_feed.ROOT / 'config/stores.json').read_text())
        self.assertTrue(all(store['enabled'] is False for store in stores))


if __name__ == '__main__':
    unittest.main()
