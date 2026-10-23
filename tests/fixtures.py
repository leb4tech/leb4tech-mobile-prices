"""Synthetic-only evidence. Never copied into production data."""
from datetime import datetime, timezone
from decimal import Decimal
from price_index.market import Source, Offer
NOW=datetime(2026,10,23,12,tzinfo=timezone.utc)
PRODUCT={'sku':'fixture-256','url':'https://a.example/phone','brand':'Fixture',
         'model':'Phone Pro','storage_gb':256,'ram_gb':8,'sim':'dual physical SIM',
         'warranty':'ضمان المتجر سنة','condition':'new','specs':['شاشة موثّقة في الاختبار فقط'],
         'image':None,'reviewed_at':NOW.isoformat(),'evidence_url':'https://a.example/phone'}
SOURCE=Source('Fixture A','owner-a','a.example','https://a.example/permission','LB')
def offer(source=SOURCE,price='100'):
    return Offer(source,'https://'+source.host+'/phone','Phone Pro',256,'dual physical SIM',
                 'ضمان المتجر سنة','new','USD',True,Decimal(price),NOW)
def jsonld(**changes):
    import json
    value={'@type':'Product','sku':'fixture-256','brand':{'name':'Fixture'},'offers':{
        '@type':'Offer','price':'100','priceCurrency':'USD','availability':'https://schema.org/InStock',
        'itemCondition':'https://schema.org/NewCondition'}}
    value['offers'].update(changes)
    return '<script type="application/ld+json">'+json.dumps(value)+'</script>'
