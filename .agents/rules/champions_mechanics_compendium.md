# Pokémon Champions — Regulation M-C Mechanics Compendium

## 1. Stat Point (SP) System (Level 50)
- **Total Budget:** Exactly `66 SP` per Pokémon.
- **Single-Stat Cap:** Maximum `32 SP` in any single stat (`HP`, `Atk`, `Def`, `SpA`, `SpD`, `Spe`).
- **Discretized Conversion:**
  * For `SP = 0`: `EV = 0`
  * For `1 ≤ SP ≤ 32`: `EV = 4 + 8 × (SP - 1)`
- **Level 50 Formula (Sequential Floor Rounding):**
  * **HP:** `⌊(2 × Base + 31 + ⌊EV / 4⌋) × 50 / 100⌋ + 60`
  * **Other Stats:** `⌊(⌊(2 × Base + 31 + ⌊EV / 4⌋) × 50 / 100⌋ + 5) × NatureMult⌋`
  * **Stat Alignments:** `+10%` (`1.1x`) / `-10%` (`0.9x`), applied *after* base + SP stat computation and always rounded down (`floor`).

## 2. Mega Evolution & Speed Scaling
- **Activation Phase:** Mega Evolution resolves during the Activation Phase prior to any move execution (before `Fake Out` and `Protect`).
- **Instantaneous Speed Recalibration:** Effective speed tiers update immediately upon Mega Evolution.
- **Simultaneous Mega Evolution:** If both sides Mega Evolve on the same turn, the Pokémon with the higher *post-Mega* speed tier resolves and triggers its ability first.

## 3. Redirection & Terrain Matrix
- **Spread Move Redirection Immunity:** `Follow Me` and `Rage Powder` cannot redirect spread moves (`Earthquake`, `Heat Wave`, `Muddy Water`, `Make It Rain`, `Dazzling Gleam`, `Rock Slide`, `Hyper Voice`, `Discharge`).
- **Psychic Terrain Priority Lockout:** Grounded Pokémon on Psychic Terrain are immune to priority moves (`Fake Out`, `Sucker Punch`, `Grassy Glide`, `Extreme Speed`, Prankster status moves).
- **Airborne Exemption:** Airborne Pokémon (`Flying`-types such as `Charizard`, `Pelipper`, `Salamence`, `Staraptor`, or `Levitate` / `Air Balloon` holders) receive zero priority protection from Psychic Terrain.

## 4. Official VGC Damage Modifiers (Sequential Rounding Scale)
- **Spread Move Penalty (Doubles):** `3072 / 4096` (`0.75x`)
- **Screens (`Reflect` / `Light Screen` in Doubles):** `2732 / 4096` (`~0.667x`)
- **Aura Abilities (`Fairy Aura`, `Dark Aura`):** `5461 / 4096` (`~1.333x`)
- **Weather Modifiers:** `1.5x` boost (`6144 / 4096`) / `0.5x` reduction (`2048 / 4096`) in Sun and Rain.
- **STAB:** `1.5x` (`6144 / 4096`), or `2.0x` (`8192 / 4096`) with `Adaptability`.

## 5. Competitive Synergies & Tactical Logic Matrix
Never evaluate a move, stat spread, or tactical option in isolation without verifying active synergistic multipliers across abilities, items, weather, and terrain:
- **No Guard Synergy:** Abilities like `No Guard` (`Raichu-Mega-Y`, `Machamp`, `Golurk`) eliminate all accuracy drawbacks, guaranteeing 100% accuracy for both user attacks and incoming attacks. Moves like `Zap Cannon` (nominal 50% accuracy) become 100% accurate nukes that inflict guaranteed paralysis. Never claim `Zap Cannon` or `Focus Blast` is inaccurate or high-variance on a `No Guard` user.
- **Sheer Force + Life Orb Recoil Nullification:** When a Pokémon with `Sheer Force` uses a move with secondary chances (`Sludge Bomb`, `Earth Power`, `Flash Cannon`, `Ice Beam`, `Heat Wave`), base power is boosted by `1.3x` and `Life Orb` recoil is completely nullified while retaining the full `1.3x` damage boost (`1.69x` cumulative offensive multiplier).
- **Technician BP Thresholds:** `Technician` amplifies moves with base power ≤ 60 by `1.5x` (`Bullet Punch` 40 -> 60 BP, `Dual Wingbeat` 40 -> 60 BP per hit, `Electroweb` 55 -> 82.5 BP spread).
- **Psychic Surge + Expanding Force:** Under Psychic Terrain (or paired with `Psychic Surge`), `Expanding Force` base power increases from 80 to 120 BP and converts into an un-redirectable spread move that strikes both foes while grounded allies are protected from priority.
- **Weather Synergies:**
  * **Rain:** Activates `Swift Swim` (2x Speed), eliminates the 1-turn charge on `Electro Shot` (granting immediate +1 Sp. Atk on turn 1), makes `Thunder` and `Hurricane` 100% accurate, and boosts Water damage by `1.5x`.
  * **Sun:** Activates `Chlorophyll` (2x Speed), allows instant `Solar Beam` / `Solar Blade` execution, boosts Fire damage by `1.5x`, and reduces Water damage by `0.5x`.
  * **Snow:** Activates `Slush Rush` (2x Speed), makes `Blizzard` 100% accurate, and grants a passive `1.5x` Physical Defense boost to all Ice-types.
  * **Sand:** Activates `Sand Rush` (2x Speed), `Sand Force` (1.3x to Rock/Ground/Steel attacks), and grants a passive `1.5x` Special Defense boost to all Rock-types.
- **Consumable Unburden Triggers:** Pokémon with `Unburden` (`Sneasler`, `Hawlucha`, `Drifblim`) immediately double their Speed upon consuming or losing their held item (`Focus Sash`, `Sitrus Berry`, `White Herb`, `Booster Energy`, or Seeds). Always factor post-consumption speed recalculations into action ordering.
- **Anti-Priority Protocols:** Before recommending priority attacks (`Fake Out`, `Sucker Punch`, `Grassy Glide`, `Prankster` status), verify that the target is airborne if under Psychic Terrain, and ensure the opponent does not have `Armor Tail` (`Farigiraf`), `Dazzling` (`Bruxish`), or `Queenly Majesty` (`Tsareena`) on the field.
