---
name: mtg
description: Answer Magic: The Gathering questions using the offline card database and Comprehensive Rules. Use for any MTG card lookup, deck analysis, rules question, or interaction question — never answer card text or rules details from memory.
---

# MTG offline reference

Three local data sources — the card database, the Comprehensive Rules, and an EDHREC page cache; always verify card text, rules, and play rates against them instead of memory. All paths below are relative to the repo root (this skill lives in the repo at `.claude/skills/mtg/`).

## Decks (Moxfield is source of truth, `decks/` is a cache)

The user's decks live on Moxfield; `decks/*.txt` are cached snapshots. Refresh with:

```bash
python3 sync_decks.py        # all decks, or pass names: sync_decks.py satoru
```

Deck names → Moxfield public IDs live in `DECKS` at the top of that script (add new decks there). The script auto-commits and pushes deck changes (repo: github.com/narfman0/mtg), so `git log -p decks/<name>.txt` is the deck's change history. Sync before analyzing a deck's contents or when the user says a deck changed; if offline or Moxfield errors, fall back to the cached file and note it may be stale. File format: mainboard lines (`<count> <name>`), blank line, commander(s), then an optional `# Considering` section mirroring the Moxfield maybeboard — considering cards are candidates, NOT in the deck; exclude them from deck counts and analysis unless asked. The Moxfield API is read-only for us, so don't hand-edit deck files (sync overwrites them) — if the user reports a change that isn't on Moxfield yet, remind them to make it there, then sync.

## Card database

`oracle-cards.jsonl` — Scryfall "Oracle Cards" bulk export (JSONL, one card per line, one entry per unique card name, ~38k cards). It is gitignored (regenerable); `python3 sync_cards.py` creates or refreshes it — see "Refreshing the data" below. Useful fields: `name`, `mana_cost`, `cmc`, `type_line`, `oracle_text`, `power`/`toughness`, `color_identity`, `keywords`, `legalities` (dict, e.g. `.commander` — `legal`/`banned`/`not_legal`), `game_changer` (bool: on the official Commander Game Changers list, which is the bracket 2/3 boundary — 53 cards), `prices.usd`, `edhrec_rank` (lower = more played), `card_faces` (for double-faced/split cards, which have ` // ` in `name` and their text under faces, not top level).

Single lookup:

```bash
python3 card.py "exact or partial name"
```

Exact matches print alone; otherwise substring matches (max 20). Output carries the Commander legality and flags Game Changers. Art-series prints, tokens and emblems are skipped — they reuse real card names with no rules text; apply the same filter (`layout` not in `art_series`/`token`/`double_faced_token`/`emblem`/`minigame`) when scanning the file yourself, or a token will shadow the real card. For batch analysis (whole decklists, curve stats, searches by oracle text/color/price), stream the JSONL in a Python script — loading all lines with `json.loads` takes ~2s. When matching decklist names, also index `name.split(' // ')[0]` since deck sites use front-face names.

If a name misses, try a substring of it — decklist sources sometimes garble names, and a card genuinely absent from the file probably doesn't exist under that name (tell the user rather than guessing).

## EDHREC (cached locally in `edhrec/`)

Popularity/synergy data for commanders, cards and themes is mirrored from `json.edhrec.com` into `edhrec/` (gzipped JSON, gitignored, regenerable). Query it offline — never fetch edhrec.com for something the cache holds:

```bash
python3 edhrec.py commander krenko        # themes, top + high-synergy cards, deck count
python3 edhrec.py rec satoru -n 30        # recommended cards the deck is NOT running
python3 edhrec.py rec satoru --by synergy --max-price 15   # synergy order, budget filter
python3 edhrec.py cuts norin              # deck's cards, least-played first (cut candidates)
python3 edhrec.py avg rinseri             # diff vs EDHREC's average decklist
python3 edhrec.py card "goblin bombardment"   # play rate, salt, top commanders
python3 edhrec.py theme goblins           # theme staples
python3 edhrec.py list                    # cache contents + age
```

