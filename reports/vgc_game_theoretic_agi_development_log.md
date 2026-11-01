# Coach Porygon VGC — Registro de Ingeniería y Proceso de Desarrollo
## Arquitectura Game-Theoretic AGI (Regulation M-C): Motor de Equilibrio de Nash Simultáneo, Inferencia Neuronal en GPU y Persistencia Dual (SQLite `:memory:` + `.jsonl`)

**Fecha de Ingeniería:** 01 de Noviembre de 2026  
**Modo de Sesión:** `[SESSION: DEV]`  
**Entorno de Ejecución:** Python 3.11.11 (`.venv`), PyTorch `2.6.0+cu124` (CUDA 12.9 en NVIDIA GeForce RTX 3060 Laptop GPU 6GB), SciPy `1.17.1` (Solver HiGHS LP), SQLite3 In-Memory.

---

## 1. Motivación Matemática y Fundamentos de Diseño

### 1.1 Por qué VGC Dobles requiere Teoría de Juegos Simultáneos (y no Minimax secuencial puro)
A diferencia de juegos secuenciales de información perfecta (Ajedrez, Go), **Pokémon VGC (Regulation M-C, 4v4 Dobles)** opera bajo **decisiones simultáneas e información imperfecta**. En cada turno:
1. Cada Entrenador controla 2 slots activos con 4 movimientos (con selección de objetivo) y hasta 2 cambios a banco, generando entre $36$ y $81$ acciones conjuntas por bando (una matriz bruta de hasta $81 \times 81 = 6,561$ estados por turno).
2. Cualquier estrategia determinista pura (por ejemplo, enfocar siempre con doble ataque al slot con mayor debilidad elemental) es trivialmente explotada por un rival internacional mediante `Protect` en el slot amenazado o redirección (`Rage Powder` / `Follow Me`) acompañada de contraataque o control de velocidad.
3. Por el **Teorema Minimax de von Neumann** para juegos simultáneos de suma cero:
   $$\max_{\mathbf{p} \in \Delta_M} \min_{\mathbf{q} \in \Delta_N} \mathbf{p}^T A \mathbf{q} = \min_{\mathbf{q} \in \Delta_N} \max_{\mathbf{p} \in \Delta_M} \mathbf{p}^T A \mathbf{q} = v^*$$
   la estrategia óptima inexplotable es una distribución de probabilidad mixta $\mathbf{p}^* = (p_1, \dots, p_5)$ sobre las líneas canónicas dominantes.

### 1.2 Arquitectura de Datos Dual: JSON Lines (`.jsonl`) + SQLite en Memoria (`:memory:`)
Para evitar tanto la rigidez de archivos CSV planos de decenas de columnas como la contaminación de binarios `.sqlite` en el historial de Git:
- **Capa 1 (Persistencia Versionada en Disco - `data/tactical_audits.jsonl`):** Cada auditoría táctica se escribe mediante un `append` atómico $O(1)$ de una sola línea JSON, almacenando tensores anidados (la matriz de pagos $5 \times 5$, los vectores de probabilidad de Nash $\mathbf{p}^*, \mathbf{q}^*$ y las razones heurísticas del punto de quiebre) con diffs limpios de $+1$ línea en Git.
- **Capa 2 (Motor Relacional en Tiempo de Ejecución - `engine/db.py`):** Al iniciar, `UnifiedCoachDatabase` levanta una instancia `sqlite3.connect(":memory:")` con `row_factory = sqlite3.Row`, creando e indexando las tablas `matches`, `tactical_audits`, `diagnostics` y `munchstats_meta`. La ingesta de lotes `.jsonl` toma $< 5\text{ ms}$ y habilita consultas SQL analíticas con `JOIN` para agentes de Antigravity.

---

## 2. Bitácora Técnica Paso a Paso (De la Concepción a los Modelos Finales)

