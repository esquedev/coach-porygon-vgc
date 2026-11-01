---
name: flashcards
description: >-
  Use this skill when the user requests live practice, 45-second turn scenarios, interactive board
  sparring, or mechanical flashcards (Interactive Board Sparring & Reflex Conditioning).
---

# Flashcards: Interactive Board Sparring & Reflex Conditioning

Condition the Trainer's decision-making under tournament clock pressure using deterministic simulation, game-theoretic strategy pruning, multi-turn Minimax lookahead, and calibrated speed reflex benchmarks.

---

## 0. Governance, Role Alignment & Validation Matrix
- **Owner Role:** Head Coach & Sparring Referee (`Role: Coach`)
- **Domain Layer:** Domain Core (Turn Simulation) & Presentation Layer (Flashcards UI)
- **Permissions:** Read-only on `data/Speed_Duel_Scenarios.csv` and `data/Flashcard_Scenarios.csv`; execute `engine/turn_simulator.py` (via scratch); append to `data/Playstyle_Diagnostics.csv`. Strictly forbidden from modifying `engine/*.py` or `tests/*.py`.
- **Minimum Viable Context (MVC):** 66-SP limits, Level 50 speed formula, active scenario board state, mistake taxonomy. Exclude: MunchStats tables, HTML CSS design tokens, CI/CD test manifests.
- **Deterministic Validation Criteria:**
  - *Mode 1 (Speed Duels):* Binary correctness check in 5.0s–7.0s with exact speed differential and field status.
  - *Mode 2 (Board Sparring):* 4 distinct categorized choices (`[A]` Minimax Optimal, `[B]` Dominated / Hope Chess, `[C]` Greed / Overkill, `[D]` Passive / Tempo Loss) evaluated across 2 to 3 turns via `engine/turn_simulator.py`.

---

## 1. Dual-Timer Training Architecture

In tournament play, the full turn timer is strictly **45 seconds**. Spending 45 seconds to evaluate an isolated speed matchup is unviable because the Trainer still requires the majority of the turn to declare targets, anticipate switches, assess Protect baiting, and execute double-slot coordination. Therefore, training is partitioned into two distinct operational modes:

| Training Mode | Focus & Scope | Target Clock | Objective |
| :--- | :--- | :--- | :--- |
| **Mode 1: Speed Reflex Conditioning (Speed Duels)** | 1v1 Speed comparison between two Regulation M-C Pokémon under active field modifiers | **5.0s – 7.0s** *(10s max)* | Instantaneous turn-order recognition; preserves ~38s for the rest of the turn |
| **Mode 2: Tactical Board Sparring (Micro-Simulation)** | Full 4v4 doubles mid-game state ($p1a/p1b$ vs $p2a/p2b$) with 4 categorized decision options | **45.0s** *(Full Tournament Clock)* | Complete double-slot execution, damage roll assessment, and multi-turn Minimax trajectory |

---

## 2. Mode 1: Speed Reflex Conditioning & 6-Tier Taxonomy

Speed Duels are drawn from `data/Speed_Duel_Scenarios.csv` (and `engine/speed_duels_data.py`), comprising 50 verified Level 50 benchmarks organized into **6 Taxonomic Tiers**:

```
                       TAXONOMÍA DE VELOCIDAD (REGULATION M-C)
                                        │
     ┌──────────────┬──────────────┬────┴─────────┬──────────────┬──────────────┐
     ▼              ▼              ▼              ▼              ▼              ▼
[T1: Base Spe] [T2: Megas]   [T3: Scarf]    [T4: Campos]   [T5: Drops]    [T6: Prio & TR]
  Tiers Nat.    Recálculo      x1.5 Spe       Tailwind/       -1 Spe Drop    Brackets +1..+4,
  y Naturaleza  Instantáneo    vs Megas/      Clima x2.0      Icy Wind/      Inversión TR y
  a Nivel 50    post-Mega      Fast Sweepers  vs Unburden     Electroweb     Speed Ties 50/50
```

