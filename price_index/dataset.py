"""Schema and semantic integrity checks; safe atomic JSON persistence."""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import os
from pathlib import Path
import tempfile
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]

def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timezone required')
    return result

def variant_id(phone):
    fields = ['brand','model','storage_gb','ram_gb','sim','warranty','condition']
    if 'market' in phone:fields.append('market')
    raw = json.dumps([phone[k] for k in fields],ensure_ascii=False,separators=(',',':'))
    return hashlib.sha256(raw.encode()).hexdigest()[:24]

def validate_dataset(data, now=None):
    schema = json.loads((ROOT/'schemas/phones.schema.json').read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(data)
    now = now or datetime.now(timezone.utc)
    ids = set()
    for phone in data['phones']:
        if phone['id'] != variant_id(phone) or phone['id'] in ids:
            raise ValueError('duplicate or invalid variant identity')
        ids.add(phone['id'])
        offers = phone['offers']
        for field in ('store','owner'):
            identities = [o[field].strip().casefold() for o in offers]
            if len(set(identities)) != len(identities):
                raise ValueError('duplicate or related store')
        from urllib.parse import urlsplit
        hosts=[urlsplit(o['url']).hostname for o in offers]
        if len(set(hosts)) != len(hosts) or any(not h for h in hosts):
            raise ValueError('duplicate or missing host')
        for offer in offers:
            if data['schema_version']==2 and offer['country'] != phone['market']:
                raise ValueError('offer market mismatch')
            if not Decimal(str(offer['price_usd'])).is_finite():
                raise ValueError('non-finite price')
            if offer['condition'] != phone['condition'] or timestamp(offer['observed_at']) > now:
                raise ValueError('condition mismatch or future price')
            if timestamp(offer['observed_at']) != timestamp(phone['updated_at']):
                raise ValueError('mixed observation timestamps')
        expected = None
        if len(offers) >= 2:
            expected = (sum(Decimal(str(o['price_usd'])) for o in offers)/len(offers)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
        if phone['status'] != ('verified' if expected is not None else 'insufficient_data'):
            raise ValueError('invalid quorum status')
        actual = phone['average_usd']
        if (expected is None and actual is not None) or (expected is not None and (actual is None or Decimal(str(actual)) != expected)):
            raise ValueError('incorrect average')
    expected_update = max((timestamp(p['updated_at']) for p in data['phones']),default=None)
    actual_update = timestamp(data['updated_at']) if data['updated_at'] is not None else None
    if expected_update != actual_update:
        raise ValueError('incorrect last successful update')
    return data

def atomic_json(path, value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    content=json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)+'\n'
    fd,name=tempfile.mkstemp(dir=path.parent,prefix='.'+path.name)
    try:
        with os.fdopen(fd,'w') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)
