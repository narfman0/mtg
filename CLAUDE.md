# MTG workspace

- My decks live on Moxfield (source of truth); `decks/` holds cached snapshots, one file per deck (e.g. `decks/satoru.txt`), in plain decklist format: `<count> <Card Name>` per line — mainboard, blank line, commander(s), then an optional `# Considering` section (the Moxfield maybeboard; candidates, not part of the deck).
- When I ask about "my deck" or a deck by name, refresh the cache with `python3 sync_decks.py` (deck name → Moxfield ID mapping is in that script), then read the matching file in `decks/` — don't ask me to paste the list. If Moxfield is unreachable, use the cached file and tell me it may be stale.
- When I say I've changed a deck, re-sync to pull the change from Moxfield. Don't hand-edit deck files (sync overwrites them); if my change isn't on Moxfield yet, remind me to make it there first.
- Card lookups and rules questions go through the mtg skill (offline oracle database + Comprehensive Rules) — never from memory.
