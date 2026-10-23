# Leb4Tech Mobile Price Index — Lebanon

A conservative starter system for an Arabic Blogger page with English phone model names. Python retrieves public Shopify catalogs; GitHub Actions runs every 6 hours, and Blogger displays the resulting `data/phones.json` through jsDelivr.

## Setup
1. Create a **public** GitHub repo `leb4tech-mobile-prices` in your GitHub account, and upload this project's contents (including `.github`). Do not publish private credentials.
2. In GitHub, open **Actions** > **Update Lebanon phone prices** > **Run workflow**. Allow Actions to write repo content: Settings > Actions > General > Workflow permissions > **Read and write permissions**, if needed.
3. Inspect the workflow logs and `data/phones.json`. The importer deliberately rejects ambiguous/used/bundled phones and requires at least two independent matched store offers. If none can be matched, the workflow fails and retains the previous feed; **don't loosen matching blindly**.
4. Update `USERNAME` in `blogger/page.html` to the actual GitHub username; change the repository portion if you used a different repo name.
5. In Blogger: Pages > New page > switch to HTML view; paste the entire `blogger/page.html` code and publish. Check Blogger theme and CSP/custom JS compatibility.
6. Check data feed in browser: `https://cdn.jsdelivr.net/gh/USERNAME/leb4tech-mobile-prices@main/data/phones.json`.

## Important cautions
- This is a starter, **not** a confirmed live price service. Shopify public `/products.json` availability and catalog completeness may change. Sites can block requests; do not bypass or ignore robots/terms. Seek permissions/API access where necessary.
- No invented phone prices or detailed specs. RAM/storage shown only if explicit in the listing. A missing spec means *unknown*, not zero.
- All input must actually be priced in USD. Shopify `products.json` often represents shop-currency values; **verify each store's actual catalog currency** before enabling live publishing. If a store uses non-USD currency, disable it until an approved conversion mechanism is implemented.
- Different warranty/region conditions may affect price comparability. Current heuristic excludes clearly marked conditions but cannot guarantee every listing is equivalent. Review mappings on first deployment; consider a manually approved matching registry for production.
- `?variant=` links may become invalid if a store changes their product variants; preserve product pages for checking.
- If two stores quote the same price, both count; if one store lists multiple colors/copies of a variant, only its cheapest qualifying offer is used (bias noted). A more rigorous version should select canonical price within store after checking colors.
- In GitHub Actions, published JSON is updated only after successful fetching and matching. If zero matches, previous file remains unchanged. Show `generated_at` so users can see stale pricing.
- Some static CDN endpoints may cache; Blogger includes a 1-hour refresh key. Changes can propagate with delay.

## Codex development brief
Improve this project without sacrificing strict matching. Add shop-specific product feed adapters where permitted; explicit currency verification, category phone-only filtering, per-variant warranty/state matching, stronger normalization and alias table, freshness cutoff, source health report, fixtures/tests, and a manual review list for uncertain variants. Keep the public JSON schema backwards-compatible and page language Arabic, phone names English. Do not invent missing specs or prices. Never bypass rate limits, protection, or access restrictions.

## Run locally
```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/build_feed.py
```
