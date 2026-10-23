"""Fail-closed validation of normalized offers from approved adapters.

This internal contract is converted to the public dataset by refresh.py. No network access, inference, currency conversion, or publication occurs.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import logging
from urllib.parse import urlsplit

LOG = logging.getLogger(__name__)
MAX_AGE = timedelta(hours=6)


@dataclass(frozen=True)
class Source:
    store: str
    independent_owner: str
    host: str
    permission_reference: str
    country: str


@dataclass(frozen=True)
class Offer:
    source: Source
    url: str
    model: str
    storage_gb: int
    sim: str
    warranty: str
    condition: str
    currency: str
    available: bool
    price: Decimal
    observed_at: datetime

    @property
    def variant(self):
        return (self.model, self.storage_gb, self.sim, self.warranty, self.condition)


def validate(offer: Offer, now: datetime):
    """Reject unknown fields rather than fill them from titles or assumptions."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('clock must be timezone aware')
    source = offer.source
    if not all(isinstance(v, str) and v.strip() for v in (
        source.store, source.independent_owner, source.host, source.permission_reference
    )) or source.country != 'LB':
        raise ValueError('unverified Lebanese source or missing access permission')
    url = urlsplit(offer.url)
    if (url.scheme != 'https' or url.hostname != source.host or url.username
            or url.password or url.port not in (None, 443) or not url.path):
        raise ValueError('invalid product URL')
    if not all(isinstance(v, str) and v.strip() for v in (
        offer.model, offer.sim, offer.warranty, offer.condition
    )):
        raise ValueError('incomplete model or variant')
    if type(offer.storage_gb) is not int or offer.storage_gb <= 0:
        raise ValueError('unknown storage capacity')
    if offer.condition not in ('new', 'used', 'refurbished'):
        raise ValueError('unknown condition')
    if offer.currency != 'USD' or offer.available is not True:
        raise ValueError('offer must explicitly be USD and in stock')
    if not isinstance(offer.price, Decimal) or not offer.price.is_finite() or offer.price <= 0:
        raise ValueError('price must be a positive finite Decimal')
    if offer.observed_at.tzinfo is None or offer.observed_at.utcoffset() is None:
        raise ValueError('observation must be timezone aware')
    age = now - offer.observed_at
    if age < timedelta(0) or age >= MAX_AGE:
        raise ValueError('future or stale observation')


def market_average(offers, now=None):
    """One offer per independent owner; exact normalized variants only.

    Adapters must explicitly resolve model identifiers and variant fields from
    source evidence. This function never fuzzy-matches or chooses a duplicate.
    """
    now = now or datetime.now(timezone.utc)
    offers = list(offers)
    for offer in offers:
        validate(offer, now)
    if len(offers) < 2:
        raise ValueError('at least two independent stores required')
    if len({o.variant for o in offers}) != 1:
        raise ValueError('model, storage, SIM, warranty or condition mismatch')
    owners = {o.source.independent_owner.casefold().strip() for o in offers}
    stores = {o.source.store.casefold().strip() for o in offers}
    hosts = {o.source.host.casefold().strip() for o in offers}
    if min(len(owners), len(stores), len(hosts)) != len(offers):
        raise ValueError('duplicate store or related owner; resolve before averaging')
    return (sum((o.price for o in offers), Decimal(0)) / len(offers)).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )


def collect(adapters, now=None):
    """Isolate source failures and report every failed source; never fabricate.

    Adapters are responsible for documented endpoint permission, robots/terms,
    bounded requests, honoring Retry-After, and stopping on access denial. No
    adapters are enabled by default.
    Returns validated offers plus explicit failures; a caller must still enforce
    independent-source quorum and validate the output schema.
    """
    now = now or datetime.now(timezone.utc)
    accepted, failures = [], []
    for adapter in adapters:
        try:
            batch = list(adapter.fetch())
            if not batch:
                raise ValueError('source returned no offers')
            for offer in batch:
                if offer.source != adapter.source:
                    raise ValueError('source identity mismatch')
                validate(offer, now)
            accepted.extend(batch)
            LOG.info('source=%s status=ok offers=%d', adapter.source.store, len(batch))
        except Exception as error:
            # Never log raw exceptions: URLs, response bodies and headers may
            # contain credentials. A typed status remains actionable and safe.
            failure = {'source': adapter.source.store, 'error': type(error).__name__}
            failures.append(failure)
            LOG.warning('source=%s status=failed error=%s', failure['source'], failure['error'])
    return accepted, failures
