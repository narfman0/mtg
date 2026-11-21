# Tivit, Seller of Secrets: build notes

List: `drafts/tivit.txt` (v3, 100 cards, 33 lands). Also on fullpod-dev as "Tivit, councilmember of the people" (`4e0b73db3543`). Not on Moxfield yet. Card text checked against Scryfall data of 2026-11-20.

## Constraints
- Bracket 3, not cEDH. Game Changers: Smothering Tithe, Rhystic Study (max 3). Plea for Power is the one extra-turn card.
- Left out on purpose: Time Sieve, Thassa's Oracle, Consecrated Sphinx, Cyclonic Rift, fast mana, tutors.
- Time Sieve is NOT a Game Changer, but the Tivit + Academy Manufactor Sieve loop chains extra turns. Official Bracket 3 text (Feb 2025 beta): "You shouldn't expect to be chaining extra turns together." One use per game is fine; a loop is Bracket 4 in practice. Sieve would also eat the artifacts the alt-win cards need.

## Plan
- Tivit's vote makes one token per vote for you, whoever casts it. Your votes: Tivit's extra vote, Brago's Representative, Ballot Broker, plus one per opponent.
- Opponents' votes split the tokens, so the plan needs Academy Manufactor (each vote makes a Treasure, a Clue and a Food) or Illusion of Choice (you choose every vote).
- Blink Tivit (Ephemerate, Cloudshift, Ghostly Flicker, Restoration Angel, Soulherder, Brago) for another vote.
- Win: Revel in Riches (10 Treasures at upkeep), Mechanized Production (8 same-name artifacts), or drain with Mirkwood Bats (every opponent loses 1 per token you create or sacrifice), Marionette Master (one opponent), Kambal, The Sackville-Bagginses.
- Realistic win: turn 9-12 in a real pod. Both enchantments are answerable for a full turn cycle.

## Changes by version
- v1: Tivit voting/politics + blink list.
- v2 (13 swaps): + Revel in Riches, Mechanized Production, Marionette Master, The Sackville-Bagginses, Restoration Angel, Skyclave Apparition, Ravenous Chupacabra, Archaeomancer, Wall of Omens, Whirler Rogue, Reflector Mage, Flickerwisp, Sphinx's Revelation. Cut Coercive Portal, Vault 11, Messenger Jays, Lieutenants of the Guard, Sadistic Shell Game, Commander's Sphere, Tempt with Reflections, Capital Punishment, Conjurer's Closet, Ghostly Prison, Fellwar Stone, Reliquary Tower, Rogue's Passage. 35 to 33 lands.
- v3: Magister of Worth to Spell Queller; Split Decision to Venser, Shaper Savant; Trap the Trespassers to Lotho, Corrupt Shirriff; one Swamp to a Plains (W pips 36, U 30, B 17).

## Engine notes (read from source, not seen in a game)
- XMage `VoteHandler.doVotes`; CPUs appear to vote the first-listed option (Evidence, Grace, Denial, Time...). Only Tyrant's Choice has AI vote logic.
- So Magister of Worth likely returns every graveyard's creatures (grace beats your votes), and Split Decision is a narrow counter. Grudge Keeper and Plea for Power should work in your favour.
- No Tivit vote has been observed: the CPU test game (to turn 12, 0 errors) never cast Tivit because the `first` policy accepts every mulligan. Next step is a client policy that keeps its hand and casts spells.
- Prompt-heavy cards to watch: Soulherder, Displacer Kitten, Teleportation Circle, Brago, Panharmonicon + Tivit.

## Cost
Buy list about $233 for 61 cards (Tivit $10.41 not included; Plea for Power and Tyrant's Choice unpriced). Smothering Tithe $61.43, Displacer Kitten $35.25, Revel in Riches $20.11 are half of it.

## Cheaper options (card text read, not guessed)
- Safe: Dovin's Veto to Negate (-$4.15; only loses "can't be countered"). Displacer Kitten to Felidar Guardian (-$32.12; may exile and return any other permanent you control, loses the per-spell trigger). Master of Ceremonies ($15.68; symmetrical upkeep resources, low impact) to a cheap enter-effect creature, still to pick and read.
- Proxy route (tcg-mint / MPC): Tithe, Kitten, Revel are $117 of the $233. With the three swaps above the buy list is about $70.
- Not good swaps:
  - Monologue Tax: "Whenever an opponent casts their second spell each turn, you create a Treasure." Not a draw tax and no replacement for Smothering Tithe.
  - Whitemane Lion: bounces a creature you control to hand, not a free blink, so not a Teleportation Circle replacement.
  - Esper Panorama: colourless; {1}, T, sacrifice for a tapped basic Plains/Island/Swamp. Slower than Raffine's Tower ($15.53, tapped tri-land with cycling {3}).
  - Phyrexian Arena ($2.91): draws for you, not a tax.
- Lotho ($7.98) can go for a cheap two-drop.

## Open
- Route choice (proxy vs swaps) not decided; list is unchanged from v3.
- Not tested in fullpod with Tivit cast.
- Not on Moxfield; the list file is the source until it is.
