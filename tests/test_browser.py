"""Chromium tests use synthetic offers only and do not overwrite production data."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import functools
import http.server
import json
import os
from pathlib import Path
import threading
import unittest
from playwright.sync_api import sync_playwright
from fixtures import PRODUCT, offer, SOURCE
from price_index.market import Source
from price_index.refresh import build

ROOT=Path(__file__).resolve().parents[1]
EMPTY={'schema_version':1,'updated_at':None,'phones':[]}
class QuietHandler(http.server.SimpleHTTPRequestHandler):
    cors_page=''
    def log_message(self,*args):pass
    def do_GET(self):
        if self.path == '/cors-test':
            self.send_response(200)
            self.send_header('Content-Type','text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(self.cors_page.encode())
        else:super().do_GET()

class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(ROOT)))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.playwright=sync_playwright().start()
        kwargs={'headless':True}
        if os.environ.get('CHROMIUM_PATH'):kwargs['executable_path']=os.environ['CHROMIUM_PATH']
        cls.browser=cls.playwright.chromium.launch(**kwargs)
    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.playwright.stop();cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def dataset(self,old=False,single=False):
        now=datetime.now(timezone.utc)-timedelta(hours=7 if old else 0,seconds=2)
        source=Source('Fixture B','owner-b','b.example','https://b.example/permission','LB')
        batch=[(PRODUCT,replace(offer(),observed_at=now))]
        if not single:batch.append((PRODUCT,replace(offer(source,'200'),observed_at=now)))
        return build(EMPTY,batch,now)[0]
    def page(self,width=390,dataset=None,blogger=False):
        page=self.browser.new_page(viewport={'width':width,'height':844})
        self.addCleanup(page.close)
        if dataset is not None:
            page.route('**/data/global-phones.json',lambda route:route.fulfill(json=dataset,headers={'Access-Control-Allow-Origin':'*'}))
        url=f'http://127.0.0.1:{self.server.server_port}/'
        if blogger:
            fragment=(ROOT/'blogger/page.html').read_text().replace('https://leb4tech.github.io/leb4tech-mobile-prices/data/global-phones.json',url+'data/global-phones.json')
            page.route('**/embed-test',lambda route:route.fulfill(content_type='text/html',body='<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><h1 id="blog-title">عنوان المدونة</h1>'+fragment+'</body></html>'))
            url+='embed-test'
        response=page.goto(url);self.assertEqual(response.status,200)
        page.wait_for_function("!document.querySelector('.reload').disabled")
        return page
    def test_responsive_rtl_english_input_and_blogger(self):
        for width in (320,390,1280):
            page=self.page(width,self.dataset(),blogger=True)
            self.assertEqual(page.locator('#leb4tech-index').get_attribute('dir'),'rtl')
            self.assertEqual(page.locator('#phone-input').get_attribute('dir'),'ltr')
            self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
            self.assertEqual(page.locator('article').count(),1)
            self.assertEqual(page.locator('#blog-title').inner_text(),'عنوان المدونة')
    def test_search_brand_and_price_filters(self):
        page=self.page(dataset=self.dataset())
        self.assertIn('$150.00',page.locator('.price').inner_text())
        page.locator('#phone-input').fill('not a model');self.assertEqual(page.locator('article').count(),0)
        page.locator('#phone-input').fill('phone pro');self.assertEqual(page.locator('article').count(),1)
        page.locator('#price-filter').fill('149');self.assertEqual(page.locator('article').count(),0)
        page.locator('#price-filter').fill('150');self.assertEqual(page.locator('article').count(),1)
        page.locator('#brand-filter').select_option('Fixture');self.assertEqual(page.locator('article').count(),1)
    def test_empty_and_single_source_never_invent_average(self):
        page=self.page(dataset=EMPTY)
        self.assertIn('لم تتوفر عروض عالمية موثقة',page.get_by_role('status').inner_text())
        page=self.page(dataset=self.dataset(single=True))
        self.assertIn('لا يتوفر متوسط',page.locator('.price').inner_text())
    def test_stale_warning_and_last_update(self):
        page=self.page(dataset=self.dataset(old=True))
        self.assertIn('قديمة',page.get_by_role('status').inner_text())
        self.assertEqual(page.locator('.badge').inner_text(),'سعر قديم')
        self.assertIn('آخر تحقق',page.locator('time').inner_text())
    def test_cache_survives_network_failure(self):
        page=self.page(dataset=self.dataset())
        page.unroute('**/data/global-phones.json')
        page.route('**/data/global-phones.json',lambda route:route.abort())
        page.reload();page.wait_for_function("!document.querySelector('.reload').disabled")
        self.assertIn('آخر نسخة محفوظة',page.get_by_role('status').inner_text())
        self.assertEqual(page.locator('article').count(),1)
    def test_corrupt_data_rejected(self):
        data=self.dataset();data['phones'][0]['average_usd']=1
        page=self.page(dataset=data)
        self.assertIn('تعذّر تحميل',page.get_by_role('status').inner_text())
        self.assertEqual(page.locator('article').count(),0)
    def test_input_and_source_markup_never_execute(self):
        data=self.dataset();data['phones'][0]['offers'][0]['store']='<img src=x onerror="window.injected=true">'
        page=self.page(dataset=data)
        page.locator('#phone-input').fill('<img src=x onerror="window.injected=true">')
        page.locator('#search-btn').click()
        page.locator('#phone-input').fill('')
        self.assertEqual(page.locator('article img').count(),0)
        self.assertFalse(page.evaluate('Boolean(window.injected)'))
    def test_failed_source_report(self):
        page=self.page(dataset=self.dataset())
        page.route('**/data/status.json',lambda route:route.fulfill(json={'state':'failed','failures':[{'source':'Fixture','error':'AccessDenied'}]}))
        page.locator('.reload').click()
        page.wait_for_function("document.querySelector('.source-status').textContent.includes('تعذّر تحديث')")
        self.assertEqual(page.locator('article').count(),1)

    def test_real_cross_origin_cors(self):
        dataset=self.dataset()
        class CorsHandler(http.server.BaseHTTPRequestHandler):
            allow=True
            def log_message(self,*args):pass
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Type','application/json; charset=utf-8')
                if self.allow:self.send_header('Access-Control-Allow-Origin','*')
                self.end_headers()
                value=dataset if self.path.endswith('phones.json') else {'state':'updated','failures':[]}
                self.wfile.write(json.dumps(value).encode())
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),CorsHandler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            for allowed in (True,False):
                CorsHandler.allow=allowed
                page=self.browser.new_page();self.addCleanup(page.close)
                fragment=(ROOT/'blogger/page.html').read_text().replace('https://leb4tech.github.io/leb4tech-mobile-prices/data/global-phones.json',f'http://127.0.0.1:{server.server_port}/data/global-phones.json')
                QuietHandler.cors_page='<!DOCTYPE html><meta charset="utf-8">'+fragment
                page.goto(f'http://127.0.0.1:{self.server.server_port}/cors-test')
                page.wait_for_function("!document.querySelector('.reload').disabled")
                self.assertEqual(page.locator('article').count(),1 if allowed else 0)
        finally:
            server.shutdown();server.server_close();thread.join()

    def international_dataset(self,single=False,second_market=False):
        from test_international import EMPTY as GLOBAL_EMPTY
        now=datetime.now(timezone.utc)-timedelta(seconds=2)
        a=replace(SOURCE,country='US')
        b=Source('Fixture B','owner-b','b.example','https://b.example/permission','CA' if second_market else 'US')
        batches=[(PRODUCT,replace(offer(a,'100'),observed_at=now))]
        if not single:batches.append((PRODUCT,replace(offer(b,'200'),observed_at=now)))
        return build(GLOBAL_EMPTY,batches,now)[0]

    def test_international_single_store_is_visible_and_filterable(self):
        page=self.page(dataset=self.international_dataset(single=True),blogger=True)
        self.assertIn('$100.00',page.locator('.price').inner_text())
        self.assertIn('سعر متجر واحد',page.locator('article').inner_text())
        self.assertIn('ليس متوسط سوق',page.locator('article').inner_text())
        self.assertIn('الولايات المتحدة',page.locator('article').inner_text())
        page.locator('#price-filter').fill('99')
        self.assertEqual(page.locator('article').count(),0)

    def test_international_market_filter_and_duplicate_models(self):
        page=self.page(dataset=self.international_dataset(second_market=True),blogger=True)
        self.assertEqual(page.locator('article').count(),2)
        page.locator('#market-filter').select_option('CA')
        self.assertEqual(page.locator('article').count(),1)
        self.assertIn('كندا',page.locator('article').inner_text())
        self.assertIn('$200.00',page.locator('.price').inner_text())

    def test_international_offer_country_mismatch_is_rejected(self):
        data=self.international_dataset(single=True)
        data['phones'][0]['offers'][0]['country']='CA'
        page=self.page(dataset=data)
        self.assertEqual(page.locator('article').count(),0)
        self.assertIn('تعذّر تحميل',page.get_by_role('status').inner_text())
