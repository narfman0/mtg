#!/usr/bin/env python3
"""Refresh oracle-cards.jsonl from Scryfall's bulk data.

Usage: sync_cards.py [--max-age DAYS] [--force] [--check]

Scryfall has no incremental/delta feed -- the bulk files are rebuilt whole
each day -- so "incremental" here means skipping the download, not patching
the file. The bulk-data metadata endpoint is a few KB and carries an
`updated_at` per file, so we fetch that first and only pull the ~25 MB
oracle-cards archive when Scryfall's copy is newer than ours.

The card file itself is gitignored (regenerable), which means git can't show
what changed between refreshes. The two fields that matter for deckbuilding
-- Commander legality and the Game Changers flag -- are therefore snapshotted
into the committed cards-status.json, and every sync diffs against it and
reports bans, unbans, and Game Changer changes.
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
CARDS = os.path.join(BASE, "oracle-cards.jsonl")
ARCHIVE = CARDS + ".gz"
STATUS = os.path.join(BASE, "cards-status.json")
BULK = "https://api.scryfall.com/bulk-data"
UA = "mtg-deck-helper/1.0 (narfman0@gmail.com; personal deck research)"
KIND = "oracle_cards"


def get_json(url):
    # Scryfall 403s requests without a User-Agent.
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def remote_meta():
    """The bulk-data entry for oracle_cards: download URI, updated_at, size."""
    for entry in get_json(BULK)["data"]:
        if entry["type"] == KIND:
            return entry
    sys.exit(f"scryfall no longer publishes a {KIND!r} bulk file")


def load_status():
    try:
        with open(STATUS) as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}


def scan():
    """Pull the fields worth tracking out of the card file."""
    banned, restricted, changers = [], [], []
    total = 0
    for line in open(CARDS):
        card = json.loads(line)
        total += 1
        legal = card.get("legalities", {}).get("commander")
        if legal == "banned":
            banned.append(card["name"])
        elif legal == "restricted":
            restricted.append(card["name"])
        if card.get("game_changer"):
            changers.append(card["name"])
    return {"cards": total, "banned": sorted(banned),
            "restricted": sorted(restricted), "game_changers": sorted(changers)}


def diff(old, new, key, label):
    """Print additions/removals for one tracked list. Returns True if changed."""
    before, after = set(old.get(key) or []), set(new[key])
    if not old:
        return False  # first run: the snapshot is the baseline, not a change
    added, removed = sorted(after - before), sorted(before - after)
    for name in added:
        print(f"  + {label}: {name}")
    for name in removed:
        print(f"  - {label}: {name}")
    return bool(added or removed)


def download(uri):
    req = urllib.request.Request(uri, headers={"User-Agent": UA})
    tmp = ARCHIVE + ".part"
    with urllib.request.urlopen(req, timeout=300) as resp, open(tmp, "wb") as fh:
        shutil.copyfileobj(resp, fh)
    os.replace(tmp, ARCHIVE)
    # Decompress to a temp file so a failure mid-stream can't leave a
    # truncated oracle-cards.jsonl behind for card.py to read.
    tmp = CARDS + ".part"
    with gzip.open(ARCHIVE, "rb") as src, open(tmp, "wb") as dst:
        shutil.copyfileobj(src, dst)
    os.replace(tmp, CARDS)


def stale(max_age):
    """True if the local card file is missing or older than max_age days."""
    if not os.path.exists(CARDS):
        return True
    age = datetime.now(timezone.utc) - datetime.fromtimestamp(
        os.path.getmtime(CARDS), timezone.utc)
    return age >= timedelta(days=max_age)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-age", type=float, default=7, metavar="DAYS",
                    help="skip the network entirely if the local file is newer "
                         "than this (default 7)")
    ap.add_argument("--force", action="store_true",
                    help="re-download even if Scryfall's copy is not newer")
    ap.add_argument("--check", action="store_true",
                    help="report staleness and exit 1 if a sync is due")
    args = ap.parse_args()

    have = os.path.exists(CARDS)
    if not stale(args.max_age) and not args.force:
        mtime = datetime.fromtimestamp(os.path.getmtime(CARDS), timezone.utc)
        print(f"oracle-cards.jsonl is fresh (fetched {mtime:%Y-%m-%d}, "
              f"max-age {args.max_age}d); nothing to do")
        return
    if args.check:
        state = "missing" if not have else "stale"
        print(f"oracle-cards.jsonl is {state}; run sync_cards.py")
        sys.exit(1)

    try:
        meta = remote_meta()
    except (urllib.error.URLError, TimeoutError) as err:
        if have:
            print(f"scryfall unreachable ({err}); keeping the cached card file, "
                  f"which may be stale")
            return
        sys.exit(f"scryfall unreachable and no cached card file: {err}")

    updated = datetime.fromisoformat(meta["updated_at"])
    local = (datetime.fromtimestamp(os.path.getmtime(CARDS), timezone.utc)
             if have else None)
    if have and local and updated <= local and not args.force:
        # Bump the mtime so the next --max-age check doesn't re-ask for a week.
        os.utime(CARDS, None)
        print(f"scryfall's {KIND} is unchanged since {updated:%Y-%m-%d}; "
              f"no download needed")
        return

    mb = meta["compressed_size"] / 1e6
    print(f"downloading {KIND} ({mb:.0f} MB compressed, "
          f"updated {updated:%Y-%m-%d %H:%M} UTC)...")
    download(meta["jsonl_download_uri"])

    old = load_status()
    new = scan()
    new["updated_at"] = meta["updated_at"]
    print(f"oracle-cards.jsonl: {new['cards']} cards, "
          f"{len(new['banned'])} banned in commander, "
          f"{len(new['game_changers'])} game changers")

    changed = False
    for key, label in (("banned", "BANNED"), ("restricted", "restricted"),
                       ("game_changers", "game changer")):
        changed |= diff(old, new, key, label)
    if old and not changed:
        print("  no ban-list or game-changer changes")

    with open(STATUS, "w") as fh:
        json.dump(new, fh, indent=1, sort_keys=True)
        fh.write("\n")
    if not old:
        print(f"wrote first {os.path.basename(STATUS)} snapshot "
              f"(commit it -- it's the baseline future syncs diff against)")


if __name__ == "__main__":
    main()
