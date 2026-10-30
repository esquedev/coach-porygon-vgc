# Pokémon Champions — Regulation M-C Mechanics Compendium

## 1. Stat Point (SP) System (Level 50)
- **Total Budget:** Exactly `66 SP` per Pokémon.
- **Single-Stat Cap:** Maximum `32 SP` in any single stat (`HP`, `Atk`, `Def`, `SpA`, `SpD`, `Spe`).
- **Discretized Conversion:**
  $$\text{EV}_{\text{equiv}} = \begin{cases} 0 & \text{if } \text{SP} = 0 \\ 4 + 8 \times (\text{SP} - 1) & \text{if } 1 \le \text{SP} \le 32 \end{cases}$$
- **Level 50 Formula (Sequential Floor Rounding):**
  - **HP:** $\lfloor (2 \times \text{Base} + 31 + \lfloor \text{EV}_{\text{equiv}} / 4 \rfloor) \times 50 / 100 \rfloor + 60$
  - **Other Stats:** $\lfloor \lfloor (2 \times \text{Base} + 31 + \lfloor \text{EV}_{\text{equiv}} / 4 \rfloor) \times 50 / 100 + 5 \rfloor \times \text{AlignmentMult} \rfloor$
  - **Stat Alignments:** `+10%` (`1.1x`) / `-10%` (`0.9x`), applied *after* base + SP stat computation and always rounded down (`floor`).

## 2. Mega Evolution & Speed Scaling
- **Activation Phase:** Mega Evolution resolves during the Activation Phase prior to any move execution (before `Fake Out` and `Protect`).
- **Instantaneous Speed Recalibration:** Effective speed tiers update immediately upon Mega Evolution.
- **Simultaneous Mega Evolution:** If both sides Mega Evolve on the same turn, the Pokémon with the higher *post-Mega* speed tier resolves and triggers its ability first.

## 3. Redirection & Terrain Matrix
- **Spread Move Redirection Immunity:** `Follow Me` and `Rage Powder` cannot redirect spread moves (`Earthquake`, `Heat Wave`, `Muddy Water`, `Make It Rain`, `Dazzling Gleam`, `Rock Slide`, `Hyper Voice`, `Discharge`).
- **Psychic Terrain Priority Lockout:** Grounded Pokémon on Psychic Terrain are immune to priority moves (`Fake Out`, `Sucker Punch`, `Grassy Glide`, `Extreme Speed`, Prankster status moves).
- **Airborne Exemption:** Airborne Pokémon (`Flying`-types such as `Charizard`, `Pelipper`, `Salamence`, `Staraptor`, or `Levitate` / `Air Balloon` holders) receive zero priority protection from Psychic Terrain.

## 4. Fixed-Point Damage Modifiers (`0x1000` / `4096` Scale)
- **Spread Move Penalty (Doubles):** `3072 / 4096` (`0.75x`)
- **Screens (`Reflect` / `Light Screen` in Doubles):** `2732 / 4096` (`~0.667x`)
- **Aura Abilities (`Fairy Aura`, `Dark Aura`):** `5461 / 4096` (`~1.333x`)
- **Weather Modifiers:** `1.5x` boost (`6144 / 4096`) / `0.5x` reduction (`2048 / 4096`) in Sun and Rain.
- **STAB:** `1.5x` (`6144 / 4096`), or `2.0x` (`8192 / 4096`) with `Adaptability`.
