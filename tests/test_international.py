"""Synthetic retail quotes: not production prices or launch-price examples."""
import copy
from dataclasses import replace
from decimal import Decimal
import unittest
from fixtures import NOW, PRODUCT, offer, SOURCE
from price_index.dataset import validate_dataset, variant_id
from price_index.market import Source, market_average
from price_index.refresh import build

EMPTY={'schema_version':2,'pricing_basis':'international_retail','currency':'USD','updated_at':None,'phones':[]}
A=replace(SOURCE,country='US')
B=Source('Fixture B','owner-b','b.example','https://b.example/permission','US')

class InternationalTests(unittest.TestCase):
    def test_same_market_current_retail_average(self):
        data,count=build(EMPTY,[(PRODUCT,offer(A,'100')),(PRODUCT,offer(B,'200'))],NOW)
        phone=data['phones'][0]
        self.assertEqual(count,1)
        self.assertEqual(phone['average_usd'],150)
        self.assertEqual(phone['market'],'US')
        self.assertTrue(all(o['country']=='US' for o in phone['offers']))
        validate_dataset(data,NOW)

    def test_single_store_quote_available_but_never_called_an_average(self):
        data,_=build(EMPTY,[(PRODUCT,offer(A,'100'))],NOW)
        phone=data['phones'][0]
        self.assertIsNone(phone['average_usd'])
        self.assertEqual(phone['status'],'insufficient_data')
        self.assertEqual(phone['offers'][0]['price_usd'],100)

    def test_different_countries_never_merge(self):
        foreign=replace(B,country='CA')
        data,_=build(EMPTY,[(PRODUCT,offer(A)),(PRODUCT,offer(foreign))],NOW)
        self.assertEqual(len(data['phones']),2)
        self.assertEqual(len({p['id'] for p in data['phones']}),2)
        self.assertTrue(all(p['average_usd'] is None for p in data['phones']))
        with self.assertRaises(ValueError):market_average([offer(A),offer(foreign)],NOW)

    def test_market_identity_and_evidence_must_agree(self):
        data,_=build(EMPTY,[(PRODUCT,offer(A))],NOW)
        data['phones'][0]['offers'][0]['country']='CA'
        with self.assertRaises(ValueError):validate_dataset(data,NOW)

    def test_no_exchange_rate_or_launch_price_fallback(self):
        from jsonschema import ValidationError
        data,_=build(EMPTY,[(PRODUCT,offer(A))],NOW)
        bad=copy.deepcopy(data);bad['currency']='EUR'
        with self.assertRaises(ValidationError):validate_dataset(bad,NOW)
        bad=copy.deepcopy(data);bad['pricing_basis']='official_us_launch'
        with self.assertRaises(ValidationError):validate_dataset(bad,NOW)
        with self.assertRaises(ValueError):build(EMPTY,[(PRODUCT,replace(offer(A),currency='EUR'))],NOW)

    def test_legacy_market_cannot_accept_international_data(self):
        with self.assertRaises(ValueError):
            build({'schema_version':1,'updated_at':None,'phones':[]},[(PRODUCT,offer(A))],NOW)

    def test_current_single_offer_replaces_average_without_retaining_old_mean(self):
        from datetime import timedelta
        previous,_=build(EMPTY,[(PRODUCT,offer(A,'100')),(PRODUCT,offer(B,'200'))],NOW)
        later=NOW+timedelta(hours=7)
        data,count=build(previous,[(PRODUCT,replace(offer(A,'120'),observed_at=later))],later)
        self.assertEqual(count,1)
        phone=data['phones'][0]
        self.assertIsNone(phone['average_usd'])
        self.assertEqual(phone['offers'][0]['price_usd'],120)
        self.assertEqual(phone['updated_at'],later.isoformat())

    def test_failed_or_empty_refresh_keeps_global_prices_and_success_time(self):
        import json,tempfile
        from pathlib import Path
        from price_index.dataset import atomic_json
        from price_index.refresh import refresh
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data_path=root/'global.json';config=root/'sources.json';report=root/'status.json'
            previous,_=build(EMPTY,[(PRODUCT,offer(A))],NOW)
            atomic_json(data_path,previous);atomic_json(config,{'sources':[]})
            before=data_path.read_bytes()
            result=refresh(config,data_path,report,now=NOW)
            self.assertEqual(result['state'],'not_configured')
            self.assertEqual(data_path.read_bytes(),before)
