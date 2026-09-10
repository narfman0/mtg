---
name: mtg
description: Answer Magic: The Gathering questions using the offline card database and Comprehensive Rules. Use for any MTG card lookup, deck analysis, rules question, or interaction question — never answer card text or rules details from memory.
---

# MTG offline reference

Two local data sources; always verify card text and rules against them instead of memory. All paths below are relative to the repo root (this skill lives in the repo at `.claude/skills/mtg/`).

## Decks (Moxfield is source of truth, `decks/` is a cache)

The user's decks live on Moxfield; `decks/*.txt` are cached snapshots. Refresh with:

```bash
python3 sync_decks.py        # all decks, or pass names: sync_decks.py satoru
```

Deck names → Moxfield public IDs live in `DECKS` at the top of that script (add new decks there). The script auto-commits and pushes deck changes (repo: github.com/narfman0/mtg), so `git log -p decks/<name>.txt` is the deck's change history. Sync before analyzing a deck's contents or when the user says a deck changed; if offline or Moxfield errors, fall back to the cached file and note it may be stale. File format: mainboard lines (`<count> <name>`), blank line, commander(s), then an optional `# Considering` section mirroring the Moxfield maybeboard — considering cards are candidates, NOT in the deck; exclude them from deck counts and analysis unless asked. The Moxfield API is read-only for us, so don't hand-edit deck files (sync overwrites them) — if the user reports a change that isn't on Moxfield yet, remind them to make it there, then sync.

## Card database

`oracle-cards.jsonl` — Scryfall "Oracle Cards" bulk export (JSONL, one card per line, one entry per unique card name, ~38k cards). It is gitignored (regenerable); on a fresh clone, download it first — see "Refreshing the data" below. Useful fields: `name`, `mana_cost`, `cmc`, `type_line`, `oracle_text`, `power`/`toughness`, `color_identity`, `keywords`, `legalities` (dict, e.g. `.commander`), `prices.usd`, `edhrec_rank` (lower = more played), `card_faces` (for double-faced/split cards, which have ` // ` in `name` and their text under faces, not top level).

Single lookup:

```bash
python3 card.py "exact or partial name"
```

Exact matches print alone; otherwise substring matches (max 20). For batch analysis (whole decklists, curve stats, searches by oracle text/color/price), stream the JSONL in a Python script — loading all lines with `json.loads` takes ~2s. When matching decklist names, also index `name.split(' // ')[0]` since deck sites use front-face names.

If a name misses, try a substring of it — decklist sources sometimes garble names, and a card genuinely absent from the file probably doesn't exist under that name (tell the user rather than guessing).

## Comprehensive Rules

`MagicCompRules.txt` — official Comprehensive Rules (check the "effective as of" line near the top when currency matters). Structure: table of contents at top, numbered rules (`NNN.Nx` subrules), then a glossary near the end. Long lines — one rule per line, so `grep -n` works well:

- By rule number: `grep -n "^702\.49" MagicCompRules.txt` (keyword abilities live in 702; e.g. ward 702.21, ninjutsu 702.49; combat is 506–511; layers 613; state-based actions 704).
- By phrase: `grep -in "put onto the battlefield attacking" MagicCompRules.txt`
- Glossary entry: `grep -n "^Ninjutsu$" MagicCompRules.txt` then Read around that line.

Read the matching rule *and its subrules* (the following `NNN.Nx` lines) before answering — the edge cases live in subrules.

## Refreshing the data

Scryfall updates bulk data daily; the download URL is timestamped and changes. To refresh:

```bash
curl -s -A "mtg-deck-helper/1.0" "https://api.scryfall.com/bulk-data" \
  | python3 -c "import json,sys; print([d['jsonl_download_uri'] for d in json.load(sys.stdin)['data'] if d['type']=='oracle_cards'][0])"
# then curl that URL (same -A header; Scryfall 403s requests without a User-Agent),
# gunzip to oracle-cards.jsonl in the repo root
```

New rules releases appear at https://magic.wizards.com/en/rules (plain-text link, URL contains the effective date).

## Context

The user pilots a Satoru Umezawa (Dimir ninjutsu) Commander deck. Key commander interactions verified previously: Satoru grants each creature card in hand ninjutsu {2}{U}{B}; creatures put onto the battlefield attacking (ninjutsu) never "attacked", so "whenever ~ attacks" triggers don't fire (rule 508.3a/508.4) — prefer enters/combat-damage triggers when suggesting ninjutsu payoffs.
