# -*- coding: utf-8 -*-
"""Canonical Bilingual Terminology & Verdict Lexicon for Coach Porygon VGC.

Single source of truth mapping internal mathematical and game-theoretic concepts
into four user-facing communication registers:
  1. `("es", "vgc")`        — Español competitivo VGC (intuitivo, directo, cero jerga académica)
  2. `("en", "vgc")`        — Competitive VGC English (actionable, player-friendly)
  3. `("es", "scientific")` — Español Científico Explícito (símbolos autoexplicativos: `Strats_1`, `RNG_Samples`, `Nash_Eq_Value`)
  4. `("en", "scientific")` — Explicit Scientific English (`Strats_1`, `RNG_Samples`, `Nash_Eq_Value`)
"""

from __future__ import annotations

from typing import Any, Dict, Literal

Language = Literal["es", "en"]
Style = Literal["vgc", "scientific"]

RNG_SAMPLED_EVENTS_TEXT: Dict[Language, Dict[Style, str]] = {
    "es": {
        "vgc": "rolls de daño (85–100%), precisión, críticos, efectos secundarios, flinch y speed ties",
        "scientific": "Damage Rolls (16 discrete steps 85..100%), Accuracy, Critical Hits, Secondary Procs, Flinch, Speed Ties",
    },
    "en": {
        "vgc": "damage rolls (85–100%), accuracy, crits, secondary procs, flinch & speed ties",
        "scientific": "Damage Rolls (16 discrete steps 85..100%), Accuracy, Critical Hits, Secondary Procs, Flinch, Speed Ties",
    },
}