1. **Tier 1: Base Speed & Nature (Speed Tiers Nativos a Nivel 50):**
   - Formula: $\text{Spe}_{50} = \lfloor (\text{Base} + \text{SP} + 20) \times \text{NatureMod} \rfloor$.
   - Fricción de borde crítico: Base 102 Garchomp Jolly (169 Spe) superando por 2 puntos a Base 100 Charizard-Mega-Y / Volcarona Timid (167 Spe); Maushold Jolly (179 Spe) vs Mega Raichu X Timid (178 Spe); Rillaboom Adamant 12 SP (117 Spe) vs Incineroar Careful 4 SP (85 Spe).
2. **Tier 2: Instant Mega Speed Scaling (Recálculo Instantáneo en Activation Phase):**
   - En Regulation M-C, la velocidad de la Megaevolución se actualiza de inmediato en el turno de activación antes de ejecutar acciones.
   - *Ejemplos clave:* Mega Lucario (Base 112, 180 Spe) superando a Garchomp (169 Spe); Mega Gengar (Base 130, 200 Spe) superando a Sneasler (Base 120, 189 Spe); Mega Metagross (Base 110, 178 Spe) superando a Garchomp (169 Spe); y la **Trampa Mega** donde Mega Garchomp pierde velocidad respecto a su forma base (Base 102 $\to$ Base 92, 158 Spe).
3. **Tier 3: Choice Scarf ($1.5\times$) vs Fast Sweepers y Megas:**
   - Multiplicador $1.5\times$ calculado vía redondeo oficial Showdown.
   - *Ejemplos clave:* Annihilape Jolly Scarf (234 Spe) superando a Dragapult Timid (213 Spe); Archaludon Timid Scarf (205 Spe) superando a Mega Gengar Timid (200 Spe); Dragonite Jolly Scarf (217 Spe) superando a Mega Lucario (180 Spe); Basculegion-M Jolly Scarf (214 Spe) superando a Mega Charizard Y (167 Spe).
4. **Tier 4: Multiplicadores de Campo (Tailwind $2.0\times$ vs Clima $2.0\times$ vs Unburden $2.0\times$):**
   - Duelos entre aceleradores simultáneos de velocidad.
   - *Ejemplos clave:* Mega Charizard Y en Tailwind (334 Spe) vs Basculegion-M en Lluvia con Swift Swim (260 Spe); Sneasler con Unburden activado tras Electric Seed (378 Spe) superando a Garchomp en Tailwind (338 Spe); Excadrill con Sand Rush en Tormenta de Arena (308 Spe) superando a Dragapult (213 Spe).
5. **Tier 5: Control Secundario de Velocidad (Drops $-1$ Spe & Parálisis):**
   - Impacto del multiplicador $\frac{2}{3} \approx 0.667\times$ por *Icy Wind* / *Electroweb* o $0.5\times$ por Parálisis.
   - *Ejemplos clave:* Primarina a $-1$ Spe (74 Spe) quedando por debajo de Armarouge (95 Spe); Annihilape a $-1$ Spe (104 Spe) perdiendo el turno ante Gholdengo Timid (149 Spe); Meowscarada con Parálisis (96 Spe) aún superando a Kingambit sin inversión (70 Spe).
6. **Tier 6: Prioridades Relativas, Desempates de Mismo Bracket & Trick Room:**
   - *Brackets Dispares:* Fake Out (+3) supera siempre a Extreme Speed (+2); Extreme Speed (+2) supera siempre a Sucker Punch (+1).
   - *Mismo Bracket (+1):* Grassy Glide (Rillaboom 117 Spe) vs Sucker Punch (Kingambit 70 Spe); Aqua Jet (Basculegion-M 130 Spe) vs Sucker Punch (Kingambit 70 Spe); Talonflame Gale Wings (+1, 195 Spe) vs Whimsicott Prankster (+1, 184 Spe).
   - *Inversión en Trick Room ($-\text{Speed}$):* El más lento actúa primero: Torkoal Quiet (22 Spe) antes que Farigiraf (58 Spe) o Skeledirge (77 Spe); Kingambit Brave (49 Spe) antes que Tyranitar Brave (63 Spe); Rhyperior Brave (54 Spe) antes que Armarouge Quiet (85 Spe).
   - *Speed Ties Oficiales (50/50):* Incineroar 0 SP (80 Spe) vs Primarina 0 SP (80 Spe); Mega Charizard Y 32 SP (167 Spe) vs Volcarona 32 SP (167 Spe); Incineroar 0 SP (80 Spe) vs Grimmsnarl 0 SP (80 Spe).

