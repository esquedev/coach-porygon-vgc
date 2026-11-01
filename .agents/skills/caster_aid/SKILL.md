---
name: caster_aid
description: >-
  Generates high-impact esports broadcast dossiers, talking points, speed ladders, and print-ready
  PDF cheat-sheets for tournament casters and commentators from two opposing Open Team Sheets (OTS).
---

# Caster Aid: Esports Broadcast Matchup Dossier & Live Commentary Cues

Autonomous broadcast intelligence engine providing tournament commentators and esports casters with real-time talking points, narrative storylines, a unified 12-Pokémon speed hierarchy, elemental threat matrices, and publication-grade multi-page PDF dossiers formatted specifically to avoid mid-infographic page clipping.

---

## 0. Governance, Role Alignment & Validation Matrix

- **Owner Role:** Esports Reporter & Visual Publisher (`Role: Reporter`) supported by Metagame & Scouting Analyst (`Role: Analyst`).
- **Domain Layer:** Presentation & Publishing Layer (UX / Infographics / Dossiers) consuming Domain Core math (`engine/turn_simulator.py`, `engine/sp_calculator.py`) and infrastructure services (`engine/caster_dossier.py`, `engine/pdf_exporter.py`).
- **Permissions:** Read `data/Regulation_MC_Items.csv`, `data/MC_Available_Pokemon.csv`, `assets/sprites/Reg_M-C/`, `assets/items/`, `assets/icons/`; write to `reports/caster_dossiers/{matchup_slug}.html` and `reports/caster_dossiers/{matchup_slug}.pdf`; execute `engine/caster_dossier.py` and `engine/pdf_exporter.py`. Codebase backend is locked in Trainer Mode.
- **Minimum Viable Context (MVC):** Both 6-Pokémon OTS sheets (items, abilities, moves, Level 50 spreads/SP), Broadcast Cyber & Clean Print CSS tokens, broadcast timing cues. Exclude: Internal CI/CD manifests, SQLite crawler tables, player tilt psychology.
- **Deterministic Validation Criteria:**
  - Unified 12-Pokémon Speed Ladder sorted with exact Level 50 speed values and modifier badges.
  - Broadcast commentary scripts divided into 5 phases (Pre-Match 30s Hook, Lead Reveal Drama, Mid-Game Checkpoints, End-Game Lethal Triggers, Cartridge Quirks).
  - HTML/PDF output is 100% self-contained (zero external CDNs or web fonts, inlined Base64 assets).
  - Strict anti-page-break pagination (`break-inside: avoid; page-break-inside: avoid;` on all cards and tables).
  - Stored strictly under `reports/caster_dossiers/` (Guardrail 11 compliance).

---

## 1. Core Workflow & 3-Page Broadcast Dossier Structure

When two Open Team Sheets (OTS) are submitted, the AI Agent acts as the **Lead Esports Broadcast Producer & Tactical Analyst**, synthesizing a 3-page executive dossier designed to be printed or displayed on caster monitors:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        PAGE 1: SPEED & OVERVIEW                        │
│   • Match Header (Player A vs Player B, Archetype Tags, Mega Stakes)   │
│   • Unified 12-Pokémon Speed Ladder (Sorted Level 50, Modifiers)       │
│   • Quick Glance Tempo Advantage & Speed Control Dominance             │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ clean page break (page-break-after: always)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        PAGE 2: TACTICAL MATRIX                         │
│   • Elemental Matchup Matrix (4.0x Weaknesses, 0.25x Resists, 0x Imms) │
│   • Projected Opening Leads (High-Probability Pairs & Turn 1 Clashes)  │
│   • Weather & Terrain War (Rain vs Sun, Terrain Priority Lockouts)     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ clean page break (page-break-after: always)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   PAGE 3: LIVE COMMENTARY CHEAT SHEET                  │
│   • 30-Second Pre-Game Broadcast Hook (Opening Narrative Monologue)    │
│   • 15-Second Lead Reveal Cues (What to scream/highlight immediately)  │
│   • Trap Tech & Berry Watchlist (Damage reduction, wide guard, items)  │
│   • Lethal Checkmate Triggers & End-Game Thresholds                    │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Print Pagination & Anti-Clipping CSS Directives

To guarantee that **no card, data table, or infographic is sliced or clipped across physical page breaks**, every generated HTML document must declare and adhere to these strict print CSS rules:

```css
@media print {
  @page {
    size: A4 portrait;
    margin: 12mm 10mm 14mm 10mm;
  }
  
  body {
    background: #0b0e14 !important;
    color: #f8fafc !important;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }

  /* Page container enforcing discrete page blocks */
  .caster-page {
    page-break-after: always;
    break-after: page;
    min-height: 98vh;
    box-sizing: border-box;
    padding-bottom: 20px;
  }
  .caster-page:last-child {
    page-break-after: avoid;
    break-after: avoid;
  }

  /* Strict anti-slice protection for all components */
  .infographic-card,
  .speed-ladder-table,
  .talking-points-box,
  .trap-tech-card,
  .lead-clash-grid {
    page-break-inside: avoid !important;
    break-inside: avoid !important;
  }
}
```