TERM_GLOSSARY: Dict[str, Dict[Language, Dict[Style, Dict[str, str]]]] = {
    "strats_pair": {
        "es": {
            "vgc": {
                "label": "Jugadas legales (Tuyas / Rival)",
                "short": "Jugadas legales",
                "desc": "Combinaciones legales de 2 slots para tu lado y para el rival tras eliminar acciones imposibles en cartucho.",
            },
            "scientific": {
                "label": "Strats_1 / Strats_2",
                "short": "Strats_1 × Strats_2",
                "desc": "Dimensiones del espacio de estrategias conjuntas legales [Strats_1 × Strats_2] tras la poda mecánica exacta.",
            },
        },
        "en": {
            "vgc": {
                "label": "Legal plays (Yours / Opp)",
                "short": "Legal plays",
                "desc": "Mechanically legal 2-slot move/switch combinations for your side and your opponent.",
            },
            "scientific": {
                "label": "Strats_1 / Strats_2",
                "short": "Strats_1 × Strats_2",
                "desc": "Joint legal strategy space dimensions [Strats_1 × Strats_2] after exact mechanical pruning.",
            },
        },
    },
    "rng_samples": {
        "es": {
            "vgc": {
                "label": "Simulaciones de RNG",
                "short": "Simulaciones RNG",
                "desc": "Muestras discretas por cruce de jugadas evaluando rolls de daño (85–100%), precisión, críticos, efectos secundarios, flinch y speed ties.",
            },
            "scientific": {
                "label": "RNG_Samples",
                "short": "RNG_Samples",
                "desc": "Dimensión de muestreo Monte Carlo discreto (RNG_Sampling sobre Damage Rolls, Accuracy, Crits, Secondary Procs, Flinch y Speed Ties).",
            },
        },
        "en": {
            "vgc": {
                "label": "RNG simulations",
                "short": "RNG sims",
                "desc": "Discrete cartridge simulations per matchup sampling damage rolls (85–100%), accuracy, crits, secondary procs, flinch & speed ties.",
            },
            "scientific": {
                "label": "RNG_Samples",
                "short": "RNG_Samples",
                "desc": "Discrete Monte Carlo sampling dimension (RNG_Sampling across Damage Rolls, Accuracy, Crits, Secondary Procs, Flinch & Speed Ties).",
            },
        },
    },
    "ieds_strict": {
        "es": {
            "vgc": {
                "label": "Descartada (siempre inferior)",
                "short": "Siempre inferior",
                "desc": "Existe otra jugada tuya que da estrictamente mejor resultado contra todas y cada una de las respuestas posibles del rival.",
            },
            "scientific": {
                "label": "IEDS_Dominated",
                "short": "IEDS_Dominated",
                "desc": "Estrategia estrictamente dominada eliminada mediante Eliminación Iterada de Estrategias Dominadas (IEDS).",
            },
        },
        "en": {
            "vgc": {
                "label": "Outclassed (always worse)",
                "short": "Outclassed",
                "desc": "Another legal play of yours yields a strictly better outcome against every possible opponent response.",
            },
            "scientific": {
                "label": "IEDS_Dominated",
                "short": "IEDS_Dominated",
                "desc": "Strictly dominated strategy pruned via Iterated Elimination of Dominated Strategies (IEDS).",
            },
        },
    },
    "ieds_weak": {
        "es": {
            "vgc": {
                "label": "Superada (hay una mejor opción)",
                "short": "Superada",
                "desc": "Existe otra jugada tuya que nunca da peor resultado y te deja mejor en al menos un escenario rival.",
            },
            "scientific": {
                "label": "IEDS_Weakly_Dominated",
                "short": "IEDS_Weakly_Dominated",
                "desc": "Estrategia débilmente dominada (empata en algunos escenarios y pierde en el resto frente a una alternativa).",
            },
        },
        "en": {
            "vgc": {
                "label": "Beaten (strictly/weakly)",
                "short": "Beaten",
                "desc": "Another legal play of yours is never worse and strictly better against at least one opponent response.",
            },
            "scientific": {
                "label": "IEDS_Weakly_Dominated",
                "short": "IEDS_Weakly_Dominated",
                "desc": "Weakly dominated strategy eliminated during weak IEDS reduction.",
            },
        },
    },
    "ieds_survivors": {
        "es": {
            "vgc": {
                "label": "Jugadas viables",
                "short": "Jugadas viables",
                "desc": "Opciones competitivas reales que no son superadas universalmente por ninguna otra jugada.",
            },
            "scientific": {
                "label": "IEDS_Survivors",
                "short": "IEDS_Survivors",
                "desc": "Subconjunto de estrategias no dominadas que sobreviven a IEDS y entran al solver de equilibrio.",
            },
        },
        "en": {
            "vgc": {
                "label": "Viable plays",
                "short": "Viable plays",
                "desc": "Competitive turn options that are not universally outclassed by any alternative line.",
            },
            "scientific": {
                "label": "IEDS_Survivors",
                "short": "IEDS_Survivors",
                "desc": "Undominated strategy set surviving IEDS reduction into the equilibrium solver.",
            },
        },
    },
    "nash_value": {
        "es": {
            "vgc": {
                "label": "Ventaja del turno",
                "short": "Ventaja del turno",
                "desc": "Balance esperado del turno si ambos jugadores eligen sus mejores líneas (> 0 ventaja tuya, < 0 ventaja rival).",
            },
            "scientific": {
                "label": "Nash_Eq_Value",
                "short": "Nash_Eq_Value",
                "desc": "Valor minimax de equilibrio de Nash de suma cero sobre la matriz de utilidad ajustada al riesgo.",
            },
        },
        "en": {
            "vgc": {
                "label": "Turn advantage",
                "short": "Turn advantage",
                "desc": "Expected turn balance assuming optimal play from both sides (> 0 your advantage, < 0 opponent advantage).",
            },
            "scientific": {
                "label": "Nash_Eq_Value",
                "short": "Nash_Eq_Value",
                "desc": "Zero-sum minimax Nash equilibrium game value on the risk-adjusted payoff matrix.",
            },
        },
    },
    "risk_utility": {
        "es": {
            "vgc": {
                "label": "Puntaje ajustado al riesgo",
                "short": "Puntaje c/riesgo",
                "desc": "Calificación que combina el resultado promedio (75%) con el escenario de mala suerte (25%) para premiar jugadas consistentes.",
            },
            "scientific": {
                "label": "Risk_Adjusted_Utility",
                "short": "Risk_Adjusted_Utility",
                "desc": "Utilidad ajustada al riesgo: (1 - λ)·E[U] + λ·CVaR_10_RNG_Floor con λ = 0.25.",
            },
        },
        "en": {
            "vgc": {
                "label": "Risk-adjusted score",
                "short": "Risk-adj. score",
                "desc": "Overall rating blending average outcome (75%) with bad-luck protection (25%) to reward consistent plays.",
            },
            "scientific": {
                "label": "Risk_Adjusted_Utility",
                "short": "Risk_Adjusted_Utility",
                "desc": "Risk-adjusted utility: (1 - λ)·E[U] + λ·CVaR_10_RNG_Floor with λ = 0.25.",
            },
        },
    },
    "cvar_10": {
        "es": {
            "vgc": {
                "label": "Impacto de mala suerte (peor 10% RNG)",
                "short": "Mala suerte (10% RNG)",
                "desc": "Resultado promedio en el 10% de escenarios con peor suerte de dados (misses, rolls bajos, crits rivales o flinches).",
            },
            "scientific": {
                "label": "CVaR_10_RNG_Floor",
                "short": "CVaR_10_RNG_Floor",
                "desc": "Conditional Value at Risk al 10% (media de la cola inferior del 10% de RNG_Samples).",
            },
        },
        "en": {
            "vgc": {
                "label": "Bad-luck floor (worst 10% RNG)",
                "short": "Bad-luck floor (10%)",
                "desc": "Average outcome across the worst 10% RNG rolls (misses, min damage rolls, opponent crits, or flinches).",
            },
            "scientific": {
                "label": "CVaR_10_RNG_Floor",
                "short": "CVaR_10_RNG_Floor",
                "desc": "10% Conditional Value at Risk (mean utility across the worst 10% tail of RNG_Samples).",
            },
        },
    },
    "nash_mix": {
        "es": {
            "vgc": {
                "label": "Mind-game mix %",
                "short": "Mind-game mix %",
                "desc": "En qué proporción alternar esta jugada en un mind-game (50/50 o Bo3) para que el rival no pueda leerte ni explotarte.",
            },
            "scientific": {
                "label": "Nash_Mindgame_Mix_%",
                "short": "Nash_Mindgame_Mix_%",
                "desc": "Probabilidad óptima de estrategia mixta en el Equilibrio de Nash de suma cero (Principio de Indiferencia).",
            },
        },
        "en": {
            "vgc": {
                "label": "Mind-game mix %",
                "short": "Mind-game mix %",
                "desc": "How often to mix this play in a mindgame (50/50 or Bo3) so an opponent who reads your habits cannot exploit you.",
            },
            "scientific": {
                "label": "Nash_Mindgame_Mix_%",
                "short": "Nash_Mindgame_Mix_%",
                "desc": "Optimal mixed-strategy probability in the Zero-Sum Nash Equilibrium (Indifference Principle).",
            },
        },
    },
    "human_qre": {
        "es": {
            "vgc": {
                "label": "Prob. en humanos %",
                "short": "Prob. humanos %",
                "desc": "Qué tan probable es que un jugador humano competitivo elija esta jugada según el nivel de precisión seleccionado.",
            },
            "scientific": {
                "label": "Human_QRE_%",
                "short": "Human_QRE_%",
                "desc": "Probabilidad de respuesta en Equilibrio de Respuesta Cuantal Logit (LQRE con temperatura racional β ajustable).",
            },
        },
        "en": {
            "vgc": {
                "label": "Human likeliness %",
                "short": "Human likeliness %",
                "desc": "How likely a human competitive player is to pick this play at the selected rival skill level.",
            },
            "scientific": {
                "label": "Human_QRE_%",
                "short": "Human_QRE_%",
                "desc": "Choice probability under Logit Quantal Response Equilibrium (LQRE with adjustable rationality β).",
            },
        },
    },
    "qre_beta": {
        "es": {
            "vgc": {
                "label": "Precisión del rival humano",
                "short": "Nivel rival",
                "desc": "Ajusta qué tan disciplinado es tu rival: valores bajos modelan ladder impredecible; valores altos modelan jugadores de Top Cut.",
            },
            "scientific": {
                "label": "LQRE Rationality (β)",
                "short": "LQRE β",
                "desc": "Inversa de temperatura de racionalidad acotada β > 0 en p_i ∝ exp(+β (Uq)_i), q_j ∝ exp(-β (pᵀU)_j).",
            },
        },
        "en": {
            "vgc": {
                "label": "Human opponent precision",
                "short": "Rival skill",
                "desc": "Controls how disciplined your human opponent is: lower = unpredictable ladder clicks; higher = Regional Top Cut precision.",
            },
            "scientific": {
                "label": "LQRE Rationality (β)",
                "short": "LQRE β",
                "desc": "Bounded-rationality inverse temperature β > 0 in p_i ∝ exp(+β (Uq)_i), q_j ∝ exp(-β (pᵀU)_j).",
            },
        },
    },
    "nash_regret": {
        "es": {
            "vgc": {
                "label": "Costo del error",
                "short": "Costo del error",
                "desc": "Cuánta ventaja del turno cediste en comparación con la mejor línea del equilibrio (0.00 = jugada óptima sin costo).",
            },
            "scientific": {
                "label": "Nash_Utility_Loss",
                "short": "Nash_Utility_Loss",
                "desc": "Pérdida de utilidad respecto al equilibrio de Nash: max(0, Nash_Eq_Value − U(a, q*)).",
            },
        },
        "en": {
            "vgc": {
                "label": "Play cost",
                "short": "Play cost",
                "desc": "How much turn advantage was given up compared to the equilibrium line (0.00 = optimal, zero loss).",
            },
            "scientific": {
                "label": "Nash_Utility_Loss",
                "short": "Nash_Utility_Loss",
                "desc": "Equilibrium utility loss (action regret): max(0, Nash_Eq_Value − U(a, q*)).",
            },
        },
    },
    "security_floor": {
        "es": {
            "vgc": {
                "label": "Counter más fuerte del rival",
                "short": "Counter más fuerte",
                "desc": "El peor castigo posible que puede hacerte el rival si adivina exactamente esta jugada.",
            },
            "scientific": {
                "label": "Minimax_Worst_Counter",
                "short": "Minimax_Worst_Counter",
                "desc": "Piso de seguridad minimax por fila: min_j U(i, j) y la respuesta rival argmin_j U(i, j).",
            },
        },
        "en": {
            "vgc": {
                "label": "Hardest rival counter",
                "short": "Hardest counter",
                "desc": "The worst possible punish your opponent can land if they call this exact play.",
            },
            "scientific": {
                "label": "Minimax_Worst_Counter",
                "short": "Minimax_Worst_Counter",
                "desc": "Row-wise minimax security floor: min_j U(i, j) and opponent counter argmin_j U(i, j).",
            },
        },
    },
    "oracle_best_response": {
        "es": {
            "vgc": {
                "label": "Lectura Future Sight (respuesta exacta)",
                "short": "Lectura Future Sight",
                "desc": "El castigo máximo si hubieras visto el futuro sabiendo de antemano qué botón exacto apretó el rival en el replay.",
            },
            "scientific": {
                "label": "Oracle_Best_Response",
                "short": "Oracle_Best_Response",
                "desc": "Mejor respuesta ex-post (hindsight argmax_i U(i, j_actual)) contra la acción real ejecutada por trainer_2.",
            },
        },
        "en": {
            "vgc": {
                "label": "Future Sight read (exact counter)",
                "short": "Future Sight read",
                "desc": "The maximum punish if you had seen the future and known the exact button your opponent clicked in the replay.",
            },
            "scientific": {
                "label": "Oracle_Best_Response",
                "short": "Oracle_BR",
                "desc": "Ex-post hindsight best response (argmax_i U(i, j_actual)) against trainer_2's recorded action.",
            },
        },
    },
    "ko_prob": {
        "es": {
            "vgc": {
                "label": "Probabilidad de KO",
                "short": "Prob. KO",
                "desc": "Porcentaje de veces que un Pokémon cae debilitado en este turno considerando daño, precisión y críticos.",
            },
            "scientific": {
                "label": "P(KO)",
                "short": "P(KO)",
                "desc": "Probabilidad empírica de debilitamiento (HP_cur == 0) al cierre de la cascada discreta de RNG_Samples.",
            },
        },
        "en": {
            "vgc": {
                "label": "KO Chance",
                "short": "KO %",
                "desc": "How often a Pokémon faints on this turn across damage rolls, accuracy checks, and critical hits.",
            },
            "scientific": {
                "label": "P(KO)",
                "short": "P(KO)",
                "desc": "Empirical faint probability (HP_cur == 0) across the discrete RNG_Samples ensemble.",
            },
        },
    },
}

