#!/usr/bin/env python3
"""Build a cautious, attributed Lebanon phone-price feed from public Shopify catalogs.
No bypassing blocks, no credentials, no scraping hidden endpoints.
"""
import datetime as dt
import json
import os
import re
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
UA = 'Leb4TechPriceIndex/1.0 (public catalog; contact: https://www.leb4tech.com/)'
BRANDS = ('Apple','Samsung','Xiaomi','Redmi','Poco','Honor','Infinix','Tecno','Oppo','Realme','OnePlus','Google','Huawei','Nokia','Motorola','Nothing','Vivo','RedMagic','ZTE','Itel')
BLOCK = re.compile(r'(?i)\b(used|pre[- ]?owned|refurbished|renewed|second hand|open box|watch|tablet|ipad|macbook|laptop|buds|case|cover|charger|screen protector|bundle|free|with|\+)\b|\+|\bTV\b')
PHONE = re.compile(r'(?i)(iphone|galaxy|redmi|poco|xiaomi|infinix|tecno|honor|oppo|realme|oneplus|pixel|huawei|nova|mate |motorola|moto |nothing phone|redmagic|nubia|zte|itel|nokia)')
STORAGE_RE = re.compile(r'(?i)(?<!\d)(64|128|256|512|1024|2048)\s*(?:GB|G|TB)\b')
PAIR_RE = re.compile(r'(?i)\b(\d{1,2})\s*(?:GB|G)?\s*[/+]\s*(64|128|256|512|1024)\s*(?:GB|G)?\b')
SIM_RE = re.compile(r'(?i)\b(e\s*-?sim|sim\s*\+\s*esim|dual\s*sim)\b')
RAM_RE = re.compile(r'(?i)\b(4|6|8|12|16|24)\s*GB\s*RAM\b')
RESTRICT_VARIANT = re.compile(r'(?i)(used|pre[- ]?owned|refurbished|renewed|open box|without warranty|damaged)')


