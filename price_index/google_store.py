"""Read reviewed US Google Store public HTML. No private /prices or cart API.

A variant's public microdata, visible full storage price and official specs must
agree. Only the standard new, unlocked retail channel is supported. Missing or
changed evidence fails closed rather than inventing SKU, specs or availability.
"""
from datetime import timedelta
from decimal import Decimal, InvalidOperation
import re
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
from price_index.dataset import timestamp
from price_index.market import Offer, validate
from price_index.sources import (
    ProductPageAdapter, Transport, AccessDenied, SourceError, OutOfStock,
)
from price_index.robots import RobotFileParser


def normalized(value):
    return ' '.join(value.split())


def document(raw):
    soup = BeautifulSoup(raw, 'html.parser')
    if len(soup.find_all('main')) != 1 or not soup.title:
        raise SourceError('public document structure changed')
    return soup


def parse_google_variant(config_doc, specs_doc, product, source, now):
    title = normalized(config_doc.title.get_text(' ', strip=True))
    expected_title = 'Discover the New Google ' + product['model']
    headings = [normalized(n.get_text(' ', strip=True)) for n in config_doc.find('main').find_all('h1')]
    if (title != expected_title or product['model'] not in headings
            or product['condition'] != 'new' or product['brand'] != 'Google'):
        raise SourceError('standard new-product channel or model changed')
    if normalized(specs_doc.title.get_text(' ', strip=True)) != 'Google ' + product['model'] + ' Specs & Hardware':
        raise SourceError('specification model mismatch')
    expected_description = f"{product['model']} {product['color']} {product['storage_gb']}GB (Unlocked)"
    if product['variant_description'] != expected_description:
        raise SourceError('ambiguous storage color or carrier mapping')

    candidates = []
    for scope in config_doc.select('[itemscope][itemtype="https://schema.org/AggregateOffer"]'):
        props = {}
        for node in scope.select('[itemprop]'):
            if node.find_parent(attrs={'itemscope': True}) is not scope:
                continue
            key = node.get('itemprop')
            value = node.get('content') or node.get('href') or node.get_text(' ', strip=True)
            if key in props:
                raise SourceError('duplicate microdata property')
            props[key] = normalized(value)
        if props.get('description') == expected_description:
            candidates.append(props)
    if len(candidates) != 1:
        raise SourceError('variant missing or duplicated')
    candidate = candidates[0]
    if candidate.get('priceCurrency') != 'USD':
        raise SourceError('explicit USD required')
    if candidate.get('availability') == 'https://schema.org/OutOfStock':
        raise OutOfStock('reviewed variant is out of stock')
    if candidate.get('availability') != 'https://schema.org/InStock':
        raise SourceError('explicit stock evidence required')
    try:
        price = Decimal(candidate['lowPrice'])
        if not price.is_finite() or price <= 0:
            raise ValueError()
        if 'highPrice' in candidate and Decimal(candidate['highPrice']) != price:
            raise ValueError()
    except (KeyError, InvalidOperation, ValueError):
        raise SourceError('price missing or ambiguous') from None

    # The AggregateOffer value is not accepted on its own. Cross-check it
    # against the public one-time, storage-specific purchase price.
    visible = []
    pattern = re.compile(r'^' + str(product['storage_gb']) + r'\s*GB\s+\$([0-9,]+(?:\.[0-9]{1,2})?)$')
    for button in config_doc.find('main').select('[data-test="storage_selection_panel"]'):
        match = pattern.fullmatch(normalized(button.get_text(' ', strip=True)))
        if match:
            visible.append(Decimal(match.group(1).replace(',', '')))
    if len(visible) != 1 or visible[0] != price:
        raise SourceError('visible full price disagrees with variant metadata')

    main = specs_doc.find('main')
    # Ignore scripts/styles when checking visible specification evidence.
    clone = BeautifulSoup(str(main), 'html.parser')
    for node in clone(['script', 'style']):
        node.decompose()
    text = normalized(clone.get_text(' ', strip=True))
    memory = rf"\b{product['storage_gb']}\s*GB\s*/\s*{product['ram_gb']}\s*GB\s*RAM\b"
    if product['ram_gb'] is None or not re.search(memory, text):
        raise SourceError('storage and RAM pair not documented')
    if product['sim'] != 'Dual eSIM' or 'SIMs Dual eSIM' not in text:
        raise SourceError('US SIM variant not documented')
    if product['warranty'] != 'ضمان Google لمدة سنة (الولايات المتحدة)' or not re.search(r'\bWarranty\s+1 year\b', text):
        raise SourceError('US manufacturer warranty not documented')
    if 'Processor ' + product['processor'] not in text:
        raise SourceError('processor not documented')
    expected_specs = [f"اللون: {product['color']}", 'نسخة Unlocked', f"المعالج: {product['processor']}"]
    if product['specs'] != expected_specs or product['image'] is not None:
        raise SourceError('unreviewed specifications or image')
    offer = Offer(source, product['url'], product['model'], product['storage_gb'],
                  product['sim'], product['warranty'], 'new', 'USD', True, price, now)
    validate(offer, now)
    return offer