---

## 3. Mode 2: Tactical Board Sparring (45-Second Full Turn Clock)

Respaldado por el pipeline vectorial en GPU [`engine/gpu/board_state_simulator.py`](../../../engine/gpu/board_state_simulator.py) y el dataset oficial `data/Flashcard_Scenarios.csv` (50 escenarios de micro-simulación):

1. **Flujo de Generación de Board States Reales:**
   - **Ingesta:** Muestreo de combinaciones 4v4 reales desde `data/MunchStats_Top_Teams.csv`, arquetipos de `data/MunchStats_Pokemon_Sets.csv` y repeticiones de `data/Raw_Matches.csv`.
   - **Validación de Legalidad:** Validación pre-flight obligatoria mediante `engine/validate_roster.py` contra `Regulation_MC_Items.csv`, `MC_Available_Pokemon.csv` y la blacklist de 25 especies. Cero objetos ilegales, estricto cumplimiento de Item Clause (máximo 1 Mega Stone por bando).
   - **Árbol de Decisiones:** Poda de macro-estrategias mediante `engine/tactics/action_pruner.py` y axiomas de cartucho en `engine/tactics/logic_engine.py`.
   - **Simulación Completa en GPU:** Simulación física de cada celda $N \times M$ con `ClientReplaySimulator` (`engine/turn_simulator.py`), vectorización en tensores de resultado `(1, N, M, 16)` con `PayoffBuilder`, evaluación en VRAM con `RegulationMcValueNet` (< 40ms en RTX 3060) y resolución de Equilibrio de Nash con `NashSolver`.
   - **Incertidumbre Discreta:** Convolución de 16 tiradas oficiales de daño (0.85 a 1.00), críticos y precisión con `UncertaintyModel`.

2. **Presentación del Estado de Tablero Doble:**
   - Slots activos: `p1a`, `p1b` vs `p2a`, `p2b` con especies verificadas en `data/MC_Available_Pokemon.csv`, tipos primario/secundario y HP% exactos.
   - Matriz de amenazas de doble tipo (debilidades 4.0x y dobles resistencias 0.25x).
   - Modificadores de campo activos (turnos restantes de Clima, Terreno, Tailwind, Pantallas, Trick Room).

3. **Formulación de 4 Opciones de Decisión Categorizadas (Spoiler-Free):**
   - `[A]` **Minimax Optimal Line:** Maximiza la equidad mínima garantizada frente a cualquier respuesta del rival ($+\Delta \text{VP}$, $v^*$).
   - `[B]` **Tactical Leak / Mistake:** Fuga táctica de posicionamiento o mecánica (`POS-01` Dry Hard Switch, `MEC-01` Fake Out en terreno, etc.).
   - `[C]` **Greed / Overkill:** Sobre-extender por daño prescindible, setup innecesario o atacar un slot con Protect telegrafiado (`TGT-01`, `SPD-02`).
   - `[D]` **Passive / Tempo Loss:** Protect pasivo cuando se está abajo en equidad (`POS-03`) o concentrar doble ataque en un objetivo ya debilitado (`TGT-03`).

