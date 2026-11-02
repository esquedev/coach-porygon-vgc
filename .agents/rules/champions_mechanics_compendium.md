# Pokémon Champions — Regulation M-C Mechanics Compendium
**Path:** `.agents/rules/champions_mechanics_compendium.md`
**Role:** Canonical source of truth for tactical reasoning, math invariants, and synergistic validations.

## 1. Stat Point (SP) System (Level 50)
- **Constraint:** `66 SP` absolute maximum per Pokémon. Max `32 SP` per single stat.
- **Translation:** `SP = 0` $\to$ `EV = 0`. For `1 \le SP \le 32` $\to$ `EV = 4 + 8 \times (SP - 1)`.
- **Formulas (Strict Floor Rounding):**
  - **HP:** $\text{Base} + \text{SP} + 75$ (Exception: Shedinja = 1 HP).
  - **Other Stats:** $\lfloor (\text{Base} + \text{SP} + 20) \times \text{NatureMult} \rfloor$
  - **NatureMult:** Applied *after* addition, truncating decimals ($1.1\times$ or $0.9\times$).

## 2. Dynamic Speed Control, Turn Order & Priority
- **Mega Evolution:** Resolves at Turn Start (Phase 0). Speed tiers update *immediately*. 
- **Priority Brackets (Overrides Speed):**
  - **+4:** Protect, Detect.
  - **+3:** Fake Out.
  - **+2:** Ally Switch, Extreme Speed.
  - **+1:** Sucker Punch, Grassy Glide (in Grassy Terrain), Prankster status moves.
  - **0:** Standard moves.
  - **-7:** Trick Room.
- **Speed Multipliers & Status:**
  - **Paralysis:** Multiplies final Speed by $0.5\times$.
  - **Tailwind:** Multiplies team Speed by $2.0\times$ for 4 turns.
  - **Icy Wind / Electroweb:** Drops targets' Speed by 1 stage ($\approx 0.67\times$ multiplier). Speed adjustments recalculate immediate turn order.
- **Trick Room:** Inverts turn order within the same priority bracket (lowest Speed moves first). Priority still supersedes Trick Room (e.g., +1 Sucker Punch hits before 0 Icy Wind, even in TR).
- **Quash:** Forces the target to execute its move *last* within its priority bracket, completely overriding their Speed stat or Trick Room advantage.
- **Ally Switch (+2):** User swaps field positions with its ally. Redirects single-target attacks aimed at the original slot. Fails if used consecutively (shares the ~33% success decay with Protect).

## 3. Official VGC Math & Damage Modifiers
All modifiers apply sequentially with $n / 4096$ scaling and strict integer truncation.
- **Spread Move (Doubles):** $0.75\times$ (`3072 / 4096`).
- **Screens (Reflect / Light Screen):** $\approx 0.667\times$ (`2732 / 4096`) in Doubles.
- **Weather:** $1.5\times$ (`6144 / 4096`) offensive boost / $0.5\times$ reduction (Sun/Rain).
- **Burn Penalty:** Physical attacks deal $0.5\times$ damage (unless user has `Guts`).
- **Critical Hits:** $1.5\times$ damage multiplier. Critically, they **ignore** defensive screens (Reflect/Light Screen), **ignore** the attacker's negative stat drops, and **ignore** the defender's positive stat boosts.
- **STAB Base:** $1.5\times$ (`6144 / 4096`). **Adaptability:** $2.0\times$ (`8192 / 4096`).

