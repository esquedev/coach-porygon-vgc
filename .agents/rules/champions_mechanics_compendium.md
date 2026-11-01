# Pokémon Champions — Regulation M-C Mechanics Compendium

## 1. Stat Point (SP) System (Level 50)
- **Total Budget:** Exactly `66 SP` per Pokémon.
- **Single-Stat Cap:** Maximum `32 SP` in any single stat (`HP`, `Atk`, `Def`, `SpA`, `SpD`, `Spe`).
- **Discretized Conversion:**
  * For `SP = 0`: `EV = 0`
  * For `1 ≤ SP ≤ 32`: `EV = 4 + 8 × (SP - 1)`
- **Level 50 Formula (Sequential Floor Rounding):**
  * **HP:** `⌊(2 × Base + 31 + ⌊EV / 4⌋) × 50 / 100⌋ + 60` $\equiv \text{Base} + \text{SP} + 75$ (unless Shedinja)
  * **Other Stats:** `⌊(⌊(2 × Base + 31 + ⌊EV / 4⌋) × 50 / 100⌋ + 5) × NatureMult⌋` $\equiv \lfloor (\text{Base} + \text{SP} + 20) \times \text{NatureMult} \rfloor$
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
- **Consumable Unburden Triggers:** Pokémon with `Unburden` (`Sneasler`, `Hawlucha`) immediately double their Speed upon consuming or losing their held item (`Focus Sash`, `Sitrus Berry`, `White Herb`, `Electric Seed`, `Psychic Seed`, `Grassy Seed`, `Misty Seed`). Always factor post-consumption speed recalculations into action ordering.
- **Anti-Priority Protocols:** Before recommending priority attacks (`Fake Out`, `Sucker Punch`, `Grassy Glide`, `Prankster` status), verify that the target is airborne if under Psychic Terrain, and ensure the opponent does not have `Armor Tail` (`Farigiraf`) or `Queenly Majesty` (`Tsareena`) on the field.

## 6. Dual-Typing Defensive Matrix, Compound Resistances & STAB Mechanics

### 6.1. Compound Type Effectiveness Scale
Against dual-typed defenders `[Type 1, Type 2]`, total elemental matchup effectiveness is the exact product of both individual matchup multipliers:
$$Eff = M(Type_{atk}, Type1_{def}) \times M(Type_{atk}, Type2_{def})$$

The official VGC calculation executes this via discrete integer shifts:
- **`0.0x` (Absolute Immunity):** Attack deals zero damage. Examples: Ground into `Flying` (`Charizard`, `Pelipper`, `Salamence`), Normal/Fighting into `Ghost` (`Gengar`, `Aegislash`), Electric into `Ground` (`Garchomp`, `Excadrill`), Psychic into `Dark` (`Tyranitar`, `Incineroar`), Dragon into `Fairy` (`Clefable`, `Primarina`).
- **`0.25x` (Double Resistance):** Damage is halved twice via floor truncation: $\lfloor \lfloor Damage / 2 \rfloor / 2 \rfloor$. Examples: Grass into `Fire/Flying` (`Charizard`), Fighting into `Poison/Ghost` (`Gengar`), Poison into `Steel/Fairy` (`Tinkaton`, `Mega Mawile`, `Klefki` $\to 0x$ immune), Bug into `Poison/Fighting` (`Sneasler`).
- **`0.5x` (Single Resistance):** Damage is halved: $\lfloor Damage / 2 \rfloor$.
- **`1.0x` (Neutral Matchup):** Damage modifier unchanged.
- **`2.0x` (Super Effective):** Damage is doubled: $Damage \times 2$.
- **`4.0x` (Double Weakness / 4x Weakness):** Damage is doubled twice: $(Damage \times 2) \times 2$. Key Regulation M-C archetypes:
  * **Rock ($4.0\times$):** Strikes `Fire/Flying` (`Charizard`, `Mega Charizard Y`, `Talonflame`), `Bug/Flying` (`Mega Pinsir`, `Vivillon`).
  * **Ice ($4.0\times$):** Strikes `Dragon/Ground` (`Garchomp`), `Dragon/Flying` (`Dragonite`, `Salamence`).
  * **Ground ($4.0\times$):** Strikes `Electric/Poison` (`Toxtricity`), `Fire/Poison` (`Salazzle`).
  * **Fighting ($4.0\times$):** Strikes `Rock/Dark` (`Tyranitar`, `Mega Tyranitar`), `Rock/Steel` (`Aggron`, `Bastiodon`).
  * **Fire ($4.0\times$):** Strikes `Bug/Steel` (`Scizor`, `Mega Scizor`, `Forretress`), `Grass/Ice` (`Abomasnow`, `Mega Abomasnow`).
  * **Grass ($4.0\times$):** Strikes `Water/Ground` (`Swampert`, `Mega Swampert`).

### 6.2. Grounding Exceptions
- **`Freeze-Dry`:** Multiplies effectiveness against `Water` targets by $2.0\times$ instead of $0.5\times$. Against `Water/Ground` (`Swampert`), compound effectiveness is $2.0 \times 2.0 = 4.0\times$. Against `Water/Flying` (`Pelipper`), it is $2.0 \times 1.0 = 2.0\times$.
- **`Scrappy` / `Mind's Eye`:** Bypasses `Ghost` type immunity to `Normal` and `Fighting` attacks, evaluating them at $1.0\times$ neutral damage.
- **`Thousand Arrows`:** Bypasses `Flying` type immunity, `Levitate`, and `Air Balloon`, striking with $1.0\times$ neutral Ground damage and permanently knocking airborne targets to the ground.

### 6.3. Dual-Type STAB & Ability-Induced Type Conversions
Damaging moves executed by a dual-typed Pokémon receive a Same Type Attack Bonus (STAB) if their effective move type matches either `Type 1` or `Type 2`:
- **Primary STAB ($1.5\times$):** Move type matches the Pokémon's primary type.
- **Secondary STAB ($1.5\times$):** Move type matches the Pokémon's secondary type.
- **`Adaptability` STAB ($2.0\times$):** Amplifies matching STAB to $2.0\times$ (`8192 / 4096`).
- **Non-STAB Coverage ($1.0\times$):** Move type does not match either of the Pokémon's types.
- **Type-Changing Abilities (`-ate` abilities & `Liquid Voice`):**
  * `Pixilate` (Fairy), `Aerilate` (Flying), `Refrigerate` (Ice), `Galvanize` (Electric), and `Dragonize` (Dragon) convert `Normal`-type moves into their respective elemental types and grant an immediate **$+20\%$ Base Power boost** (`4915 / 4096`).
  * If the converted type matches either of the Pokémon's types (e.g., `Aerilate` on `Mega Salamence` Dragon/Flying, `Pixilate` on `Mega Altaria` Dragon/Fairy, `Dragonize` on `Mega Feraligatr`), the move additionally receives the **$1.5\times$ STAB multiplier** ($1.2 \times 1.5 = 1.8\times$ cumulative offensive boost).
  * `Liquid Voice` converts all sound-based attacks into `Water`-type moves, granting $1.5\times$ STAB to Water-type users.
