# -*- coding: utf-8 -*-
"""100% Zero-AI Deterministic Causal Commentary Engine.

Generates transparent, mathematically grounded Spanish tactical commentary for every
turn of a Pokémon Showdown replay purely from GPU Tensor Core witnesses:
  1. Strict & Weak IEDS elimination witnesses (`DominatedActionRecord`)
  2. Zero-Sum Nash Equilibrium regret (`v* - U(a_actual, q*)`) & QRE human ranking
  3. Bad-luck floor (`CVaR_0.10`) & worst-case opponent counter (`argmin_j U`)
  4. Actual replay RNG audit (comparing logged crits/flinches/misses vs `faint_prob`)
  5. Field context warnings (1-ply Trick Room / Weather tempo caveats)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def generate_deterministic_commentary(
    turn_number: int,
    actual_action: Dict[str, Any],
    top_actions: List[Dict[str, Any]],
    nash_value: float,
    ieds_summary: Dict[str, Any],
    events: Dict[str, Any],
    field_context: Dict[str, Any],
) -> Dict[str, Any]:
    """Produce a zero-AI structured verdict, grade badge, and causal bullet list."""
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

    # Classify verdict badge strictly from IEDS & Nash Regret math
    if flinched:
        badge = "INTERRUMPIDA (FLINCH)"
        badge_class = "warn"
        symbol = "!"
        headline = (
            "Un Pokémon de trainer_1 sufrió flinch/bloqueo antes de actuar; "
            "el protocolo oculta el movimiento elegido para ese slot."
        )
    elif strict_dom is not None:
        badge = "DOMINADA EN IEDS"
        badge_class = "blunder"
        symbol = "??"
        headline = (
            f"Jugada estrictamente dominada en Ronda {strict_dom['round']} de IEDS "
            f"(Regret de Nash: {regret:+.3f}). Existía una línea superior contra toda respuesta rival."
        )
    elif weak_dom is not None:
        badge = "DÉBILMENTE DOMINADA"
        badge_class = "mistake"
        symbol = "?"
        headline = (
            f"Eliminada en Ronda {weak_dom['round']} de IEDS débil "
            f"(Regret de Nash: {regret:+.3f})."
        )
    elif regret <= 0.03 or nash_pct >= 5.0:
        badge = "ÓPTIMA (NASH)"
        badge_class = "optimal"
        symbol = "!!"
        headline = (
            f"Ejecución óptima de equilibrio: sobrevivió IEDS Estricto/Débil "
            f"con Regret de Nash de {regret:+.4f} (Nash {nash_pct:.1f}%, QRE {qre_pct:.1f}%)."
        )
    elif regret <= 0.22:
        badge = "SÓLIDA / CERCANA A NASH"
        badge_class = "good"
        symbol = "!"
        headline = (
            f"Buena línea no dominada (sobrevive IEDS), apenas {regret:.3f} debajo del valor "
            f"de equilibrio v* = {nash_value:+.3f}."
        )
    else:
        badge = "SUBÓPTIMA (NO DOMINADA)"
        badge_class = "inaccuracy"
        symbol = "?!"
        headline = (
            f"Sobrevivió a IEDS (no es estrictamente dominada), pero cede {regret:.3f} "
            f"de utilidad ajustada al riesgo frente al equilibrio de Nash ({best_ev:+.3f})."
        )

    bullets: List[Dict[str, str]] = []

    # 1. IEDS Dominance Witness
    if strict_dom is not None:
        bullets.append(
            {
                "tag": "IEDS_ESTRICTO",
                "tone": "bad",
                "text": (
                    f"Eliminada en Ronda {strict_dom['round']} por [{strict_dom['desc']}], "
                    f"que mejora el resultado en al menos +{strict_dom['worst_margin']:.3f} "
                    f"en el peor escenario y +{strict_dom['mean_margin']:.3f} en promedio "
                    f"frente a todas las respuestas rivales sobrevivientes."
                ),
            }
        )
    elif weak_dom is not None:
        bullets.append(
            {
                "tag": "IEDS_DÉBIL",
                "tone": "warn",
                "text": (
                    f"Débilmente dominada en Ronda {weak_dom['round']} por [{weak_dom['desc']}] "
                    f"(margen promedio +{weak_dom['mean_margin']:.3f} sin empeorar ningún escenario)."
                ),
            }
        )
    else:
        bullets.append(
            {
                "tag": "IEDS_OK",
                "tone": "good",
                "text": (
                    f"Sobrevive a la poda iterada: {ieds_summary['t1_total']} → "
                    f"{ieds_summary['t1_strict']} estrategias estrictas ({ieds_summary['t1_weak']} débiles) "
                    f"en {ieds_summary['strict_rounds']} ronda(s). No existe ninguna acción que la domine "
                    f"uniformemente."
                ),
            }
        )

    # 2. Best Alternative Comparison
    if best.get("choice_pair") != actual_action.get("choice_pair"):
        ev_diff = best_ev - risk_ev
        cvar_diff = best_cvar - cvar10
        bullets.append(
            {
                "tag": "MEJOR_LÍNEA",
                "tone": "info",
                "text": (
                    f"Recomendación #1 Nash ({best.get('nash_pct', 0.0):.1f}% Nash, "
                    f"{best.get('qre_pct', 0.0):.1f}% QRE): [{best_desc}] "
                    f"→ RiskEV {best_ev:+.3f} ({ev_diff:+.3f} vs. jugada real), "
                    f"CVaR_10 {best_cvar:+.3f} ({cvar_diff:+.3f})."
                ),
            }
        )
    else:
        bullets.append(
            {
                "tag": "NASH_MATCH",
                "tone": "good",
                "text": (
                    f"Tu jugada coincide con la #1 del motor GPU (RiskEV {risk_ev:+.3f}, "
                    f"CVaR_10 {cvar10:+.3f}, QRE humano {qre_pct:.1f}%)."
                ),
            }
        )

    # 3. Worst-Case Counter & Bad-Luck Floor
    bullets.append(
        {
            "tag": "PISO_RIESGO",
            "tone": "good" if min_j >= 0.0 else "warn",
            "text": (
                f"Piso de seguridad (peor respuesta rival): {min_j:+.3f} frente a "
                f"[{worst_counter}]. Contra la jugada real que ejecutó el oponente, "
                f"tu línea obtuvo U_risk = {actual_action.get('vs_actual_opp_u', 0.0):+.3f} "
                f"(Oracle Best Response: [{actual_action.get('oracle_best_desc', 'N/A')}] "
                f"con {actual_action.get('oracle_best_u', 0.0):+.3f})."
            ),
        }
    )

    # 4. RNG / Crit / Flinch Witness
    if t1_got_crit_luck:
        crit_targets = ", ".join(
            c["target_species"] for c in crits if c.get("target_trainer") == "trainer_2"
        )
        ko_probs = actual_action.get("ko_probs_vs_actual_opp") or {}
        ko_note = ", ".join(f"{k}: {v:.1f}%" for k, v in ko_probs.items())
        bullets.append(
            {
                "tag": "AUDITORÍA_RNG",
                "tone": "warn",
                "text": (
                    f"Crítico favorable registrado en el replay sobre {crit_targets}. "
                    f"Probabilidades de KO discretas (K={actual_action.get('num_mc', 256)}): "
                    f"{ko_note or 'N/A'}."
                ),
            }
        )
    if t1_got_flinched:
        fl_names = ", ".join(
            f["species"] for f in flinches if f.get("trainer") == "trainer_1"
        )
        bullets.append(
            {
                "tag": "FLINCH_DETECTADO",
                "tone": "warn",
                "text": f"Interrupción por Fake Out / Flinch sobre {fl_names} en este turno.",
            }
        )
    if misses:
        miss_names = ", ".join(m["actor_species"] for m in misses)
        bullets.append(
            {
                "tag": "MISS_DETECTADO",
                "tone": "warn",
                "text": f"Fallo de precisión registrado en el replay por: {miss_names}.",
            }
        )

    # 5. Field Tempo Caveat (Honest 1-Ply Trick Room / Weather Context)
    if tr_turns > 0 or turn_number == 1:
        ctx_parts = []
        if tr_turns > 0:
            ctx_parts.append(f"Trick Room activo ({tr_turns}t restantes)")
        if weather:
            ctx_parts.append(f"Clima: {weather} ({field_context.get('weather_turns', 0)}t)")
        if turn_number == 1 and tr_turns == 0:
            ctx_parts.append("Turno 1 ante setter de Trick Room")
        bullets.append(
            {
                "tag": "CONTEXTO_HORIZONTE",
                "tone": "info",
                "text": (
                    f"{' | '.join(ctx_parts)}. Nota técnica del solver 1-ply: "
                    f"el equilibrio de un solo turno valora daño/KOs inmediatos y puede "
                    f"subestimar el valor multi-turno de desgastar turnos de Trick Room o "
                    f"bloquear el setup en T1."
                ),
            }
        )

    return {
        "badge": badge,
        "badge_class": badge_class,
        "symbol": symbol,
        "headline": headline,
        "bullets": bullets,
    }