def clean(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def make_identity(title, variant_title):
    title = clean(title)
    variant_title = clean(variant_title)
    if not PHONE.search(title) or BLOCK.search(title) or BLOCK.search(variant_title) or RESTRICT_VARIANT.search(variant_title):
        return None
    # Storage must be explicit: prevents accidental mixing of 128GB and 256GB variants.
    combined = title + ' ' + ('' if variant_title.lower() == 'default title' else variant_title)
    pairs = PAIR_RE.findall(combined)
    storage = None
    ram = None
    if pairs:
        ram, storage = pairs[-1]
    else:
        tokens = STORAGE_RE.findall(combined)
        if tokens:
            storage = tokens[-1]
    explicit_ram = RAM_RE.search(combined)
    if explicit_ram:
        ram = explicit_ram.group(1)
    if not storage:
        return None
    if storage in ('1024','2048'):
        storage = str(int(storage) // 1024) + 'TB'
    else:
        storage = storage + 'GB'
    brand = next((b for b in BRANDS if re.search(r'(?i)\b' + re.escape(b) + r'\b', title)), None)
    if title.lower().startswith('iphone'):
        brand = 'Apple'
    if title.lower().startswith('galaxy'):
        brand = 'Samsung'
    if not brand:
        return None
    model = title
    model = PAIR_RE.sub(' ', model)
    model = re.sub(r'(?i)\b(?:4|6|8|12|16|24)\s*GB\s*RAM\b', ' ', model)
    model = STORAGE_RE.sub(' ', model)
    model = re.sub(r'(?i)\b(ABM|2 years warranty|warranty|official|international|middle east|version|global|new|sealed|mobile|mobiles)\b', ' ', model)
    model = SIM_RE.sub(' ', model)
    model = re.sub(r'\([^)]*\)', ' ', model)
    model = clean(re.sub(r'[^\w\s+\-]', ' ', model)).strip(' -+')
    # Avoid ambiguous generic titles and models with long merchandising text.
    if len(model) < 5 or len(model) > 75:
        return None
    sim = SIM_RE.search(combined)
    sim_type = re.sub(r'\s+', '', sim.group(1).lower()) if sim else 'unspecified'
    # Only compare like-for-like explicit SIM configurations.
    key = re.sub(r'[^a-z0-9]+','', model.casefold()) + ':' + storage.casefold() + ':' + sim_type
    display = model + ' — ' + storage
    if sim_type != 'unspecified':
        display += ' (' + sim.group(1) + ')'
    return dict(key=key, name=display, brand=brand, model=model, storage=storage, ram=(ram + 'GB') if ram else None, sim=sim_type)


def fetch_store(store, session):
    parsed = urlparse(store['url'])
    if parsed.scheme != 'https' or not parsed.netloc:
        raise ValueError('Store must use HTTPS')
    results = []
    for page in range(1, 9):
        endpoint = store['url'].rstrip('/') + '/products.json'
        response = session.get(endpoint, params={'limit': 250, 'page': page}, timeout=20)
        if response.status_code in (401, 403, 404, 429):
            raise RuntimeError(f'Catalog unavailable (HTTP {response.status_code}); do not bypass')
        response.raise_for_status()
        data = response.json()
        products = data.get('products')
        if not isinstance(products, list):
            raise ValueError('Unexpected catalog response')
        for product in products:
            title = clean(product.get('title'))
            handle = clean(product.get('handle'))
            if not handle:
                continue
            # Store collection may contain non-phone items; conservatively filter.
            for variant in product.get('variants') or []:
                if variant.get('available') is not True:
                    continue
                try:
                    price = float(variant.get('price'))
                except (ValueError, TypeError):
                    continue
                if not (25 <= price <= 8000):
                    continue
                identity = make_identity(title, variant.get('title'))
                if not identity:
                    continue
                # Full website URL; no affiliate or redirect manipulation.
                item = dict(**identity, store_id=store['id'], store=store['name'], price=round(price, 2), url=store['url'].rstrip('/')+'/products/'+handle+'?variant='+str(variant.get('id','')))
                results.append(item)
        if len(products) < 250:
            break
        time.sleep(0.6)
    return results


def build(now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    with (ROOT/'config/stores.json').open(encoding='utf-8') as f:
        stores = json.load(f)
    sess = requests.Session()
    sess.headers.update({'User-Agent':UA, 'Accept':'application/json'})
    all_quotes, statuses = [], []
    for store in stores:
        if not store.get('enabled'):
            continue
        try:
            quotes = fetch_store(store, sess)
            all_quotes += quotes
            statuses.append({'store':store['name'],'status':'ok','quotes':len(quotes)})
        except (requests.RequestException, ValueError, RuntimeError, json.JSONDecodeError) as e:
            statuses.append({'store':store['name'],'status':'error','message':str(e)[:180]})
        time.sleep(1)
    grouped = defaultdict(list)
    for quote in all_quotes:
        grouped[quote['key']].append(quote)
    phones = []
    for key, candidates in grouped.items():
        # Only one quote per store, prevent artificial weight for many colors.
        by_store = {}
        for quote in candidates:
            current = by_store.get(quote['store_id'])
            if current is None or quote['price'] < current['price']:
                by_store[quote['store_id']] = quote
        quotes = list(by_store.values())
        if len(quotes) < 2:
            continue
        prices = [q['price'] for q in quotes]
        # No outlier rejection by default: transparently disclose range.
        item = quotes[0]
        phones.append({'id':key,'name':item['name'],'model':item['model'],'brand':item['brand'], 'storage':item['storage'], 'ram':item['ram'], 'sim':item['sim'], 'average_usd':round(statistics.mean(prices),2),'min_usd':min(prices),'max_usd':max(prices),'store_count':len(quotes),'offers':sorted([{'store':q['store'],'price_usd':q['price'],'url':q['url']} for q in quotes],key=lambda q:q['price_usd'])})
    phones.sort(key=lambda p:(p['brand'].lower(),p['model'].lower(),p['storage']))
    out = {'schema_version':1,'generated_at':now.isoformat().replace('+00:00','Z'), 'currency':'USD','method':'Arithmetic average of one eligible in-stock new-phone quote per independent store, at least 2 stores, identical parsed model/storage/SIM label. Excludes ambiguous variants and bundles.','phones':phones,'sources':statuses}
    # Never replace good published data with an empty feed after transient failure.
    dest = ROOT/'data/phones.json'
    if phones:
        dest.parent.mkdir(exist_ok=True)
        dest.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('Published',len(phones),'phone variants from',len(all_quotes),'quotes')
    else:
        print('No eligible multi-store matches: preserved prior feed',file=sys.stderr)
    for s in statuses:
        print(s)
    if not phones:
        raise SystemExit(1)

if __name__=='__main__':
    build()
