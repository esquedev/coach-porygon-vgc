---
trigger: always_on
---

# Standardized Playstyle & Mistake Taxonomy

Every tactical leak identified in Replay Analysis (Mode 1), Sparring (Mode 3), or Sports Psychology (Mode 5) must be assigned a standardized player error code and linked to its underlying cognitive driver:

## 1. Tactical Error Codes

* **Positioning (`POS`):**
  * `POS-01` (**Dry Hard Switch**): Switching a fragile sweeper directly into active attacks without `Protect` or redirection.
  * `POS-02` (**Lead Compression Failure**): Opening with leads that concede immediate positional collapse to spread moves or Unburden sweepers.
  * `POS-03` (**Passive Protect**): Burning `Protect` when behind on board equity instead of making necessary offensive trades.
* **Targeting (`TGT`):**
  * `TGT-01` (**Protect Tunneling**): Directing high-value offensive attacks into predictable `Protect` slots instead of punishing the partner.
  * `TGT-02` (**Spread Redirection Error**): Directing single-target nukes into `Follow Me`/`Rage Powder` instead of executing un-redirectable spread moves.
  * `TGT-03` (**Damage Overkill**): Committing dual-slot attacks into a target already fainted to a single hit, abandoning secondary board control.
* **Mechanics (`MEC`):**
  * `MEC-01` (**Terrain Priority Collision**): Clicking priority moves (`Fake Out`, `Sucker Punch`, `Grassy Glide`) into grounded targets in Psychic Terrain.
  * `MEC-02` (**Airborne Ground Exemption**): Exposing airborne teammates (`Charizard`, `Pelipper`, `Salamence`) to priority attacks under the false assumption of Psychic Terrain protection.
* **Speed Control (`SPD`):**
  * `SPD-01` (**Activation Phase Blindness**): Miscalculating turn order due to instantaneous post-Mega speed recalculations.
  * `SPD-02` (**Weather/Terrain Sequencing Error**): Overwriting active climates or terrains in the wrong operational order.

## 2. Cognitive Trap Drivers

Every tactical error code (`POS`, `TGT`, `MEC`, `SPD`) logged to `data/Playstyle_Diagnostics.csv` must be paired with one primary psychological driver:
* `Tunnel_Vision`: Fixating on eliminating a single damaged slot while ignoring partner retaliation or `Protect`.
* `Greed`: Over-extending for maximum damage or stat boosts when a safe board-stabilizing play guarantees the win condition.
* `Autopilot`: Clicking default lead attacks or switches out of habit without running the 4-Step Pre-Turn Validation Checklist.
* `Tilt`: Rushing turn execution or making high-variance desperation reads after suffering an unexpected KO or critical hit.
* `Format_Divergence`: Applying legacy VGC mechanics instead of Regulation M-C rules (e.g., forgetting instantaneous Mega speed or Psychic Terrain airborne exemptions).

## 3. High-Risk / High-Reward Strategic Evaluation

In elite VGC tournaments, tactical decisions do not exist on a rigid binary ($0$ or $100$) scale. Not every high-variance action represents an unforced error:
- **`Mechanically_Invalid`:** Physical cartridge impossibilities that always fail with $0\%$ utility (e.g., `Fake Out` on active turns $> 1$, priority into grounded targets under Psychic Terrain). Always classified under `MEC-01` or `MEC-02`.
- **`High_Risk_High_Reward` (Calculated Tournament Gambles):**
  * **Consecutive Protect:** Carries a $\approx 33\%$ mechanical success chance. When facing guaranteed double lethal, gambling on a consecutive Protect is mathematically superior to taking guaranteed fainting, preserving the win condition.
  * **Hard Prediction Switches:** Switching a fragile sweeper directly into an opponent's slot on a hard read that the opponent will status, protect, or target the partner slot.
  * **Switch-In Targeting:** Directing offensive nukes into an apparent resistance or immunity anticipating a hard switch by the opponent into a fragile sweeper.
- **Coaching Directive:** Coach Porygon evaluates high-risk lines by assessing whether the player held a commanding board state (where gambling represents `Greed`) or was in a desperate/checkmate position (where gambling represents a necessary high-upside `Calculated_Risk`).
