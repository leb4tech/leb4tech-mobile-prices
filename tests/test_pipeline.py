import copy
from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fixtures import NOW, PRODUCT, SOURCE, offer, jsonld
from price_index.dataset import validate_dataset, atomic_json
from price_index.market import Source
from price_index.refresh import build, refresh
from price_index.sources import parse_product, SourceError, ProductPageAdapter, AccessDenied, Transport, NoRedirect

EMPTY={'schema_version':1,'updated_at':None,'phones':[]}
B=Source('Fixture B','owner-b','b.example','https://b.example/permission','LB')

def batch():return [(PRODUCT,offer()),(PRODUCT,offer(B,'200'))]

class PipelineTests(unittest.TestCase):
    def test_empty_and_two_store_dataset(self):
        validate_dataset(EMPTY,NOW)
        data,count=build(EMPTY,batch(),NOW)
        self.assertEqual(count,1)
        self.assertEqual(data['phones'][0]['average_usd'],150)
        self.assertEqual(data['phones'][0]['ram_gb'],8)
        validate_dataset(data,NOW+timedelta(days=1)) # old records remain honest and render stale

    def test_unknown_ram_never_invented(self):
        product=dict(PRODUCT,ram_gb=None)
        data,_=build(EMPTY,[(product,offer())],NOW)
        self.assertIsNone(data['phones'][0]['ram_gb'])
        self.assertIsNone(data['phones'][0]['average_usd'])
        self.assertEqual(data['phones'][0]['status'],'insufficient_data')

    def test_variant_storage_ram_and_sim_not_merged(self):
        for field,value in [('storage_gb',128),('ram_gb',12),('sim','eSIM'),('warranty','ضمان مختلف')]:
            product=dict(PRODUCT,**{field:value})
            # Offers are reconstructed as an adapter would do for the reviewed variant.
            second=replace(offer(B),**{field:value}) if field!='ram_gb' else offer(B)
            data,_=build(EMPTY,[(PRODUCT,offer()),(product,second)],NOW)
            self.assertEqual(len(data['phones']),2)
            self.assertTrue(all(p['average_usd'] is None for p in data['phones']))

    def test_insufficient_update_preserves_last_good_timestamp(self):
        previous,_=build(EMPTY,batch(),NOW)
        next_time=NOW+timedelta(hours=7)
        data,count=build(previous,[(PRODUCT,replace(offer(),observed_at=next_time))],next_time)
        self.assertEqual(data,previous)
        self.assertEqual(count,0)

    def test_duplicate_or_incorrect_mean_rejected(self):
        data,_=build(EMPTY,batch(),NOW)
        bad=copy.deepcopy(data);bad['phones'][0]['average_usd']=1
        with self.assertRaises(ValueError):validate_dataset(bad,NOW)
        bad=copy.deepcopy(data);bad['phones'].append(bad['phones'][0])
        with self.assertRaises(ValueError):validate_dataset(bad,NOW)
        with self.assertRaises(ValueError):build(EMPTY,[(PRODUCT,offer()),(PRODUCT,offer())],NOW)

    def test_jsonld_requires_explicit_price_stock_currency_condition(self):
        value=parse_product(jsonld(),PRODUCT,SOURCE,NOW)
        self.assertEqual(value.price,100)
        for changes in ({'priceCurrency':'LBP'},{'availability':None},{'itemCondition':None},{'price':None},{'price':'NaN'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                parse_product(jsonld(**changes),PRODUCT,SOURCE,NOW)
        with self.assertRaises(SourceError):
            parse_product(jsonld(),dict(PRODUCT,sku='different'),SOURCE,NOW)
        with self.assertRaises(SourceError):
            parse_product(jsonld()+jsonld(),PRODUCT,SOURCE,NOW)

    def config(self):
        return {'enabled':True,'permission_confirmed':True,'permission_url':SOURCE.permission_reference,
                'country':'LB','store':SOURCE.store,'owner':SOURCE.independent_owner,'host':SOURCE.host,
                'reviewed_at':NOW.isoformat(),'user_agent':'FixtureBot/1.0','min_interval_seconds':5,'products':[PRODUCT]}

    def test_robots_denial_stops_before_product_request(self):
        class Fake:
            interval=5
            calls=[]
            def get(self,url,host):
                self.calls.append(url)
                return 'User-agent: *\nDisallow: /'
        fake=Fake()
        with self.assertRaises(AccessDenied):ProductPageAdapter(self.config(),NOW,fake).fetch()
        self.assertEqual(len(fake.calls),1)

    def test_permission_and_review_expiry_are_enforced(self):
        for changes in ({'permission_confirmed':False},{'enabled':False},{'reviewed_at':(NOW-timedelta(days=31)).isoformat()}):
            with self.assertRaises(AccessDenied):
                ProductPageAdapter(dict(self.config(),**changes),NOW).fetch()

    def test_redirect_and_bad_url_never_fetch(self):
        with self.assertRaises(AccessDenied):NoRedirect().redirect_request(None,None,None,None,None,None)
        for url in ('http://a.example/p','https://other.example/p','https://u:p@a.example/p'):
            with self.assertRaises(AccessDenied):Transport('FixtureBot').get(url,'a.example')

    def test_no_sources_or_failed_source_preserve_data_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);data=path/'phones.json';config=path/'sources.json';report=path/'status.json'
            original,_=build(EMPTY,batch(),NOW)
            atomic_json(data,original)
            before=data.read_bytes()
            for sources in ([],[self.config()]):
                atomic_json(config,{'sources':sources})
                class Broken:
                    def __init__(self,*args,**kwargs):pass
                    def fetch(self):raise RuntimeError('do not log secret')
                result=refresh(config,data,report,Broken,NOW)
                self.assertEqual(data.read_bytes(),before)
                self.assertEqual(result['updated_variants'],0)
                self.assertEqual(result['state'],'failed' if sources else 'not_configured')
                self.assertNotIn('secret',report.read_text())

    def test_atomic_failure_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'phones.json';atomic_json(path,EMPTY)
            before=path.read_bytes()
            with patch('price_index.dataset.os.replace',side_effect=OSError('disk')):
                with self.assertRaises(OSError):atomic_json(path,{'new':'value'})
            self.assertEqual(path.read_bytes(),before)

    def test_rate_limit_has_no_retry(self):
        import urllib.error
        transport=Transport('FixtureBot/1.0')
        class Limited:
            calls=0
            def open(self,*args,**kwargs):
                self.calls+=1
                raise urllib.error.HTTPError('https://a.example/p',429,'limited',{'Retry-After':'86400'},None)
        limited=Limited();transport.opener=limited
        from price_index.sources import RateLimited
        with self.assertRaises(RateLimited):transport.get('https://a.example/p','a.example')
        self.assertEqual(limited.calls,1)

    def test_one_failed_source_prevents_all_price_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);data=path/'phones.json';config=path/'sources.json';report=path/'status.json'
            atomic_json(data,EMPTY);before=data.read_bytes()
            first=self.config();second=dict(first,store='Fixture B',owner='owner-b',host='b.example',permission_url='https://b.example/permission')
            atomic_json(config,{'sources':[first,second]})
            class Mixed:
                def __init__(self,c,now):self.c=c
                def fetch(self):
                    if self.c['store']=='Fixture B':raise RuntimeError('failure')
                    return [(PRODUCT,offer())]
            result=refresh(config,data,report,Mixed,NOW)
            self.assertEqual(result['state'],'failed')
            self.assertEqual(data.read_bytes(),before)

    def test_invalid_single_source_offer_rejected(self):
        for changed in (replace(offer(),currency='LBP'),replace(offer(),available=False),replace(offer(),model='Other')):
            with self.assertRaises(ValueError):build(EMPTY,[(PRODUCT,changed)],NOW)