# Canonical alias map so both snake_case keys and legacy/scientific PascalCase keys resolve cleanly
TERM_KEY_ALIASES: Dict[str, str] = {
    "Strats_1": "strats_pair",
    "Strats_2": "strats_pair",
    "RNG_Samples": "rng_samples",
    "RNG_Sample_Count": "rng_samples",
    "IEDS_Strict_Eliminated": "ieds_strict",
    "IEDS_Dominated": "ieds_strict",
    "IEDS_Weak_Eliminated": "ieds_weak",
    "IEDS_Weakly_Dominated": "ieds_weak",
    "IEDS_Survivors": "ieds_survivors",
    "IEDS_Pruned": "ieds_survivors",
    "Nash_Eq_Value": "nash_value",
    "Risk_Adjusted_EV": "risk_utility",
    "Risk_Adjusted_Utility": "risk_utility",
    "Downside_CVaR_10": "cvar_10",
    "CVaR_10_RNG_Floor": "cvar_10",
    "Nash_Mix_Prob": "nash_mix",
    "Nash_Mindgame_Mix_%": "nash_mix",
    "QRE_Human_Prob": "human_qre",
    "Human_QRE_%": "human_qre",
    "Nash_Utility_Loss": "nash_regret",
    "Worst_Case_Payoff": "security_floor",
    "Minimax_Worst_Counter": "security_floor",
    "Future_Sight_Best_Play": "oracle_best_response",
    "Oracle_Best_Response": "oracle_best_response",
    "KO_Prob": "ko_prob",
}

