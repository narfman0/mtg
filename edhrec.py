#!/usr/bin/env python3
"""Query the local EDHREC cache (written by sync_edhrec.py) -- no network.

Usage:
  edhrec.py commander <deck|"Commander Name">   overview: themes, top + high-synergy cards
  edhrec.py rec <deck> [-n N] [--max-price P]   recommended cards you are NOT running
  edhrec.py cuts <deck>                         your cards, least-played first
  edhrec.py avg <deck>                          diff against EDHREC's average decklist
  edhrec.py card <name>                         a card's page: play rate, salt, top commanders
  edhrec.py theme <slug> [-n N]                 a theme page's staples
  edhrec.py list                                what is in the cache and how old it is

"Inclusion" is num_decks/potential_decks: of the decks that could run a card,
the share that do. "Synergy" is EDHREC's lift over that card's baseline play
rate -- high synergy means the card is played *because of* this commander.
"""
import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE, "edhrec")
BASICS = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"}
BASICS |= {f"Snow-Covered {b}" for b in BASICS}
TYPE_LISTS = ("creatures", "instants", "sorceries", "utilityartifacts",
              "enchantments", "battles", "planeswalkers", "utilitylands",
              "manaartifacts", "lands")
# EDHREC promotes these cards into their own boxes and then *omits* them from
# the per-type lists -- the two sets are disjoint. Scanning only TYPE_LISTS
# silently drops ~35 of a page's highest-profile cards, so recommendations must
# read both.
FEATURE_LISTS = ("highsynergycards", "topcards", "gamechangers", "newcards")
REC_LISTS = FEATURE_LISTS + TYPE_LISTS

sys.path.insert(0, BASE)
from sync_edhrec import deck_sections, read_page, slugify, load_index  # noqa: E402


def die(msg):
    sys.exit(f"edhrec.py: {msg}")


def page(rel, hint):
    data = read_page(rel)
    if data is None:
        die(f"{rel} not cached -- run: python3 sync_edhrec.py {hint}")
    meta = load_index().get(rel, {})
    if meta.get("fetched"):
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(meta["fetched"])).days
        if age >= 7:
            print(f"[cache is {age} days old; refresh with sync_edhrec.py]\n")
    return data


def cardlists(data):
    return {cl["tag"]: cl for cl in data.get("container", {}).get("json_dict", {}).get("cardlists", [])}


def resolve(target):
    """-> (deck_path or None, sections). A non-deck target is read as a commander."""
    path = os.path.join(BASE, "decks", f"{target}.txt")
    if os.path.exists(path):
        return path, deck_sections(path)
    return None, {"mainboard": [], "commanders": [target], "considering": [], "proxies": []}


def front(names):
    """Deck files use full names; EDHREC lists split/DFC cards by front face too."""
    return {n for name in names for n in (name, re.sub(r" // .*", "", name))}


def pct(cv):
    pot = cv.get("potential_decks") or 0
    return 100.0 * cv.get("num_decks", 0) / pot if pot else 0.0


def row(cv, extra=""):
    syn = cv.get("synergy")
    syn = f"{syn:+6.0%}" if isinstance(syn, (int, float)) else " " * 7
    return f"  {pct(cv):5.1f}%  {syn}  {cv['name']}{extra}"


def prices():
    """name -> usd, from the Scryfall oracle dump (for --max-price)."""
    out = {}
    db = os.path.join(BASE, "oracle-cards.jsonl")
    if not os.path.exists(db):
        return out
    with open(db) as fh:
        for line in fh:
            c = json.loads(line)
            usd = (c.get("prices") or {}).get("usd")
            if usd:
                out[c["name"]] = float(usd)
                out[c["name"].split(" // ")[0]] = float(usd)
    return out


