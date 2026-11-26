# -*- coding: utf-8 -*-
"""100% Zero-AI Deterministic Causal Commentary Engine (Bilingual ES/EN x VGC/Scientific).

Generates transparent, mathematically grounded tactical commentary for every turn of a
Pokémon Showdown replay purely from Tensor Core witnesses, with strictly separated
registers:
  - `vgc` (`es_vgc`, `en_vgc`): Direct competitive VGC coach language — ZERO academic
    abbreviations (`IEDS`, `Nash`, `QRE`, `CVaR`, `EV`, `Minimax`, `1-ply`).
  - `scientific` (`es_scientific`, `en_scientific`): Full formal game-theoretic and
    quantitative notation (`IEDS`, `Nash_Eq_Value`, `Nash_Utility_Loss`, `U_risk`,
    `CVaR_10_RNG_Floor`, `Human_QRE_%`, `Minimax_Worst_Counter`, `Oracle_Best_Response`).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.terminology import (
    get_rng_sampling_note,
    get_term_label,
    get_verdict_badge,
)


def _classify_verdict_key(
    strict_dom: Any,
    weak_dom: Any,
    regret: float,
    nash_pct: float,
) -> str:
    """Classify a play into one of the 5 canonical verdict keys strictly from IEDS & Nash math."""
    if strict_dom is not None:
        return "strict_dominated"
    if weak_dom is not None:
        return "weak_dominated"
    if regret <= 0.03 or nash_pct >= 5.0:
        return "optimal"
    if regret <= 0.22:
        return "good"
    return "inaccuracy"


_PILLAR_LABELS: Dict[str, Dict[str, str]] = {
    "material": {
        "es_vgc": "Material (HP y KOs)",
        "en_vgc": "Material (HP & KOs)",
        "es_scientific": "Material_KO",
        "en_scientific": "Material_KO",
    },
    "threat": {
        "es_vgc": "Presión de KO",
        "en_vgc": "Lethal Pressure",
        "es_scientific": "Amenaza_Letal",
        "en_scientific": "Lethal_Threat",
    },
    "malposition": {
        "es_vgc": "Mal Posicionamiento Rival",
        "en_vgc": "Enemy Mal-Positioning",
        "es_scientific": "Mal_Posicionamiento",
        "en_scientific": "Mal_Positioning",
    },
    "restriction": {
        "es_vgc": "Restricción de Opciones",
        "en_vgc": "Option Lock",
        "es_scientific": "Restriccion_Opciones",
        "en_scientific": "Option_Restriction",
    },
    "status_boost": {
        "es_vgc": "Estados y Boosts",
        "en_vgc": "Status & Boosts",
        "es_scientific": "Estados_Boosts",
        "en_scientific": "Status_Boosts",
    },
    "two_turn_prime": {
        "es_vgc": "Jugada Preparada (2 Turnos)",
        "en_vgc": "2-Turn Primed Payoff",
        "es_scientific": "Primed_2Turn",
        "en_scientific": "Two_Turn_Prime",
    },
    "resources": {
        "es_vgc": "Escudos y Recursos",
        "en_vgc": "Shields & Resources",
        "es_scientific": "Recursos_Escudos",
        "en_scientific": "Resource_Shields",
    },
    "field_tempo": {
        "es_vgc": "Control de Campo y Velocidad",
        "en_vgc": "Field & Speed Tempo",
        "es_scientific": "Tempo_Campo",
        "en_scientific": "Field_Tempo",
    },
}


def generate_deterministic_commentary(
    turn_number: int,
    actual_action: Dict[str, Any],
    top_actions: List[Dict[str, Any]],
    nash_value: float,
    ieds_summary: Dict[str, Any],
    events: Dict[str, Any],
    field_context: Dict[str, Any],
    lang: str = "es",
    style: str = "vgc",
    equity_breakdown: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Produce a zero-AI structured verdict, grade badge, and causal bullet list in the requested language and style."""
    lg = "en" if str(lang or "es").lower().strip().startswith("en") else "es"
    st = "scientific" if str(style or "vgc").lower().strip() == "scientific" else "vgc"
    is_sci = st == "scientific"

    regret = float(actual_action.get("nash_regret", 0.0))
    nash_pct = float(actual_action.get("nash_pct", 0.0))
    qre_pct = float(actual_action.get("qre_pct", 0.0))
    strict_dom = actual_action.get("strict_dominated_by")
    weak_dom = actual_action.get("weak_dominated_by")
    risk_ev = float(actual_action.get("risk_ev", 0.0))
    cvar10 = float(actual_action.get("cvar10", 0.0))
    min_j = float(actual_action.get("security_floor", 0.0))
    worst_counter = actual_action.get("worst_counter_desc", "N/A")
    flinched = bool(actual_action.get("flinched_hidden", False))
    num_mc = int(actual_action.get("num_mc", 256))

    best = top_actions[0] if top_actions else actual_action
    best_desc = best.get("desc", "N/A")
    best_ev = float(best.get("risk_ev", nash_value))
    best_cvar = float(best.get("cvar10", 0.0))

    crits = events.get("crits") or []
    misses = events.get("misses") or []
    flinches = events.get("flinches") or []
    t1_got_crit_luck = any(c.get("target_trainer") == "trainer_2" for c in crits)
    t1_got_flinched = any(f.get("trainer") == "trainer_1" for f in flinches)
    tr_turns = int(field_context.get("trick_room_turns", 0))
    weather = field_context.get("weather")

    verdict_key = _classify_verdict_key(strict_dom, weak_dom, regret, nash_pct)
    v_meta = get_verdict_badge(verdict_key, style=st, lang=lg)
    badge = v_meta["badge"]
    badge_class = v_meta["badge_class"]
    symbol = v_meta["symbol"]

    lbl_loss = get_term_label("nash_regret", style=st, lang=lg)
    lbl_val = get_term_label("nash_value", style=st, lang=lg)
    lbl_mix = get_term_label("nash_mix", style=st, lang=lg)
    lbl_qre = get_term_label("human_qre", style=st, lang=lg)
    lbl_risk = get_term_label("risk_utility", style=st, lang=lg)
    lbl_cvar = get_term_label("cvar_10", style=st, lang=lg)
    lbl_floor = get_term_label("security_floor", style=st, lang=lg)
    lbl_fs = get_term_label("oracle_best_response", style=st, lang=lg)
    lbl_ko = get_term_label("ko_prob", style=st, lang=lg)

    # -------------------------------------------------------------------------
    # Headline: Strictly differentiated between VGC coach prose & Scientific audit
    # -------------------------------------------------------------------------
    if not is_sci:
        # Plain Competitive VGC Coach (ZERO math jargon)
        if lg == "es":
            if verdict_key == "strict_dominated":
                headline = (
                    f"Había una jugada estrictamente mejor contra cualquier botón del rival: "
                    f"[{strict_dom['desc']}]."
                )
            elif verdict_key == "weak_dominated":
                headline = (
                    f"[{weak_dom['desc']}] hacía lo mismo o mejor en todos los escenarios de este turno."
                )
            elif verdict_key == "optimal":
                headline = (
                    f"Excelente decisión: esta jugada está entre las mejores líneas del turno "
                    f"(frecuencia ideal de mix: {nash_pct:.0f}%)."
                )
            elif verdict_key == "good":
                headline = (
                    f"Jugada sólida y competitiva: mantiene prácticamente toda la ventaja del turno "
                    f"(solo cede {regret:.2f} frente a la opción #1)."
                )
            else:
                headline = (
                    f"Jugada imprecisa: pierdes {regret:.2f} de ventaja frente a la línea recomendada "
                    f"[{best_desc}]."
                )
            if flinched:
                headline += " (Un Pokémon sufrió Flinch antes de actuar; evaluado con su mejor ataque disponible)."
        else:
            if verdict_key == "strict_dominated":
                headline = (
                    f"Strictly outclassed: [{strict_dom['desc']}] gives a better board against every opponent response."
                )
            elif verdict_key == "weak_dominated":
                headline = (
                    f"[{weak_dom['desc']}] matches or beats this play across every opponent option."
                )
            elif verdict_key == "optimal":
                headline = (
                    f"Great call: this line is right in the optimal turn plan (recommended mix rate: {nash_pct:.0f}%)."
                )
            elif verdict_key == "good":
                headline = (
                    f"Solid competitive play: keeps almost all of your turn advantage "
                    f"(only {regret:.2f} behind the #1 line)."
                )
            else:
                headline = (
                    f"Inaccurate line: gives up {regret:.2f} of turn advantage compared to [{best_desc}]."
                )
            if flinched:
                headline += " (One slot flinched before moving; graded with its best available attack)."
    else:
        # Formal Quantitative / Game-Theoretic Scientific Register
        if lg == "es":
            if verdict_key == "strict_dominated":
                headline = (
                    f"Estrategia estrictamente dominada en IEDS Ronda {strict_dom['round']} "
                    f"({lbl_loss} = {regret:+.4f} vs. {lbl_val} = {nash_value:+.4f})."
                )
            elif verdict_key == "weak_dominated":
                headline = (
                    f"Estrategia débilmente dominada en IEDS Ronda {weak_dom['round']} "
                    f"({lbl_loss} = {regret:+.4f}, {lbl_val} = {nash_value:+.4f})."
                )
            elif verdict_key == "optimal":
                headline = (
                    f"Soporte óptimo del Equilibrio de Nash ({lbl_loss} = {regret:.4f}, "
                    f"{lbl_mix} = {nash_pct:.1f}%, {lbl_qre} = {qre_pct:.1f}%)."
                )
            elif verdict_key == "good":
                headline = (
                    f"Estrategia no dominada cercana al equilibrio: {lbl_loss} = {regret:.4f} "
                    f"bajo {lbl_val} ({nash_value:+.4f})."
                )
            else:
                headline = (
                    f"Estrategia subóptima no dominada: {lbl_loss} = {regret:.4f} respecto a "
                    f"U* = {best_ev:+.4f} ({lbl_val} = {nash_value:+.4f})."
                )
            if flinched:
                headline += " [Flinch pre-acción: slot reconstruido vía argmax U_risk(no-Protect/no-Switch)]."
        else:
            if verdict_key == "strict_dominated":
                headline = (
                    f"Strictly dominated strategy eliminated in IEDS Round {strict_dom['round']} "
                    f"({lbl_loss} = {regret:+.4f} vs. {lbl_val} = {nash_value:+.4f})."
                )
            elif verdict_key == "weak_dominated":
                headline = (
                    f"Weakly dominated strategy eliminated in IEDS Round {weak_dom['round']} "
                    f"({lbl_loss} = {regret:+.4f}, {lbl_val} = {nash_value:+.4f})."
                )
            elif verdict_key == "optimal":
                headline = (
                    f"Optimal Nash equilibrium support ({lbl_loss} = {regret:.4f}, "
                    f"{lbl_mix} = {nash_pct:.1f}%, {lbl_qre} = {qre_pct:.1f}%)."
                )
            elif verdict_key == "good":
                headline = (
                    f"Undominated near-equilibrium strategy: {lbl_loss} = {regret:.4f} "
                    f"below {lbl_val} ({nash_value:+.4f})."
                )
            else:
                headline = (
                    f"Suboptimal undominated strategy: {lbl_loss} = {regret:.4f} relative to "
                    f"U* = {best_ev:+.4f} ({lbl_val} = {nash_value:+.4f})."
                )
            if flinched:
                headline += " [Pre-action Flinch: slot reconstructed via argmax U_risk(non-Protect/non-Switch)]."

    bullets: List[Dict[str, str]] = []

    # -------------------------------------------------------------------------
    # 1. Dominance / Viability Analysis
    # -------------------------------------------------------------------------
    if strict_dom is not None:
        if not is_sci:
            bullets.append(
                {
                    "tag": "Por qué fue error" if lg == "es" else "Why it loses",
                    "tone": "bad",
                    "text": (
                        f"[{strict_dom['desc']}] te deja mejor contra todas las respuestas posibles del rival "
                        f"(gana al menos +{strict_dom['worst_margin']:.2f} incluso en el peor escenario y +{strict_dom['mean_margin']:.2f} en promedio)."
                        if lg == "es"
                        else f"[{strict_dom['desc']}] leaves you better off against every possible rival move "
                        f"(at least +{strict_dom['worst_margin']:.2f} better in the worst case and +{strict_dom['mean_margin']:.2f} on average)."
                    ),
                }
            )
        else:
            bullets.append(
                {
                    "tag": get_term_label("ieds_strict", style=st, lang=lg),
                    "tone": "bad",
                    "text": (
                        f"Eliminada en IEDS estricta (Ronda {strict_dom['round']}) por [{strict_dom['desc']}]: "
                        f"margen minimax ≥ +{strict_dom['worst_margin']:.4f}, margen medio +{strict_dom['mean_margin']:.4f} ∀ j ∈ Strats_2."
                        if lg == "es"
                        else f"Eliminated in strict IEDS (Round {strict_dom['round']}) by [{strict_dom['desc']}]: "
                        f"minimax margin ≥ +{strict_dom['worst_margin']:.4f}, mean margin +{strict_dom['mean_margin']:.4f} ∀ j ∈ Strats_2."
                    ),
                }
            )
    elif weak_dom is not None:
        if not is_sci:
            bullets.append(
                {
                    "tag": "Opción superior" if lg == "es" else "Cleaner alternative",
                    "tone": "warn",
                    "text": (
                        f"[{weak_dom['desc']}] nunca te deja peor que tu jugada y gana +{weak_dom['mean_margin']:.2f} en promedio."
                        if lg == "es"
                        else f"[{weak_dom['desc']}] is never worse than your play and gains +{weak_dom['mean_margin']:.2f} on average."
                    ),
                }
            )
        else:
            bullets.append(
                {
                    "tag": get_term_label("ieds_weak", style=st, lang=lg),
                    "tone": "warn",
                    "text": (
                        f"Dominada débilmente en IEDS Ronda {weak_dom['round']} por [{weak_dom['desc']}] "
                        f"(ΔU medio = +{weak_dom['mean_margin']:.4f}, ΔU mínimo ≥ 0)."
                        if lg == "es"
                        else f"Weakly dominated in IEDS Round {weak_dom['round']} by [{weak_dom['desc']}] "
                        f"(mean ΔU = +{weak_dom['mean_margin']:.4f}, min ΔU ≥ 0)."
                    ),
                }
            )
    else:
        if not is_sci:
            bullets.append(
                {
                    "tag": "Jugada viable" if lg == "es" else "Viable option",
                    "tone": "good",
                    "text": (
                        f"Pasó el filtro táctico entre {ieds_summary['t1_strict']} opciones reales (de {ieds_summary['t1_total']} legales): "
                        f"ninguna otra jugada la supera en todos los escenarios."
                        if lg == "es"
                        else f"Cleared the tactical filter among {ieds_summary['t1_strict']} real options (out of {ieds_summary['t1_total']} legal plays): "
                        f"no other line beats it in every scenario."
                    ),
                }
            )
        else:
            bullets.append(
                {
                    "tag": get_term_label("ieds_survivors", style=st, lang=lg),
                    "tone": "good",
                    "text": (
                        f"Sobrevive a IEDS: Strats_1 {ieds_summary['t1_total']} → {ieds_summary['t1_strict']} estrictas "
                        f"({ieds_summary['t1_weak']} débiles) en {ieds_summary['strict_rounds']} ronda(s)."
                        if lg == "es"
                        else f"Survives IEDS: Strats_1 {ieds_summary['t1_total']} → {ieds_summary['t1_strict']} strict "
                        f"({ieds_summary['t1_weak']} weak) in {ieds_summary['strict_rounds']} round(s)."
                    ),
                }
            )

    # -------------------------------------------------------------------------
    # 2. Best Alternative Comparison
    # -------------------------------------------------------------------------
    if best.get("choice_pair") != actual_action.get("choice_pair"):
        ev_diff = best_ev - risk_ev
        cvar_diff = best_cvar - cvar10
        if not is_sci:
            bullets.append(
                {
                    "tag": "Mejor jugada" if lg == "es" else "Recommended line",
                    "tone": "info",
                    "text": (
                        f"[{best_desc}] mejora tu posición en {ev_diff:+.2f} "
                        f"y protege mejor ante mala suerte ({cvar_diff:+.2f} en el peor 10% de RNG)."
                        if lg == "es"
                        else f"[{best_desc}] improves your board score by {ev_diff:+.2f} "
                        f"and holds up better on bad RNG rolls ({cvar_diff:+.2f} in the worst 10% tail)."
                    ),
                }
            )
        else:
            bullets.append(
                {
                    "tag": "Optimum_Line (p*)" if lg == "en" else "Línea_Óptima (p*)",
                    "tone": "info",
                    "text": (
                        f"[{best_desc}] ({lbl_mix}={best.get('nash_pct', 0.0):.1f}%, {lbl_qre}={best.get('qre_pct', 0.0):.1f}%): "
                        f"{lbl_risk}={best_ev:+.4f} (Δ={ev_diff:+.4f}), {lbl_cvar}={best_cvar:+.4f} (Δ={cvar_diff:+.4f})."
                        if lg == "es"
                        else f"[{best_desc}] ({lbl_mix}={best.get('nash_pct', 0.0):.1f}%, {lbl_qre}={best.get('qre_pct', 0.0):.1f}%): "
                        f"{lbl_risk}={best_ev:+.4f} (Δ={ev_diff:+.4f}), {lbl_cvar}={best_cvar:+.4f} (Δ={cvar_diff:+.4f})."
                    ),
                }
            )
    else:
        if not is_sci:
            bullets.append(
                {
                    "tag": "Elección #1" if lg == "es" else "#1 Choice",
                    "tone": "good",
                    "text": (
                        f"Coincidiste exactamente con la recomendación #1 del motor "
                        f"(puntaje {risk_ev:+.2f}, piso en mala suerte {cvar10:+.2f})."
                        if lg == "es"
                        else f"You matched the engine's #1 recommendation "
                        f"(score {risk_ev:+.2f}, bad-luck floor {cvar10:+.2f})."
                    ),
                }
            )
        else:
            bullets.append(
                {
                    "tag": "Nash_Argmax_Match",
                    "tone": "good",
                    "text": (
                        f"Coincidencia con el soporte #1: {lbl_risk}={risk_ev:+.4f}, "
                        f"{lbl_cvar}={cvar10:+.4f}, {lbl_qre}={qre_pct:.1f}%."
                        if lg == "es"
                        else f"Matched #1 equilibrium support: {lbl_risk}={risk_ev:+.4f}, "
                        f"{lbl_cvar}={cvar10:+.4f}, {lbl_qre}={qre_pct:.1f}%."
                    ),
                }
            )

    # -------------------------------------------------------------------------
    # 3. Hardest Rival Counter & Exact Read
    # -------------------------------------------------------------------------
    if not is_sci:
        bullets.append(
            {
                "tag": "Mayor castigo rival" if lg == "es" else "Hardest rival punish",
                "tone": "good" if min_j >= 0.0 else "warn",
                "text": (
                    f"Si el rival adivina tu jugada, su castigo más fuerte es [{worst_counter}] ({min_j:+.2f}). "
                    f"Contra lo que realmente jugó el rival, el castigo perfecto habría sido [{actual_action.get('oracle_best_desc', 'N/A')}]."
                    if lg == "es"
                    else f"If your opponent reads this play, their hardest punish is [{worst_counter}] ({min_j:+.2f}). "
                    f"Against what they actually clicked, the exact read was [{actual_action.get('oracle_best_desc', 'N/A')}]."
                ),
            }
        )
    else:
        bullets.append(
            {
                "tag": lbl_floor,
                "tone": "good" if min_j >= 0.0 else "warn",
                "text": (
                    f"{lbl_floor}: min_j U(a, j) = {min_j:+.4f} vs. [{worst_counter}]. "
                    f"Ex-post vs. j_actual: U_risk = {actual_action.get('vs_actual_opp_u', 0.0):+.4f} "
                    f"({lbl_fs}: [{actual_action.get('oracle_best_desc', 'N/A')}] con U = {actual_action.get('oracle_best_u', 0.0):+.4f})."
                    if lg == "es"
                    else f"{lbl_floor}: min_j U(a, j) = {min_j:+.4f} vs. [{worst_counter}]. "
                    f"Ex-post vs. j_actual: U_risk = {actual_action.get('vs_actual_opp_u', 0.0):+.4f} "
                    f"({lbl_fs}: [{actual_action.get('oracle_best_desc', 'N/A')}] at U = {actual_action.get('oracle_best_u', 0.0):+.4f})."
                ),
            }
        )

    # -------------------------------------------------------------------------
    # 4. RNG / Crit / Flinch / Miss Witnesses
    # -------------------------------------------------------------------------
    if t1_got_crit_luck:
        crit_targets = ", ".join(
            c["target_species"] for c in crits if c.get("target_trainer") == "trainer_2"
        )
        ko_probs = actual_action.get("ko_probs_vs_actual_opp") or {}
        ko_note = ", ".join(f"{k}: {v:.0f}%" for k, v in ko_probs.items())
        if not is_sci:
            bullets.append(
                {
                    "tag": "Suerte / Crítico" if lg == "es" else "Crit luck",
                    "tone": "warn",
                    "text": (
                        f"Conectaste un golpe crítico sobre {crit_targets}. Probabilidad real de KO en este turno: {ko_note or 'N/A'}."
                        if lg == "es"
                        else f"You landed a critical hit on {crit_targets}. True KO odds on this turn: {ko_note or 'N/A'}."
                    ),
                }
            )
        else:
            bullets.append(
                {
                    "tag": get_term_label("rng_samples", style=st, lang=lg),
                    "tone": "warn",
                    "text": (
                        f"Crítico favorable sobre {crit_targets}. {lbl_ko} (K={num_mc}): {ko_note or 'N/A'}. "
                        f"{get_rng_sampling_note(style=st, lang=lg, num_samples=num_mc)}"
                        if lg == "es"
                        else f"Favorable critical hit onto {crit_targets}. {lbl_ko} (K={num_mc}): {ko_note or 'N/A'}. "
                        f"{get_rng_sampling_note(style=st, lang=lg, num_samples=num_mc)}"
                    ),
                }
            )
    if t1_got_flinched:
        fl_names = ", ".join(
            f["species"] for f in flinches if f.get("trainer") == "trainer_1"
        )
        bullets.append(
            {
                "tag": "Flinch" if not is_sci else "FLINCH_EVENT",
                "tone": "warn",
                "text": (
                    f"{fl_names} fue interrumpido por Fake Out / Flinch en este turno."
                    if lg == "es"
                    else f"{fl_names} was interrupted by Fake Out / Flinch on this turn."
                ),
            }
        )
    if misses:
        miss_names = ", ".join(m["actor_species"] for m in misses)
        bullets.append(
            {
                "tag": "Fallo de precisión" if (lg == "es" and not is_sci) else ("Accuracy miss" if not is_sci else "ACCURACY_MISS"),
                "tone": "warn",
                "text": (
                    f"Fallo de precisión registrado en el replay por: {miss_names}."
                    if lg == "es"
                    else f"Accuracy miss logged in the replay by: {miss_names}."
                ),
            }
        )

    # -------------------------------------------------------------------------
    # 4b. 8-Pillar Victory Equity Drivers (Non-Material Tactical Edge)
    # -------------------------------------------------------------------------
    if isinstance(equity_breakdown, dict):
        top_drivers = equity_breakdown.get("top_drivers") or []
        prof_key = f"{lg}_{st}"
        driver_strs: List[str] = []
        mode_is_delta = False
        for drv in top_drivers[:3]:
            pkey = str(drv.get("pillar", ""))
            if not pkey or pkey == "material":
                continue
            val = float(drv.get("value", 0.0))
            if abs(val) < 0.03:
                continue
            if drv.get("mode") == "delta":
                mode_is_delta = True
            plabel = _PILLAR_LABELS.get(pkey, {}).get(prof_key, pkey)
            driver_strs.append(f"{val:+.2f} {plabel}")

        if driver_strs:
            joined = " · ".join(driver_strs)
            if not is_sci:
                if lg == "es":
                    prefix = (
                        "Ventaja táctica clave de la mejor línea sobre tu jugada: "
                        if mode_is_delta
                        else "Factores tácticos clave de la posición al cierre del turno: "
                    )
                    tag = "Motores de Equity"
                else:
                    prefix = (
                        "Key tactical edge of the top line over your play: "
                        if mode_is_delta
                        else "Key tactical drivers of the end-of-turn position: "
                    )
                    tag = "Equity Drivers"
            else:
                if lg == "es":
                    prefix = (
                        "ΔV_eq (Nash - Jugada) fuera de material: "
                        if mode_is_delta
                        else "Descomposición V_eq (pilares no materiales, 1 KO = 1.75): "
                    )
                    tag = "Atribucion_Equity_8_Pilares"
                else:
                    prefix = (
                        "ΔV_eq (Nash - Played) non-material drivers: "
                        if mode_is_delta
                        else "V_eq 8-Pillar decomposition (non-material, 1 KO = 1.75): "
                    )
                    tag = "8_Pillar_Equity_Attribution"
            bullets.append(
                {
                    "tag": tag,
                    "tone": "info",
                    "text": f"{prefix}{joined}.",
                }
            )

    # -------------------------------------------------------------------------
    # 5. Field Tempo Context (Trick Room / Weather / Turn 1)
    # -------------------------------------------------------------------------
    if tr_turns > 0 or turn_number == 1:
        ctx_parts = []
        if tr_turns > 0:
            ctx_parts.append(
                f"Trick Room activo ({tr_turns}t)" if lg == "es" else f"Trick Room active ({tr_turns}t)"
            )
        if weather:
            ctx_parts.append(
                f"Clima: {weather} ({field_context.get('weather_turns', 0)}t)"
                if lg == "es"
                else f"Weather: {weather} ({field_context.get('weather_turns', 0)}t)"
            )
        if turn_number == 1 and tr_turns == 0:
            ctx_parts.append(
                "Turno 1 (leads iniciales)" if lg == "es" else "Turn 1 (opening leads)"
            )
        if not is_sci:
            bullets.append(
                {
                    "tag": "Tempo de campo" if lg == "es" else "Board tempo",
                    "tone": "info",
                    "text": (
                        f"{' · '.join(ctx_parts)}. Se valora HP restante, KOs, control de velocidad (incluyendo Trick Room) y clima/terreno."
                        if lg == "es"
                        else f"{' · '.join(ctx_parts)}. Weighs remaining HP, KOs, speed control (including Trick Room), and weather/terrain."
                    ),
                }
            )
        else:
            bullets.append(
                {
                    "tag": "1_Ply_State_Context" if lg == "en" else "Contexto_1_Ply",
                    "tone": "info",
                    "text": (
                        f"{' | '.join(ctx_parts)}. Utilidad terminal U(F_eot, P_eot) integra HP%, KOs, boosts, speed initiative (signo TR) y sinergia clima/terreno."
                        if lg == "es"
                        else f"{' | '.join(ctx_parts)}. Terminal utility U(F_eot, P_eot) integrates HP%, KOs, boosts, speed initiative (TR sign), and weather/terrain synergy."
                    ),
                }
            )

    return {
        "verdict_key": verdict_key,
        "lang": lg,
        "style": st,
        "badge": badge,
        "badge_class": badge_class,
        "symbol": symbol,
        "headline": headline,
        "bullets": bullets,
    }


def generate_all_commentary_variants(
    turn_number: int,
    actual_action: Dict[str, Any],
    top_actions: List[Dict[str, Any]],
    nash_value: float,
    ieds_summary: Dict[str, Any],
    events: Dict[str, Any],
    field_context: Dict[str, Any],
    equity_breakdown: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Pre-render all 4 combinations (`es_vgc`, `en_vgc`, `es_scientific`, `en_scientific`) for instant UI toggling."""
    variants: Dict[str, Dict[str, Any]] = {}
    for lg in ("es", "en"):
        for st in ("vgc", "scientific"):
            variants[f"{lg}_{st}"] = generate_deterministic_commentary(
                turn_number=turn_number,
                actual_action=actual_action,
                top_actions=top_actions,
                nash_value=nash_value,
                ieds_summary=ieds_summary,
                events=events,
                field_context=field_context,
                lang=lg,
                style=st,
                equity_breakdown=equity_breakdown,
            )
    return variants
