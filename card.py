#!/usr/bin/env python3
"""Look up MTG cards in the offline Scryfall oracle database.

Usage: card.py <name or substring> [more terms...]
Exact (case-insensitive) name matches print alone; otherwise all cards whose
name contains the joined query are printed (capped at 20).
"""
import json
import os
import sys

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "oracle-cards.jsonl")
NONCARD = {"art_series", "token", "double_faced_token", "emblem", "minigame"}


def fmt(c):
    faces = c.get("card_faces") or [c]
    out = []
    for f in faces:
        pt = f"{f['power']}/{f['toughness']} " if "power" in f else ""
        loy = f"[{f['loyalty']}] " if "loyalty" in f else ""
        out.append(f"{f['name']} {f.get('mana_cost', '')} | {f['type_line']} | {pt}{loy}")
        if f.get("oracle_text"):
            out.append(f["oracle_text"])
    usd = (c.get("prices") or {}).get("usd")
    legal = c.get("legalities", {}).get("commander", "?")
    # Game Changers are the bracket 2/3 boundary, so flag them next to legality.
    gc = " | GAME CHANGER" if c.get("game_changer") else ""
    out.append(f"-- ${usd} | commander: {legal}{gc} | edhrec rank: {c.get('edhrec_rank')}")
    return "\n".join(out)


def main():
    query = " ".join(sys.argv[1:]).lower()
    if not query:
        sys.exit("usage: card.py <name or substring>")
    exact, partial = [], []
    with open(DB) as fh:
        for line in fh:
            c = json.loads(line)
            # Art-series prints, tokens and emblems reuse real card names with
            # no rules text, so they'd shadow the card actually being looked up.
            if c.get("layout") in NONCARD:
                continue
            name = c["name"].lower()
            if name == query or query in name.split(" // "):
                exact.append(c)
            elif query in name:
                partial.append(c)
    hits = exact or partial
    if not hits:
        print(f"no match for {query!r}")
        return
    for c in hits[:20]:
        print(fmt(c))
        print()
    if len(hits) > 20:
        print(f"...and {len(hits) - 20} more matches")


if __name__ == "__main__":
    main()
