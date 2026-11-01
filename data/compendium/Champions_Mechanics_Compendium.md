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

## 6. Dual-Typing Defensive Matrix, Compound Resistances & STAB Mechanics

### 6.1. Compound Type Effectiveness Scale
Against dual-typed defenders `[Type 1, Type 2]`, total elemental matchup effectiveness is the exact product of both individual matchup multipliers:
$$Eff = M(Type_{atk}, Type1_{def}) \times M(Type_{atk}, Type2_{def})$$

The official VGC calculation executes this via discrete integer shifts:
- **`0.0x` (Absolute Immunity):** Attack deals zero damage. Examples: Ground into `Flying` (`Charizard`, `Pelipper`, `Salamence`), Normal/Fighting into `Ghost` (`Gengar`, `Aegislash`), Electric into `Ground` (`Garchomp`, `Excadrill`), Psychic into `Dark` (`Tyranitar`, `Incineroar`), Dragon into `Fairy` (`Clefable`, `Primarina`).
- **`0.25x` (Double Resistance):** Damage is halved twice via floor truncation: $\lfloor \lfloor Damage / 2 \rfloor / 2 \rfloor$. Examples: Grass into `Fire/Flying` (`Charizard`), Fighting into `Poison/Ghost` (`Gengar`), Poison into `Steel/Fairy` (`Tinkaton`, `Magearna` $\to 0x$ immune), Bug into `Poison/Fighting` (`Sneasler`).
- **`0.5x` (Single Resistance):** Damage is halved: $\lfloor Damage / 2 \rfloor$.
- **`1.0x` (Neutral Matchup):** Damage modifier unchanged.
- **`2.0x` (Super Effective):** Damage is doubled: $Damage \times 2$.
- **`4.0x` (Double Weakness / 4x Weakness):** Damage is doubled twice: $(Damage \times 2) \times 2$. Key Regulation M-C archetypes:
  * **Rock ($4.0\times$):** Strikes `Fire/Flying` (`Charizard`, `Moltres`), `Bug/Flying` (`Pinsir-Mega`, `Scyther`).
  * **Ice ($4.0\times$):** Strikes `Dragon/Ground` (`Garchomp`), `Dragon/Flying` (`Dragonite`, `Salamence`).
  * **Ground ($4.0\times$):** Strikes `Electric/Steel` (`Magnezone`), `Fire/Rock` (`Magcargo`).
  * **Fighting ($4.0\times$):** Strikes `Rock/Dark` (`Tyranitar`), `Normal/Dark` (`Obstagoon`).
  * **Fire ($4.0\times$):** Strikes `Bug/Steel` (`Scizor`, `Genesect` if format), `Grass/Steel` (`Ferrothorn`).
  * **Grass ($4.0\times$):** Strikes `Water/Ground` (`Swampert`, `Quagsire`).

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
