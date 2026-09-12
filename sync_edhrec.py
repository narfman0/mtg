#!/usr/bin/env python3
"""Cache EDHREC pages into edhrec/ so lookups are instant and offline.

Usage: sync_edhrec.py [--cards] [--themes] [--max-age DAYS] [--force]
                     [deck or "Commander Name" ...]

With no positional args every deck in decks/ is covered. Fetched by default:
the commander page and the average decklist for each deck's commander(s).
--cards adds a card page per distinct card across the selected decks (~550
pages, slow); --themes adds each commander's top themes; --card NAME caches
one card's page on its own.

Pages are stored gzipped under edhrec/<kind>/<slug>.json.gz with fetch
metadata (ETag, Last-Modified) in edhrec/index.json, so re-syncs send
conditional requests and usually get a cheap 304. Query the cache with
edhrec.py -- this script only writes it.
"""
import argparse
import glob
import gzip
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE, "edhrec")
INDEX = os.path.join(CACHE, "index.json")
HOST = "https://json.edhrec.com/pages"
UA = "mtg-deck-helper/1.0 (narfman0@gmail.com; personal deck research)"
DELAY = 0.25  # seconds between requests; EDHREC is a free service, be polite


def slugify(name, front_only=False):
    """Best-effort EDHREC slug for a card name ('Krenko, Mob Boss' -> krenko-mob-boss).

    EDHREC indexes double-faced and split cards by their front face alone
    ('Agadeem's Awakening // Agadeem, the Undercrypt' -> agadeems-awakening),
    which front_only=True produces; the default keeps both faces.
    """
    name = name.split(" // ")[0] if front_only else name.replace(" // ", " ")
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = name.lower().replace("&", "and").replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-")


def load_index():
    try:
        with open(INDEX) as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}


def read_page(rel):
    """Read a cached page (rel is like 'commanders/krenko-mob-boss'). None if absent."""
    path = os.path.join(CACHE, rel + ".json.gz")
    try:
        with gzip.open(path, "rt") as fh:
            return json.load(fh)
    except (FileNotFoundError, OSError):
        return None