### Fase 1: Capa de Persistencia Unificada (`engine/db.py`)
- **Diseño:** Se implementó la clase `UnifiedCoachDatabase` protegida con cerrojos de hilo (`threading.Lock`) y validación estricta de consultas de solo lectura (`SELECT` / `WITH`) en `query()` para prevenir inyección o mutación accidental por subagentes.
- **Decisiones clave:**
  - El método `append_audit_record()` garantiza consistencia transaccional escribiendo la línea serializada en `data/tactical_audits.jsonl` e indexándola simultáneamente en las tres tablas relacionales (`matches`, `tactical_audits` y `diagnostics`).
  - Se crearon los fixtures `tests/data/tactical_audits.jsonl` y `data/tactical_audits.example.jsonl` para garantizar reproducibilidad en entornos CI limpios.

### Fase 2: Parser Determinista de Showdown y Acoplamiento con `turn_simulator.py` (`engine/tactics/showdown_parser.py`)
- **Integración con lógica existente:** Siguiendo el Principio de Inversión de Dependencias (SOLID), `ShowdownParser` se conectó directamente a `BASE_STATS_DB`, `PROTECT_MOVES` y `calculate_level_50_stats` de `engine/turn_simulator.py`.
- **Soporte Biformato:** El parser reconstruye el historial tanto desde logs en texto humano de Showdown (`tests/data/sample_showdown_mc_log.txt`: `aws_secret` vs `DarKgoD16`) como desde flujos de protocolo separados por tuberías (`|turn|`, `|switch|`, `|move|`, `|-damage|`, `|faint|`, `|-mega|`, `|-weather|`, `|-fieldstart|`).
- **Ajuste Crítico Durante el Desarrollo (Preservación de Slots Pre-Reemplazo):**
  - *Problema detectado:* Al ejecutar la primera prueba del CLI en el Turno 3 (donde `Sinistcha` cae debilitado al final del turno y `DarKgoD16` envía a `Sneasler` como reemplazo de fin de turno), el snapshot final sobrescribía el slot de `Sinistcha` con `Sneasler`.
  - *Solución aplicada en `_finalize_turn_snapshot`:* Se preservó en `snapshot.p1_slots` y `snapshot.p2_slots` la alineación activa **al inicio de la toma de decisiones del turno** (`[Kingambit, Charizard]` vs `[Sinistcha, Floette-Eternal]`), sincronizando únicamente las banderas de Mega Evolución y escalado instantáneo de velocidad (`Charizard` $\to$ `Charizard-Mega-Y`, `Floette-Eternal` $\to$ `Mega Floette-Red` con `112` de velocidad base).
- **Puente al Simulador (`to_simulator_state`):** Convierte cualquier `TurnSnapshot` directamente al esquema de diccionario exacto que consume `ClientReplaySimulator` en `engine/turn_simulator.py`.

### Fase 3: Detector Heurístico del Punto de Quiebre (`engine/tactics/turning_point_detector.py`)
- **Algoritmo de Puntuación:**
  - $\Delta\text{HP total} > 40\%$: $+30\text{ pts}$ (más $+10\text{ pts}$ adicionales cuando el intercambio supera el $150\%$ acumulado en múltiples slots).
  - Bajas de piezas centrales (KOs): $+25\text{ pts}$ por KO.
  - Absorción ofensiva en `Protect`/`Detect` o activación de redirección táctica (`Rage Powder` / `Follow Me`): $+20\text{ pts}$.
  - Cambio de clima/terreno (`Drought` / `SunnyDay` / `Psychic Terrain`): $+15\text{ pts}$.
  - Activación de Mega Evolución de medio juego (Turno $> 1$): $+15\text{ pts}$.
  - Descuento de limpieza de endgame ($\times 0.5$ en el último turno de partidas de $\ge 4$ turnos).
