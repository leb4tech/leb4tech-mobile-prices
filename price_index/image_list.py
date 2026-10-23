"""Validate attributed image transcriptions without treating them as retail offers."""
from datetime import date, datetime
from zoneinfo import ZoneInfo
import math
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]

def validate_image_list(value):
    schema = json.loads((ROOT/'schemas/image-prices.schema.json').read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)
    if date.fromisoformat(value['list_date']) > datetime.now(ZoneInfo('Asia/Beirut')).date():
        raise ValueError('future image list date')
    seen = set()
    for row in value['listings']:
        if not math.isfinite(row['price_usd']):
            raise ValueError('nonfinite image price')
        identity = (row['source_section'].casefold(), row['listing_text'].casefold())
        if identity in seen:
            raise ValueError('duplicate image listing')
        seen.add(identity)
    return value
