#!/usr/bin/env python3
"""Sync decks/ from Moxfield (source of truth). Local files are a cache.

Usage: sync_decks.py [deck ...]     (no args = sync all)

Writes decks/<name>.txt as: mainboard, blank line, commander(s), then one
section per Moxfield tag the deck's author put on cards. Two tags keep
their long-standing headings: "# Proxies" (cards carrying "proxy" -- a
subset of the list above, not extra cards) and "# Purchased" (cards tagged
"purchased" -- bought but not necessarily arrived, so usually still
maybeboard entries, marked [considering]). Every other tag gets a
"# Tagged <tag>" section in the same shape ("printme", say), so a new tag
on Moxfield needs no change here. Then a "# Considering" section (the
maybeboard: candidates, not part of the deck). Deck changes are committed
and pushed automatically.

    sync_decks.py --tag printme        (no sync: list every card carrying the tag, across the cached decks)
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
    "meren": "91xtZt8BVUi4GhSnVdf00Q",
}

BASE = os.path.dirname(os.path.abspath(__file__))
# the tags with a heading of their own; any other tag is "# Tagged <tag>"
HEADINGS = {
    "proxy": "# Proxies (tagged on Moxfield; also listed above)",
    "purchased": "# Purchased (tagged on Moxfield; [considering] = not in the deck yet)",
}


def tagged(tag, names=None):
    """{card name: [(deck, count)]} for every card carrying `tag` in the cached deck files --
    what a print run wants, without touching Moxfield."""
    tag = tag.lower()
    want = {"proxy": HEADINGS["proxy"], "purchased": HEADINGS["purchased"]}.get(tag, f"# Tagged {tag} (")
    out = {}
    for name in names or DECKS:
        path = os.path.join(BASE, "decks", f"{name}.txt")
        if not os.path.exists(path):
            continue
        section = None
        for line in open(path).read().splitlines():
            if line.startswith("# "):
                section = line
                continue
            if section and section.startswith(want) and line.strip():
                count, _, card = line.partition(" ")
                out.setdefault(card.replace("  [considering]", ""), []).append((name, int(count)))
    return out
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
    maybe = boards.get("maybeboard", {"count": 0})
    in_maybe = {v["card"]["name"]: v["quantity"]
                for v in maybe.get("cards", {}).values()}
    # one section per tag, in a fixed order: proxy, purchased, then the rest alphabetically.
    # A tag on a card in neither board (a deleted card) is skipped. "purchased" is the
    # in-the-mail marker -- bought, not necessarily arrived -- so it usually sits on
    # maybeboard cards, which are marked [considering]; the same mark serves every tag.
    by_tag = {}
    for card_name, card_tags in tags.items():
        for t in card_tags:
            by_tag.setdefault(t.lower(), set()).add(card_name)
    counts = {}
    for tag in sorted(by_tag, key=lambda t: (t not in HEADINGS, list(HEADINGS).index(t) if t in HEADINGS else 0, t)):
        names = sorted(n for n in by_tag[tag] if n in in_deck or n in in_maybe)
        if not names:
            continue
        counts[tag] = len(names)
        out += ["", HEADINGS.get(tag, f"# Tagged {tag} (tagged on Moxfield; [considering] = not in the deck yet)")]
        out += [f"{in_deck.get(n) or in_maybe[n]} {n}" + ("" if n in in_deck else "  [considering]") for n in names]
    if maybe["count"]:
        out += ["", "# Considering"] + board_lines(maybe)

    path = os.path.join(BASE, "decks", f"{name}.txt")
    with open(path, "w") as fh:
        fh.write("\n".join(out) + "\n")
    tagged = ", ".join(f"{k} {t}" for t, k in counts.items()) or "no tags"
    print(f"{name}: {deck['name']!r} -> {path} "
          f"({boards['mainboard']['count']} main + {boards['commanders']['count']} cmdr"
          f" + {maybe['count']} considering; {tagged})")


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
    args = sys.argv[1:]
    if args[:1] == ["--tag"]:
        if len(args) < 2:
            sys.exit("usage: sync_decks.py --tag <tag> [deck ...]")
        found = tagged(args[1], args[2:] or None)
        for card, where in sorted(found.items()):
            print(f"{max(k for _, k in where)} {card}" + (f"    ({', '.join(d for d, _ in where)})" if len(where) > 1 else ""))
        print(f"{len(found)} card(s) tagged {args[1]!r}" + (f"; {sum(len(w) > 1 for w in found.values())} in more than one deck" if found else ""), file=sys.stderr)
        return
    names = args or list(DECKS)
    for name in names:
        if name not in DECKS:
            sys.exit(f"unknown deck {name!r}; known: {', '.join(DECKS)}")
        sync(name, DECKS[name])
    commit_and_push()


if __name__ == "__main__":
    main()