VERDICT_BADGES: Dict[str, Dict[str, Any]] = {
    "optimal": {
        "symbol": "!!",
        "badge_class": "optimal",
        "es": {
            "vgc": "Jugada Top",
            "scientific": "Óptima (Nash)",
        },
        "en": {
            "vgc": "Top Play",
            "scientific": "Optimal (Nash)",
        },
    },
    "good": {
        "symbol": "!",
        "badge_class": "good",
        "es": {
            "vgc": "Sólida",
            "scientific": "Cercana a Nash",
        },
        "en": {
            "vgc": "Solid",
            "scientific": "Near-Nash",
        },
    },
    "inaccuracy": {
        "symbol": "?!",
        "badge_class": "inaccuracy",
        "es": {
            "vgc": "Imprecisión",
            "scientific": "Subóptima",
        },
        "en": {
            "vgc": "Inaccuracy",
            "scientific": "Suboptimal",
        },
    },
    "weak_dominated": {
        "symbol": "?",
        "badge_class": "mistake",
        "es": {
            "vgc": "Superada",
            "scientific": "IEDS_Weakly_Dominated",
        },
        "en": {
            "vgc": "Outclassed",
            "scientific": "IEDS_Weakly_Dominated",
        },
    },
    "strict_dominated": {
        "symbol": "??",
        "badge_class": "blunder",
        "es": {
            "vgc": "Error Grave (Siempre Peor)",
            "scientific": "IEDS_Dominated",
        },
        "en": {
            "vgc": "Blunder (Always Worse)",
            "scientific": "IEDS_Dominated",
        },
    },
}