`commander`/`rec`/`cuts`/`avg` take a deck name from `decks/`; `commander` and `card` also accept any card name. Two numbers appear in every row: **inclusion** (`num_decks/potential_decks` — share of decks that could run the card and do) and **synergy** (EDHREC's lift over the card's baseline play rate; high synergy = played *because of* this commander). Read raw pages with `read_page("commanders/<slug>")` from `sync_edhrec.py` for anything the CLI doesn't print — the JSON also carries mana curves, bracket/budget splits, combo counts, and `similar` commanders.

Refresh (conditional requests, so re-syncs are cheap; skips pages fetched within `--max-age`, default 3 days):

```bash
python3 sync_edhrec.py                    # commander + average-deck page per deck commander
python3 sync_edhrec.py --themes --cards   # + top themes, + a page per card in every deck (slow, ~10 min)
python3 sync_edhrec.py "Ygra, Eater of All"   # a commander that isn't one of the user's decks
```

A cache miss prints the exact sync command to run. Pages older than 7 days print a staleness note when queried — EDHREC recomputes weekly, so a week-old page is still usable; say so rather than refusing. Theme pages live under `tags/<slug>`, not `themes/`.

## Comprehensive Rules

`MagicCompRules.txt` — official Comprehensive Rules (check the "effective as of" line near the top when currency matters). Structure: table of contents at top, numbered rules (`NNN.Nx` subrules), then a glossary near the end. Long lines — one rule per line, so `grep -n` works well:

- By rule number: `grep -n "^702\.49" MagicCompRules.txt` (keyword abilities live in 702; e.g. ward 702.21, ninjutsu 702.49; combat is 506–511; layers 613; state-based actions 704).
- By phrase: `grep -in "put onto the battlefield attacking" MagicCompRules.txt`
- Glossary entry: `grep -n "^Ninjutsu$" MagicCompRules.txt` then Read around that line.

Read the matching rule *and its subrules* (the following `NNN.Nx` lines) before answering — the edge cases live in subrules.

## Refreshing the data

**Run `python3 sync_cards.py` before the first card lookup of a session.** It is
a no-op costing nothing when the data is fresh, so just run it — do not inspect
the file's mtime first to decide.

```bash
python3 sync_cards.py                 # refresh if older than 7 days (the default)
python3 sync_cards.py --max-age 0     # ask Scryfall whether a newer file exists
python3 sync_cards.py --check         # report staleness only; exit 1 if due
```

Scryfall publishes no incremental/delta feed — the bulk files are rebuilt whole
each day — so the script's cheap path is skipping the download, not patching the
file. Under `--max-age` it does not touch the network at all; past that it reads
the few-KB bulk-data metadata endpoint and only pulls the ~25 MB archive when
Scryfall's `updated_at` is newer than the local copy.

Because `oracle-cards.jsonl` is gitignored, git cannot show what a refresh
changed. The two fields that matter for deckbuilding — Commander legality and
the `game_changer` flag — are snapshotted in the committed `cards-status.json`,
and each sync diffs against it and prints bans, unbans, and Game Changer
changes. **Report those lines to the user** rather than swallowing them; a new
ban can invalidate a deck. Commit `cards-status.json` when it changes.

If Scryfall is unreachable the script keeps the cached file and says so — use it
and tell the user it may be stale, same as with a deck sync.

The Comprehensive Rules are not scripted: new releases appear at
https://magic.wizards.com/en/rules (plain-text link, URL contains the effective
date). Check the "effective as of" line in `MagicCompRules.txt` when currency
matters.

## Context

The user pilots a Satoru Umezawa (Dimir ninjutsu) Commander deck. Key commander interactions verified previously: Satoru grants each creature card in hand ninjutsu {2}{U}{B}; creatures put onto the battlefield attacking (ninjutsu) never "attacked", so "whenever ~ attacks" triggers don't fire (rule 508.3a/508.4) — prefer enters/combat-damage triggers when suggesting ninjutsu payoffs.
