"""Permission-gated product-page JSON-LD adapter; no invented API endpoints."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from html.parser import HTMLParser
import json
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from price_index.dataset import timestamp
from price_index.market import Source, Offer, validate

MAX_BYTES=2_000_000

class SourceError(ValueError):pass
class AccessDenied(SourceError):pass
class RateLimited(SourceError):pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise AccessDenied('redirect requires separate permission review')

class Transport:
    def __init__(self, user_agent, interval=5):
        if not user_agent or '\n' in user_agent:
            raise SourceError('reviewed user agent required')
        self.user_agent=user_agent
        if interval > 60:raise SourceError('interval requires a separately scheduled adapter')
        self.interval=max(5,interval)
        self.last={}
        self.opener=urllib.request.build_opener(NoRedirect())

    def get(self,url,host):
        parsed=urlsplit(url)
        if (parsed.scheme!='https' or parsed.hostname!=host or parsed.username
                or parsed.password or parsed.port not in (None,443) or parsed.fragment):
            raise AccessDenied('unapproved URL')
        delay=self.interval-(time.monotonic()-self.last.get(host,0))
        if delay>0:time.sleep(delay)
        self.last[host]=time.monotonic()
        try:
            req=urllib.request.Request(url,headers={'User-Agent':self.user_agent,'Accept':'text/html, text/plain;q=0.9','Accept-Encoding':'identity'})
            with self.opener.open(req,timeout=20) as response:
                body=response.read(MAX_BYTES+1)
                if len(body)>MAX_BYTES:raise SourceError('response too large')
                return body.decode('utf-8',errors='strict')
        except urllib.error.HTTPError as error:
            if error.code==429:
                # No retry within this run; Retry-After cannot be shortened.
                raise RateLimited('rate limited; stop source') from None
            if error.code in (401,403):raise AccessDenied('access denied') from None
            raise SourceError('HTTP failure') from None
        except urllib.error.URLError:
            raise SourceError('network or TLS failure') from None

class JsonLD(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active=False
        self.buffer=[]
        self.documents=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()=='script' and dict(attrs).get('type','').lower()=='application/ld+json':
            self.active=True
            self.buffer=[]
    def handle_data(self,data):
        if self.active:self.buffer.append(data)
    def handle_endtag(self,tag):
        if tag.lower()=='script' and self.active:
            self.documents.append(json.loads(''.join(self.buffer)))
            self.active=False

def nodes(value):
    if isinstance(value,list):
        for child in value:yield from nodes(child)
    elif isinstance(value,dict):
        yield value
        if '@graph' in value:yield from nodes(value['@graph'])

def typed(value,name):
    types=value.get('@type',[])
    return name in (types if isinstance(types,list) else [types])

def parse_product(html,product,source,now):
    parser=JsonLD()
    parser.feed(html)
    products=[v for doc in parser.documents for v in nodes(doc)
              if typed(v,'Product') and str(v.get('sku',''))==product['sku']]
    if len(products)!=1:raise SourceError('product identity missing or ambiguous')
    item=products[0]
    brand=item.get('brand')
    brand=brand.get('name') if isinstance(brand,dict) else brand
    if brand != product['brand']:raise SourceError('brand mismatch')
    # Review maps this SKU to exact model/storage/RAM/SIM/warranty. Never infer
    # any of those from loosely matching product titles or numeric substrings.
    offers=item.get('offers')
    offers=offers if isinstance(offers,list) else [offers]
    if len(offers)!=1 or not isinstance(offers[0],dict) or not typed(offers[0],'Offer'):
        raise SourceError('one unambiguous Offer required')
    offer=offers[0]
    if offer.get('priceCurrency')!='USD':raise SourceError('explicit USD required')
    if offer.get('availability') not in ('https://schema.org/InStock','http://schema.org/InStock'):
        raise SourceError('not explicitly in stock')
    conditions={'new':'NewCondition','used':'UsedCondition','refurbished':'RefurbishedCondition'}
    condition=offer.get('itemCondition',item.get('itemCondition'))
    if condition not in ('https://schema.org/'+conditions[product['condition']], 'http://schema.org/'+conditions[product['condition']]):
        raise SourceError('unknown or mismatched condition')
    raw=offer.get('price')
    if isinstance(raw,bool) or not isinstance(raw,(str,int,float)):
        raise SourceError('invalid price')
    try:price=Decimal(str(raw))
    except Exception:raise SourceError('invalid price') from None
    value=Offer(source, product['url'], product['model'],product['storage_gb'],
                product['sim'],product['warranty'],product['condition'],'USD',True,price,now)
    validate(value,now)
    return value

class ProductPageAdapter:
    def __init__(self,config,now=None,transport=None):
        self.config=config
        self.now=now or datetime.now(timezone.utc)
        self.source=Source(config['store'],config['owner'],config['host'],config['permission_url'],config['country'])
        self.transport=transport or Transport(config['user_agent'],config.get('min_interval_seconds',5))
    def fetch(self):
        c=self.config
        if c.get('enabled') is not True or c.get('permission_confirmed') is not True:
            raise AccessDenied('not reviewed')
        age=self.now-timestamp(c['reviewed_at'])
        if age<timedelta(0) or age>=timedelta(days=30):raise AccessDenied('permission review expired')
        if urlsplit(c['permission_url']).scheme!='https':raise AccessDenied('permission reference required')
        products=c['products']
        if not products or len(products)>50:raise SourceError('configure 1 to 50 reviewed products per source')
        robot_url='https://'+self.source.host+'/robots.txt'
        robots=RobotFileParser(robot_url)
        robots.parse(self.transport.get(robot_url,self.source.host).splitlines())
        ua=c['user_agent']
        interval=robots.crawl_delay(ua) or robots.crawl_delay('*') or 0
        rate=robots.request_rate(ua) or robots.request_rate('*')
        if rate:interval=max(interval,rate.seconds/rate.requests)
        if interval>60:raise SourceError('crawl delay requires separately scheduled requests')
        self.transport.interval=max(self.transport.interval,interval)
        results=[]
        seen=set()
        for product in products:
            if product['sku'] in seen:raise SourceError('duplicate SKU')
            seen.add(product['sku'])
            if not robots.can_fetch(ua,product['url']):raise AccessDenied('robots disallows product')
            metadata_age=self.now-timestamp(product['reviewed_at'])
            if metadata_age<timedelta(0) or metadata_age>=timedelta(days=30):
                raise SourceError('variant review expired')
            if product['evidence_url']!=product['url']:
                raise SourceError('variant evidence must identify reviewed product page')
            offer=parse_product(self.transport.get(product['url'],self.source.host),product,self.source,self.now)
            results.append((product,offer))
        return results