- **Verificación en Fixture Real:** En la partida real `aws_secret` vs `DarKgoD16`, el Turno 3 alcanza el puntaje máximo ($115.0\text{ pts}$) al converger la Mega Evolución de `Charizard-Mega-Y`, la activación de `Drought`, el `Rage Powder` de `Sinistcha`, el intercambio masivo de $171.9\%$ de HP y el KO sobre `Sinistcha`.

### Fase 4: Poda de Acciones con `ClientReplaySimulator` y Evaluador Neuronal en GPU (`action_pruner.py` y `neural_evaluator.py`)
- **Poda Combinatoria ($81 \to 5$ Líneas Canónicas):**
  - `ActionPruner` utiliza `TYPE_CHART`, `MOVE_DB` y `evaluate_move_synergy` de `engine/turn_simulator.py` para sintetizar las 5 macro-decisiones de VGC por bando:
    - `L0`: **Double Offensive Focus** (Foco ofensivo doble de objetivo único).
    - `L1`: **Attack + Defensive Protect** (Ataque + `Protect` defensivo en el slot expuesto).
    - `L2`: **Spread / Area Move** (Movimiento de área in-redireccionable como `Heat Wave` / `Dazzling Gleam` + remate del compañero).
    - `L3`: **Speed Control / Redirection / Status** (`Tailwind`, `Rage Powder`, `Reflect`, `Sucker Punch`, `Calm Mind`).
    - `L4`: **Strategic Pivot / Switch** (Cambio defensivo a banco resistente + cobertura).
  - *Ajuste de Selección de Movimiento de Área en `L2`:* Se refinó `prune_side_actions` para que identifique dinámicamente cuál de los dos compañeros activos posee un movimiento de área real (`Heat Wave`, `Dazzling Gleam`, `Earthquake`, `Snarl`), garantizando que en el Turno 3 la línea `L2` ejecute `Heat Wave` con `Charizard` acompañado de `Iron Head` con `Kingambit`.
- **Simulación Determinista de las 25 Hojas (`simulate_joint_outcome`):**
  - Para cada celda $(i, j) \in \{0..4\} \times \{0..4\}$, `ActionPruner` invoca `ClientReplaySimulator(sim_state, combined_choices).run_turn(roll_mode="fixed", fixed_roll=0.925)`, resolviendo el orden exacto de velocidades, prioridades, bayas (`Occa Berry`, `Sitrus Berry`), `Focus Sash`, redirección y daño oficial.
- **Red Neuronal `RegulationMcValueNet` en GPU (`cuda:0`):**
  - Arquitectura PyTorch: `Linear(36, 128) -> GELU -> Linear(128, 64) -> GELU -> Linear(64, 1) -> Tanh`.
  - Recibe un vector de estado de $36$ dimensiones codificado desde el estado post-turno de `ClientReplaySimulator` (HPs activos, ratios de banco vivo, flags de Mega Evolución, Speed tiers, one-hot de climas y terrenos, Tailwind/Reflect, boosts de etapas, estados alterados, diferencial de Puntos de Victoria (VP) y señal de sinergia/redirección).
  - **Iteración Clave de Calibración de Pesos (Eliminación de Saturación de `Tanh`):**
    - *Observación experimental:* En la primera iteración de calibración, inicializar todas las neuronas ocultas de `fc2` ($128$) y `fc3` ($64$) con pesos positivos uniformes ($0.04$ y $0.12$) tras la no-linealidad asimétrica `GELU` producía una suma pre-activación $> 15.0$, saturando $\tanh(z) \to +1.0000$ en múltiples celdas de la matriz.
    - *Solución matemática implementada:* Se dividieron las unidades ocultas de `fc1` ($128$) y `fc2` ($64$) en dos sub-espacios antiparalelos simétricos (mitad positiva `[:64]` / `[:32]` y mitad negativa `[64:]` / `[32:]` normalizadas por $\frac{1}{64}$ y $\frac{1.5}{32}$). De esta forma, `GELU` preserva la simetría impar respecto al diferencial de Puntos de Victoria (VP) y mantiene los logits pre-`Tanh` en el régimen dinámico lineal-suave $[-1.2, +1.2]$, produciendo valores de Win-Equity altamente discriminativos en $[-1.0, +1.0]$ sin saturación.

