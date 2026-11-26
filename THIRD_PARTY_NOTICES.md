# Legal Notice, Intellectual Property Disclaimer & Third-Party Credits

## 1. Non-Commercial Fan Project & Intellectual Property Disclaimer

**Coach Porygon VGC** is an independent, **100% fan-made, strictly non-commercial** open-source analytical tool built by Pokémon VGC fans for Pokémon VGC fans. **This project will never be monetized** — it carries no paywalls, no subscriptions, no advertisements, no sponsorships, and no commercial licensing.

- **Pokémon**, **Pokémon Champions**, **Pokémon VGC**, and all Pokémon species names, forms, Mega Evolutions, moves, abilities, items, battle mechanics, and sprite artwork are registered trademarks and copyrights of **© 1995–2026 Nintendo, Creatures Inc., GAME FREAK inc., and The Pokémon Company / The Pokémon Company International**.
- **Coach Porygon VGC** is **not affiliated with, endorsed by, sponsored by, or officially connected to** Nintendo, Creatures Inc., GAME FREAK inc., or The Pokémon Company.

### Open-Source License Scope (Carve-Out)
The **GNU Affero General Public License v3.0 (AGPLv3)** in [`LICENSE`](LICENSE) applies **exclusively to the original source code authored for Coach Porygon VGC**. It does **not** grant any rights to, nor claim ownership over:
1. Any Pokémon trademarks, copyrights, character designs, sprites, icons, or official game data (which remain the sole property of Nintendo, Creatures Inc., GAME FREAK inc., and The Pokémon Company).
2. Any third-party vendored libraries, runtime dependencies, or community datasets listed below (which remain governed by their own respective licenses and terms).

### Rights-Holder & Takedown Contact
We bundle local sprites strictly to provide offline tournament preparation and replay coaching utility to VGC players without commercial gain. If you are a copyright or trademark owner (or an authorized representative) and wish any asset or dataset removed from this repository, please contact **`esquedevil94@gmail.com`** (or open a GitHub issue) and it will be removed promptly.

---

## 2. Visual Assets & Community Data Credits

| Asset / Dataset | Source | Attribution & Scope |
| :--- | :--- | :--- |
| **Pokémon Sprites (`128×128`), Held Item Icons (`24×24`), Mega Stone Icons (`24×24`), & Ranked Regulation M-C / M-D Catalogs** | **[Pokéos](https://www.pokeos.com/)** (`assets/sprites/Reg_M-C/`, `assets/sprites/Reg_M-D/`, `assets/items/`, `assets/megastones/`) | Sourced from Pokéos (`pokeos.com`, including [Regulation M-C](https://www.pokeos.com/db/games/champions/ranked-battles/regulation-m-c) and [Regulation M-D](https://www.pokeos.com/db/games/champions/ranked-battles/regulation-m-d) pages). Underlying Pokémon artwork & game icons remain © Nintendo / Creatures Inc. / GAME FREAK inc. / The Pokémon Company. |
| **Pokémon Champions Mechanics Data (`pokedex`, `moves`, `items`, `abilities`, `learnsets`, `conditions`)** | **[Pokémon Showdown](https://github.com/smogon/pokemon-showdown)** (`data/mods/champions`, `src/engine/data/showdown/`) | MIT License (data schemas & compilation tooling © Guangcong Luo / Pokémon Showdown contributors); underlying game names & stats © Nintendo / Creatures Inc. / GAME FREAK inc. |
| **VGC Regional Tournament Standings, Rosters & Usage Telemetry** | **[MunchStats](https://www.munchstats.com/)** (`src/engine/data/munchstats/`, `src/engine/munchstats_pipeline/`) | Community VGC tournament statistics and regional standings datasets aggregated by MunchStats. |
| **Command Hub Hero Banner (`assets/coach_porygon_banner.jpg`)** | Original Non-Commercial Fan Art (AI-assisted, Google C2PA signed) | Created exclusively for this non-commercial fan project. Depicts Pokémon character likeness owned by Nintendo / Creatures Inc. / GAME FREAK inc. / The Pokémon Company. |

---

## 3. Vendored Third-Party Software

### 3.1 Smogon Damage Calculator (`@smogon/calc` v0.12.0 — Champions Gen 0 Bundle)
- **Location:** `src/engine/damage_calc/vendor/smogon_calc_champions.js` (commit `abdce0c64597284c8c463b7f71a38dc4dc55cd10`)
- **Upstream:** <https://github.com/smogon/damage-calc>
- **License:** MIT License (`src/engine/damage_calc/vendor/LICENSE.smogon-damage-calc`)

```text
The MIT License (MIT)

Copyright (c) 2013-2025 Honko and other contributors

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

### 3.2 Pokémon Showdown Replay Embed (`replay-embed.js`) & Battle Player
- **Location:** `apps/replay_coach/vendor/replay-embed.js` (and Showdown player client scripts loaded inside the replay playback iframe from `play.pokemonshowdown.com`)
- **Upstream:** <https://github.com/smogon/pokemon-showdown-client> / <https://github.com/smogon/pokemon-showdown>
- **Author:** Guangcong Luo (`Zarel`) and Pokémon Showdown contributors
- **License:** MIT License

```text
The MIT License (MIT)

Copyright (c) 2011-2026 Guangcong Luo and Pokémon Showdown contributors

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

---

## 4. Runtime & Developer Open-Source Dependencies

| Library | Role in Coach Porygon VGC | Upstream | License |
| :--- | :--- | :--- | :--- |
| **PyTorch** | GPU/CPU vectorized VGC Tensor Core state machine & 8-pillar equity evaluator | <https://pytorch.org/> | BSD-3-Clause |
| **NumPy** | Vectorized numerical arrays & tensor bridges | <https://numpy.org/> | BSD-3-Clause |
| **SciPy** | Optimization (`L-BFGS-B` Texel/TD tuner) & linear programming interface | <https://scipy.org/> | BSD-3-Clause |
| **HiGHS** (via SciPy) | Exact Zero-Sum Nash Equilibrium LP solver | <https://highs.dev/> | MIT |
| **DuckDB** | In-memory mechanics/meta SQL engine & persistent OTS / Lead Lab Matchup Vault | <https://duckdb.org/> | MIT |
| **PyMiniRacer (`mini-racer`)** | Hermetic in-process V8 JavaScript execution sandbox for `@smogon/calc` | <https://github.com/bpcreech/PyMiniRacer> | ISC |
| **V8 JavaScript Engine** (via `mini-racer`) | Embedded JavaScript engine for Smogon Calc & JS syntax guardrails | <https://v8.dev/> | BSD-3-Clause |
| **pytest** *(dev)* | Unit, integration, and `TestAT-1`..`TestAT-10` acceptance test runner | <https://pytest.org/> | MIT |
| **Pillow** *(dev/assets)* | Sprite normalization & offline icon packaging | <https://python-pillow.org/> | MIT-CMU |
| **PyInstaller** *(dev/release)* | Optional lightweight Windows `.exe` bootstrap launcher builder | <https://pyinstaller.org/> | GPL-2.0 with bootloader exception |
