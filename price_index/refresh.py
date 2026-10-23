"""Collect reviewed sources, merge fresh variants, preserve last known good data."""
from datetime import datetime, timezone
from decimal import Decimal
import json
import logging
from pathlib import Path
from price_index.dataset import validate_dataset, atomic_json, variant_id, timestamp
from price_index.market import market_average, validate
from price_index.sources import ProductPageAdapter

LOG=logging.getLogger(__name__)

def build(previous,batches,now):
    validate_dataset(previous,now)
    grouped={}
    for product,offer in batches:
        validate(offer,now)
        if any(product[k] != getattr(offer,k) for k in ('model','storage_gb','sim','warranty','condition')):
            raise ValueError('offer and reviewed variant mismatch')
        phone={k:product[k] for k in ('brand','model','storage_gb','ram_gb','sim','warranty','condition','specs','image')}
        key=variant_id(phone)
        if key not in grouped:grouped[key]=(phone,[])
        existing,offers=grouped[key]
        # Conflicting metadata requires manual review, never a guessed merge.
        if existing!=phone:raise ValueError('conflicting variant metadata')
        offers.append(offer)
    merged={p['id']:p for p in previous['phones']}
    updated=0
    for key,(phone,offers) in grouped.items():
        # Duplicated listings from the same owner invalidate the variant rather
        # than overweight its contribution or silently choose a low price.
        identities=[o.source.independent_owner.strip().casefold() for o in offers]
        if len(identities)!=len(set(identities)):raise ValueError('duplicate owner offers')
        avg=market_average(offers,now) if len(offers)>=2 else None
        # Never replace an older verified average with a single-source result.
        if key in merged and avg is None:continue
        phone.update(id=key,average_usd=float(avg) if avg is not None else None,
                     status='verified' if avg is not None else 'insufficient_data',
                     updated_at=now.isoformat(),offers=[{
                         'store':o.source.store,'owner':o.source.independent_owner,
                         'url':o.url,'currency':'USD','price_usd':float(o.price),
                         'available':True,'condition':o.condition,'observed_at':o.observed_at.isoformat()
                     } for o in offers])
        merged[key]=phone
        updated+=1
    phones=sorted(merged.values(),key=lambda p:(p['brand'],p['model'],p['id']))
    result={'schema_version':1,'updated_at':max((p['updated_at'] for p in phones),key=timestamp,default=None),'phones':phones}
    return validate_dataset(result,now),updated

def refresh(config_path='config/sources.json',data_path='data/phones.json',report_path='data/status.json',factory=ProductPageAdapter,now=None):
    now=now or datetime.now(timezone.utc)
    previous=json.loads(Path(data_path).read_text())
    validate_dataset(previous,now)
    config=json.loads(Path(config_path).read_text())
    from jsonschema import Draft202012Validator, FormatChecker
    schema=json.loads((Path(__file__).resolve().parents[1]/'schemas/sources.schema.json').read_text())
    Draft202012Validator(schema,format_checker=FormatChecker()).validate(config)
    failures=[]
    batches=[]
    enabled=[s for s in config['sources'] if s.get('enabled') is True]
    for source in enabled:
        try:
            # Batch is atomic: a malformed product prevents partial source writes.
            values=list(factory(source,now=now).fetch())
            if not values:raise ValueError('empty source result')
            batches.extend(values)
            LOG.info('source=%s status=ok count=%d',source['store'],len(values))
        except Exception as error:
            failures.append({'source':source.get('store','unknown'),'error':type(error).__name__})
            LOG.warning('source=%s status=failed error=%s',source.get('store','unknown'),type(error).__name__)
    try:
        candidate,count=build(previous,batches,now) if not failures else (previous,0)
    except Exception as error:
        failures.append({'source':'validation','error':type(error).__name__})
        candidate,count=previous,0
        LOG.error('candidate rejected error=%s',type(error).__name__)
    state='not_configured' if not enabled else ('partial_failure' if failures and count else 'failed' if failures else 'updated' if count else 'no_update')
    report={'checked_at':now.isoformat(),'state':state,'failures':failures,'updated_variants':count}
    # Report is separate: failed runs cannot advance any price timestamp.
    atomic_json(report_path,report)
    if count:atomic_json(data_path,candidate)
    LOG.info('refresh state=%s updated_variants=%d failures=%d',state,count,len(failures))
    return report

if __name__=='__main__':
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    try:
        report=refresh()
    except Exception as error:
        LOG.error('refresh failed error=%s',type(error).__name__)
        report={'checked_at':datetime.now(timezone.utc).isoformat(),'state':'failed','failures':[{'source':'configuration_or_dataset','error':type(error).__name__}],'updated_variants':0}
        atomic_json('data/status.json',report)
        raise SystemExit(1)
    if report['state'] in ('failed','partial_failure'):raise SystemExit(1)