## 4. Invariants, Immunities & Compound Effectiveness
- **Effectiveness (`Eff`):** `Eff = M(Type_atk, Type1_def) × M(Type_atk, Type2_def)`.
- **Type chart delegation:** Exact `0.5×`, `1.0×`, and `2.0×` multipliers are calculated via the runtime `TYPE_CHART`. The tactical extremes below are the most important readouts:
  - **Hard immunities (`0.0×` - Attacking Type → Immune Defending Type):**
    - `Normal` or `Fighting` attacks → `Ghost` is immune.
    - `Ghost` attacks → `Normal` is immune.
    - `Electric` attacks → `Ground` is immune.
    - `Ground` attacks → `Flying` (and `Levitate` / `Air Balloon`) are immune.
    - `Psychic` attacks → `Dark` is immune.
    - `Dragon` attacks → `Fairy` is immune.
    - `Poison` attacks → `Steel` is immune.
  - **Double weaknesses (`4.0×` - Requires BOTH defending types to be weak):**
    - `Rock` attacks → `Fire/Flying`, `Bug/Flying`, `Bug/Fire`, `Ice/Flying` (e.g., Charizard, Talonflame, Volcarona).
    - `Ice` attacks → `Dragon/Flying`, `Dragon/Ground`, `Ground/Flying`, `Grass/Flying` (e.g., Salamence, Garchomp, Landorus).
    - `Ground` attacks → `Electric/Steel`, `Fire/Steel`, `Electric/Poison`, `Fire/Rock`, `Rock/Steel` (e.g., Magnezone, Heatran, Toxtricity, Stakataka).
    - `Fire` attacks → `Bug/Steel`, `Grass/Steel`, `Grass/Bug`, `Ice/Steel` (e.g., Scizor, Ferrothorn, Kartana).
    - `Grass` attacks → `Water/Ground`, `Water/Rock`, `Ground/Rock` (e.g., Swampert, Gastrodon, Rhyperior).
    - `Water` attacks → `Fire/Ground`, `Fire/Rock`, `Ground/Rock` (e.g., Camerupt, Coalossal).
    - `Fighting` attacks → `Dark/Rock`, `Steel/Rock`, `Normal/Rock`, `Dark/Ice` (e.g., Tyranitar, Aggron, Weavile).
    - `Electric` attacks → `Water/Flying` (e.g., Gyarados, Pelipper).
- **Powder / Spore Immunities:** `Grass`-type Pokémon and `Overcoat` ability users are 100% immune to `Rage Powder`, `Spore`, and `Sleep Powder`. (Do not recommend redirection against Grass-types).
- **Psychic Terrain:** Grounded targets are IMMUNE to priority moves ($>0$). Airborne targets (Flying, Levitate, Balloon) remain vulnerable.
- **Armor Tail / Queenly Majesty:** Flat immunity to incoming priority moves regardless of grounding.
- **Redirection (Follow Me / Rage Powder):** Fails to redirect spread moves (e.g., Earthquake, Heat Wave, Icy Wind).
- **Effectiveness ($Eff$):** $Eff = M(Type_{atk}, Type1_{def}) \times M(Type_{atk}, Type2_{def})$
  - *Freeze-Dry:* Calculates as $2.0\times$ against `Water`.
  - *Scrappy / Mind's Eye:* Normal/Fighting vs Ghost = $1.0\times$.

## 5. Tactical Synergies (Validation Directives)
*WARNING: Never evaluate items/moves in isolation. Validate against these rules:*
- **IF [No Guard] THEN:** All attacks hit (100%). Accuracies like 50% (Zap Cannon) become deterministic nukes.
- **IF [Sheer Force + Life Orb] THEN:** Moves with secondary effects get $1.3\times$ BP. Life Orb recoil is *nullified* while retaining the $1.3\times$ damage boost. Total: $1.69\times$.
- **IF [Technician] THEN:** Base Power $\le 60 \to 1.5\times$ multiplier.
- **IF [Psychic Terrain + Expanding Force] THEN:** Base Power $80 \to 120$ AND becomes a spread move AND grounded targets are immune to priority.
- **IF [-ate Ability] (Pixilate/Aerilate/Refrigerate/Galvanize) THEN:** Normal moves convert to element AND gain $+20\%$ BP. If converted type matches user type, apply STAB ($1.5\times$).
- **IF [Liquid Voice] THEN:** Sound moves convert to `Water` type. Applies $1.5\times$ STAB if user is Water-type. (Does NOT grant the $+20\%$ BP boost of -ate abilities).
- **IF [Unburden + Item Loss] THEN:** Speed is immediately doubled. Recalibrate turn order.
- **IF [Weather Active] THEN:**
  - *Rain:* Swift Swim ($2\times$ Spe), Electro Shot (0 turn charge), Thunder/Hurricane (100% Acc).
  - *Sun:* Chlorophyll ($2\times$ Spe), Solar Beam (0 turn charge).
  - *Snow:* Slush Rush ($2\times$ Spe), Blizzard (100% Acc), Ice-types gain $1.5\times$ Def.
  - *Sand:* Sand Rush ($2\times$ Spe), Rock/Ground/Steel gain $1.3\times$ BP (Sand Force), Rock-types gain $1.5\times$ SpD.
