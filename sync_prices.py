#!/usr/bin/env python3
"""Refresh manapool-prices.json from Mana Pool's public singles price feed.

Usage: sync_prices.py [--max-age HOURS] [--force]

The feed (https://manapool.com/api/v1/prices/singles, no auth) lists every
printing Mana Pool sells with its in-stock quantity and prices in cents:
`price_cents` (cheapest listing), `price_cents_lp_plus`, `price_cents_nm`, the
same three for foil and etched, `price_market`, plus `scryfall_id` and a
product `url`. Take the minimum over in-stock printings of a name for "the
cheapest copy I could actually buy".

The file is ~50 MB and re-priced constantly, so it stays gitignored and each
machine fetches its own copy. Unlike oracle-cards.jsonl there's no shared pin:
prices are only meaningful when fresh, so there's nothing to keep in sync.
"""
import argparse
import gzip
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
PRICES = os.path.join(BASE, "manapool-prices.json")
URL = "https://manapool.com/api/v1/prices/singles"
UA = "mtg-deck-helper/1.0 (narfman0@gmail.com; personal deck research)"


def download():
    req = urllib.request.Request(URL, headers={"User-Agent": UA,
                                               "Accept": "application/json",
                                               "Accept-Encoding": "gzip"})
    tmp = PRICES + ".part"
    with urllib.request.urlopen(req, timeout=300) as resp, open(tmp, "wb") as fh:
        src = (gzip.GzipFile(fileobj=resp)
               if resp.headers.get("Content-Encoding") == "gzip" else resp)
        shutil.copyfileobj(src, fh)
    # Validate before replacing so a truncated download can't clobber a good file.
    with open(tmp) as fh:
        feed = json.load(fh)
    os.replace(tmp, PRICES)
    return feed


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-age", type=float, default=24, metavar="HOURS",
                    help="skip the download if the local file is newer than "
                         "this (default 24)")
    ap.add_argument("--force", action="store_true", help="download regardless of age")
    args = ap.parse_args()

    if os.path.exists(PRICES) and not args.force:
        mtime = datetime.fromtimestamp(os.path.getmtime(PRICES), timezone.utc)
        if datetime.now(timezone.utc) - mtime < timedelta(hours=args.max_age):
            print(f"manapool-prices.json is fresh (fetched {mtime:%Y-%m-%d %H:%M} "
                  f"UTC, max-age {args.max_age:g}h); nothing to do")
            return

    print("downloading mana pool singles prices...")
    try:
        feed = download()
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as err:
        if os.path.exists(PRICES):
            print(f"mana pool unreachable ({err}); keeping the cached prices, "
                  f"which may be stale")
            return
        sys.exit(f"mana pool unreachable and no cached prices: {err}")
    print(f"{len(feed['data']):,} printings, as of {feed['meta']['as_of']}")


if __name__ == "__main__":
    main()
