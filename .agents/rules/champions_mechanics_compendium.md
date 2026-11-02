# Pokémon Champions — Regulation M-C Mechanics Compendium
**Path:** `.agents/rules/champions_mechanics_compendium.md`
**Role:** Canonical source of truth for tactical reasoning, math invariants, and synergistic validations.

## 1. Stat Point (SP) System (Level 50)
- **Constraint:** `66 SP` absolute maximum per Pokémon. Max `32 SP` per single stat.
- **Translation:** `SP = 0` $\to$ `EV = 0`. For `1 \le SP \le 32` $\to$ `EV = 4 + 8 \times (SP - 1)`.
- **Formulas (Strict Floor Rounding):**
  - **HP:** $\text{Base} + \text{SP} + 75$
  - **Other Stats:** $\lfloor (\text{Base} + \text{SP} + 20) \times \text{NatureMult} \rfloor$
  - **NatureMult:** Applied *after* addition, truncating decimals ($1.1\times$ or $0.9\times$).

## 2. Dynamic Speed Control, Turn Order & Priority
- **Mega Evolution & Auto-Setters:** Resolves at Turn Start (Phase 0). Speed tiers update *immediately*. Abilities that set Weather (Drought, Drizzle) or Terrain (Psychic/Grassy Surge) trigger immediately upon entry or post-Mega based on instantaneous speed tiers.
- **Priority Brackets (Overrides Speed):**
  - **+5:** Helping Hand.
  - **+4:** Protect, Detect.
  - **+3:** Fake Out *(Valid ONLY on the user's first turn on the field)*, Wide Guard. *(Note: Wide Guard protects against spread moves and **does not decay** upon consecutive uses).*
  - **+2:** Ally Switch, Extreme Speed.
  - **+1:** Sucker Punch, Grassy Glide (in Grassy Terrain), Prankster status moves.
  - **0:** Standard moves.
  - **-7:** Trick Room.
- **Speed Multipliers & Status:**
  - **Paralysis:** Multiplies final Speed by $0.5\times$.
  - **Tailwind:** Multiplies team Speed by $2.0\times$ for 4 turns. *(Note: Tailwind modifies raw speed; if Trick Room is active, Tailwind makes you move LAST).*
  - **Icy Wind / Electroweb:** Drops targets' Speed by 1 stage ($\approx 0.67\times$ multiplier). Speed adjustments recalculate immediate turn order.
- **Trick Room:** Inverts turn order within the same priority bracket (lowest Speed moves first). Priority still supersedes Trick Room.
- **Quash:** Forces the target to execute its move *last* within its priority bracket.
- **Ally Switch (+2):** User swaps field positions with its ally. Redirects single target attacks aimed at the original slot. Fails if used consecutively (shares the ~33% decay with Protect).

## 3. Official VGC Math & Damage Modifiers
All modifiers apply sequentially with $n / 4096$ scaling and strict integer truncation.
- **Spread Move (Doubles):** $0.75\times$ (`3072 / 4096`).
- **Screens (Reflect / Light Screen):** $\approx 0.667\times$ (`2732 / 4096`) in Doubles.
- **Weather:** $1.5\times$ (`6144 / 4096`) offensive boost / $0.5\times$ reduction (Sun/Rain).
- **Burn Penalty:** Physical attacks deal $0.5\times$ damage (unless user has `Guts`).
- **Critical Hits:** $1.5\times$ damage multiplier. They **ignore** defensive screens (Reflect/Light Screen), **ignore** attacker's negative stat drops, and **ignore** defender's positive stat boosts.
- **STAB Base:** $1.5\times$ (`6144 / 4096`). **Adaptability:** $2.0\times$ (`8192 / 4096`).

## 4. Invariants, Immunities & Compound Effectiveness
- **Effectiveness (`Eff`):** `Eff = M(Type_{atk}, Type1_{def}) \times M(Type_{atk}, Type2_{def})`.
- **Type chart delegation:** Exact `0.5\times`, `1.0\times`, and `2.0\times` multipliers calculated via runtime `TYPE_CHART`. Tactical extremes dictate strict logic:
  - **Hard immunities (`0.0\times`):**
    - `Normal` or `Fighting` attacks $\to$ `Ghost` is immune.
    - `Ghost` attacks $\to$ `Normal` is immune.
    - `Electric` attacks $\to$ `Ground` is immune.
    - `Ground` attacks $\to$ `Flying` (and `Levitate` / `Air Balloon`) are immune.
    - `Psychic` attacks $\to$ `Dark` is immune.
    - `Dragon` attacks $\to$ `Fairy` is immune.
    - `Poison` attacks $\to$ `Steel` is immune.
  - **Double weaknesses (`4.0\times`):**
    - `Rock` attacks $\to$ `Fire/Flying`, `Bug/Flying`, `Ice/Flying` (e.g., Mega Charizard Y).
    - `Ice` attacks $\to$ `Dragon/Ground`, `Dragon/Flying`, `Ground/Flying`, `Grass/Flying` (e.g., Garchomp).
    - `Fairy` attacks $\to$ `Dragon/Fighting`, `Dark/Fighting`, `Dragon/Dark` (e.g., Kommo-o).
    - `Psychic` attacks $\to$ `Poison/Fighting` (e.g., Sneasler).
    - `Ground` attacks $\to$ `Electric/Steel`, `Fire/Steel`, `Rock/Steel`, `Fire/Rock`.
    - `Fire` attacks $\to$ `Bug/Steel`, `Grass/Steel`, `Ice/Steel`.
    - `Grass` attacks $\to$ `Water/Ground`, `Water/Rock`, `Ground/Rock`.
    - `Fighting` attacks $\to$ `Dark/Rock`, `Steel/Rock`, `Normal/Rock`, `Dark/Ice`.
- **Intimidate & Stat Modifying Abilities:**
  - **Intimidate:** Automatically drops both opponents' Attack by 1 stage upon entry.
  - **Defiant / Competitive:** If ANY stat is lowered by an opponent (including Intimidate, Icy Wind, Snarl), the Pokémon gains a +2 Attack (Defiant) or +2 Sp. Atk (Competitive) boost.
  - **Clear Body / White Smoke:** Flat immunity to all opponent-induced stat drops.
  - **Inner Focus:** Flat immunity to Intimidate and Flinch (Fake Out).
- **Ability-Based Invulnerability & Redirection:**
  - **Lightning Rod & Storm Drain:** Unconditionally redirect single-target Electric/Water attacks to the ability bearer, granting immunity and +1 stat boost.
  - **Powder / Spore Immunities:** `Grass`-types and `Overcoat` users are 100% immune to `Rage Powder` and `Spore`.
  - **Good as Gold:** Flat immunity to status moves (Taunt, Thunder Wave, Parting Shot).
  - **Soundproof:** Flat immunity to sound-based moves (Hyper Voice, Snarl, Roar).
  - **Flash Fire / Volt Absorb / Water Absorb:** Flat immunities to elements that trigger stat boosts/healing.
  - **Armor Tail / Queenly Majesty:** Flat immunity to incoming priority moves regardless of grounding.
  - **Mold Breaker:** Ignores defensive abilities (Levitate, Flash Fire, Disguise, Multiscale).
- **Terrain Invariants (Affect Grounded Targets Only):**
  - **Psychic Terrain:** Grounded targets are IMMUNE to priority moves ($>0$).
  - **Electric Terrain:** Grounded targets are 100% immune to Sleep.
  - **Misty Terrain:** Grounded targets are 100% immune to major status conditions. Dragon-type damage against them is halved ($0.5\times$).
  - **Grassy Terrain:** Halves damage ($0.5\times$) of Earthquake/Bulldoze against grounded targets, grants passive recovery.
- **Freeze-Dry:** Calculates as $2.0\times$ against `Water`.
- **Scrappy:** Normal/Fighting vs Ghost = $1.0\times$.

## 5. Tactical Synergies, Held Items & Disruption
*WARNING: Never evaluate items/moves in isolation. Validate against these rules:*
- **IF [No Guard] THEN:** All attacks hit (100%). Accuracies like 50% become deterministic nukes.
- **IF [Sheer Force + Life Orb] THEN:** Moves with secondary effects get $1.3\times$ BP. Life Orb recoil is *nullified* while retaining the $1.3\times$ damage boost. Total: $1.69\times$.
- **IF [Technician] THEN:** Base Power $\le 60 \to 1.5\times$ multiplier.
- **IF [Psychic Terrain + Expanding Force] THEN:** BP $80 \to 120$ AND becomes a spread move AND grounded targets are immune to priority.
- **IF [-ate Ability] (Pixilate/Aerilate/Refrigerate/Galvanize) THEN:** Normal moves convert to element AND gain $+20\%$ BP. Apply STAB ($1.5\times$) if matches user type.
- **IF [Liquid Voice] THEN:** Sound moves convert to `Water` type. Applies $1.5\times$ STAB if user is Water-type.
- **IF [Unburden + Item Loss] THEN:** Speed is immediately doubled. Recalibrate turn order.
- **IF [Stamina] THEN:** User gains +1 Defense every time it is hit by an attack (e.g., Archaludon).
- **IF [Choice Band / Specs / Scarf] THEN:** Apply $1.5\times$ multiplier to Atk / SpA / Spe, but user is locked into first move selected.
- **IF [Assault Vest] THEN:** Apply $1.5\times$ multiplier to Sp. Def; Status moves cannot be selected.
- **IF [Focus Sash] THEN:** User survives any OHKO from 100% HP at exactly 1 HP.
- **Disruption Moves (Taunt / Encore):** Taunt prevents status moves for 3 turns. Encore locks target into their last used move for 3 turns. `Mental Herb` cures these instantly once.
- **IF [Weather Active] THEN:**
  - *Rain:* Swift Swim ($2\times$ Spe), Electro Shot (0 turn charge), Thunder/Hurricane (100% Acc).
  - *Sun:* Chlorophyll ($2\times$ Spe), Solar Beam (0 turn charge).
  - *Snow:* Slush Rush ($2\times$ Spe), Blizzard (100% Acc), Ice-types gain $1.5\times$ Def.
  - *Sand:* Sand Rush ($2\times$ Spe), Rock/Ground/Steel gain $1.3\times$ BP (Sand Force), Rock-types gain $1.5\times$ SpD.