class GoogleStoreAdapter(ProductPageAdapter):
    def __init__(self, config, now=None, transport=None):
        transport = transport or Transport(config['user_agent'], config['min_interval_seconds'], max_bytes=8_000_000)
        super().__init__(config, now=now, transport=transport)

    def fetch(self):
        c = self.config
        if self.source.host != 'store.google.com' or self.source.country != 'US':
            raise AccessDenied('only reviewed US Google Store source is supported')
        if c.get('enabled') is not True or c.get('permission_confirmed') is not True:
            raise AccessDenied('public access review required')
        age = self.now - timestamp(c['reviewed_at'])
        if age < timedelta(0) or age >= timedelta(days=30):
            raise AccessDenied('source access review expired')
        products = c['products']
        if not products or len(products) > 50:
            raise SourceError('configure 1 to 50 reviewed variants')
        seen = set()
        for product in products:
            age = self.now - timestamp(product['reviewed_at'])
            if age < timedelta(0) or age >= timedelta(days=30):
                raise SourceError('variant review expired')
            if product['variant_description'] in seen:
                raise SourceError('duplicate variant configuration')
            seen.add(product['variant_description'])
            url = urlsplit(product['url'])
            if (url.scheme != 'https' or url.netloc != 'store.google.com'
                    or not re.fullmatch(r'/us/config/pixel_[a-z0-9_]+', url.path)
                    or url.query != 'hl=en-US' or url.fragment):
                raise AccessDenied('unreviewed configuration page')
            slug = url.path.rsplit('/', 1)[-1]
            expected_specs = f'https://store.google.com/us/product/{slug}_specs?hl=en-US'
            if product['spec_url'] != expected_specs or product['evidence_url'] != product['url']:
                raise AccessDenied('specification or evidence URL mismatch')
        robots = RobotFileParser('https://store.google.com/robots.txt')
        robots.parse(self.transport.get('https://store.google.com/robots.txt', self.source.host).splitlines())
        ua = c['user_agent']
        interval = robots.crawl_delay(ua) or 0
        rate = robots.request_rate(ua)
        if rate:
            interval = max(interval, rate.seconds / rate.requests)
        if interval > 60:
            raise AccessDenied('crawl delay requires a separately scheduled source')
        self.transport.interval = max(self.transport.interval, interval)
        docs = {}
        results = []
        for product in products:
            for url in (product['url'], product['spec_url']):
                if not robots.can_fetch(ua, url):
                    raise AccessDenied('robots disallows reviewed public page')
                if url not in docs:
                    docs[url] = document(self.transport.get(url, self.source.host))
            results.append((product, parse_google_variant(
                docs[product['url']], docs[product['spec_url']], product, self.source, self.now)))
        return results