def cmd_commander(args):
    for name in resolve(args.target)[1]["commanders"]:
        data = page(f"commanders/{slugify(name)}", args.target)
        lists = cardlists(data)
        # On a commander page, card.num_decks is the commander's own deck count.
        card = data.get("container", {}).get("json_dict", {}).get("card") or {}
        total = card.get("num_decks") or 0
        print(f"== {data.get('header') or name}  ({total:,} decks on EDHREC)")
        themes = ", ".join(f"{t['value']} ({t['count']:,})" for t in (data.get("tag_counts") or [])[:8])
        print(f"themes: {themes}\n")
        for tag in ("highsynergycards", "topcards", "gamechangers", "newcards"):
            cl = lists.get(tag)
            if not cl:
                continue
            print(f"{cl['header']}:")
            for cv in cl["cardviews"][:args.n]:
                print(row(cv))
            print()


def cmd_rec(args):
    path, deck = resolve(args.target)
    if not path:
        die(f"no deck named {args.target!r}; rec/cuts/avg need a deck in decks/")
    have = front(deck["mainboard"] + deck["commanders"])
    maybe = front(deck["considering"])
    usd = prices() if args.max_price else {}
    for name in deck["commanders"]:
        data = page(f"commanders/{slugify(name)}", args.target)
        lists = cardlists(data)
        seen, out, basics, gc = set(), [], 0, set()
        for tag in REC_LISTS:
            for cv in lists.get(tag, {}).get("cardviews", []):
                if cv["name"] in have or cv["name"] in seen:
                    continue
                if cv["name"] in BASICS and not args.basics:
                    basics += 1  # "run more Plains" is never the answer
                    continue
                if args.max_price and usd.get(cv["name"], 0) > args.max_price:
                    continue
                if tag == "gamechangers":
                    gc.add(cv["name"])  # bracket-relevant: 3 is the bracket 3 cap
                seen.add(cv["name"])
                out.append(cv)
        out.sort(key=lambda cv: -(cv.get("synergy") or 0) if args.by == "synergy" else -pct(cv))
        print(f"== recommended for {name}, not in the {args.target} deck "
              f"(by {args.by}{f', <= ${args.max_price:g}' if args.max_price else ''}; "
              f"[considering] = already on your maybeboard)\n")
        for cv in out[:args.n]:
            tail = f"  ${usd[cv['name']]:g}" if cv["name"] in usd else ""
            if cv["name"] in gc:
                tail += "  [game changer]"
            if cv["name"] in maybe:
                tail += "  [considering]"
            print(row(cv, tail))
        tail = f"; skipped {basics} basic land(s) (--basics to keep)" if basics else ""
        print(f"\n{len(out)} candidates total; {len(have)} of your cards already match{tail}.")


def cmd_cuts(args):
    path, deck = resolve(args.target)
    if not path:
        die(f"no deck named {args.target!r}")
    mainboard = deck["mainboard"]
    for name in deck["commanders"]:
        data = page(f"commanders/{slugify(name)}", args.target)
        lists = cardlists(data)
        stats = {cv["name"]: cv for cl in lists.values() for cv in cl["cardviews"]}
        rated = [stats[c] for c in mainboard if c in stats]
        unrated = [c for c in mainboard if c not in stats]
        rated.sort(key=lambda cv: pct(cv))
        print(f"== decks/{args.target}.txt cards by {name} play rate, least-played first\n")
        for cv in rated[:args.n]:
            print(row(cv))
        print(f"\nnot on EDHREC's lists for this commander ({len(unrated)}) -- "
              f"off-meta picks, basics, or just below the cutoff:")
        print("  " + ", ".join(unrated) if unrated else "  (none)")


def cmd_avg(args):
    path, deck = resolve(args.target)
    if not path:
        die(f"no deck named {args.target!r}")
    have = front(deck["mainboard"] + deck["commanders"])
    for name in deck["commanders"]:
        data = page(f"average-decks/{slugify(name)}", args.target)
        avg = {cv["name"] for cl in cardlists(data).values() for cv in cl["cardviews"]}
        shared = sorted(avg & have)
        print(f"== decks/{args.target}.txt vs EDHREC's average {name} deck\n")
        print(f"shared ({len(shared)}/{len(avg)}): {', '.join(shared)}\n")
        print(f"in the average deck, not yours ({len(avg - have)}):")
        print("  " + ", ".join(sorted(avg - have)))


