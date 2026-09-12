#!/usr/bin/env python3
"""Sync decks/ from Moxfield (source of truth). Local files are a cache.

Usage: sync_decks.py [deck ...]     (no args = sync all)

Writes decks/<name>.txt as: mainboard, blank line, commander(s), then a
"# Proxies" section (mainboard cards carrying Moxfield's "proxy" tag --
a subset of the list above, not extra cards) and a "# Considering"
section (the maybeboard: candidates, not part of the deck). Deck changes
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
    "krenko": "mdyk7Zw6tEuRmAR86ijzPw",
    "rinseri": "LK0bV1ELS0S_IdnNgX_jwg",
    "shuyun": "hDAQlRfG_UiwReylsH404Q",
    "slivers": "hCiV_CCqY0ywuV7AZV4lKA",
    "norin": "0buTKZDWX0KSksQNoFHgkw",
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
    tags = deck.get("authorTags") or {}
    in_deck = {v["card"]["name"]: v["quantity"]
               for b in ("mainboard", "commanders")
               for v in boards[b]["cards"].values()}
    # Tags can also sit on maybeboard cards; only the deck's own count here.
    proxies = sorted(n for n, t in tags.items()
                     if any(x.lower() == "proxy" for x in t) and n in in_deck)
    if proxies:
        out += ["", "# Proxies (tagged on Moxfield; also listed above)"]
        out += [f"{in_deck[n]} {n}" for n in proxies]
    other = sorted({x for t in tags.values() for x in t if x.lower() != "proxy"})
    if other:
        print(f"  note: {name} has untracked tags: {', '.join(other)}")
    maybe = boards.get("maybeboard", {"count": 0})
    if maybe["count"]:
        out += ["", "# Considering"] + board_lines(maybe)

    path = os.path.join(BASE, "decks", f"{name}.txt")
    with open(path, "w") as fh:
        fh.write("\n".join(out) + "\n")
    print(f"{name}: {deck['name']!r} -> {path} "
          f"({boards['mainboard']['count']} main + {boards['commanders']['count']} cmdr"
          f" + {len(proxies)} proxied + {maybe['count']} considering)")


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