---

## 3. Caster Commentary Protocol & Script Templates

Commentators must never have to search for what to say. The dossier delivers ready-to-speak phrasing:

1. **The 30-Second Pre-Game Hook:**
   - *"Welcome back to the finals! We have an explosive clash of philosophies: [Player A]'s Rain Offense looking to overwhelm the field with Archaludon and swift swim Basculegion, against [Player B]'s Sun Balance anchored by Mega Charizard Y and Garchomp. The critical question of this set: Can [Player B] prevent the activation of Electro Shot on turn 1, or will weather control decide the champion?"*
2. **The 15-Second Lead Reveal Cues:**
   - If Lead A+B vs Lead C+D: *"Look at the front row! [Player A] respects the Sun lead and opens with Pelipper and Archaludon, setting immediate weather dominance. But [Player B] anticipates the rain and leads Whimsicott with Tailwind pressure!"*
3. **Mid-Game Checkpoint Alerts:**
   - Remind casters of format-specific mechanics: *"Remember folks, under Regulation M-C, Mega Evolution speed recalculates INSTANTLY in the activation phase—Mega Lucario jumps straight to 180 speed before Garchomp can click Earthquake!"*
   - Redirection limits: *"Follow Me cannot redirect spread attacks like Earthquake, Heat Wave, or Make It Rain!"*
4. **End-Game Checkmate Countdown:**
   - Clearly delineate lethal thresholds: *"Once the opposing Archaludon is below 40% HP, Mega Charizard Y's Solar Beam is guaranteed lethal. [Player B] is just one pivot away from checkmate."*

---

## 4. Execution Workflow

1. **Ingest Two Open Team Sheets (OTS):**
   - Parse Player A and Player B rosters (6 Pokémon each, held items, abilities, 4 moves, and 66-SP spreads).
   - Validate that all items exist in [`data/Regulation_MC_Items.csv`](../../../data/Regulation_MC_Items.csv) and all species exist in [`data/MC_Available_Pokemon.csv`](../../../data/MC_Available_Pokemon.csv).
2. **Compute Matchup Metrics via Python Engine:**
   - Run [`engine/caster_dossier.py`](../../../engine/caster_dossier.py) to calculate exact Level 50 speed tiers and format the interleaved speed ladder.
   - Cross-reference compound 4.0x weaknesses, 0.25x resistances, and 0.0x immunities.
3. **Compose Broadcast HTML Report:**
   - Generate self-contained HTML with Midnight Cyber styling and print-safe page breaks.
   - Inlay Base64 sprites sourced from [`assets/sprites/Reg_M-C/`](../../../assets/sprites/Reg_M-C/), [`assets/items/`](../../../assets/items/), and [`assets/icons/`](../../../assets/icons/).
   - Save directly to `reports/caster_dossiers/{matchup_slug}.html`.
4. **Compile Headless PDF via Engine:**
   - Execute [`engine/pdf_exporter.py`](../../../engine/pdf_exporter.py):
     ```powershell
     python engine/pdf_exporter.py --input reports/caster_dossiers/{matchup_slug}.html --output reports/caster_dossiers/{matchup_slug}.pdf
     ```
   - Verify that the PDF compiles cleanly with zero page-cut defects.

---

## 5. First-Proof Worked Example

```markdown
### Broadcast Matchup: Regional Grand Finals — Trainer A (Rain Balance) vs Trainer B (Sun Offense)

#### 1. Unified 12-Pokémon Speed Ladder
1. Whimsicott (184 Spe | 368 in Tailwind) [Team B]
2. Basculegion-M (138 Spe | 276 in Rain) [Team A]
3. Mega Charizard Y (167 Spe | Post-Mega) [Team B]
4. Garchomp (169 Spe | Jolly 32 SP) [Team B]
5. Archaludon (105 Spe | Modest 4 SP) [Team A]
6. Pelipper (85 Spe | Damp Rock) [Team A]

#### 2. Key Tactical Clashes & Lead Matrix
- Weather Dominance: Pelipper (Drizzle) vs Charizard-Mega-Y (Drought). Slower weather setter wins climate on turn 1 switch-in.
- 4x Weakness Alert: Basculegion threatens Charizard-Mega-Y with 2.0x Water STAB; Garchomp threatens Archaludon with 2.0x Ground STAB.
- Trap Tech Watchlist: Archaludon holds Assault Vest; Opposing Whimsicott holds Focus Sash with Encore.

#### 3. Caster Talking Point Hook (30s)
"We have a textbook elemental clash in the finals. Trainer A wants the storm; Trainer B wants the drought. The entire set hinges on who controls the field state on turn 1. If Trainer A resolves an Electro Shot into Charizard, Trainer B loses their primary win condition."
```