def cmd_card(args):
    # EDHREC indexes double-faced cards by front face, so accept either spelling.
    rels = [f"cards/{slugify(args.target)}", f"cards/{slugify(args.target, front_only=True)}"]
    rel = next((r for r in rels if read_page(r)), rels[0])
    data = page(rel, f'--card "{args.target}"')
    card = data.get("container", {}).get("json_dict", {}).get("card", {}) or {}
    lists = cardlists(data)
    n, pot = card.get("num_decks", 0), card.get("potential_decks", 0)
    print(f"== {card.get('name') or args.target}  |  {card.get('type_line', '')}")
    bits = [f"in {n:,} of {pot:,} possible decks ({100.0 * n / pot if pot else 0:.1f}%)"]
    # prices is vendor -> {price, slug}; tcgplayer is the USD reference here.
    vendors = card.get("prices") or {}
    for vendor in ("tcgplayer", "cardkingdom", "cardmarket"):
        if (vendors.get(vendor) or {}).get("price"):
            bits.append(f"${vendors[vendor]['price']:g} ({vendor})")
            break
    if card.get("salt"):  # only cards on EDHREC's salt list carry a score
        bits.append(f"salt {card['salt']:.2f}")
    print("  |  ".join(bits) + "\n")
    for tag in ("topcommanders", "newcommanders", "highliftcards", "topcards"):
        cl = lists.get(tag)
        if not cl:
            continue
        print(f"{cl['header']}:")
        for cv in cl["cardviews"][:args.n]:
            print(row(cv))
        print()


def cmd_theme(args):
    data = page(f"tags/{slugify(args.target)}", f"--themes")
    lists = cardlists(data)
    print(f"== {data.get('header') or args.target}\n")
    for tag in ("topcommanders",) + FEATURE_LISTS + TYPE_LISTS:
        cl = lists.get(tag)
        if not cl:
            continue
        print(f"{cl['header']}:")
        for cv in cl["cardviews"][:args.n]:
            print(row(cv))
        print()


def cmd_list(args):
    index = load_index()
    if not index:
        die("cache is empty -- run: python3 sync_edhrec.py")
    now = datetime.now(timezone.utc)
    by_kind = {}
    for rel, meta in index.items():
        if meta.get("missing"):
            continue
        kind = rel.split("/")[0]
        age = (now - datetime.fromisoformat(meta["fetched"])).total_seconds() / 86400
        by_kind.setdefault(kind, []).append((rel, age))
    for kind, entries in sorted(by_kind.items()):
        oldest = max(a for _, a in entries)
        print(f"{kind}: {len(entries)} pages, oldest {oldest:.1f} days")
        if kind != "cards" or args.n > 20:
            for rel, age in sorted(entries)[:args.n]:
                print(f"  {rel.split('/', 1)[1]}  ({age:.1f}d)")
    size = sum(os.path.getsize(p) for p in glob.glob(os.path.join(CACHE, "**", "*.gz"), recursive=True))
    pages = sum(1 for m in index.values() if not m.get("missing"))
    print(f"\n{pages} pages, {size / 1e6:.1f} MB")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["commander", "rec", "cuts", "avg", "card", "theme", "list"])
    ap.add_argument("target", nargs="?", default="")
    ap.add_argument("-n", type=int, default=25, help="rows per list (default 25)")
    ap.add_argument("--by", choices=["inclusion", "synergy"], default="inclusion",
                    help="rec sort order (default inclusion)")
    ap.add_argument("--basics", action="store_true",
                    help="rec: keep basic lands in the recommendations")
    ap.add_argument("--max-price", type=float, metavar="USD",
                    help="rec: skip cards over this price (uses oracle-cards.jsonl)")
    args = ap.parse_args()
    if args.command != "list" and not args.target:
        die(f"{args.command} needs a target")
    globals()[f"cmd_{args.command}"](args)


if __name__ == "__main__":
    main()
