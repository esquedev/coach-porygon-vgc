# -*- coding: utf-8 -*-
"""100% Zero-AI Deterministic Causal Commentary Engine (Bilingual ES/EN x VGC/Scientific).

Generates transparent, mathematically grounded tactical commentary for every
turn of a Pokémon Showdown replay purely from GPU Tensor Core witnesses:
  1. Strict & Weak IEDS elimination witnesses (`DominatedActionRecord`)
  2. Zero-Sum Nash Equilibrium utility loss (`Nash_Eq_Value - U(a_actual, q*)`) & QRE human ranking
  3. Bad-luck floor (`Downside_CVaR_10`) & worst-case opponent counter (`Worst_Case_Payoff`)
  4. Actual replay RNG audit (comparing logged crits/flinches/misses vs `KO_Prob`)
  5. Field context warnings (1-ply Trick Room / Weather tempo caveats)
"""
from __future__ import annotations

from typing import Any, Dict, List

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
) -> Dict[str, Any]:
    """Produce a zero-AI structured verdict, grade badge, and causal bullet list in the requested language and style."""
    lg = "en" if str(lang or "es").lower().strip().startswith("en") else "es"
    st = "scientific" if str(style or "vgc").lower().strip() == "scientific" else "vgc"

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

    verdict_key = _classify_verdict_key(strict_dom, weak_dom, regret, nash_pct)
    v_meta = get_verdict_badge(verdict_key, style=st, lang=lg)
    badge = v_meta["badge"]
    badge_class = v_meta["badge_class"]
    symbol = v_meta["symbol"]

    lbl_loss = get_term_label("Nash_Utility_Loss", style=st, lang=lg)
    lbl_val = get_term_label("Nash_Eq_Value", style=st, lang=lg)
    lbl_mix = get_term_label("Nash_Mix_Prob", style=st, lang=lg)
    lbl_qre = get_term_label("QRE_Human_Prob", style=st, lang=lg)
    lbl_risk = get_term_label("Risk_Adjusted_EV", style=st, lang=lg)
    lbl_cvar = get_term_label("Downside_CVaR_10", style=st, lang=lg)
    lbl_floor = get_term_label("Worst_Case_Payoff", style=st, lang=lg)
    lbl_fs = get_term_label("Future_Sight_Best_Play", style=st, lang=lg)
    lbl_ko = get_term_label("KO_Prob", style=st, lang=lg)
    lbl_s1 = get_term_label("Strats_1", style=st, lang=lg)

    if lg == "es":
        if verdict_key == "strict_dominated":
            headline = (
                f"Jugada superada en todo escenario (Ronda {strict_dom['round']}, "
                f"{lbl_loss}: {regret:+.3f}). Existía una línea superior contra toda respuesta rival."
            )
        elif verdict_key == "weak_dominated":
            headline = (
                f"Jugada empatada o superada en Ronda {weak_dom['round']} "
                f"({lbl_loss}: {regret:+.3f})."
            )
        elif verdict_key == "optimal":
            headline = (
                f"Ejecución óptima: sobrevivió al descarte táctico "
                f"con {lbl_loss} de {regret:+.4f} ({lbl_mix}: {nash_pct:.1f}%, {lbl_qre}: {qre_pct:.1f}%)."
            )
        elif verdict_key == "good":
            headline = (
                f"Jugada sólida no superada, a solo {regret:.3f} debajo de "
                f"{lbl_val} ({nash_value:+.3f})."
            )
        else:
            headline = (
                f"Jugada imprecisa (no dominada): cede {regret:.3f} en {lbl_loss} "
                f"frente a la mejor línea ({best_ev:+.3f})."
            )
        if flinched:
            headline += (
                " (Nota: un slot sufrió Flinch antes de actuar; evaluado con su mejor ataque disponible)."
            )
    else:
        if verdict_key == "strict_dominated":
            headline = (
                f"Outclassed in every scenario (Round {strict_dom['round']}, "
                f"{lbl_loss}: {regret:+.3f}). A strictly superior play existed against every opponent response."
            )
        elif verdict_key == "weak_dominated":
            headline = (
                f"Tied or outclassed in Round {weak_dom['round']} "
                f"({lbl_loss}: {regret:+.3f})."
            )
        elif verdict_key == "optimal":
            headline = (
                f"Optimal execution: survived tactical pruning "
                f"with {lbl_loss} of {regret:+.4f} ({lbl_mix}: {nash_pct:.1f}%, {lbl_qre}: {qre_pct:.1f}%)."
            )
        elif verdict_key == "good":
            headline = (
                f"Solid un-dominated play, only {regret:.3f} below "
                f"{lbl_val} ({nash_value:+.3f})."
            )
        else:
            headline = (
                f"Suboptimal play (un-dominated): gives up {regret:.3f} in {lbl_loss} "
                f"compared to the top line ({best_ev:+.3f})."
            )
        if flinched:
            headline += (
                " (Note: one slot flinched before acting; graded using its best available attack)."
            )

    bullets: List[Dict[str, str]] = []

    # 1. IEDS Dominance Witness
    if strict_dom is not None:
        bullets.append(
            {
                "tag": get_term_label("IEDS_Strict_Eliminated", style=st, lang=lg),
                "tone": "bad",
                "text": (
                    f"Eliminada en Ronda {strict_dom['round']} por [{strict_dom['desc']}], "
                    f"que mejora el resultado en al menos +{strict_dom['worst_margin']:.3f} "
                    f"en el peor escenario y +{strict_dom['mean_margin']:.3f} en promedio."
                    if lg == "es"
                    else f"Eliminated in Round {strict_dom['round']} by [{strict_dom['desc']}], "
                    f"which improves the outcome by at least +{strict_dom['worst_margin']:.3f} "
                    f"in the worst case and +{strict_dom['mean_margin']:.3f} on average."
                ),
            }
        )
    elif weak_dom is not None:
        bullets.append(
            {
                "tag": get_term_label("IEDS_Weak_Eliminated", style=st, lang=lg),
                "tone": "warn",
                "text": (
                    f"Superada o empatada en Ronda {weak_dom['round']} por [{weak_dom['desc']}] "
                    f"(margen promedio +{weak_dom['mean_margin']:.3f} sin empeorar ningún escenario)."
                    if lg == "es"
                    else f"Tied or outclassed in Round {weak_dom['round']} by [{weak_dom['desc']}] "
                    f"(average margin +{weak_dom['mean_margin']:.3f} without worsening any scenario)."
                ),
            }
        )
    else:
        bullets.append(
            {
                "tag": lbl_s1,
                "tone": "good",
                "text": (
                    f"Sobrevive al descarte táctico: {ieds_summary['t1_total']} → "
                    f"{ieds_summary['t1_strict']} opciones principales ({ieds_summary['t1_weak']} desempate) "
                    f"en {ieds_summary['strict_rounds']} ronda(s). Ninguna otra jugada la supera en todos los escenarios."
                    if lg == "es"
                    else f"Survives tactical pruning: {ieds_summary['t1_total']} → "
                    f"{ieds_summary['t1_strict']} core options ({ieds_summary['t1_weak']} tie-break) "
                    f"in {ieds_summary['strict_rounds']} round(s). No other play beats it across all scenarios."
                ),
            }
        )

    # 2. Best Alternative Comparison
    if best.get("choice_pair") != actual_action.get("choice_pair"):
        ev_diff = best_ev - risk_ev
        cvar_diff = best_cvar - cvar10
        bullets.append(
            {
                "tag": "MEJOR_LÍNEA" if lg == "es" else "TOP_RECOMMENDATION",
                "tone": "info",
                "text": (
                    f"Recomendación #1 ({lbl_mix}: {best.get('nash_pct', 0.0):.1f}%, "
                    f"{lbl_qre}: {best.get('qre_pct', 0.0):.1f}%): [{best_desc}] "
                    f"→ {lbl_risk} {best_ev:+.3f} ({ev_diff:+.3f} vs. jugada real), "
                    f"{lbl_cvar} {best_cvar:+.3f} ({cvar_diff:+.3f})."
                    if lg == "es"
                    else f"#1 Recommendation ({lbl_mix}: {best.get('nash_pct', 0.0):.1f}%, "
                    f"{lbl_qre}: {best.get('qre_pct', 0.0):.1f}%): [{best_desc}] "
                    f"→ {lbl_risk} {best_ev:+.3f} ({ev_diff:+.3f} vs. played move), "
                    f"{lbl_cvar} {best_cvar:+.3f} ({cvar_diff:+.3f})."
                ),
            }
        )
    else:
        bullets.append(
            {
                "tag": "NASH_MATCH",
                "tone": "good",
                "text": (
                    f"Tu jugada coincide con la #1 del motor ({lbl_risk}: {risk_ev:+.3f}, "
                    f"{lbl_cvar}: {cvar10:+.3f}, {lbl_qre}: {qre_pct:.1f}%)."
                    if lg == "es"
                    else f"Your play matches the engine's #1 recommendation ({lbl_risk}: {risk_ev:+.3f}, "
                    f"{lbl_cvar}: {cvar10:+.3f}, {lbl_qre}: {qre_pct:.1f}%)."
                ),
            }
        )

    # 3. Worst-Case Counter & Future Sight Best Play
    bullets.append(
        {
            "tag": lbl_floor,
            "tone": "good" if min_j >= 0.0 else "warn",
            "text": (
                f"{lbl_floor}: {min_j:+.3f} frente a [{worst_counter}]. "
                f"Contra la jugada real del rival, tu línea obtuvo {lbl_risk} = "
                f"{actual_action.get('vs_actual_opp_u', 0.0):+.3f} "
                f"({lbl_fs}: [{actual_action.get('oracle_best_desc', 'N/A')}] "
                f"con {actual_action.get('oracle_best_u', 0.0):+.3f})."
                if lg == "es"
                else f"{lbl_floor}: {min_j:+.3f} against [{worst_counter}]. "
                f"Against the opponent's actual play, your line scored {lbl_risk} = "
                f"{actual_action.get('vs_actual_opp_u', 0.0):+.3f} "
                f"({lbl_fs}: [{actual_action.get('oracle_best_desc', 'N/A')}] "
                f"at {actual_action.get('oracle_best_u', 0.0):+.3f})."
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
                "tag": get_term_label("RNG_Sample_Count", style=st, lang=lg),
                "tone": "warn",
                "text": (
                    f"Crítico favorable registrado sobre {crit_targets}. "
                    f"{lbl_ko} (K={actual_action.get('num_mc', 256)}): {ko_note or 'N/A'}. "
                    f"{get_rng_sampling_note(style=st, lang=lg)}"
                    if lg == "es"
                    else f"Favorable critical hit logged onto {crit_targets}. "
                    f"{lbl_ko} (K={actual_action.get('num_mc', 256)}): {ko_note or 'N/A'}. "
                    f"{get_rng_sampling_note(style=st, lang=lg)}"
                ),
            }
        )
    if t1_got_flinched:
        fl_names = ", ".join(
            f["species"] for f in flinches if f.get("trainer") == "trainer_1"
        )
        bullets.append(
            {
                "tag": "FLINCH",
                "tone": "warn",
                "text": (
                    f"Interrupción por Fake Out / Flinch sobre {fl_names} en este turno."
                    if lg == "es"
                    else f"Fake Out / Flinch interruption on {fl_names} this turn."
                ),
            }
        )
    if misses:
        miss_names = ", ".join(m["actor_species"] for m in misses)
        bullets.append(
            {
                "tag": "MISS",
                "tone": "warn",
                "text": (
                    f"Fallo de precisión registrado en el replay por: {miss_names}."
                    if lg == "es"
                    else f"Accuracy miss logged in the replay by: {miss_names}."
                ),
            }
        )

    # 5. Field Tempo Caveat (Honest 1-Ply Trick Room / Weather Context)
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
                "Turno 1 (posicionamiento inicial)" if lg == "es" else "Turn 1 (opening positioning)"
            )
        bullets.append(
            {
                "tag": "CONTEXTO_1_TURNO" if lg == "es" else "1_PLY_CONTEXT",
                "tone": "info",
                "text": (
                    f"{' | '.join(ctx_parts)}. El motor evalúa ventaja posicional, iniciativa de velocidad "
                    f"(incluyendo inversión de Trick Room) y sinergia de clima/terreno al cierre del turno."
                    if lg == "es"
                    else f"{' | '.join(ctx_parts)}. The engine evaluates positional advantage, speed initiative "
                    f"(including Trick Room inversion), and weather/terrain synergy at end of turn."
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
            )
    return variants