def normalize_lang_style(lang: str = "es", style: str = "vgc") -> tuple[Language, Style]:
    """Normalize language (`es`/`en`) and style (`vgc`/`scientific`) identifiers."""
    l_clean: Language = "en" if str(lang or "es").lower().strip().startswith("en") else "es"
    s_raw = str(style or "vgc").lower().strip()
    s_clean: Style = "scientific" if s_raw in ("scientific", "sci", "nerd", "math", "audit") else "vgc"
    return l_clean, s_clean


def resolve_term_key(key: str) -> str:
    """Resolve either a canonical snake_case key or a PascalCase alias to its `TERM_GLOSSARY` key."""
    if key in TERM_GLOSSARY:
        return key
    return TERM_KEY_ALIASES.get(key, key)


def get_term_label(key: str, lang: str = "es", style: str = "vgc", short: bool = False) -> str:
    """Return the localized label (or compact column header) for `key`."""
    l_clean, s_clean = normalize_lang_style(lang, style)
    canon = resolve_term_key(key)
    entry = TERM_GLOSSARY.get(canon, {}).get(l_clean, {}).get(s_clean, {})
    if short:
        return entry.get("short") or entry.get("label") or key
    return entry.get("label") or key


def get_term_description(key: str, lang: str = "es", style: str = "vgc") -> str:
    """Return the localized tooltip / explanation for `key`."""
    l_clean, s_clean = normalize_lang_style(lang, style)
    canon = resolve_term_key(key)
    return TERM_GLOSSARY.get(canon, {}).get(l_clean, {}).get(s_clean, {}).get("desc", "")


