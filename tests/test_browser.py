"""Browser checks for the simplified price list; synthetic data only."""
import copy
import functools
import http.server
import json
import os
from pathlib import Path
import threading
import unittest
from playwright.sync_api import sync_playwright
from test_image_list import IMAGE

ROOT=Path(__file__).resolve().parents[1]
PUBLIC='https://leb4tech.github.io/leb4tech-mobile-prices/data/image-prices.json'

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    cors_page=''
    def log_message(self,*args):pass
    def do_GET(self):
        if self.path=='/cors-test':
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers()
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
    def page(self,width=390,value=None,blogger=False):
        page=self.browser.new_page(viewport={'width':width,'height':844});self.addCleanup(page.close)
        page.route('**/data/image-prices.json',lambda route:route.fulfill(json=IMAGE if value is None else value,headers={'Access-Control-Allow-Origin':'*'}))
        url=f'http://127.0.0.1:{self.server.server_port}/'
        if blogger:
            fragment=(ROOT/'blogger/page.html').read_text().replace(PUBLIC,url+'data/image-prices.json')
            page.route('**/embed-test',lambda route:route.fulfill(content_type='text/html',body='<!DOCTYPE html><meta charset="utf-8"><h1 id="blog-title">عنوان المدونة</h1>'+fragment))
            url+='embed-test'
        page.goto(url);page.wait_for_function("document.querySelector('.image-prices').getAttribute('aria-busy') === 'false'")
        return page

    def test_simple_responsive_blogger_without_google_or_image_controls(self):
        for width in (320,390,1280):
            page=self.page(width,blogger=True)
            self.assertEqual(page.locator('#leb4tech-index').get_attribute('dir'),'rtl')
            self.assertEqual(page.locator('#image-search').get_attribute('dir'),'ltr')
            self.assertEqual(page.locator('tbody tr').count(),1)
            self.assertEqual(page.locator('#blog-title').inner_text(),'عنوان المدونة')
            self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
            text=page.locator('#leb4tech-index').inner_text()
            for word in ['Google','صورة','مصورة','المصورة','إعادة تحميل','متوسط سوق']:
                self.assertNotIn(word,text)
            self.assertEqual(page.locator('button').count(),0)
            self.assertEqual(page.locator('script[src="assets/app.js"]').count(),0)

    def test_search_brand_and_price_filters(self):
        page=self.page()
        self.assertIn('$123.00',page.locator('tbody').inner_text())
        page.locator('#image-search').fill('missing');self.assertEqual(page.locator('tbody tr').count(),0)
        page.locator('#image-search').fill('pm mix');self.assertEqual(page.locator('tbody tr').count(),1)
        page.locator('#image-search').fill('Example');self.assertEqual(page.locator('tbody tr').count(),1)
        page.locator('#image-search').fill('');page.locator('#image-brand').select_option('Example')
        page.locator('#image-price').fill('122');self.assertEqual(page.locator('tbody tr').count(),0)
        page.locator('#image-price').fill('123');self.assertEqual(page.locator('tbody tr').count(),1)

    def test_original_date_and_stale_warning(self):
        page=self.page()
        self.assertIn('2020-01-02',page.locator('.image-meta').inner_text())
        self.assertIn('يوم سابق',page.get_by_role('status').inner_text())
        self.assertEqual(page.get_by_role('link',name='المصدر',exact=True).get_attribute('href'),IMAGE['source_url'])

    def test_cache_keeps_original_date_on_network_failure(self):
        page=self.page();page.route('**/data/image-prices.json',lambda route:route.abort())
        page.reload();page.wait_for_function("document.querySelector('.image-notice').textContent.includes('محفوظة')")
        self.assertEqual(page.locator('tbody tr').count(),1)
        self.assertIn('2020-01-02',page.locator('.image-meta').inner_text())

    def test_invalid_data_is_never_displayed(self):
        for field,value in [('currency','LBP'),('source_url','javascript:alert(1)'),('list_date','2999-01-01')]:
            data=copy.deepcopy(IMAGE);data[field]=value
            page=self.page(value=data)
            self.assertEqual(page.locator('tbody tr').count(),0)
            self.assertIn('تعذر تحميل',page.get_by_role('status').inner_text())
        data=copy.deepcopy(IMAGE);data['listings'].append(copy.deepcopy(data['listings'][0]))
        self.assertEqual(self.page(value=data).locator('tbody tr').count(),0)

    def test_names_are_literal_and_do_not_execute_markup(self):
        data=copy.deepcopy(IMAGE);data['listings'][0]['listing_text']='<img src=x onerror="window.injected=true"> PM Mix'
        page=self.page(value=data,blogger=True)
        self.assertIn('<img src=x',page.locator('tbody').inner_text())
        self.assertEqual(page.locator('img').count(),0)
        self.assertFalse(page.evaluate('Boolean(window.injected)'))

    def test_only_price_list_is_fetched(self):
        page=self.browser.new_page();self.addCleanup(page.close);requests=[]
        page.on('request',lambda req:requests.append(req.url))
        page.goto(f'http://127.0.0.1:{self.server.server_port}/')
        page.wait_for_function("document.querySelector('.image-prices').getAttribute('aria-busy') === 'false'")
        self.assertTrue(any(u.endswith('/data/image-prices.json') for u in requests))
        self.assertFalse(any('global-phones' in u or 'status.json' in u or 'store.google' in u for u in requests))

    def test_real_cross_origin_cors(self):
        class CorsHandler(http.server.BaseHTTPRequestHandler):
            allow=True
            def log_message(self,*args):pass
            def do_GET(self):
                self.send_response(200);self.send_header('Content-Type','application/json')
                if self.allow:self.send_header('Access-Control-Allow-Origin','*')
                self.end_headers();self.wfile.write(json.dumps(IMAGE).encode())
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),CorsHandler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            for allowed in (True,False):
                CorsHandler.allow=allowed;page=self.browser.new_page();self.addCleanup(page.close)
                fragment=(ROOT/'blogger/page.html').read_text().replace(PUBLIC,f'http://127.0.0.1:{server.server_port}/data/image-prices.json')
                QuietHandler.cors_page='<!DOCTYPE html><meta charset="utf-8">'+fragment
                page.goto(f'http://127.0.0.1:{self.server.server_port}/cors-test')
                page.wait_for_function("document.querySelector('.image-prices').getAttribute('aria-busy') === 'false'")
                self.assertEqual(page.locator('tbody tr').count(),1 if allowed else 0)
        finally:server.shutdown();server.server_close();thread.join()
