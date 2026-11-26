# Pokémon Champions — Regulation M-C Mechanics Compendium
**Path:** `.agents/rules/champions_mechanics_compendium.md`
**Role:** Canonical source of truth for tactical reasoning, math invariants, and synergistic validations.

## 1. Stat Point (SP) System (Level 50)
- **Constraint:** `66 SP` absolute maximum per Pokémon. Max `32 SP` per single stat.
- **Translation:** `SP = 0` → `EV = 0`. For `1 ≤ SP ≤ 32` → `EV = 4 + 8 × (SP - 1)`.
- **Formulas (Strict Floor Rounding):**
  - **HP:** `Base + SP + 75`
  - **Other Stats:** `⌊(Base + SP + 20) × NatureMult⌋`
  - **NatureMult:** Applied *after* addition, truncating decimals (`1.1×` or `0.9×`).

## 2. Dynamic Speed Control, Turn Order & Priority
- **Turn-0 Lead Entry vs. Mega Evolution (+5.5):**
  - **Turn-0 Lead Entry Auto-Setters:** On lead entry (before Turn 1 action selection), Weather (`Drought`, `Drizzle`, `Sand Stream`, `Snow Warning`), Terrain (`Electric/Grassy/Psychic Surge`), and `Intimidate` trigger in Base Speed order.
  - **Barrier 1 Voluntary Switches (+6):** Execute first during the turn, resetting volatiles and resolving switch-in entry hazards (`Toxic Spikes`) and entry abilities.
  - **Barrier 2 Mega Evolution (+5.5):** Resolves *after* Turn 1 action selection and *after* Priority `+6` Voluntary Switches. Base stats, typing, and Mega ability update *immediately*, recalculating Turn 1 speed order before any move fires (e.g., `Charizard-Mega-Y` Drought overwrites Rain/Snow before Aurora Veil or Swift Swim moves execute). Terastallization is strictly forbidden.