def fetch(rel, index, max_age, force):
    """Fetch HOST/<rel>.json into the cache. Returns 'fresh', 'new', 'updated',
    'unchanged', or 'miss'."""
    meta = index.get(rel, {})
    path = os.path.join(CACHE, rel + ".json.gz")
    have = os.path.exists(path)
    known = have or meta.get("missing")  # remember 403s so re-syncs skip them
    if known and not force and meta.get("fetched"):
        age = datetime.now(timezone.utc) - datetime.fromisoformat(meta["fetched"])
        if age < timedelta(days=max_age):
            return "fresh" if have else "known-miss"

    headers = {"User-Agent": UA, "Accept": "application/json"}
    if have and not force:
        if meta.get("etag"):
            headers["If-None-Match"] = meta["etag"]
        if meta.get("last_modified"):
            headers["If-Modified-Since"] = meta["last_modified"]

    req = urllib.request.Request(f"{HOST}/{rel}.json", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            new_meta = {
                "url": resp.geturl(),
                "etag": resp.headers.get("ETag"),
                "last_modified": resp.headers.get("Last-Modified"),
                "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
    except urllib.error.HTTPError as err:
        if err.code == 304:
            meta["fetched"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            index[rel] = meta
            return "unchanged"
        # 403 is what EDHREC's CDN returns for pages that do not exist.
        print(f"  miss {rel} (HTTP {err.code})")
        if err.code in (403, 404):
            index[rel] = {"missing": True, "fetched":
                          datetime.now(timezone.utc).isoformat(timespec="seconds")}
        return "miss"
    except (urllib.error.URLError, TimeoutError) as err:
        print(f"  error {rel}: {err}")
        return "miss"

    try:
        json.loads(body)
    except json.JSONDecodeError:
        print(f"  miss {rel} (not JSON)")
        return "miss"

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wb") as fh:
        fh.write(body)
    index[rel] = new_meta
    return "updated" if have else "new"


def deck_sections(path):
    """Split a decks/*.txt snapshot into its sections.

    Format: mainboard, blank line, commander(s), then optional '# ...' sections
    -- '# Proxies' (a subset of the mainboard) and '# Considering' (the
    maybeboard: candidates, not part of the deck).
    """
    out = {"mainboard": [], "commanders": [], "proxies": [], "considering": []}
    key = "mainboard"
    for raw in open(path):
        line = raw.strip()
        if line.startswith("#"):
            low = line.lower()
            key = ("considering" if "considering" in low
                   else "proxies" if "prox" in low else "other")
            out.setdefault(key, [])
            continue
        if not line:
            if key == "mainboard" and out["mainboard"]:
                key = "commanders"  # the blank line separates deck from commander
            continue
        out[key].append(re.sub(r"^\d+\s+", "", line))
    return out


def deck_cards(path):
    """(commanders, every distinct card name worth caching a page for)."""
    s = deck_sections(path)
    cards = s["mainboard"] + s["commanders"] + s["considering"]
    return s["commanders"], list(dict.fromkeys(cards))


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("targets", nargs="*", help="deck names, or commander names")
    ap.add_argument("--cards", action="store_true", help="also cache a page per deck card")
    ap.add_argument("--card", action="append", default=[], metavar="NAME",
                    help="cache just this card's page (repeatable)")
    ap.add_argument("--themes", action="store_true", help="also cache each commander's top themes")
    ap.add_argument("--max-age", type=float, default=3.0, metavar="DAYS",
                    help="skip pages fetched more recently (default 3)")
    ap.add_argument("--force", action="store_true", help="re-fetch, ignoring age and ETags")
    args = ap.parse_args()

    commanders, cards = [], []
    decks = sorted(glob.glob(os.path.join(BASE, "decks", "*.txt")))
    known = {os.path.splitext(os.path.basename(p))[0]: p for p in decks}
    if args.targets:
        for t in args.targets:
            if t in known:
                cmd, cds = deck_cards(known[t])
                commanders += cmd
                cards += cds
            else:  # not a deck name -- treat it as a commander to research
                commanders.append(t)
    elif not args.card:
        for path in decks:
            cmd, cds = deck_cards(path)
            commanders += cmd
            cards += cds
    if not commanders and not args.card:
        sys.exit("nothing to sync (no decks/ snapshots; run sync_decks.py first)")

    index = load_index()
    counts = {}
    pending = []
    for name in dict.fromkeys(commanders):
        slug = slugify(name)
        pending += [f"commanders/{slug}", f"average-decks/{slug}"]

    def run(rels):
        for rel in dict.fromkeys(rels):
            result = fetch(rel, index, args.max_age, args.force)
            counts[result] = counts.get(result, 0) + 1
            if result not in ("fresh",):
                time.sleep(DELAY)

    if args.card:
        print(f"cards: {', '.join(args.card)}")
        run([f"cards/{slugify(c)}" for c in args.card])
    if commanders:
        print(f"commanders: {', '.join(dict.fromkeys(commanders))}")
        run(pending)

    if args.themes:
        themes = []
        for name in dict.fromkeys(commanders):
            page = read_page(f"commanders/{slugify(name)}") or {}
            for tag in (page.get("tag_counts") or [])[:5]:
                themes.append(f"tags/{tag['slug']}")
        print(f"themes: {len(set(themes))}")
        run(themes)

    if args.cards:
        # Prefer slugs EDHREC itself published (in the commander pages we just
        # cached) over slugifying names ourselves.
        slugs = {}
        for name in dict.fromkeys(commanders):
            for rel in (f"commanders/{slugify(name)}", f"average-decks/{slugify(name)}"):
                page = read_page(rel) or {}
                for cl in page.get("container", {}).get("json_dict", {}).get("cardlists", []):
                    for cv in cl.get("cardviews", []):
                        slugs[cv["name"]] = cv["slug"]
        want = [f"cards/{slugs.get(n) or slugify(n)}" for n in dict.fromkeys(cards)]
        print(f"cards: {len(set(want))} distinct")
        run(want)
        # Double-faced names that EDHREC only indexes by front face 403 above.
        retry = [f"cards/{slugify(n, front_only=True)}" for n in dict.fromkeys(cards)
                 if " // " in n and not read_page(f"cards/{slugs.get(n) or slugify(n)}")]
        if retry:
            print(f"cards: retrying {len(set(retry))} double-faced name(s) by front face")
            run(retry)

    # Re-read and merge: a concurrent sync (a long --cards run, say) holds its
    # own copy in memory, and last-write-wins would drop one side's entries.
    merged = load_index()
    merged.update(index)
    # Adopt any cached file that has no index entry (a lost write, a manual
    # copy), dated from the file so staleness checks keep working.
    for path in glob.glob(os.path.join(CACHE, "**", "*.json.gz"), recursive=True):
        rel = os.path.relpath(path, CACHE)[: -len(".json.gz")]
        if rel not in merged:
            mtime = datetime.fromtimestamp(os.path.getmtime(path), timezone.utc)
            merged[rel] = {"fetched": mtime.isoformat(timespec="seconds")}
    with open(INDEX, "w") as fh:
        json.dump(merged, fh, indent=1, sort_keys=True)
    index = merged
    size = sum(os.path.getsize(p) for p in glob.glob(os.path.join(CACHE, "**", "*.gz"), recursive=True))
    print("  ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "nothing to do")
    pages = sum(1 for m in index.values() if not m.get("missing"))
    print(f"cache: {pages} pages, {size / 1e6:.1f} MB in {CACHE}")


if __name__ == "__main__":
    main()