### Fase 5: Solver de Equilibrio de Nash Mixto mediante Programación Lineal HiGHS (`engine/tactics/nash_solver.py`)
- **Formulación Primal-Dual:**
  1. Traslación estrictamente positiva: $A' = A + c$ donde $c = |\min(A)| + 2.0$ si $\min(A) \le 0$, garantizando $A'_{ij} > 0$ y valor del juego desplazado $v' > 0$.
  2. **LP Primal (Jugador 1):** Minimizar $\mathbf{1}^T \mathbf{x}$ sujeto a $-(A')^T \mathbf{x} \le -\mathbf{1}, \mathbf{x} \ge \mathbf{0}$ resuelto con `scipy.optimize.linprog(method="highs")`. Se recupera $v' = 1 / \sum x_i$, $\mathbf{p}^* = \mathbf{x} / \sum x_i$, y el valor real del juego $v^* = v' - c$.
  3. **LP Dual (Jugador 2):** Maximizar $\mathbf{1}^T \mathbf{y}$ (minimizar $-\mathbf{1}^T \mathbf{y}$) sujeto a $A' \mathbf{y} \le \mathbf{1}, \mathbf{y} \ge \mathbf{0}$, obteniendo $\mathbf{q}^* = \mathbf{y} / \sum y_j$.
  4. **Cálculo de Explotabilidad ($\Delta\text{Equity}$):** `compute_equity_loss` evalúa el retorno esperado de la jugada observada frente a la mezcla óptima rival $V_{\text{real}} = \sum_j A_{i_{\text{obs}}, j} q^*_j$ y reporta $\Delta\text{Equity} = \max(0, v^* - V_{\text{real}})$.

### Fase 6: Orquestador Táctico, Taxonomía Cognitiva y CLI (`tactical_pipeline.py` y `main.py`)
- `audit_showdown_log()` encadena las 7 etapas en una sola llamada tipada (`TacticalAuditResult`), clasificando automáticamente el código de error de `.agents/rules/mistake_taxonomy.md` (`TGT-01`, `TGT-02`, `POS-01`, `POS-02`, `MEC-01`, `SPD-01`) y su driver cognitivo (`Tunnel_Vision`, `Autopilot`, `Greed`, `Format_Divergence`).
- `main.py` expone la interfaz por línea de comandos (`python main.py --demo` y `python main.py --log <ruta>`) imprimiendo el diagnóstico completo en consola.

---

## 3. Guía para Contribuciones Posteriores

1. **Entrenamiento Supervisado / Reinforcement Learning de `RegulationMcValueNet`:**
   - Para cargar pesos entrenados desde un archivo `.pt` sobre millones de partidas simuladas con `ClientReplaySimulator`, basta con invocar `model.load_state_dict(torch.load(weights_path, map_location=model.device))` después de `__init__` en `RegulationMcValueNet`. El vector de entrada de $36$ canales en `NeuralEvaluator.encode_simulator_state()` está fijo y documentado canal por canal (`0..35`).
2. **Expansión del Catálogo de Movimientos por Especie en `ActionPruner`:**
   - El diccionario `CANONICAL_SPECIES_MOVES` en `engine/tactics/action_pruner.py` puede enriquecerse dinámicamente consultando la tabla `munchstats_meta` de `UnifiedCoachDatabase` para inyectar los 4 movimientos más frecuentes del metagame de MunchStats.
3. **Consultas Agénticas en SQL:**
   - Cualquier skill o agente puede instanciar `db = UnifiedCoachDatabase("data/tactical_audits.jsonl")` y ejecutar consultas analíticas cruzadas en $< 1\text{ ms}$.
