#!/usr/bin/env python3
"""Refresh oracle-cards.jsonl from Scryfall's bulk data.

Usage: sync_cards.py [--max-age DAYS] [--force] [--check]

Scryfall has no incremental/delta feed -- the bulk files are rebuilt whole
each day -- so "incremental" here means skipping the download, not patching
the file. The bulk-data metadata endpoint is a few KB and carries an
`updated_at` per file, so we fetch that first and only pull the ~25 MB
oracle-cards archive when Scryfall's copy is newer than ours.

The card file itself stays gitignored: at ~200 MB it exceeds GitHub's 100 MB
per-file limit, and because Scryfall re-prices every card daily, git can delta
neither it nor its archive -- each refresh would add ~22 MB to history forever.
Since the same upstream file lands byte-identical on every machine, the sync is
the sharing mechanism and only the *version* needs to be shared.

So the committed cards-status.json doubles as that shared pin: it records the
Scryfall `updated_at` every machine should be on, plus the two fields that
matter for deckbuilding -- Commander legality and the Game Changers flag -- so
each sync can diff against it and report bans, unbans, and Game Changer
changes. This machine's own version lives in the gitignored .cards-local.json,
and a mismatch between the two means "git pull happened, re-run this script".
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
LOCAL = os.path.join(BASE, ".cards-local.json")   # gitignored; what THIS machine has
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


def load(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
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


def stamp(updated_at):
    """Record which upstream build this machine now holds."""
    with open(LOCAL, "w") as fh:
        json.dump({"updated_at": updated_at,
                   "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                  fh, indent=1)
        fh.write("\n")


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


def fetched_at():
    """When this machine last pulled the card file, or None if it has none."""
    if not os.path.exists(CARDS):
        return None
    stamp = load(LOCAL).get("fetched")
    if stamp:
        return datetime.fromisoformat(stamp)
    # Predates .cards-local.json (or it was deleted): fall back to the mtime.
    return datetime.fromtimestamp(os.path.getmtime(CARDS), timezone.utc)


def behind_baseline():
    """The repo's pinned version, when this machine doesn't have it yet.

    cards-status.json is committed, so a git pull can advance the pin while
    this machine's card file stays where it was."""
    pinned = load(STATUS).get("updated_at")
    if pinned and pinned != load(LOCAL).get("updated_at"):
        return pinned
    return None


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
    fetched = fetched_at()
    fresh = fetched and datetime.now(timezone.utc) - fetched < timedelta(days=args.max_age)
    pinned = behind_baseline()
    if pinned:
        # Another machine synced and committed the pin; match it regardless of age.
        mine = load(LOCAL).get("updated_at")
        print(f"repo pins scryfall {pinned[:10]}, this machine has "
              f"{mine[:10] if mine else 'an untracked copy'}")
    if fresh and not pinned and not args.force:
        print(f"oracle-cards.jsonl is fresh (fetched {fetched:%Y-%m-%d}, "
              f"max-age {args.max_age}d); nothing to do")
        return
    if args.check:
        state = ("missing" if not have
                 else "behind the repo pin" if pinned else "stale")
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
    if have and meta["updated_at"] == load(LOCAL).get("updated_at") and not args.force:
        # Same upstream build we already hold. Restamp so the next --max-age
        # check doesn't re-ask for a week.
        stamp(meta["updated_at"])
        print(f"scryfall's {KIND} is unchanged since {updated:%Y-%m-%d}; "
              f"no download needed")
        return

    mb = meta["compressed_size"] / 1e6
    print(f"downloading {KIND} ({mb:.0f} MB compressed, "
          f"updated {updated:%Y-%m-%d %H:%M} UTC)...")
    download(meta["jsonl_download_uri"])

    stamp(meta["updated_at"])
    old = load(STATUS)
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
    if old.get("updated_at") != new["updated_at"]:
        print(f"commit cards-status.json to pin scryfall "
              f"{new['updated_at'][:10]} for your other machines")
    if not old:
        print(f"wrote first {os.path.basename(STATUS)} snapshot "
              f"(commit it -- it's the baseline future syncs diff against)")


if __name__ == "__main__":
    main()