- **Priority Brackets (Overrides Speed):**
  - **+5:** Helping Hand.
  - **+4:** Protect, Detect.
  - **+3:** Fake Out *(Valid ONLY on the user's first turn on the field)*, Upper Hand *(Succeeds ONLY against opposing priority `> 0` damaging moves; 100% flinch)*, Wide Guard / Quick Guard. *(Note: Wide Guard and Quick Guard **do not decay** upon consecutive uses).*
  - **+2:** Follow Me, Rage Powder, Ally Switch, Extreme Speed.
  - **+1:** Sucker Punch, Grassy Glide (in Grassy Terrain), Prankster status moves.
  - **0:** Standard moves. *(Note: `Quick Claw` has a 20% chance to act first **within** its own priority bracket, even under Trick Room, but never jumps above higher priority brackets).*
  - **-7:** Trick Room.
- **Speed Multipliers & Status:**
  - **Paralysis:** Multiplies final Speed by `0.5×`.
  - **Tailwind:** Multiplies team Speed by `2.0×` for 4 turns. *(Note: Tailwind modifies raw speed; if Trick Room is active, Tailwind makes you move LAST).*
  - **Icy Wind / Electroweb:** Drops targets' Speed by 1 stage (`≈ 0.67×` multiplier). Speed adjustments recalculate immediate turn order.
- **Trick Room:** Inverts turn order within the same priority bracket (lowest Speed moves first). Priority still supersedes Trick Room (e.g., +1 Sucker Punch hits before 0 Icy Wind, even in TR).
- **Quash:** Forces the target to execute its move *last* within its priority bracket, completely overriding their Speed stat or Trick Room advantage.
- **Ally Switch (+2):** User swaps field positions with its ally. Redirects single-target attacks aimed at the original slot. Fails if used consecutively (shares the ~33% success decay with Protect).

## 3. Official VGC Math & Damage Modifiers
All modifiers apply sequentially with `n / 4096` scaling and strict integer truncation.
- **Spread Move (Doubles):** `0.75×` (`3072 / 4096`).
- **Screens (Reflect / Light Screen):** `≈ 0.667×` (`2732 / 4096`) in Doubles.
- **Weather:** `1.5×` (`6144 / 4096`) offensive boost / `0.5×` reduction (Sun/Rain).
- **Burn Penalty:** Physical attacks deal `0.5×` damage (unless user has `Guts`).
- **Critical Hits:** `1.5×` damage multiplier. They **ignore** defensive screens (Reflect/Light Screen), **ignore** attacker's negative stat drops, and **ignore** defender's positive stat boosts.
- **STAB Base:** `1.5×` (`6144 / 4096`). **Adaptability:** `2.0×` (`8192 / 4096`).

## 4. Invariants, Immunities & Compound Effectiveness
- **Effectiveness (`Eff`):** `Eff = M(Type_atk, Type1_def) × M(Type_atk, Type2_def)`.
- **Type chart delegation:** Exact `0.5×`, `1.0×`, and `2.0×` multipliers calculated via runtime `TYPE_CHART`. Tactical extremes dictate strict logic:
  - **Hard immunities (`0.0×`):**
    - `Normal` or `Fighting` attacks → `Ghost` is immune.
    - `Ghost` attacks → `Normal` is immune.
    - `Electric` attacks → `Ground` is immune.
    - `Ground` attacks → `Flying` (and `Levitate` / `Air Balloon`) are immune.
    - `Psychic` attacks → `Dark` is immune.
    - `Dragon` attacks → `Fairy` is immune.
    - `Poison` attacks → `Steel` is immune.
  - **Double weaknesses (`4.0×`):**
    - `Rock` attacks → `Fire/Flying`, `Bug/Flying`, `Ice/Flying` (e.g., Mega Charizard Y).
    - `Ice` attacks → `Dragon/Ground`, `Dragon/Flying`, `Ground/Flying`, `Grass/Flying` (e.g., Garchomp).
    - `Fairy` attacks → `Dragon/Fighting`, `Dark/Fighting`, `Dragon/Dark` (e.g., Kommo-o).
    - `Psychic` attacks → `Poison/Fighting` (e.g., Sneasler).
    - `Ground` attacks → `Electric/Steel`, `Fire/Steel`, `Rock/Steel`, `Fire/Rock`.
    - `Fire` attacks → `Bug/Steel`, `Grass/Steel`, `Ice/Steel`.
    - `Grass` attacks → `Water/Ground`, `Water/Rock`, `Ground/Rock`.
    - `Fighting` attacks → `Dark/Rock`, `Steel/Rock`, `Normal/Rock`, `Dark/Ice`.
- **Intimidate & Stat Modifying Abilities:**
  - **Intimidate:** Automatically drops both opponents' Attack by 1 stage upon entry.
  - **Defiant / Competitive:** If ANY stat is lowered by an opponent (including Intimidate, Icy Wind, Snarl), the Pokémon gains a +2 Attack (Defiant) or +2 Sp. Atk (Competitive) boost.
  - **Clear Body / White Smoke:** Flat immunity to all opponent-induced stat drops.
  - **Inner Focus:** Flat immunity to Intimidate and Flinch (Fake Out).
  - **Oblivious:** Flat immunity to Intimidate and Taunt.
  - **Limber:** Flat immunity to Paralysis (`Thunder Wave`, `Nuzzle`, `Dire Claw`).
  - **Unaware:** Ignores opposing stat stage changes when attacking or defending.
  - **Water Bubble:** Doubles Water-type offensive power (`2.0×`), halves incoming Fire damage (`0.5×`), and grants Burn immunity.
  - **Disguise:** Blocks the first damaging hit for `1/8` max HP bust chip (bypassed by `Mold Breaker`; busted state persists across switches).
  - **Magic Bounce:** Reflects opposing status moves (`Taunt`, `Will-O-Wisp`, `Thunder Wave`, `Spore`, `Encore`, `Parting Shot`, `Toxic Spikes`) back onto the user.
  - **Champions Balance Invariants:** `Make It Rain` is `95%` accuracy with `-2 SpA` self-drop; `Dire Claw` has a `30%` tri-status chance; `Piercing Drill` (`Excadrill-Mega`) and `Unseen Fist` (`Golurk-Mega`) deal `0.25×` damage through `Protect` on contact moves; `Snowscape` replaces `Hail`.
- **Ability-Based Invulnerability & Redirection:**
  - **Lightning Rod:** Unconditionally redirects single-target Electric attacks to the ability bearer, granting immunity and `+1 SpA` boost.
  - **Powder / Spore Immunities:** `Grass`-types and `Overcoat` users are 100% immune to `Rage Powder` and `Spore`.
  - **Good as Gold:** Flat immunity to status moves (Taunt, Thunder Wave, Parting Shot).
  - **Soundproof:** Flat immunity to sound-based moves (Hyper Voice, Snarl, Roar).
  - **Flash Fire / Volt Absorb / Water Absorb:** Flat immunities to elements that trigger stat boosts/healing.
  - **Armor Tail / Queenly Majesty:** Flat immunity to incoming priority moves regardless of grounding.
  - **Mold Breaker:** Ignores defensive abilities (Levitate, Flash Fire, Disguise, Multiscale).
- **Terrain Invariants (Affect Grounded Targets Only):**
  - **Psychic Terrain:** Grounded targets are IMMUNE to priority moves (`> 0`).
  - **Electric Terrain:** Grounded targets are 100% immune to Sleep.
  - **Misty Terrain:** Grounded targets are 100% immune to major status conditions. Dragon-type damage against them is halved (`0.5×`).
  - **Grassy Terrain:** Halves damage (`0.5×`) of Earthquake/Bulldoze against grounded targets, grants passive recovery.
- **Freeze-Dry:** Calculates as `2.0×` against `Water`.
- **Scrappy:** Normal/Fighting vs Ghost = `1.0×`.

## 5. Tactical Synergies, Held Items & Disruption
*WARNING: Never evaluate items/moves in isolation. Validate against these rules:*
- **IF [No Guard] THEN:** All attacks hit (100%). Accuracies like 50% become deterministic nukes.
- **IF [Sheer Force + Life Orb] THEN:** Moves with secondary effects get `1.3×` BP. Life Orb recoil is *nullified* while retaining the `1.3×` damage boost. Total: `1.69×`.
- **IF [Technician] THEN:** Base Power `≤ 60` → `1.5×` multiplier.
- **IF [Psychic Terrain + Expanding Force] THEN:** BP `80 → 120` AND becomes a spread move AND grounded targets are immune to priority.
- **IF [-ate Ability] (Pixilate/Aerilate/Refrigerate) THEN:** Normal moves convert to element AND gain `+20%` BP. Apply STAB (`1.5×`) if matches user type.
- **IF [Liquid Voice] THEN:** Sound moves convert to `Water` type. Applies `1.5×` STAB if user is Water-type.
- **IF [Unburden + Item Loss] THEN:** Speed is immediately doubled. Recalibrate turn order (e.g., Sneasler becomes the fastest in the format with unburden active).
- **IF [Stamina] THEN:** User gains +1 Defense every time it is hit by an attack (e.g., Archaludon).
- **IF [Choice Scarf] THEN:** Apply `1.5×` multiplier to Spe, but user is locked into first move selected.
- **IF [Focus Sash] THEN:** User survives any OHKO from 100% HP at exactly 1 HP.
- **Disruption Moves (Taunt / Encore):** Taunt prevents status moves for 3 turns. Encore locks target into their last used move for 3 turns. `Mental Herb` cures these instantly once.
- **IF [Weather Active] THEN:**
  - *Rain:* Swift Swim (`2×` Spe), Electro Shot (0 turn charge), Thunder/Hurricane (100% Acc).
  - *Sun:* Chlorophyll (`2×` Spe), Solar Beam (0 turn charge).
  - *Snow:* Slush Rush (`2×` Spe), Blizzard (100% Acc), Ice-types gain `1.5×` Def.
  - *Sand:* Sand Rush (`2×` Spe), Rock/Ground/Steel gain `1.3×` BP (Sand Force), Rock-types gain `1.5×` SpD.

### Setting / Setup Moves
- **Field-Setting Moves:** Moves that establish the battle state or control turn order for the team.
  - **Reflect / Light Screen / Aurora Veil:** Setting screens grants defensive reduction for the active side, with full-screen math applied before damage resolves.
  - **Terrain Setters:** `Electric Terrain`, `Grassy Terrain`, `Psychic Terrain`, and `Misty Terrain` establish zone control that affects grounded targets and priority interactions.
  - **Hazards / Entry Control:** `Stealth Rock`, `Spikes`, `Toxic Spikes`, and similar hazard-setting moves impose persistent pressure but do not themselves count as offensive damage unless a move resolves them as part of a turn.
- **Stat-Setting / Setup Moves:** Moves that create an immediate tactical advantage by modifying attack, speed, or utility turns.
  - **Offensive Setup:** `Swords Dance`, `Nasty Plot`, `Dragon Dance`, `Calm Mind`, `Bulk Up`, `Shell Smash`, and similar boosting moves modify the battle state before the turn-attack sequence resolves.
  - **Control Setup:** `Protect`/`Detect`, and `Substitute` are context-setting actions that change the other side's decision space while preserving momentum for the user.
  - **Setup Integrity:** Setup actions must always be evaluated with turn order, priority, screens, weather, and target immunity rules in the same calculation chain; a setup that appears “safe” may fail if it is invalidated by prior field state or a priority interrupt.
- **Decision Rule:** If a move creates a persistent battle-state change (weather, terrain, hazard, team speed, screen, or stat momentum), it must be treated as a “setting” and evaluated as part of the full tactical tree, not as a standalone event.
