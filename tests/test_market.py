import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from price_index.market import Source, Offer, validate, market_average, collect

NOW = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)
# Entirely synthetic fixtures; these are not real stores or deployable prices.
A = Source('Fixture A', 'owner-a', 'a.example', 'fixture permission', 'LB')
B = Source('Fixture B', 'owner-b', 'b.example', 'fixture permission', 'LB')
BASE = Offer(A, 'https://a.example/product', 'Fixture Phone', 256,
             'dual physical SIM', 'manufacturer 1 year', 'new', 'USD', True,
             Decimal('100.00'), NOW)
SECOND = replace(BASE, source=B, url='https://b.example/product', price=Decimal('201.01'))

class MarketTests(unittest.TestCase):
    def test_arithmetic_mean_and_rounding(self):
        self.assertEqual(market_average([BASE, SECOND], NOW), Decimal('150.51'))

    def test_no_quorum(self):
        for offers in ([], [BASE]):
            with self.assertRaises(ValueError):
                market_average(offers, NOW)

    def test_related_owners_and_duplicates(self):
        for source in (A, replace(B, independent_owner=A.independent_owner),
                       replace(B, host=A.host), replace(B, store=A.store)):
            offer = replace(SECOND, source=source, url=f'https://{source.host}/product')
            with self.assertRaises(ValueError):
                market_average([BASE, offer], NOW)

    def test_variants_are_never_merged(self):
        for field, value in [('model', 'Fixture Phone Pro'), ('storage_gb', 128),
                             ('sim', 'eSIM'), ('warranty', 'store 1 year'),
                             ('condition', 'used')]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                market_average([BASE, replace(SECOND, **{field: value})], NOW)

    def test_rejects_missing_or_invalid_evidence(self):
        cases = dict(currency='LBP', available=False, model='', sim='', warranty='',
                     condition='unknown', storage_gb=True)
        for field, value in cases.items():
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate(replace(BASE, **{field: value}), NOW)
        for price in (Decimal('NaN'), Decimal('Infinity'), Decimal('0'), Decimal('-1'), 100.0):
            with self.subTest(price=price), self.assertRaises(ValueError):
                validate(replace(BASE, price=price), NOW)

    def test_freshness(self):
        for timestamp in (NOW-timedelta(hours=6), NOW+timedelta(seconds=1), NOW.replace(tzinfo=None)):
            with self.assertRaises(ValueError):
                validate(replace(BASE, observed_at=timestamp), NOW)
        validate(replace(BASE, observed_at=NOW-timedelta(hours=5, minutes=59)), NOW)

    def test_source_validation(self):
        for source in (replace(A, country='XX'), replace(A, permission_reference='')):
            with self.assertRaises(ValueError):
                validate(replace(BASE, source=source), NOW)
        for url in ('http://a.example/p', 'https://other.example/p', 'https://u:p@a.example/p'):
            with self.assertRaises(ValueError):
                validate(replace(BASE, url=url), NOW)

    def test_failed_sources_are_reported_without_secrets(self):
        class Broken:
            source = A
            def fetch(self):
                raise RuntimeError('secret-key-must-not-be-logged')
        class Working:
            source = B
            def fetch(self):
                return [SECOND]
        with self.assertLogs('price_index.market', level='INFO') as logs:
            offers, failures = collect([Broken(), Working()], NOW)
        self.assertEqual(offers, [SECOND])
        self.assertEqual(failures, [{'source': 'Fixture A', 'error': 'RuntimeError'}])
        self.assertNotIn('secret-key', str(logs.output))
        with self.assertRaises(ValueError):
            market_average(offers, NOW)

    def test_source_batch_is_atomic(self):
        class Invalid:
            source = A
            def fetch(self):
                return [BASE, replace(BASE, currency='EUR')]
        with self.assertLogs('price_index.market', level='WARNING'):
            offers, failures = collect([Invalid()], NOW)
        self.assertEqual(offers, [])
        self.assertEqual(len(failures), 1)

if __name__ == '__main__':
    unittest.main()
