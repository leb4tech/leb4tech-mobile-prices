#!/usr/bin/env python3
"""Compatibility entry point for the schema-validated, permission-gated pipeline.

The previous title-based Shopify scraper is retired. Public visibility does not
prove USD currency, condition, warranty, independent ownership or republication
permission. config/stores.json is a historical review list, never an input feed.
"""
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ''):
    sys.path.insert(0, str(ROOT))

from price_index.refresh import refresh


def build():
    return refresh(
        config_path=ROOT / 'config/sources.json',
        data_path=ROOT / 'data/phones.json',
        report_path=ROOT / 'data/status.json',
    )


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    report = build()
    if report['state'] in ('failed', 'partial_failure'):
        raise SystemExit(1)
