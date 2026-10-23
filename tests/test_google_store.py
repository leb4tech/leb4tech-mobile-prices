"""Synthetic public HTML: never published as real price data."""
import copy
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from price_index.google_store import GoogleStoreAdapter
from price_index.sources import SourceError, AccessDenied, OutOfStock, source_adapter
from price_index.robots import RobotFileParser
from price_index.refresh import refresh
from price_index.dataset import atomic_json

NOW = datetime.now(timezone.utc)

def config():
    c = json.loads(Path('config/sources.json').read_text())['sources'][0]
    c['reviewed_at'] = NOW.isoformat()
    for p in c['products']: p['reviewed_at'] = NOW.isoformat()
    return c

CONFIG_HTML = '''<title>Discover the New Google Pixel 10</title><main><h1>Pixel 10</h1>
<button data-test="storage_selection_panel">128 GB $100</button>
<button data-test="storage_selection_panel">256 GB $200</button>
'''+''.join(f'''<div itemscope itemtype="https://schema.org/AggregateOffer">
<meta itemprop="description" content="Pixel 10 Obsidian {capacity}GB (Unlocked)">
<meta itemprop="lowPrice" content="{price}"><meta itemprop="priceCurrency" content="USD">
<link itemprop="availability" href="https://schema.org/InStock"></div>'''
for capacity, price in ((128,100),(256,200)))+'</main>'
SPECS_HTML = '''<title>Google Pixel 10 Specs &amp; Hardware</title><main>
Memory and storage 128 GB / 12 GB RAM 256 GB / 12 GB RAM
SIMs Dual eSIM Warranty 1 year Processor Google Tensor G5</main>'''

class Fake:
    interval = 5
    def __init__(self, html=CONFIG_HTML, specs=SPECS_HTML, robots='User-agent: *\nAllow: /'):
        self.html, self.specs, self.robots = html, specs, robots
        self.calls = []
    def get(self,url,host):
        self.calls.append(url)
        if url.endswith('robots.txt'): return self.robots
        return self.specs if '_specs?' in url else self.html

class GoogleStoreTests(unittest.TestCase):
    def test_two_exact_variants_share_three_public_requests(self):
        fake = Fake()
        values = GoogleStoreAdapter(config(),NOW,fake).fetch()
        self.assertEqual([o.price for p,o in values],[100,200])
        self.assertEqual(len(fake.calls),3)
        self.assertTrue(all(o.currency=='USD' and o.available for p,o in values))
        self.assertIsInstance(source_adapter(config(),NOW),GoogleStoreAdapter)

    def test_variant_price_currency_and_stock_fail_closed(self):
        for before,after in [('USD','CAD'),('InStock','PreOrder'),('100','NaN'),
                             ('Obsidian 128GB','Indigo 128GB'),('(Unlocked)','(Verizon)'),
                             ('128 GB $100','128 GB $10/month'),('128 GB $100','128 GB $101'),
                             ('<h1>Pixel 10</h1>','<h1>Pixel 10 Pro</h1>'),
                             ('Discover the New Google','Refurbished Google')]:
            with self.subTest(after=after), self.assertRaises(SourceError):
                GoogleStoreAdapter(config(),NOW,Fake(CONFIG_HTML.replace(before,after))).fetch()
        with self.assertRaises(OutOfStock):
            GoogleStoreAdapter(config(),NOW,Fake(CONFIG_HTML.replace('InStock','OutOfStock'))).fetch()

    def test_no_ambiguous_aggregate_or_duplicate_variant(self):
        for html in (CONFIG_HTML.replace('content="100"','content="100"><meta itemprop="highPrice" content="200"'),
                     CONFIG_HTML.replace('</main>',CONFIG_HTML+'</main>')):
            with self.assertRaises(SourceError):GoogleStoreAdapter(config(),NOW,Fake(html)).fetch()

    def test_specs_must_prove_all_variant_fields(self):
        for before,after in [('12 GB RAM','8 GB RAM'),('Dual eSIM','nano SIM'),
                             ('Warranty 1 year','Warranty 2 years'),('Google Tensor G5','Other'),
                             ('Google Pixel 10 Specs','Google Pixel 9 Specs')]:
            with self.subTest(after=after),self.assertRaises(SourceError):
                GoogleStoreAdapter(config(),NOW,Fake(specs=SPECS_HTML.replace(before,after))).fetch()
        for field,value in [('condition','refurbished'),('image',{'url':'https://example.com/a'}),
                            ('specs',['undocumented']),('ram_gb',16)]:
            c=config();c['products'][0][field]=value
            with self.assertRaises(SourceError):GoogleStoreAdapter(c,NOW,Fake()).fetch()

    def test_reviews_and_urls_rejected_before_network(self):
        for field,value in [('enabled',False),('permission_confirmed',False),
                            ('reviewed_at',(NOW-timedelta(days=30)).isoformat())]:
            c=config();c[field]=value;fake=Fake()
            with self.assertRaises(AccessDenied):GoogleStoreAdapter(c,NOW,fake).fetch()
            self.assertEqual(fake.calls,[])
        for field,value in [('url','https://store.google.com/us/prices'),
                            ('spec_url','https://store.google.com/cart'),
                            ('evidence_url','https://example.com')]:
            c=config();c['products'][0][field]=value;fake=Fake()
            with self.assertRaises(AccessDenied):GoogleStoreAdapter(c,NOW,fake).fetch()
            self.assertEqual(fake.calls,[])

    def test_robots_wildcard_and_longest_allow(self):
        policy='User-agent: *\nDisallow: /us/\nAllow: /us/config/\nAllow: /us/product/\nDisallow: /*/prices\nDisallow: /cart\n'
        r=RobotFileParser();r.parse(policy.splitlines())
        self.assertTrue(r.can_fetch('Leb4TechPriceIndex/1.0','https://store.google.com/us/config/pixel_10'))
        self.assertFalse(r.can_fetch('Leb4TechPriceIndex/1.0','https://store.google.com/us/prices'))
        self.assertFalse(r.can_fetch('Leb4TechPriceIndex/1.0','https://store.google.com/cart'))
        fake=Fake(robots='User-agent: *\nDisallow: /')
        with self.assertRaises(AccessDenied):GoogleStoreAdapter(config(),NOW,fake).fetch()
        self.assertEqual(len(fake.calls),1)

    def test_failed_source_keeps_successful_snapshot_and_reports_out_of_stock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); data=root/'data.json'; conf=root/'config.json'; status=root/'status.json'
            atomic_json(data,dict(schema_version=2,pricing_basis='international_retail',currency='USD',updated_at=None,phones=[]))
            atomic_json(conf,{'sources':[config()]})
            good=lambda c,now:GoogleStoreAdapter(c,now,Fake())
            self.assertEqual(refresh(conf,data,status,good,NOW)['updated_variants'],2)
            original=data.read_bytes()
            bad=lambda c,now:GoogleStoreAdapter(c,now,Fake(CONFIG_HTML.replace('InStock','OutOfStock')))
            report=refresh(conf,data,status,bad,NOW+timedelta(minutes=1))
            self.assertEqual(report['state'],'failed')
            self.assertEqual(report['failures'][0]['error'],'OutOfStock')
            self.assertEqual(data.read_bytes(),original)