def get_rng_sampling_note(lang: str = "es", style: str = "vgc", num_samples: int = 128) -> str:
    """Return an explicit description of the discrete RNG sampling dimension and events."""
    l_clean, s_clean = normalize_lang_style(lang, style)
    events = RNG_SAMPLED_EVENTS_TEXT[l_clean][s_clean]
    if s_clean == "scientific":
        if l_clean == "es":
            return f"RNG_Samples = {num_samples} (RNG_Sampling discreto sobre: {events})"
        return f"RNG_Samples = {num_samples} (discrete RNG_Sampling across: {events})"
    if l_clean == "es":
        return f"{num_samples} simulaciones de RNG por cruce (evaluando {events})"
    return f"{num_samples} RNG simulations per matchup (sampling {events})"


def get_verdict_badge(verdict_key: str, lang: str = "es", style: str = "vgc") -> Dict[str, str]:
    """Return `{badge, badge_class, symbol, verdict_key}` for one of the 5 real verdict tiers."""
    l_clean, s_clean = normalize_lang_style(lang, style)
    v_info = VERDICT_BADGES.get(verdict_key, VERDICT_BADGES["inaccuracy"])
    return {
        "verdict_key": verdict_key,
        "badge": v_info[l_clean][s_clean],
        "badge_class": v_info["badge_class"],
        "symbol": v_info["symbol"],
    }


def export_glossary_payload() -> Dict[str, Any]:
    """Export the full 4-variant glossary, aliases, and badge dictionary for zero-latency GUI switching."""
    return {
        "terms": TERM_GLOSSARY,
        "aliases": TERM_KEY_ALIASES,
        "badges": VERDICT_BADGES,
        "rng_events": RNG_SAMPLED_EVENTS_TEXT,
    }
