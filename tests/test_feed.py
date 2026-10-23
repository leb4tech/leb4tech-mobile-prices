import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from build_feed import make_identity

class FeedTests(unittest.TestCase):
    def test_model_storage(self):
        x=make_identity('Samsung Galaxy S26 Ultra','12GB/256GB')
        self.assertEqual(x['storage'],'256GB')
        self.assertEqual(x['ram'],'12GB')
    def test_no_ambiguous_capacity(self):
        self.assertIsNone(make_identity('Apple iPhone 17 Pro Max','Default Title'))
    def test_no_bundles(self):
        self.assertIsNone(make_identity('Samsung Galaxy A27 + Free Watch 8/256GB','Default Title'))
    def test_used_excluded(self):
        self.assertIsNone(make_identity('Pre-Owned Apple iPhone 16 128GB','Default Title'))
    def test_sim_separate(self):
        a=make_identity('Apple iPhone 17 Pro 256GB','eSIM')
        b=make_identity('Apple iPhone 17 Pro 256GB','Dual SIM')
        self.assertNotEqual(a['key'],b['key'])
if __name__=='__main__':unittest.main()
