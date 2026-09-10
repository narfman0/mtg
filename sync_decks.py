#!/usr/bin/env python3
"""Sync decks/ from Moxfield (source of truth). Local files are a cache.

Usage: sync_decks.py [deck ...]     (no args = sync all)

Writes decks/<name>.txt as: mainboard, blank line, commander(s), then a
"# Considering" section mirroring the Moxfield maybeboard. Deck changes
are committed and pushed automatically.
"""
import json
import os
import subprocess
import sys
import urllib.request

DECKS = {
    "satoru": "y-k2M1abFEmeATCYD04W1A",
    "niv": "cm0ImMAUZUWxdvEegyYrQw",
}

BASE = os.path.dirname(os.path.abspath(__file__))
UA = "mtg-deck-helper/1.0 (narfman0@gmail.com; personal deck sync)"


def board_lines(board):
    cards = sorted(board["cards"].values(), key=lambda v: v["card"]["name"])
    return [f"{v['quantity']} {v['card']['name']}" for v in cards]


def sync(name, public_id):
    url = f"https://api2.moxfield.com/v3/decks/all/{public_id}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        deck = json.load(resp)

    boards = deck["boards"]
    out = board_lines(boards["mainboard"])
    out += [""] + board_lines(boards["commanders"])
    maybe = boards.get("maybeboard", {"count": 0})
    if maybe["count"]:
        out += ["", "# Considering"] + board_lines(maybe)

    path = os.path.join(BASE, "decks", f"{name}.txt")
    with open(path, "w") as fh:
        fh.write("\n".join(out) + "\n")
    print(f"{name}: {deck['name']!r} -> {path} "
          f"({boards['mainboard']['count']} main + {boards['commanders']['count']} cmdr"
          f" + {maybe['count']} considering)")


def commit_and_push():
    git = ["git", "-C", BASE]
    status = subprocess.run(git + ["status", "--porcelain", "decks"],
                            capture_output=True, text=True, check=True).stdout
    if not status.strip():
        print("decks unchanged; nothing to commit")
        return
    changed = sorted(os.path.splitext(os.path.basename(line[3:]))[0]
                     for line in status.strip().splitlines())
    subprocess.run(git + ["add", "decks"], check=True)
    subprocess.run(git + ["commit", "-m",
                          f"Sync {', '.join(changed)} from Moxfield"], check=True)
    subprocess.run(git + ["push"], check=True)


def main():
    names = sys.argv[1:] or list(DECKS)
    for name in names:
        if name not in DECKS:
            sys.exit(f"unknown deck {name!r}; known: {', '.join(DECKS)}")
        sync(name, DECKS[name])
    commit_and_push()


if __name__ == "__main__":
    main()