4. **Simulación Determinista y Proyección a 2–3 Turnos ($T_N \to T_{N+1} \to T_{N+2}$):**
   - Ejecución mediante [`engine/turn_simulator.py`](../../../engine/turn_simulator.py).
   - Evaluación de puntos de inflexión y asignación de la taxonomía de errores oficiales:
     - `SPD-01` (**Activation Phase Blindness**): Error por cálculo de velocidad instantánea de Mega.
     - `SPD-02` (**Weather/Terrain Sequencing Error**): Error en interacción de climas, terrenos o expiración de Tailwind.
     - `MEC-01` (**Terrain Priority Collision**): Ataque de prioridad a objetivo en suelo en Terreno Psíquico.
     - `MEC-02` (**Airborne Ground Exemption**): Asumir erróneamente que voladores están protegidos en Terreno Psíquico.
     - `POS-01`–`POS-03` / `TGT-01`–`TGT-03`.
     - Vinculación con Driver Cognitivo: `Autopilot`, `Format_Divergence`, `Tunnel_Vision`, `Greed`, o `Tilt`.

---

## 4. Ejemplos Resueltos de Referencia

### Ejemplo 1: Speed Duel Reflexivo (Benchmark 5.0s – 7.0s)
```markdown
### [SPEED DUEL REFLEX FLASHCARD | TIER 2]
- Pokémon A: Mega Metagross @ Metagrossite (Recálculo Instantáneo post-Mega, Jolly 32 SP)
- Pokémon B: Garchomp @ Life Orb (Inversión 32 SP (+Spe), Jolly 32 SP)
- Contexto de Campo: Neutral, sin clima ni viento afín.

Pregunta (Responder en <7.0s): ¿Quién ataca primero a Nivel 50?
[A] Mega Metagross
[B] Garchomp
[C] Speed Tie (50/50)

---
#### Resolución Inmediata:
- Veredicto: [A] Mega Metagross
- Estadísticas Nivel 50: Mega Metagross 178 Spe vs Garchomp 169 Spe (ΔSpe: +9 puntos a favor de Mega Metagross).
- Explicación: En forma base Metagross tiene Base 70 (134 Spe) y sería superado por Garchomp (169 Spe). No obstante, en Regulation M-C el recálculo post-Mega es instantáneo en el Activation Phase elevando su Base a 110 (178 Spe), superando a Garchomp por 9 puntos.
```

### Ejemplo 2: Sparring Táctico Completo (Reloj de Torneo de 45s)
```markdown
### [45-SECOND BOARD SPARRING | TURNO 4]
- Campo: Tailwind (Usuario, 1 turno restante) | Sol activo (Rival, 2 turnos restantes)
- Usuario (p1): Archaludon (68% HP, Stamina +1 Def) | Pelipper (42% HP)
- Rival (p2): Mega Charizard Y (100% HP) | Torkoal (55% HP)

Seleccionar acción doble (Límite 45s):
[A] Archaludon Electro Shot (p2a) + Pelipper Wide Guard (Minimax Optimal)
[B] Archaludon Protect + Pelipper Weather Ball en Charizard (Strictly Dominated / Hope Chess)
[C] Archaludon Body Press (p2b) + Pelipper Hurricane (p2a) (Greed / Overkill)
[D] Archaludon Protect + Pelipper switch a la banca (Passive / Tempo Loss)

---
#### Evaluación del Simulador (engine/turn_simulator.py):
- Turno 4: Pelipper ejecuta Wide Guard (Prioridad +3) bloqueando Heat Wave en área de Mega Charizard Y. Archaludon conecta Electro Shot en Charizard logrando el OHKO (+3 VP Mega KO). Torkoal inflige daño residual en Archaludon activando Stamina.
- Turno 5 (Proyección TN+1): Tailwind expira. Rival envía Venusaur en Sol. Usuario retiene superioridad de piezas 2v1. Pelipper supera a Torkoal; Archaludon asegura Flash Cannon sobre Venusaur.
- Veredicto Óptimo: Opción [A] asegura la partida. Opciones [B], [C] y [D] pierden a Pelipper ante Heat Wave regalando iniciativa al rival.
```
