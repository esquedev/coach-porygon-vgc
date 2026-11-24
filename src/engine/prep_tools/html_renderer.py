# -*- coding: utf-8 -*-
"""Zero-Dependency Portable Base64 Mobile HTML Renderers (Regulation M-C).

Renders self-contained single-file HTML reports for:
  1. **Interactive Speed Tiers** (`render_speed_tiers_html` / `build_speed_tiers_html`)
  2. **Interactive Damage & KO Matrix** (`render_damage_matrix_html` / `build_damage_matrix_html`)

Zero external CDN scripts, stylesheets, or remote image URLs — every sprite is
embedded inline as Base64 from `assets/slug_map.json`, and all damage lookups
are pre-computed by official `SmogonChampionsCalc` (`@smogon/calc` Gen 0).
"""
from __future__ import annotations

import html
import json
from typing import Any, Dict

from engine.prep_tools.damage_matrix_builder import (
    DamageMatrixPayload,
    build_damage_matrix_payload,
)
from engine.prep_tools.speed_tiers_builder import (
    SpeedTiersPayload,
    build_speed_tiers_payload,
)


def _safe_json_for_script(obj: Any) -> str:
    """Serialize an object to compact JSON safe for inline `<script>` embedding."""
    return (
        json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _speed_tiers_i18n(lang: str) -> Dict[str, str]:
    """Return bilingual ES/EN UI copy for the portable Speed Tiers HTML."""
    is_es = (lang or "en").lower().startswith("es")
    if is_es:
        return {
            "html_lang": "es",
            "title_prefix": "Velocidades Reg M-C",
            "badge": "Reg M-C • Base64 Offline",
            "subtitle_pre": "Top Meta (",
            "subtitle_mid": " equipos DuckDB) vs. tus 6 sets bloqueados (31 IVs exactos). Toca una tarjeta para enfocar • Toca cualquier fila para ver los 6 deltas.",
            "sec_team": "★ Tus 6 Sets Bloqueados (Toca para Enfocar · Base/Mega interactivo)",
            "show_all": "↺ Mostrar las 6 Líneas",
            "my_side": "Tu Lado:",
            "my_tw": "💨 Mi TW (2×)",
            "opp_side": "Rival:",
            "opp_scarf": "🧣 Pañuelo",
            "opp_tw": "💨 TW Rival",
            "opp_dbl": "⚡ 2× Hab.",
            "tr": "🌀 Espacio Raro",
            "nat_common": "Naturalezas Comunes (≥4%)",
            "nat_plus32": "+Vel Máx (32 SP)",
            "nat_neu32": "Neutra Máx (32 SP)",
            "nat_neu0": "Neutra Mín (0 SP)",
            "nat_minus0": "-Vel Mín (0 SP)",
            "sort_speed": "Orden: Velocidad",
            "sort_usage": "Orden: Uso %",
            "search_ph": "🔍 Buscar Pokémon...",
            "leg_mine": "Tu Set",
            "leg_scarf": "Pañuelo 1.5×",
            "leg_dbl": "Hab. 2×",
            "col_mon": "Pokémon • Uso y Naturalezas",
            "col_range": "Rango de Vel.",
            "footer": "100% Portátil Base64 Offline • Cero IA • Fórmulas Oficiales Lv.50 31-IV Reg M-C • Coach Porygon VGC",
            "first": "Primero",
            "mixed": "Mixto",
            "after": "Después",
            "my_set_pill": "TU SET",
            "modal_speeds": "Velocidades Champions Lv. 50 (31 IVs)",
            "modal_natures": "Naturalezas DuckDB",
            "modal_vs": "vs. Tu Equipo Bloqueado",
        }
    return {
        "html_lang": "en",
        "title_prefix": "Reg M-C Speed Tiers",
        "badge": "Reg M-C • Offline Base64",
        "subtitle_pre": "Top Meta (",
        "subtitle_mid": " DuckDB regional teams) vs. your 6 locked spreads (31 IVs exact). Tap any card to spotlight • Tap any meta row for 6-way speed deltas.",
        "sec_team": "★ Your 6 Locked Sets (Tap to Spotlight · Interactive Base/Mega)",
        "show_all": "↺ Show All 6 Lines",
        "my_side": "My Side:",
        "my_tw": "💨 My TW (2×)",
        "opp_side": "Opp:",
        "opp_scarf": "🧣 Scarf",
        "opp_tw": "💨 Opp TW",
        "opp_dbl": "⚡ 2× Abil",
        "tr": "🌀 Trick Room",
        "nat_common": "Common Natures (≥4%)",
        "nat_plus32": "+Spe Max (32 SP)",
        "nat_neu32": "Neutral Max (32 SP)",
        "nat_neu0": "Neutral Min (0 SP)",
        "nat_minus0": "-Spe Min (0 SP)",
        "sort_speed": "Sort: Speed",
        "sort_usage": "Sort: Usage %",
        "search_ph": "🔍 Search Pokémon...",
        "leg_mine": "Your Set",
        "leg_scarf": "Scarf 1.5×",
        "leg_dbl": "2× Ability",
        "col_mon": "Pokémon • Usage & Natures",
        "col_range": "Speed Range",
        "footer": "100% Portable Single-File Base64 • Zero-AI • Official Champions Lv.50 31-IV Math • Coach Porygon VGC",
        "first": "First",
        "mixed": "Mixed",
        "after": "After",
        "my_set_pill": "MY SET",
        "modal_speeds": "Champions Lv. 50 Speeds (31 IVs)",
        "modal_natures": "DuckDB Natures",
        "modal_vs": "vs. Your Locked Team",
    }


def _damage_matrix_i18n(lang: str) -> Dict[str, str]:
    """Return bilingual ES/EN UI copy for the portable Damage & KO Matrix HTML."""
    is_es = (lang or "en").lower().startswith("es")
    if is_es:
        return {
            "html_lang": "es",
            "title_prefix": "Matriz de Daño y KO Reg M-C",
            "badge": "Reg M-C • Smogon Exacto Base64",
            "subtitle_pre": "Toca cualquier movimiento de tu equipo para evaluar 16 rolls exactos de Smogon Champions contra el Top Meta (",
            "subtitle_post": " equipos DuckDB). Los modificadores se mantienen al cambiar de movimiento • Toca cualquier rival para ver los 7 spreads legales 66-SP.",
            "sec_atk": "★ 1. Selecciona tu Movimiento (Toca Base/Mega en portadores de Megapiedra)",
            "sec_lock": "Modificadores bloqueados entre movimientos · 5 Climas × 5 Campos",
            "atk_stage": "Boost:",
            "hh": "🤝 Refuerzo (1.5×)",
            "crit": "🎯 Crítico",
            "burn": "🔥 Quemado",
            "single_tgt": "🎯 Objetivo Único (1.0×)",
            "partner_lbl": "Doble Foco (Golpe 1 → Golpe 2):",
            "partner_none": "Ninguno (Ataque Individual — 16 Rolls)",
            "weather": "Clima:",
            "w_none": "⚪ Despejado",
            "w_sun": "☀️ Sol",
            "w_rain": "🌧️ Lluvia",
            "w_sand": "🏜️ Arena",
            "w_snow": "❄️ Nieve",
            "terrain": "Campo:",
            "t_none": "⚪ Ninguno",
            "t_elec": "⚡ Eléctrico",
            "t_grass": "🌿 Hierba",
            "t_psy": "🔮 Psíquico",
            "t_misty": "🌫️ Niebla",
            "defender": "Defensor:",
            "bulk_meta": "Bulk: Smart Meta (+ Rango Mín/Máx)",
            "bulk_min0": "Bulk: Mínimo (0 HP / 0 Def-SpD)",
            "bulk_hp32": "Bulk: 32 HP / 0 Def-SpD",
            "bulk_bal": "Bulk: Balanceado (32/18/16)",
            "bulk_maxdef": "Bulk: Máx +Def (32/32+/2)",
            "bulk_maxspd": "Bulk: Máx +SpD (32/2/32+)",
            "sim_items": "🍒 Sim. Objetos (Banda/Zidra/Bayas/Semillas)",
            "screens": "🛡️ Pantallas",
            "sort_ko": "Orden: Mayor % KO ↓",
            "sort_usage": "Orden: Uso Meta % ↓",
            "search_ph": "🔍 Filtrar rival...",
            "col_def": "Defensor Meta • Bulk y Objeto",
            "col_verdict": "Veredicto KO y Rolls",
            "footer": "100% Portátil Base64 Offline • Cero IA • Precomputado con Smogon Champions Calc (66-SP / 31 IVs / Sin Tera) • Coach Porygon VGC",
            "f_all": "Todos",
            "f_ohko": "✓ 100% OHKO",
            "f_roll": "⚡ Roll OHKO",
            "f_2hko": "2HKO",
            "f_surv": "3HKO+ / Inm",
            "survives": "Sobrevive",
            "modal_spread": "Spread Legal (≤66 SP)",
            "modal_net": "Daño Neto %",
            "modal_item": "Objeto",
            "modal_ko": "Prob. OHKO",
        }
    return {
        "html_lang": "en",
        "title_prefix": "Reg M-C Damage & KO Matrix",
        "badge": "Reg M-C • Exact Smogon Base64",
        "subtitle_pre": "Tap any move on your 6 Pokémon to evaluate exact Smogon Champions 16-roll tables against the Top Meta (",
        "subtitle_post": " DuckDB teams). Modifiers stay locked across move clicks • Tap any defender for all 7 legal 66-SP bulk spreads.",
        "sec_atk": "★ 1. Select Your Move (Tap Base/Mega pill on Mega Stone holders)",
        "sec_lock": "Modifiers Stay Locked · All 5 Weathers × All 5 Terrains",
        "atk_stage": "Stage:",
        "hh": "🤝 Helping Hand (1.5×)",
        "crit": "🎯 Crit",
        "burn": "🔥 Burned",
        "single_tgt": "🎯 Single Target (1.0×)",
        "partner_lbl": "Partner Pin (Hit 1 → Hit 2):",
        "partner_none": "None (Single Move — 16 Rolls)",
        "weather": "Weather:",
        "w_none": "⚪ Clear",
        "w_sun": "☀️ Sun",
        "w_rain": "🌧️ Rain",
        "w_sand": "🏜️ Sand",
        "w_snow": "❄️ Snow",
        "terrain": "Terrain:",
        "t_none": "⚪ None",
        "t_elec": "⚡ Electric",
        "t_grass": "🌿 Grassy",
        "t_psy": "🔮 Psychic",
        "t_misty": "🌫️ Misty",
        "defender": "Defender:",
        "bulk_meta": "Bulk: Smart Meta (+ Min/Max Whisker)",
        "bulk_min0": "Bulk: All Min (0 HP / 0 Def-SpD)",
        "bulk_hp32": "Bulk: All 32 HP / 0 Def-SpD",
        "bulk_bal": "Bulk: All Balanced (32/18/16)",
        "bulk_maxdef": "Bulk: All Max +Def (32/32+/2)",
        "bulk_maxspd": "Bulk: All Max +SpD (32/2/32+)",
        "sim_items": "🍒 Sim Items (Sash/Sitrus/Berries/Seeds)",
        "screens": "🛡️ Screens",
        "sort_ko": "Sort: Highest KO % ↓",
        "sort_usage": "Sort: Meta Usage % ↓",
        "search_ph": "🔍 Filter defender...",
        "col_def": "Top Meta Defender • Bulk & Item",
        "col_verdict": "KO Verdict & Rolls",
        "footer": "100% Portable Single-File Base64 • Zero-AI • Pre-Computed via Smogon Champions Calc (66-SP / 31 IVs / No Tera) • Coach Porygon VGC",
        "f_all": "All",
        "f_ohko": "✓ 100% OHKO",
        "f_roll": "⚡ Roll OHKO",
        "f_2hko": "2HKO",
        "f_surv": "3HKO+ / Imm",
        "survives": "Survives",
        "modal_spread": "Legal Spread (≤66 SP)",
        "modal_net": "Net Damage %",
        "modal_item": "Item",
        "modal_ko": "OHKO Odds",
    }


def render_speed_tiers_html(
    payload: SpeedTiersPayload,
    lang: str = "en",
) -> str:
    """Render a zero-dependency single-file Base64 Speed Tiers HTML report."""
    tr = _speed_tiers_i18n(lang)
    team_esc = html.escape(payload.team_name)
    data_json = _safe_json_for_script(payload.data)
    sprites_json = _safe_json_for_script(payload.sprites)
    i18n_json = _safe_json_for_script(tr)

    top_n_opts = []
    for n_opt in (50, 35, 20):
        if n_opt <= len(payload.data.get("topMeta") or []) or n_opt == payload.top_n:
            sel = " selected" if n_opt == payload.top_n else ""
            top_n_opts.append(f'<option value="{n_opt}"{sel}>Top {n_opt}</option>')
    if not top_n_opts:
        top_n_opts.append(f'<option value="{payload.top_n}" selected>Top {payload.top_n}</option>')
    top_n_select_html = "\n        ".join(top_n_opts)

    return f"""<!DOCTYPE html>
<html lang="{tr['html_lang']}">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0" />
<title>{tr['title_prefix']} — {team_esc}</title>
<style>
  :root {{
    --bg: #0b1020;
    --panel: #121a2e;
    --panel-2: #18233d;
    --border: #253457;
    --text: #e6eefc;
    --muted: #8ea2c8;
    --accent: #38bdf8;
    --gold: #facc15;
    --green: #22c55e;
    --amber: #f59e0b;
    --red: #f43f5e;
    --purple: #c084fc;
  }}
  * {{ box-sizing: border-box; -webkit-tap-highlight-color: transparent; }}
  body {{
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, Helvetica, Arial, sans-serif;
    background: radial-gradient(circle at top right, #162241 0%, var(--bg) 55%);
    color: var(--text);
    min-height: 100vh;
    padding: 14px 12px 60px;
  }}
  .container {{ max-width: 1480px; margin: 0 auto; }}
  header {{
    display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-end;
    gap: 10px; margin-bottom: 14px; border-bottom: 1px solid var(--border); padding-bottom: 12px;
  }}
  .title-block h1 {{
    margin: 0; font-size: clamp(1.12rem, 3.8vw, 1.5rem); letter-spacing: -0.02em;
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  }}
  .badge-format {{
    background: linear-gradient(135deg, #f97316, #eab308); color: #0b1020;
    font-size: 0.68rem; font-weight: 800; padding: 3px 8px; border-radius: 999px;
    text-transform: uppercase; letter-spacing: 0.05em;
  }}
  .subtitle {{ margin: 4px 0 0; color: var(--muted); font-size: 0.8rem; }}

  .section-label {{
    font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted);
    margin: 0 0 8px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px;
  }}
  .team-strip {{
    display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 8px; margin-bottom: 14px;
  }}
  @media (max-width: 1120px) {{ .team-strip {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }} }}
  @media (max-width: 600px) {{ .team-strip {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; }} }}
  .team-card {{
    background: linear-gradient(180deg, rgba(24,35,61,0.95), rgba(15,22,40,0.95));
    border: 1.5px solid var(--border); border-radius: 11px; padding: 8px 10px; cursor: pointer;
    position: relative; overflow: hidden; transition: border-color 0.14s ease, box-shadow 0.14s ease;
  }}
  .team-card::before {{
    content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: var(--mon-color, var(--accent));
  }}
  .team-card.active {{
    border-color: var(--mon-color, var(--gold));
    box-shadow: 0 0 0 2px rgba(250,204,21,0.22), 0 6px 18px rgba(0,0,0,0.45);
    background: linear-gradient(180deg, rgba(35,49,84,0.98), rgba(18,26,46,0.98));
  }}
  .tc-top {{ display: flex; align-items: center; justify-content: space-between; gap: 6px; }}
  .tc-top-l {{ display: flex; align-items: center; gap: 7px; min-width: 0; }}
  .tc-top img {{ width: 38px; height: 38px; object-fit: contain; flex-shrink: 0; }}
  .tc-name {{ font-weight: 700; font-size: 0.82rem; line-height: 1.15; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .tc-sub {{ font-size: 0.66rem; color: var(--muted); margin-top: 1px; }}
  .form-btn {{
    background: rgba(255,255,255,0.08); border: 1px solid var(--mon-color, var(--accent)); color: #fff;
    font-size: 0.6rem; font-weight: 800; padding: 2px 5px; border-radius: 999px; cursor: pointer; flex-shrink: 0;
  }}
  .tc-speed-row {{
    display: flex; align-items: baseline; justify-content: space-between;
    margin-top: 6px; padding-top: 5px; border-top: 1px solid rgba(255,255,255,0.07);
  }}
  .tc-speed {{ font-size: 1.24rem; font-weight: 800; color: var(--mon-color, var(--gold)); font-variant-numeric: tabular-nums; }}
  .tc-speed-tag {{ font-size: 0.65rem; color: var(--muted); text-align: right; }}

  .controls-bar {{
    background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
    padding: 10px 12px; margin-bottom: 12px; display: flex; flex-wrap: wrap; gap: 9px 14px; align-items: center;
  }}
  .ctrl-group {{ display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }}
  .ctrl-label {{ font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); font-weight: 700; }}
  .toggle-btn {{
    background: var(--panel-2); border: 1px solid var(--border); color: var(--text);
    padding: 6px 9px; border-radius: 8px; font-size: 0.75rem; font-weight: 600; cursor: pointer;
    display: inline-flex; align-items: center; gap: 4px;
  }}
  .toggle-btn.on {{ background: rgba(56,189,248,0.2); border-color: var(--accent); color: #bae6fd; }}
  .toggle-btn.on-sun {{ background: rgba(249,115,22,0.24); border-color: #fb923c; color: #fed7aa; }}
  .toggle-btn.on-gold {{ background: rgba(250,204,21,0.22); border-color: var(--gold); color: #fef08a; }}
  .toggle-btn.on-purple {{ background: rgba(192,132,252,0.24); border-color: var(--purple); color: #f3e8ff; }}
  .toggle-btn.on-tr {{ background: rgba(192,132,252,0.24); border-color: var(--purple); color: #f3e8ff; }}
  .toggle-btn.on-opp {{ background: rgba(244,63,94,0.22); border-color: var(--red); color: #fecdd3; }}
  select, input[type="text"] {{
    background: var(--panel-2); border: 1px solid var(--border); color: var(--text);
    padding: 6px 8px; border-radius: 8px; font-size: 0.75rem; outline: none;
  }}
  input[type="text"] {{ width: 150px; }}

  .spotlight-banner {{
    display: none; background: linear-gradient(90deg, rgba(250,204,21,0.14), rgba(56,189,248,0.08));
    border: 1px solid rgba(250,204,21,0.45); border-radius: 10px; padding: 9px 12px; margin-bottom: 10px;
    align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; font-size: 0.82rem;
  }}
  .spotlight-banner.visible {{ display: flex; }}
  .sb-stats {{ display: flex; gap: 7px; flex-wrap: wrap; }}
  .sb-chip {{ padding: 2px 8px; border-radius: 999px; font-weight: 700; font-size: 0.74rem; }}
  .chip-win {{ background: rgba(34,197,94,0.18); color: #86efac; border: 1px solid rgba(34,197,94,0.4); }}
  .chip-tie {{ background: rgba(245,158,11,0.18); color: #fde68a; border: 1px solid rgba(245,158,11,0.4); }}
  .chip-loss {{ background: rgba(244,63,94,0.18); color: #fda4af; border: 1px solid rgba(244,63,94,0.4); }}

  .legend {{
    display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center;
    margin-bottom: 9px; font-size: 0.72rem; color: var(--muted); padding: 0 2px;
  }}
  .leg-item {{ display: inline-flex; align-items: center; gap: 5px; }}
  .dot {{ width: 9px; height: 9px; border-radius: 50%; display: inline-block; }}
  .dot-minus {{ background: #c084fc; transform: rotate(45deg); border-radius: 2px; width: 8px; height: 8px; }}
  .dot-neu0 {{ background: #94a3b8; }}
  .dot-neu32 {{ background: #38bdf8; }}
  .dot-plus32 {{ background: #f59e0b; }}
  .dot-scarf {{ background: transparent; border: 2px solid #f43f5e; width: 10px; height: 10px; }}
  .dot-dbl {{ background: transparent; border: 2px solid #22c55e; width: 10px; height: 10px; }}
  .dot-mine {{ background: #facc15; box-shadow: 0 0 6px #facc15; width: 11px; height: 11px; }}

  .chart-card {{ background: var(--panel); border: 1px solid var(--border); border-radius: 13px; overflow: hidden; }}
  .chart-scroll {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
  .chart-inner {{ min-width: 680px; }}
  .chart-header {{
    display: grid; grid-template-columns: 245px 1fr 125px;
    background: rgba(11,16,32,0.94); border-bottom: 1px solid var(--border);
    padding: 9px 12px 7px; position: sticky; top: 0; z-index: 20;
  }}
  .ch-label {{
    font-size: 0.69rem; text-transform: uppercase; letter-spacing: 0.06em;
    color: var(--muted); font-weight: 700; display: flex; align-items: flex-end;
  }}
  .axis-wrap {{ position: relative; height: 34px; }}
  .axis-tick {{ position: absolute; bottom: 0; transform: translateX(-50%); font-size: 0.69rem; color: var(--muted); font-variant-numeric: tabular-nums; }}
  .axis-my-tag {{
    position: absolute; top: 0; transform: translateX(-50%);
    font-size: 0.62rem; font-weight: 800; padding: 1px 4px; border-radius: 4px;
    color: #0b1020; white-space: nowrap; box-shadow: 0 1px 4px rgba(0,0,0,0.45);
  }}
  .chart-row {{
    display: grid; grid-template-columns: 245px 1fr 125px; align-items: center;
    padding: 6px 12px; border-bottom: 1px solid rgba(37,52,87,0.45); cursor: pointer;
  }}
  .chart-row:hover {{ background: rgba(56,189,248,0.08); }}
  .chart-row.is-mine {{
    background: linear-gradient(90deg, rgba(250,204,21,0.14), rgba(56,189,248,0.06) 55%, rgba(250,204,21,0.04));
    border-top: 1px solid rgba(250,204,21,0.4); border-bottom: 1px solid rgba(250,204,21,0.4);
  }}
  .chart-row.is-mine.spotlighted {{ background: linear-gradient(90deg, rgba(250,204,21,0.26), rgba(56,189,248,0.12)); }}

  .mon-cell {{ display: flex; align-items: center; gap: 7px; min-width: 0; padding-right: 6px; }}
  .rank-num {{ width: 24px; font-size: 0.69rem; color: var(--muted); font-weight: 700; text-align: right; flex-shrink: 0; }}
  .mon-cell img {{ width: 32px; height: 32px; object-fit: contain; flex-shrink: 0; }}
  .mon-info {{ min-width: 0; flex: 1; }}
  .mon-name {{ font-size: 0.81rem; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: flex; align-items: center; gap: 4px; }}
  .mine-pill {{ background: var(--gold); color: #0b1020; font-size: 0.58rem; font-weight: 900; padding: 1px 4px; border-radius: 3px; flex-shrink: 0; }}
  .mon-meta {{ font-size: 0.66rem; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}

  .plot-cell {{ position: relative; height: 32px; }}
  .grid-line {{ position: absolute; top: -6px; bottom: -6px; width: 1px; background: rgba(148,163,184,0.1); pointer-events: none; }}
  .ref-line {{ position: absolute; top: -6px; bottom: -6px; width: 1.5px; border-left: 1.5px dashed var(--ref-color); opacity: 0.45; pointer-events: none; z-index: 2; }}
  .ref-line.bright {{ opacity: 0.95; border-left-width: 2.5px; box-shadow: 0 0 8px var(--ref-color); z-index: 4; }}
  .ref-line.dim {{ opacity: 0.12; }}

  .range-bar {{ position: absolute; top: 50%; transform: translateY(-50%); height: 7px; border-radius: 999px; background: linear-gradient(90deg, rgba(148,163,184,0.45), rgba(56,189,248,0.65), rgba(245,158,11,0.75)); z-index: 3; }}
  .range-bar-ext {{ position: absolute; top: 50%; transform: translateY(-50%); height: 3px; border-radius: 999px; background: rgba(244,63,94,0.45); z-index: 2; }}
  .range-bar-dbl {{ position: absolute; top: 50%; transform: translateY(-50%); height: 3px; border-radius: 999px; background: rgba(34,197,94,0.45); z-index: 2; }}
  .node {{ position: absolute; top: 50%; transform: translate(-50%, -50%); z-index: 6; pointer-events: none; }}
  .node-minus {{ width: 8px; height: 8px; background: #c084fc; border: 1.5px solid #0b1020; transform: translate(-50%, -50%) rotate(45deg); border-radius: 2px; }}
  .node-neu0 {{ width: 8px; height: 8px; background: #94a3b8; border: 1.5px solid #0b1020; border-radius: 50%; }}
  .node-neu32 {{ width: 9px; height: 9px; background: #38bdf8; border: 1.5px solid #0b1020; border-radius: 50%; }}
  .node-plus32 {{ width: 10px; height: 10px; background: #f59e0b; border: 1.5px solid #0b1020; border-radius: 50%; }}
  .node-scarf {{ width: 11px; height: 11px; background: #0b1020; border: 2px solid #f43f5e; border-radius: 50%; }}
  .node-dbl {{ width: 11px; height: 11px; background: #0b1020; border: 2px solid #22c55e; border-radius: 50%; }}
  .node-mine {{ width: 14px; height: 14px; border-radius: 50%; background: var(--mon-color, #facc15); border: 2px solid #0b1020; box-shadow: 0 0 9px var(--mon-color, #facc15); z-index: 8; }}
  .node-val {{ position: absolute; top: 50%; transform: translateY(-50%); font-size: 0.67rem; font-weight: 700; color: var(--text); white-space: nowrap; z-index: 7; text-shadow: 0 1px 3px #0b1020; }}

  .verdict-cell {{ text-align: right; padding-left: 8px; font-size: 0.72rem; font-variant-numeric: tabular-nums; }}
  .verdict-badge {{ display: inline-block; padding: 2px 7px; border-radius: 6px; font-weight: 700; font-size: 0.68rem; white-space: nowrap; }}
  .vb-win {{ background: rgba(34,197,94,0.16); color: #86efac; border: 1px solid rgba(34,197,94,0.35); }}
  .vb-tie {{ background: rgba(245,158,11,0.16); color: #fde68a; border: 1px solid rgba(245,158,11,0.35); }}
  .vb-loss {{ background: rgba(244,63,94,0.16); color: #fda4af; border: 1px solid rgba(244,63,94,0.35); }}
  .vb-mine {{ background: rgba(250,204,21,0.2); color: #fef08a; border: 1px solid rgba(250,204,21,0.5); }}
  .vb-range {{ color: var(--muted); font-weight: 600; }}

  .modal-backdrop {{
    display: none; position: fixed; inset: 0; background: rgba(3, 6, 14, 0.72);
    z-index: 90; align-items: flex-end; justify-content: center; padding: 14px;
  }}
  .modal-backdrop.open {{ display: flex; }}
  @media (min-width: 760px) {{ .modal-backdrop {{ align-items: center; }} }}
  .modal-card {{
    background: #0e1629; border: 1.5px solid var(--accent); border-radius: 16px;
    padding: 15px 16px; width: 100%; max-width: 420px; box-shadow: 0 20px 50px rgba(0,0,0,0.7);
    font-size: 0.82rem; line-height: 1.4;
  }}
  .tt-head {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; border-bottom: 1px solid var(--border); padding-bottom: 8px; margin-bottom: 9px; }}
  .tt-head-l {{ display: flex; align-items: center; gap: 10px; }}
  .tt-head img {{ width: 44px; height: 44px; object-fit: contain; }}
  .tt-title {{ font-weight: 800; font-size: 0.98rem; }}
  .tt-sub {{ color: var(--muted); font-size: 0.74rem; }}
  .close-btn {{
    background: rgba(255,255,255,0.08); border: 1px solid var(--border); color: #fff;
    border-radius: 8px; padding: 4px 9px; font-weight: 800; cursor: pointer;
  }}
  .tt-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px 8px; margin-bottom: 9px; }}
  .tt-kv {{ display: flex; justify-content: space-between; background: rgba(24,35,61,0.8); padding: 4px 8px; border-radius: 6px; font-variant-numeric: tabular-nums; }}
  .tt-kv span:first-child {{ color: var(--muted); }}
  .tt-section {{ font-size: 0.69rem; text-transform: uppercase; letter-spacing: 0.07em; color: var(--muted); margin: 8px 0 4px; font-weight: 700; }}
  .tt-vs-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 5px 8px; }}
  .tt-vs-row {{ display: flex; justify-content: space-between; font-size: 0.75rem; padding: 3px 7px; border-radius: 5px; background: rgba(255,255,255,0.04); }}
  .c-win {{ color: #86efac; font-weight: 700; }}
  .c-tie {{ color: #fde68a; font-weight: 700; }}
  .c-loss {{ color: #fda4af; font-weight: 700; }}

  footer {{ margin-top: 14px; font-size: 0.72rem; color: var(--muted); text-align: center; }}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="title-block">
      <h1>
        ⚡ {tr['title_prefix']} — {team_esc}
        <span class="badge-format">{tr['badge']}</span>
      </h1>
      <p class="subtitle">
        {tr['subtitle_pre']}<strong id="totalTeamsLbl"></strong>{tr['subtitle_mid']}
      </p>
    </div>
  </header>

  <div class="section-label">
    <span>{tr['sec_team']}</span>
    <span id="clearSpotlightHint" style="cursor:pointer; color:#38bdf8; display:none;" onclick="setSpotlight(null)">{tr['show_all']}</span>
  </div>
  <div class="team-strip" id="teamStrip"></div>

  <div class="controls-bar">
    <div class="ctrl-group" id="mySideControls">
      <span class="ctrl-label">{tr['my_side']}</span>
      <button class="toggle-btn" id="btnMyTW" onclick="toggleState('myTW')">{tr['my_tw']}</button>
      <span id="dynamicTeamMods" style="display:inline-flex; gap:6px; flex-wrap:wrap;"></span>
      <select id="selMyStage" onchange="state.myStage = Number(this.value); render();">
        <option value="-2">-2 Spe</option>
        <option value="-1">-1 Spe</option>
        <option value="0" selected>0 Spe</option>
        <option value="1">+1 Spe</option>
        <option value="2">+2 Spe</option>
      </select>
    </div>
    <div class="ctrl-group">
      <span class="ctrl-label">{tr['opp_side']}</span>
      <button class="toggle-btn on-opp" id="btnOppScarf" onclick="toggleState('oppScarf')">{tr['opp_scarf']}</button>
      <button class="toggle-btn" id="btnOppTW" onclick="toggleState('oppTW')">{tr['opp_tw']}</button>
      <button class="toggle-btn" id="btnOppDbl" onclick="toggleState('oppDbl')">{tr['opp_dbl']}</button>
      <button class="toggle-btn" id="btnTR" onclick="toggleState('trickRoom')">{tr['tr']}</button>
    </div>
    <div class="ctrl-group">
      <select id="selNatureMode" onchange="state.natureMode = this.value; render();">
        <option value="common">{tr['nat_common']}</option>
        <option value="plus32">{tr['nat_plus32']}</option>
        <option value="neu32">{tr['nat_neu32']}</option>
        <option value="neu0">{tr['nat_neu0']}</option>
        <option value="minus0">{tr['nat_minus0']}</option>
      </select>
      <select id="selTopN" onchange="state.topN = Number(this.value); render();">
        {top_n_select_html}
      </select>
      <select id="selSort" onchange="state.sortBy = this.value; render();">
        <option value="speed">{tr['sort_speed']}</option>
        <option value="usage">{tr['sort_usage']}</option>
      </select>
      <input type="text" id="txtSearch" placeholder="{tr['search_ph']}" oninput="state.search = this.value.trim().toLowerCase(); render();" />
    </div>
  </div>

  <div class="spotlight-banner" id="spotlightBanner">
    <div id="spotlightTitle"></div>
    <div class="sb-stats" id="spotlightStats"></div>
  </div>

  <div class="legend">
    <span class="leg-item"><span class="dot dot-mine"></span> <strong>{tr['leg_mine']}</strong></span>
    <span class="leg-item"><span class="dot dot-minus"></span> -Spe 0</span>
    <span class="leg-item"><span class="dot dot-neu0"></span> Neu 0</span>
    <span class="leg-item"><span class="dot dot-neu32"></span> Neu 32</span>
    <span class="leg-item"><span class="dot dot-plus32"></span> +Spe 32</span>
    <span class="leg-item"><span class="dot dot-scarf"></span> {tr['leg_scarf']}</span>
    <span class="leg-item"><span class="dot dot-dbl"></span> {tr['leg_dbl']}</span>
  </div>

  <div class="chart-card">
    <div class="chart-scroll">
      <div class="chart-inner">
        <div class="chart-header">
          <div class="ch-label">{tr['col_mon']}</div>
          <div class="axis-wrap" id="axisHeader"></div>
          <div class="ch-label" style="justify-content:flex-end;" id="verdictHeader">{tr['col_range']}</div>
        </div>
        <div class="chart-body" id="chartBody"></div>
      </div>
    </div>
  </div>

  <footer>{tr['footer']}</footer>
</div>

<div class="modal-backdrop" id="modalBackdrop" onclick="if(event.target===this) closeModal()">
  <div class="modal-card" id="modalCard"></div>
</div>

<script>
const DATA = {data_json};
const SPRITES = {sprites_json};
const I18N = {i18n_json};

const state = {{
  myTW: false,
  myStage: 0,
  teamMods: {{}},
  megaForm: {{}},
  oppScarf: true,
  oppTW: false,
  oppDbl: false,
  trickRoom: false,
  natureMode: 'common',
  topN: DATA.defaultTopN || 50,
  sortBy: 'speed',
  search: '',
  spotlightId: null,
}};

for (const mon of DATA.trainer1Team) {{
  state.megaForm[mon.id] = Boolean(mon.hasMega && mon.defaultMega);
}}
for (const modBtn of DATA.teamModButtons) {{
  state.teamMods[modBtn.key] = false;
}}

function escapeHtml(s) {{
  return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}

function applySpeStage(val, stage) {{
  if (stage > 0) return Math.floor(val * (2 + stage) / 2);
  if (stage < 0) return Math.floor(val * 2 / (2 - stage));
  return val;
}}

function getMyActiveForm(mon) {{
  const useMega = Boolean(mon.hasMega && mon.mega && state.megaForm[mon.id]);
  return useMega ? mon.mega : mon.base;
}}

function getMyEffectiveSpeed(mon) {{
  const form = getMyActiveForm(mon);
  let s = applySpeStage(form.rawSpeed, state.myStage);
  if (mon.hasScarf && !(mon.hasMega && state.megaForm[mon.id])) {{
    s = Math.floor(s * 1.5);
  }}
  if (form.speedModKey && state.teamMods[form.speedModKey]) {{
    s = s * 2;
  }}
  if (state.myTW) {{
    s = s * 2;
  }}
  return s;
}}

function getOppSpeedInfo(mon) {{
  const sp = mon.speeds;
  const twMult = state.oppTW ? 2 : 1;
  const minus0 = sp.minus0 * twMult, neu0 = sp.neu0 * twMult, neu32 = sp.neu32 * twMult, plus32 = sp.plus32 * twMult;

  const points = [];
  if (state.natureMode === 'common') {{
    if (mon.hasMinus) points.push({{ type: 'minus', val: minus0 }});
    if (mon.hasNeu) {{ points.push({{ type: 'neu0', val: neu0 }}); points.push({{ type: 'neu32', val: neu32 }}); }}
    if (mon.hasPlus) points.push({{ type: 'plus32', val: plus32 }});
    if (!points.length) {{ points.push({{ type: 'neu0', val: neu0 }}); points.push({{ type: 'neu32', val: neu32 }}); }}
  }} else if (state.natureMode === 'plus32') points.push({{ type: 'plus32', val: plus32 }});
  else if (state.natureMode === 'neu32') points.push({{ type: 'neu32', val: neu32 }});
  else if (state.natureMode === 'neu0') points.push({{ type: 'neu0', val: neu0 }});
  else points.push({{ type: 'minus', val: minus0 }});

  const coreMin = Math.min(...points.map(p => p.val));
  const coreMax = Math.max(...points.map(p => p.val));

  let scarfVal = null;
  if (state.oppScarf && mon.hasScarf) {{
    scarfVal = Math.floor((mon.plusPct >= 10 ? sp.plus32 : sp.neu32) * 1.5) * twMult;
  }}
  let dblVal = null;
  if (state.oppDbl && mon.doublerAbil) {{
    dblVal = (mon.plusPct >= 15 ? sp.plus32 : sp.neu32) * 2 * twMult;
  }}
  return {{ points, coreMin, coreMax, scarfVal, dblVal, effMin: coreMin, effMax: Math.max(coreMax, scarfVal || 0, dblVal || 0) }};
}}

function toggleState(key) {{ state[key] = !state[key]; render(); }}
function toggleTeamMod(key) {{ state.teamMods[key] = !state.teamMods[key]; render(); }}
function toggleMega(id, e) {{
  e.stopPropagation();
  state.megaForm[id] = !state.megaForm[id];
  render();
}}
function setSpotlight(id) {{ state.spotlightId = (state.spotlightId === id) ? null : id; render(); }}
function closeModal() {{ document.getElementById('modalBackdrop').classList.remove('open'); }}

function compareVsSpotlight(mySpe, oppInfo) {{
  if (!state.trickRoom) {{
    if (mySpe > oppInfo.effMax) return 'win';
    if (mySpe < oppInfo.effMin) return 'loss';
    return 'tie';
  }} else {{
    if (mySpe < oppInfo.effMin) return 'win';
    if (mySpe > oppInfo.effMax) return 'loss';
    return 'tie';
  }}
}}

function openOppModal(idx) {{
  const m = DATA.topMeta[idx];
  const info = getOppSpeedInfo(m);
  const sp = m.speeds;
  const tw = state.oppTW ? 2 : 1;
  const natChips = m.topNatures.map(n => `${{escapeHtml(n.name)}} <strong>${{n.pct}}%</strong>`).join(' • ');
  const vsRows = DATA.trainer1Team.map(my => {{
    const mySpe = getMyEffectiveSpeed(my);
    const res = compareVsSpotlight(mySpe, info);
    const cls = res === 'win' ? 'c-win' : (res === 'loss' ? 'c-loss' : 'c-tie');
    const txt = res === 'win' ? ('✓ ' + I18N.first) : (res === 'loss' ? ('✗ ' + I18N.after) : ('≈ ' + I18N.mixed));
    return `<div class="tt-vs-row"><span>${{escapeHtml(my.label.split(' ')[0])}} (${{mySpe}})</span><span class="${{cls}}">${{txt}}</span></div>`;
  }}).join('');
  document.getElementById('modalCard').innerHTML = `
    <div class="tt-head">
      <div class="tt-head-l">
        <img src="${{SPRITES[m.spriteKey] || ''}}" alt="${{escapeHtml(m.species)}}" />
        <div>
          <div class="tt-title">#${{m.rank}} ${{escapeHtml(m.species)}}</div>
          <div class="tt-sub">Base Spe: <strong>${{m.baseSpe}}</strong> • Usage: <strong>${{m.usagePct}}%</strong> • T32: <strong>${{m.top32Count}}</strong></div>
        </div>
      </div>
      <button class="close-btn" onclick="closeModal()">✕</button>
    </div>
    <div class="tt-section">${{I18N.modal_speeds}} ${{state.oppTW ? '(Opp TW 2×)' : ''}}</div>
    <div class="tt-grid">
      <div class="tt-kv"><span>-Spe 0 SP</span><strong>${{sp.minus0 * tw}}</strong></div>
      <div class="tt-kv"><span>Neutral 0 SP</span><strong>${{sp.neu0 * tw}}</strong></div>
      <div class="tt-kv"><span>Neutral 32 SP</span><strong>${{sp.neu32 * tw}}</strong></div>
      <div class="tt-kv"><span>+Spe 32 SP</span><strong>${{sp.plus32 * tw}}</strong></div>
      <div class="tt-kv"><span>Scarf (Neu/+)</span><strong>${{Math.floor(sp.neu32 * 1.5) * tw}} / ${{Math.floor(sp.plus32 * 1.5) * tw}}</strong></div>
      <div class="tt-kv"><span>2× Spe (Neu/+)</span><strong>${{sp.neu32 * 2 * tw}} / ${{sp.plus32 * 2 * tw}}</strong></div>
    </div>
    <div class="tt-section">${{I18N.modal_natures}} (+:${{m.plusPct}}% | Neu:${{m.neuPct}}% | -:${{m.minusPct}}%)</div>
    <div style="font-size:0.75rem; margin-bottom:6px;">${{natChips}}</div>
    ${{m.hasScarf ? `<div style="font-size:0.74rem; color:#fda4af;">🧣 Choice Scarf: <strong>${{m.scarfPct}}%</strong></div>` : ''}}
    ${{m.doublerAbil ? `<div style="font-size:0.74rem; color:#86efac;">⚡ Ability: <strong>${{escapeHtml(m.doublerAbil)}}</strong> (${{m.doublerPct}}%)</div>` : ''}}
    <div class="tt-section">${{I18N.modal_vs}} — ${{escapeHtml(DATA.teamName)}} ${{state.trickRoom ? '(TR)' : ''}}</div>
    <div class="tt-vs-grid">${{vsRows}}</div>
  `;
  document.getElementById('modalBackdrop').classList.add('open');
}}

function render() {{
  document.getElementById('totalTeamsLbl').textContent = DATA.totalTeams.toLocaleString();
  document.getElementById('btnMyTW').className = 'toggle-btn' + (state.myTW ? ' on' : '');
  document.getElementById('btnOppScarf').className = 'toggle-btn' + (state.oppScarf ? ' on-opp' : '');
  document.getElementById('btnOppTW').className = 'toggle-btn' + (state.oppTW ? ' on-opp' : '');
  document.getElementById('btnOppDbl').className = 'toggle-btn' + (state.oppDbl ? ' on-opp' : '');
  document.getElementById('btnTR').className = 'toggle-btn' + (state.trickRoom ? ' on-tr' : '');

  const isEs = I18N.html_lang === 'es';
  document.getElementById('dynamicTeamMods').innerHTML = DATA.teamModButtons.map(btn => {{
    const on = Boolean(state.teamMods[btn.key]);
    const lbl = isEs ? btn.labelEs : btn.labelEn;
    return `<button class="toggle-btn ${{on ? btn.style : ''}}" onclick="toggleTeamMod('${{btn.key}}')">${{btn.icon}} ${{escapeHtml(lbl)}}</button>`;
  }}).join('');

  const sortedTeam = [...DATA.trainer1Team].sort((a, b) => {{
    const sa = getMyEffectiveSpeed(a), sb = getMyEffectiveSpeed(b);
    return state.trickRoom ? sa - sb : sb - sa;
  }});

  document.getElementById('teamStrip').innerHTML = sortedTeam.map(mon => {{
    const form = getMyActiveForm(mon);
    const spe = getMyEffectiveSpeed(mon);
    const mods = [];
    if (mon.hasScarf && !(mon.hasMega && state.megaForm[mon.id])) mods.push('🧣1.5×');
    if (form.speedModKey && state.teamMods[form.speedModKey]) mods.push('⚡2×');
    if (state.myTW) mods.push('💨2×');
    if (state.myStage !== 0) mods.push((state.myStage > 0 ? '+' : '') + state.myStage);
    const megaBtn = mon.hasMega
      ? `<button class="form-btn" onclick="toggleMega('${{mon.id}}', event)">${{state.megaForm[mon.id] ? '🧬 Mega' : 'Base'}}</button>`
      : '';
    return `
      <div class="team-card ${{state.spotlightId === mon.id ? 'active' : ''}}" style="--mon-color:${{mon.color}}" onclick="setSpotlight('${{mon.id}}')">
        <div class="tc-top">
          <div class="tc-top-l">
            <img src="${{SPRITES[form.spriteKey] || ''}}" alt="${{escapeHtml(form.species)}}" />
            <div style="min-width:0;">
              <div class="tc-name">${{escapeHtml(mon.label)}}</div>
              <div class="tc-sub">${{escapeHtml(mon.nature)}} • ${{mon.speSp}} SP</div>
            </div>
          </div>
          ${{megaBtn}}
        </div>
        <div class="tc-speed-row">
          <div class="tc-speed">${{spe}}</div>
          <div class="tc-speed-tag">${{mods.length ? mods.join(' ') : ('Base ' + form.baseSpe)}}</div>
        </div>
      </div>
    `;
  }}).join('');
  document.getElementById('clearSpotlightHint').style.display = state.spotlightId ? 'inline' : 'none';

  const oppList = DATA.topMeta.slice(0, state.topN)
    .filter(m => !state.search || m.species.toLowerCase().includes(state.search))
    .map(m => ({{ kind: 'opp', mon: m, info: getOppSpeedInfo(m) }}));
  const myRows = DATA.trainer1Team.map(m => ({{ kind: 'mine', mon: m, form: getMyActiveForm(m), speed: getMyEffectiveSpeed(m) }}));

  let maxVal = 230;
  for (const r of oppList) maxVal = Math.max(maxVal, r.info.effMax + 25);
  for (const r of myRows) maxVal = Math.max(maxVal, r.speed + 25);
  const step = maxVal > 420 ? 60 : (maxVal > 280 ? 40 : 25);
  maxVal = Math.ceil(maxVal / step) * step;
  const pct = v => Math.max(0, Math.min(100, (v / maxVal) * 100));

  const ticks = [];
  for (let v = 0; v <= maxVal; v += step) ticks.push(v);

  let axisHtml = ticks.map(v => `<div class="axis-tick" style="left:${{pct(v)}}%">${{v}}</div>`).join('');
  const myRefSorted = [...myRows].sort((a, b) => a.speed - b.speed);
  let lastLeft = -999;
  axisHtml += myRefSorted.map(r => {{
    const p = pct(r.speed);
    const isSpot = state.spotlightId === r.mon.id;
    const isDim = state.spotlightId && !isSpot;
    const topPx = (p - lastLeft < 7.5) ? 12 : 0;
    lastLeft = p;
    return `<div class="axis-my-tag" style="left:${{p}}%; top:${{topPx}}px; background:${{r.mon.color}}; opacity:${{isDim ? 0.25 : 1}}; z-index:${{isSpot ? 12 : 6}};">${{escapeHtml(r.mon.label.split(' ')[0].slice(0,6))}} ${{r.speed}}</div>`;
  }}).join('');
  document.getElementById('axisHeader').innerHTML = axisHtml;

  const spotMon = DATA.trainer1Team.find(m => m.id === state.spotlightId) || null;
  const banner = document.getElementById('spotlightBanner');
  if (spotMon) {{
    const mySpe = getMyEffectiveSpeed(spotMon);
    let wins = 0, ties = 0, losses = 0;
    for (const r of oppList) {{
      const res = compareVsSpotlight(mySpe, r.info);
      if (res === 'win') wins++; else if (res === 'tie') ties++; else losses++;
    }}
    banner.classList.add('visible');
    document.getElementById('spotlightTitle').innerHTML = `🎯 <strong>${{escapeHtml(spotMon.label)}}</strong> (<strong>${{mySpe}}</strong>) vs Top ${{state.topN}}:`;
    document.getElementById('spotlightStats').innerHTML = `
      <span class="sb-chip chip-win">✓ ${{I18N.first}}: ${{wins}}</span>
      <span class="sb-chip chip-tie">≈ ${{I18N.mixed}}: ${{ties}}</span>
      <span class="sb-chip chip-loss">✗ ${{I18N.after}}: ${{losses}}</span>
    `;
    document.getElementById('verdictHeader').textContent = `vs. ${{spotMon.label.split(' ')[0]}}`;
  }} else {{
    banner.classList.remove('visible');
    document.getElementById('verdictHeader').textContent = I18N.col_range;
  }}

  const combined = state.sortBy === 'speed' ? [...oppList, ...myRows].sort((a, b) => {{
    const va = a.kind === 'mine' ? a.speed : (state.trickRoom ? a.info.effMin : a.info.effMax);
    const vb = b.kind === 'mine' ? b.speed : (state.trickRoom ? b.info.effMin : b.info.effMax);
    if (va !== vb) return state.trickRoom ? va - vb : vb - va;
    return a.kind === 'mine' ? -1 : 1;
  }}) : [...myRows.sort((a,b) => state.trickRoom ? a.speed - b.speed : b.speed - a.speed), ...oppList];

  const gridLinesHtml = ticks.map(v => `<div class="grid-line" style="left:${{pct(v)}}%"></div>`).join('');
  const refLinesHtml = myRows.map(r => {{
    const cls = state.spotlightId ? (state.spotlightId === r.mon.id ? 'ref-line bright' : 'ref-line dim') : 'ref-line';
    return `<div class="${{cls}}" style="left:${{pct(r.speed)}}%; --ref-color:${{r.mon.color}}"></div>`;
  }}).join('');

  document.getElementById('chartBody').innerHTML = combined.map(row => {{
    if (row.kind === 'mine') {{
      const m = row.mon, form = row.form, spe = row.speed;
      const valLeft = pct(spe) > 85 ? `right:${{100 - pct(spe) + 1.5}}%` : `left:${{pct(spe) + 1.5}}%`;
      return `
        <div class="chart-row is-mine ${{state.spotlightId === m.id ? 'spotlighted' : ''}}" onclick="setSpotlight('${{m.id}}')">
          <div class="mon-cell">
            <span class="rank-num" style="color:${{m.color}}">★</span>
            <img src="${{SPRITES[form.spriteKey] || ''}}" alt="${{escapeHtml(form.species)}}" />
            <div class="mon-info">
              <div class="mon-name"><span>${{escapeHtml(m.label)}}</span><span class="mine-pill">${{I18N.my_set_pill}}</span></div>
              <div class="mon-meta">${{escapeHtml(m.nature)}} • ${{m.speSp}} Spe SP • ${{escapeHtml(m.item)}}</div>
            </div>
          </div>
          <div class="plot-cell">
            ${{gridLinesHtml}}${{refLinesHtml}}
            <div class="node node-mine" style="left:${{pct(spe)}}%; --mon-color:${{m.color}}"></div>
            <div class="node-val" style="${{valLeft}}; color:${{m.color}};">${{spe}}</div>
          </div>
          <div class="verdict-cell"><span class="verdict-badge vb-mine">${{spe}}</span></div>
        </div>
      `;
    }} else {{
      const m = row.mon, info = row.info;
      const natSummary = m.topNatures.slice(0, 2).map(x => `${{x.name}} ${{Math.round(x.pct)}}%`).join(' · ');
      const barLeft = pct(info.coreMin), barWidth = Math.max(0.5, pct(info.coreMax) - barLeft);
      let extHtml = '';
      if (info.scarfVal) {{
        const sL = pct(info.coreMax);
        extHtml += `<div class="range-bar-ext" style="left:${{sL}}%; width:${{Math.max(0.5, pct(info.scarfVal)-sL)}}%"></div><div class="node node-scarf" style="left:${{pct(info.scarfVal)}}%"></div>`;
      }}
      if (info.dblVal) {{
        const dL = pct(info.coreMax);
        extHtml += `<div class="range-bar-dbl" style="left:${{dL}}%; width:${{Math.max(0.5, pct(info.dblVal)-dL)}}%"></div><div class="node node-dbl" style="left:${{pct(info.dblVal)}}%"></div>`;
      }}
      const nodesHtml = info.points.map(pt => `<div class="node node-${{pt.type}}" style="left:${{pct(pt.val)}}%"></div>`).join('');
      const maxPos = pct(info.effMax);
      const labelStyle = maxPos > 85 ? `right:${{100 - pct(info.effMin) + 1.5}}%` : `left:${{maxPos + 1.3}}%`;
      const rangeStr = info.effMin === info.effMax ? `${{info.effMax}}` : `${{info.effMin}}–${{info.effMax}}`;
      let rightHtml = `<span class="vb-range">${{rangeStr}}</span>`;
      if (spotMon) {{
        const mySpe = getMyEffectiveSpeed(spotMon);
        const res = compareVsSpotlight(mySpe, info);
        if (res === 'win') rightHtml = `<span class="verdict-badge vb-win">✓ +${{state.trickRoom ? (info.effMin - mySpe) : (mySpe - info.effMax)}}</span>`;
        else if (res === 'loss') rightHtml = `<span class="verdict-badge vb-loss">✗ -${{state.trickRoom ? (mySpe - info.effMax) : (info.effMin - mySpe)}}</span>`;
        else rightHtml = `<span class="verdict-badge vb-tie">≈ ${{I18N.mixed.toUpperCase()}}</span>`;
      }}
      return `
        <div class="chart-row" onclick="openOppModal(${{m.rank - 1}})">
          <div class="mon-cell">
            <span class="rank-num">#${{m.rank}}</span>
            <img src="${{SPRITES[m.spriteKey] || ''}}" alt="${{escapeHtml(m.species)}}" />
            <div class="mon-info">
              <div class="mon-name">${{escapeHtml(m.species)}}</div>
              <div class="mon-meta">${{m.usagePct}}% • ${{escapeHtml(natSummary)}}</div>
            </div>
          </div>
          <div class="plot-cell">
            ${{gridLinesHtml}}${{refLinesHtml}}
            <div class="range-bar" style="left:${{barLeft}}%; width:${{barWidth}}%"></div>
            ${{extHtml}}${{nodesHtml}}
            <div class="node-val" style="${{labelStyle}}">${{rangeStr}}</div>
          </div>
          <div class="verdict-cell">${{rightHtml}}</div>
        </div>
      `;
    }}
  }}).join('');
}}

render();
</script>
</body>
</html>
"""


def render_damage_matrix_html(
    payload: DamageMatrixPayload,
    lang: str = "en",
) -> str:
    """Render a zero-dependency single-file Base64 Damage & KO Matrix HTML report."""
    tr = _damage_matrix_i18n(lang)
    team_esc = html.escape(payload.team_name)
    data_json = _safe_json_for_script(payload.data)
    sprites_json = _safe_json_for_script(payload.sprites)
    i18n_json = _safe_json_for_script(tr)

    top_n_opts = []
    for n_opt in (50, 35, 20):
        if n_opt <= len(payload.data.get("defenders") or []) or n_opt == payload.top_n:
            sel = " selected" if n_opt == payload.top_n else ""
            top_n_opts.append(f'<option value="{n_opt}"{sel}>Top {n_opt}</option>')
    if not top_n_opts:
        top_n_opts.append(f'<option value="{payload.top_n}" selected>Top {payload.top_n}</option>')
    top_n_select_html = "\n        ".join(top_n_opts)

    return f"""<!DOCTYPE html>
<html lang="{tr['html_lang']}">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0" />
<title>{tr['title_prefix']} — {team_esc}</title>
<style>
  :root {{
    --bg: #080d1a;
    --panel: #11192e;
    --panel-2: #17223d;
    --border: #26365c;
    --text: #eef4ff;
    --muted: #8ea3c9;
    --accent: #38bdf8;
    --gold: #facc15;
    --green: #22c55e;
    --amber: #f59e0b;
    --cyan: #06b6d4;
    --red: #f43f5e;
    --purple: #c084fc;
    --pink: #f472b6;
  }}
  * {{ box-sizing: border-box; -webkit-tap-highlight-color: transparent; }}
  body {{
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, Helvetica, Arial, sans-serif;
    background: radial-gradient(circle at top right, #162344 0%, var(--bg) 58%);
    color: var(--text);
    min-height: 100vh;
    padding: 14px 12px 64px;
  }}
  .container {{ max-width: 1480px; margin: 0 auto; }}
  header {{
    display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-end;
    gap: 10px; margin-bottom: 14px; border-bottom: 1px solid var(--border); padding-bottom: 12px;
  }}
  .title-block h1 {{
    margin: 0; font-size: clamp(1.12rem, 3.8vw, 1.5rem); letter-spacing: -0.02em;
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  }}
  .badge-format {{
    background: linear-gradient(135deg, #22c55e, #38bdf8); color: #080d1a;
    font-size: 0.68rem; font-weight: 900; padding: 3px 9px; border-radius: 999px;
    text-transform: uppercase; letter-spacing: 0.05em;
  }}
  .subtitle {{ margin: 4px 0 0; color: var(--muted); font-size: 0.8rem; }}

  .section-label {{
    font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted);
    margin: 0 0 8px; font-weight: 700; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px;
  }}
  .attacker-grid {{
    display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 8px; margin-bottom: 12px;
  }}
  @media (max-width: 1180px) {{ .attacker-grid {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }} }}
  @media (max-width: 680px) {{ .attacker-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; }} }}

  .atk-card {{
    background: linear-gradient(180deg, rgba(23,34,61,0.95), rgba(14,21,38,0.95));
    border: 1.5px solid var(--border); border-radius: 12px; padding: 9px 10px;
    position: relative; overflow: hidden;
  }}
  .atk-card::before {{
    content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: var(--mon-color);
  }}
  .atk-card.active-mon {{
    border-color: var(--mon-color);
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--mon-color) 28%, transparent), 0 8px 22px rgba(0,0,0,0.45);
  }}
  .atk-top {{ display: flex; align-items: center; justify-content: space-between; gap: 6px; margin-bottom: 7px; }}
  .atk-top-l {{ display: flex; align-items: center; gap: 7px; min-width: 0; }}
  .atk-top img {{ width: 36px; height: 36px; object-fit: contain; flex-shrink: 0; }}
  .atk-name {{ font-weight: 800; font-size: 0.82rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .atk-stat {{ font-size: 0.66rem; color: var(--muted); }}
  .form-btn {{
    background: rgba(255,255,255,0.08); border: 1px solid var(--mon-color); color: #fff;
    font-size: 0.62rem; font-weight: 800; padding: 2px 6px; border-radius: 999px; cursor: pointer; flex-shrink: 0;
  }}
  .move-pills {{ display: flex; flex-direction: column; gap: 4px; }}
  .mv-btn {{
    background: rgba(8,13,26,0.75); border: 1px solid rgba(148,163,184,0.22);
    border-left: 3px solid var(--mcol, #38bdf8); color: var(--text);
    padding: 5px 8px; border-radius: 7px; font-size: 0.73rem; font-weight: 700;
    cursor: pointer; text-align: left; display: flex; justify-content: space-between; align-items: center; gap: 4px;
    transition: all 0.12s ease;
  }}
  .mv-btn:hover {{ border-color: var(--mcol); }}
  .mv-btn.selected {{
    background: color-mix(in srgb, var(--mcol) 24%, #0f172a);
    border-color: var(--gold);
    box-shadow: 0 0 10px rgba(250,204,21,0.25);
    color: #fff;
  }}
  .mv-bp {{ font-size: 0.64rem; color: var(--muted); font-weight: 600; flex-shrink: 0; }}
  .mv-btn.selected .mv-bp {{ color: #fde047; font-weight: 800; }}

  .controls-bar {{
    background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
    padding: 10px 12px; margin-bottom: 12px; display: flex; flex-wrap: wrap; gap: 9px 14px; align-items: center;
  }}
  .ctrl-group {{ display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }}
  .ctrl-label {{ font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); font-weight: 800; }}
  .toggle-btn {{
    background: var(--panel-2); border: 1px solid var(--border); color: var(--text);
    padding: 6px 9px; border-radius: 8px; font-size: 0.74rem; font-weight: 700; cursor: pointer;
    display: inline-flex; align-items: center; gap: 4px;
  }}
  .toggle-btn:disabled {{ opacity: 0.4; cursor: not-allowed; }}
  .toggle-btn.on {{ background: rgba(56,189,248,0.22); border-color: var(--accent); color: #bae6fd; }}
  .toggle-btn.on-sun {{ background: rgba(249,115,22,0.25); border-color: #fb923c; color: #fed7aa; }}
  .toggle-btn.on-snow {{ background: rgba(125,211,252,0.24); border-color: #7dd3fc; color: #e0f2fe; }}
  .toggle-btn.on-gold {{ background: rgba(250,204,21,0.22); border-color: var(--gold); color: #fef08a; }}
  .toggle-btn.on-green {{ background: rgba(34,197,94,0.22); border-color: var(--green); color: #bbf7d0; }}
  .toggle-btn.on-purple {{ background: rgba(192,132,252,0.24); border-color: var(--purple); color: #f3e8ff; }}
  .toggle-btn.on-pink {{ background: rgba(244,114,182,0.24); border-color: var(--pink); color: #fce7f3; }}
  .toggle-btn.on-red {{ background: rgba(244,63,94,0.22); border-color: var(--red); color: #fecdd3; }}
  select, input[type="text"] {{
    background: var(--panel-2); border: 1px solid var(--border); color: var(--text);
    padding: 6px 8px; border-radius: 8px; font-size: 0.74rem; font-weight: 600; outline: none;
  }}
  input[type="text"] {{ width: 140px; }}

  .summary-strip {{
    background: linear-gradient(90deg, rgba(23,34,61,0.92), rgba(17,25,46,0.92));
    border: 1px solid var(--border); border-radius: 11px; padding: 10px 13px; margin-bottom: 11px;
    display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px;
  }}
  .active-move-summary {{ font-size: 0.85rem; line-height: 1.35; }}
  .filter-pills {{ display: flex; flex-wrap: wrap; gap: 7px; }}
  .fpill {{
    padding: 5px 11px; border-radius: 999px; font-size: 0.74rem; font-weight: 800;
    cursor: pointer; border: 1.5px solid transparent; transition: all 0.14s ease;
  }}
  .fpill-all {{ background: rgba(148,163,184,0.16); color: var(--text); border-color: rgba(148,163,184,0.35); }}
  .fpill-ohko {{ background: rgba(34,197,94,0.18); color: #86efac; border-color: rgba(34,197,94,0.45); }}
  .fpill-roll {{ background: rgba(245,158,11,0.18); color: #fde68a; border-color: rgba(245,158,11,0.45); }}
  .fpill-2hko {{ background: rgba(6,182,212,0.18); color: #67e8f9; border-color: rgba(6,182,212,0.45); }}
  .fpill-surv {{ background: rgba(148,163,184,0.12); color: var(--muted); border-color: rgba(148,163,184,0.25); }}
  .fpill.active-filter {{ transform: scale(1.04); box-shadow: 0 0 12px rgba(255,255,255,0.22); border-color: #fff; }}

  .chart-card {{ background: var(--panel); border: 1px solid var(--border); border-radius: 13px; overflow: hidden; }}
  .chart-scroll {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
  .chart-inner {{ min-width: 720px; }}
  .chart-header {{
    display: grid; grid-template-columns: 250px 1fr 175px;
    background: rgba(8,13,26,0.94); border-bottom: 1px solid var(--border);
    padding: 9px 12px 7px; position: sticky; top: 0; z-index: 20;
  }}
  .ch-label {{
    font-size: 0.69rem; text-transform: uppercase; letter-spacing: 0.06em;
    color: var(--muted); font-weight: 800; display: flex; align-items: flex-end;
  }}
  .axis-wrap {{ position: relative; height: 24px; }}
  .axis-tick {{ position: absolute; bottom: 0; transform: translateX(-50%); font-size: 0.69rem; color: var(--muted); font-variant-numeric: tabular-nums; }}
  .axis-ko-tag {{
    position: absolute; top: 0; left: 80%; transform: translateX(-50%);
    font-size: 0.63rem; font-weight: 900; padding: 1px 6px; border-radius: 4px;
    background: var(--red); color: #fff; white-space: nowrap;
  }}

  .chart-row {{
    display: grid; grid-template-columns: 250px 1fr 175px; align-items: center;
    padding: 7px 12px; border-bottom: 1px solid rgba(38,54,92,0.45); cursor: pointer;
    transition: background 0.1s ease;
  }}
  .chart-row:hover {{ background: rgba(56,189,248,0.08); }}
  .chart-row.tier-ohko {{
    background: linear-gradient(90deg, rgba(34,197,94,0.13), rgba(34,197,94,0.03) 65%);
    border-left: 3.5px solid var(--green);
  }}
  .chart-row.tier-roll {{
    background: linear-gradient(90deg, rgba(245,158,11,0.13), rgba(245,158,11,0.03) 65%);
    border-left: 3.5px solid var(--amber);
  }}
  .chart-row.tier-2hko {{ border-left: 3.5px solid var(--cyan); }}
  .chart-row.tier-surv {{ border-left: 3.5px solid rgba(148,163,184,0.3); }}

  .mon-cell {{ display: flex; align-items: center; gap: 7px; min-width: 0; padding-right: 8px; }}
  .rank-num {{ width: 24px; font-size: 0.69rem; color: var(--muted); font-weight: 700; text-align: right; flex-shrink: 0; }}
  .mon-cell img {{ width: 33px; height: 33px; object-fit: contain; flex-shrink: 0; }}
  .mon-info {{ min-width: 0; flex: 1; }}
  .mon-name {{ font-size: 0.82rem; font-weight: 800; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: flex; align-items: center; gap: 5px; }}
  .eff-tag {{ font-size: 0.6rem; font-weight: 900; padding: 1px 4px; border-radius: 3px; background: rgba(255,255,255,0.1); }}
  .mon-meta {{ font-size: 0.66rem; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 1px; }}

  .plot-cell {{ position: relative; height: 30px; }}
  .grid-line {{ position: absolute; top: -7px; bottom: -7px; width: 1px; background: rgba(148,163,184,0.1); pointer-events: none; }}
  .ko-line {{
    position: absolute; top: -7px; bottom: -7px; left: 80%; width: 2px;
    border-left: 2px dashed rgba(244,63,94,0.85); z-index: 5; pointer-events: none;
  }}
  .thko-line {{
    position: absolute; top: -7px; bottom: -7px; left: 40%; width: 1px;
    border-left: 1px dashed rgba(6,182,212,0.45); z-index: 2; pointer-events: none;
  }}
  .whisker-bar {{
    position: absolute; top: 50%; transform: translateY(-50%); height: 4px;
    border-radius: 999px; background: rgba(148,163,184,0.28); z-index: 2;
  }}
  .dmg-bar-low {{
    position: absolute; top: 50%; transform: translateY(-50%); height: 12px;
    border-radius: 6px 0 0 6px; opacity: 0.88; z-index: 3;
  }}
  .dmg-bar-roll {{
    position: absolute; top: 50%; transform: translateY(-50%); height: 12px;
    border-radius: 0 6px 6px 0; opacity: 0.52; z-index: 3;
    border: 1px solid rgba(255,255,255,0.35);
  }}
  .dmg-label {{
    position: absolute; top: 50%; transform: translateY(-50%);
    font-size: 0.7rem; font-weight: 800; color: #fff; white-space: nowrap; z-index: 7;
    text-shadow: 0 1px 3px #080d1a, 0 0 5px #080d1a; font-variant-numeric: tabular-nums;
  }}

  .verdict-cell {{ text-align: right; padding-left: 8px; font-variant-numeric: tabular-nums; }}
  .ko-badge {{
    display: inline-block; padding: 3px 8px; border-radius: 6px;
    font-weight: 800; font-size: 0.7rem; white-space: nowrap;
  }}
  .kb-ohko {{ background: rgba(34,197,94,0.22); color: #86efac; border: 1px solid rgba(34,197,94,0.55); box-shadow: 0 0 10px rgba(34,197,94,0.2); }}
  .kb-roll {{ background: rgba(245,158,11,0.22); color: #fde68a; border: 1px solid rgba(245,158,11,0.55); }}
  .kb-2hko {{ background: rgba(6,182,212,0.18); color: #67e8f9; border: 1px solid rgba(6,182,212,0.45); }}
  .kb-surv {{ background: rgba(148,163,184,0.12); color: var(--muted); border: 1px solid rgba(148,163,184,0.25); }}
  .item-proc-note {{ font-size: 0.62rem; color: #fde047; margin-top: 2px; font-weight: 700; }}

  .modal-backdrop {{
    display: none; position: fixed; inset: 0; background: rgba(3, 6, 14, 0.76);
    z-index: 100; align-items: flex-end; justify-content: center; padding: 12px;
  }}
  .modal-backdrop.open {{ display: flex; }}
  @media (min-width: 760px) {{ .modal-backdrop {{ align-items: center; }} }}
  .modal-card {{
    background: #0e1629; border: 1.5px solid var(--accent); border-radius: 16px;
    padding: 15px 16px; width: 100%; max-width: 560px; max-height: 90vh; overflow-y: auto;
    box-shadow: 0 22px 55px rgba(0,0,0,0.75); font-size: 0.8rem; line-height: 1.4;
  }}
  .tt-head {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; border-bottom: 1px solid var(--border); padding-bottom: 8px; margin-bottom: 10px; }}
  .tt-head-l {{ display: flex; align-items: center; gap: 10px; }}
  .tt-head img {{ width: 44px; height: 44px; object-fit: contain; }}
  .tt-title {{ font-weight: 900; font-size: 1rem; }}
  .tt-sub {{ color: var(--muted); font-size: 0.74rem; }}
  .close-btn {{ background: rgba(255,255,255,0.08); border: 1px solid var(--border); color: #fff; border-radius: 8px; padding: 4px 10px; font-weight: 800; cursor: pointer; }}
  table.modal-tbl {{ width: 100%; border-collapse: collapse; font-size: 0.74rem; margin-top: 6px; font-variant-numeric: tabular-nums; }}
  table.modal-tbl th, table.modal-tbl td {{ padding: 6px 6px; border-bottom: 1px solid rgba(255,255,255,0.07); text-align: right; }}
  table.modal-tbl th:first-child, table.modal-tbl td:first-child {{ text-align: left; }}
  table.modal-tbl tr.is-meta-row {{ background: rgba(56,189,248,0.11); font-weight: 800; }}

  footer {{ margin-top: 16px; font-size: 0.72rem; color: var(--muted); text-align: center; }}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="title-block">
      <h1>
        💥 {tr['title_prefix']} — {team_esc}
        <span class="badge-format">{tr['badge']}</span>
      </h1>
      <p class="subtitle">
        {tr['subtitle_pre']}<strong id="totalTeamsLbl"></strong>{tr['subtitle_post']}
      </p>
    </div>
  </header>

  <div class="section-label">
    <span>{tr['sec_atk']}</span>
    <span style="color:#38bdf8;">{tr['sec_lock']}</span>
  </div>
  <div class="attacker-grid" id="attackerGrid"></div>

  <div class="controls-bar">
    <div class="ctrl-group">
      <span class="ctrl-label">{tr['atk_stage']}</span>
      <select id="selAtkStage" onchange="state.atkStage = Number(this.value); render();">
        <option value="-2">-2 Stage</option>
        <option value="-1">-1 (Intimidate)</option>
        <option value="0" selected>0 (Neutral)</option>
        <option value="1">+1 Stage</option>
        <option value="2">+2 Stage</option>
      </select>
      <button class="toggle-btn" id="btnHH" onclick="toggleFlag('helpingHand')">{tr['hh']}</button>
      <button class="toggle-btn" id="btnCrit" onclick="toggleFlag('crit')">{tr['crit']}</button>
      <button class="toggle-btn" id="btnBurn" onclick="toggleFlag('burn')">{tr['burn']}</button>
      <button class="toggle-btn" id="btnSingleTarget" onclick="toggleFlag('singleTarget')">{tr['single_tgt']}</button>
    </div>

    <div class="ctrl-group">
      <span class="ctrl-label">{tr['partner_lbl']}</span>
      <select id="selPartnerMove" onchange="state.partnerMoveUid = this.value; render();"></select>
      <select id="selPartnerStage" onchange="state.partnerStage = Number(this.value); render();">
        <option value="-1">Hit 1: -1</option>
        <option value="0" selected>Hit 1: 0</option>
        <option value="1">Hit 1: +1</option>
      </select>
    </div>

    <div class="ctrl-group">
      <span class="ctrl-label">{tr['weather']}</span>
      <button class="toggle-btn on" id="btnWNone" onclick="setWeather('none')">{tr['w_none']}</button>
      <button class="toggle-btn" id="btnWSun" onclick="setWeather('sun')">{tr['w_sun']}</button>
      <button class="toggle-btn" id="btnWRain" onclick="setWeather('rain')">{tr['w_rain']}</button>
      <button class="toggle-btn" id="btnWSand" onclick="setWeather('sand')">{tr['w_sand']}</button>
      <button class="toggle-btn" id="btnWSnow" onclick="setWeather('snow')">{tr['w_snow']}</button>
    </div>

    <div class="ctrl-group">
      <span class="ctrl-label">{tr['terrain']}</span>
      <button class="toggle-btn on" id="btnTNone" onclick="setTerrain('none')">{tr['t_none']}</button>
      <button class="toggle-btn" id="btnTElec" onclick="setTerrain('electric')">{tr['t_elec']}</button>
      <button class="toggle-btn" id="btnTGrass" onclick="setTerrain('grassy')">{tr['t_grass']}</button>
      <button class="toggle-btn" id="btnTPsy" onclick="setTerrain('psychic')">{tr['t_psy']}</button>
      <button class="toggle-btn" id="btnTMisty" onclick="setTerrain('misty')">{tr['t_misty']}</button>
    </div>

    <div class="ctrl-group">
      <span class="ctrl-label">{tr['defender']}</span>
      <select id="selBulkMode" onchange="state.bulkMode = this.value; render();">
        <option value="meta" selected>{tr['bulk_meta']}</option>
        <option value="min0">{tr['bulk_min0']}</option>
        <option value="hp32">{tr['bulk_hp32']}</option>
        <option value="bal">{tr['bulk_bal']}</option>
        <option value="maxDef">{tr['bulk_maxdef']}</option>
        <option value="maxSpd">{tr['bulk_maxspd']}</option>
      </select>
      <button class="toggle-btn on-gold" id="btnSimItems" onclick="toggleFlag('simItems')">{tr['sim_items']}</button>
      <button class="toggle-btn" id="btnScreens" onclick="toggleFlag('screens')">{tr['screens']}</button>
      <select id="selTopN" onchange="state.topN = Number(this.value); render();">
        {top_n_select_html}
      </select>
      <select id="selSort" onchange="state.sortBy = this.value; render();">
        <option value="ko" selected>{tr['sort_ko']}</option>
        <option value="usage">{tr['sort_usage']}</option>
      </select>
      <input type="text" id="txtSearch" placeholder="{tr['search_ph']}" oninput="state.search = this.value.trim().toLowerCase(); render();" />
    </div>
  </div>

  <div class="summary-strip">
    <div class="active-move-summary" id="activeMoveSummary"></div>
    <div class="filter-pills" id="filterPills"></div>
  </div>

  <div class="chart-card">
    <div class="chart-scroll">
      <div class="chart-inner">
        <div class="chart-header">
          <div class="ch-label">{tr['col_def']}</div>
          <div class="axis-wrap">
            <div class="axis-tick" style="left:0%">0%</div>
            <div class="axis-tick" style="left:20%">25%</div>
            <div class="axis-tick" style="left:40%">50% (2HKO)</div>
            <div class="axis-tick" style="left:60%">75%</div>
            <div class="axis-ko-tag">100% OHKO</div>
            <div class="axis-tick" style="left:100%">125%+</div>
          </div>
          <div class="ch-label" style="justify-content:flex-end;">{tr['col_verdict']}</div>
        </div>
        <div class="chart-body" id="chartBody"></div>
      </div>
    </div>
  </div>

  <footer>{tr['footer']}</footer>
</div>

<div class="modal-backdrop" id="modalBackdrop" onclick="if(event.target===this) closeModal()">
  <div class="modal-card" id="modalCard"></div>
</div>

<script>
const DATA = {data_json};
const SPRITES = {sprites_json};
const I18N = {i18n_json};

const TYPE_COLORS = {{
  Normal: '#9ca3af', Fire: '#f97316', Water: '#3b82f6', Electric: '#eab308',
  Grass: '#22c55e', Ice: '#06b6d4', Fighting: '#dc2626', Poison: '#a855f7',
  Ground: '#ca8a04', Flying: '#818cf8', Psychic: '#ec4899', Bug: '#84cc16',
  Rock: '#b45309', Ghost: '#6366f1', Dragon: '#4f46e5', Dark: '#475569',
  Steel: '#64748b', Fairy: '#f472b6'
}};

const state = {{
  selectedMoveUid: DATA.defaultMoveUid || '',
  megaForm: Object.assign({{}}, DATA.defaultMegaForm || {{}}),
  atkStage: 0,
  helpingHand: false,
  crit: false,
  burn: false,
  singleTarget: false,
  partnerMoveUid: 'none',
  partnerStage: 0,
  weather: 'none',
  terrain: 'none',
  bulkMode: 'meta',
  topN: DATA.defaultTopN || 50,
  simItems: true,
  screens: false,
  sortBy: 'ko',
  koFilter: 'all',
  search: '',
}};

function escapeHtml(s) {{
  return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}

function pokeRound(val, mod4096) {{
  return Math.floor((val * mod4096 + 2048) / 4096);
}}

function applyStatStage(stat, stage) {{
  if (stage >= 0) return Math.floor(stat * (2 + stage) / 2);
  return Math.floor(stat * 2 / (2 - stage));
}}

function isGrounded(types, ability) {{
  if (types.includes('Flying')) return false;
  if (ability === 'Levitate') return false;
  return true;
}}

function getEffectiveMoveType(move, form) {{
  let mType = move.type;
  if (move.name === 'Weather Ball') {{
    if (state.weather === 'sun') mType = 'Fire';
    else if (state.weather === 'rain') mType = 'Water';
    else if (state.weather === 'sand') mType = 'Rock';
    else if (state.weather === 'snow') mType = 'Ice';
  }} else if (move.name === 'Terrain Pulse' && isGrounded(form.types, form.ability)) {{
    if (state.terrain === 'electric') mType = 'Electric';
    else if (state.terrain === 'grassy') mType = 'Grass';
    else if (state.terrain === 'psychic') mType = 'Psychic';
    else if (state.terrain === 'misty') mType = 'Fairy';
  }} else if (mType === 'Normal') {{
    if (form.ability === 'Aerilate') mType = 'Flying';
    else if (form.ability === 'Pixilate') mType = 'Fairy';
    else if (form.ability === 'Refrigerate') mType = 'Ice';
    else if (form.ability === 'Galvanize') mType = 'Electric';
  }} else if (move.isSound && form.ability === 'Liquid Voice') {{
    mType = 'Water';
  }}
  return mType;
}}

function getTypeEff(moveType, defTypes) {{
  let mult = 1.0;
  const chart = DATA.typeChart[moveType] || {{}};
  for (const dt of defTypes) {{
    const m = chart[dt];
    if (m !== undefined) mult *= m;
  }}
  return mult;
}}

function getAttackerForm(attackerId) {{
  const atk = DATA.attackers.find(a => a.id === attackerId);
  const useMega = Boolean(atk && atk.mega && state.megaForm[attackerId]);
  return {{ atk, form: useMega ? atk.mega : atk.base, formTag: useMega ? 'mega' : 'base', isMega: useMega }};
}}

// Lookup exact pre-computed SmogonChampionsCalc 16-roll array with smart fallback
function lookupPrecomputedRolls(fmKey, defIdx, profKey, move, weather, terrain, singleFlag, seedFlag) {{
  const byDef = DATA.calcLut[fmKey];
  if (!byDef || !byDef[defIdx]) return DATA.rollPool[0];
  const profMap = byDef[defIdx];
  const canonicalKey = move.usesHpDependent
    ? profKey
    : (move.targetsDef ? (DATA.defEquiv[profKey] || profKey) : (DATA.spdEquiv[profKey] || profKey));
  const entry = profMap[canonicalKey];
  if (entry === undefined) return DATA.rollPool[0];
  if (typeof entry === 'number') return DATA.rollPool[entry] || DATA.rollPool[0];

  const w = weather || 'none';
  const t = terrain || 'none';
  const s = singleFlag ? 1 : 0;
  const sd = seedFlag ? 1 : 0;

  const candidates = [
    `${{w}}|${{t}}|${{s}}|${{sd}}`,
    `${{w}}|${{t}}|${{s}}|0`,
    `${{w}}|none|${{s}}|0`,
    `none|${{t}}|${{s}}|${{sd}}`,
    `none|${{t}}|${{s}}|0`,
    `${{w}}|none|0|0`,
    `none|${{t}}|0|0`,
    `none|none|${{s}}|0`,
    '_',
  ];
  for (const k of candidates) {{
    if (entry[k] !== undefined) return DATA.rollPool[entry[k]] || DATA.rollPool[0];
  }}
  return DATA.rollPool[0];
}}

function inferZeroReason(move, mType, form, defender) {{
  const defAb = defender.ability;
  const defGrounded = isGrounded(defender.types, defAb);
  if (move.priority > 0) {{
    if (defAb === 'Armor Tail' || defAb === 'Dazzling' || defAb === 'Queenly Majesty') return defAb;
    if (state.terrain === 'psychic' && defGrounded) return 'Psychic Terrain';
  }}
  if (mType === 'Ground' && !defGrounded) return defAb === 'Levitate' ? 'Levitate' : 'Flying';
  if (mType === 'Fire' && (defAb === 'Flash Fire' || defAb === 'Well-Baked Body')) return defAb;
  if (mType === 'Water' && (defAb === 'Water Absorb' || defAb === 'Storm Drain' || defAb === 'Dry Skin')) return defAb;
  if (mType === 'Electric' && (defAb === 'Lightning Rod' || defAb === 'Volt Absorb' || defAb === 'Motor Drive')) return defAb;
  if (mType === 'Grass' && defAb === 'Sap Sipper') return defAb;
  if (move.isBullet && defAb === 'Bulletproof') return 'Bulletproof';
  if (move.isSound && defAb === 'Soundproof') return 'Soundproof';
  if (getTypeEff(mType, defender.types) === 0) return 'Immune';
  return 'Immune';
}}

// Retrieve exact SmogonChampionsCalc 16-roll base array & apply tactical toggles
function getAdjustedRolls(move, stage, defender, defIdx, profKey, opts) {{
  const {{ atk, form, formTag }} = getAttackerForm(move.attackerId);
  const fmKey = `${{formTag}}:${{move.uid}}`;
  const mType = getEffectiveMoveType(move, form);
  const eff = getTypeEff(mType, defender.types);

  const isCrit = Boolean((opts.isCrit || move.willCrit) && defender.ability !== 'Battle Armor' && defender.ability !== 'Shell Armor');
  const seedMatches = Boolean(
    state.simItems &&
    defender.terrainSeed &&
    defender.terrainSeedTerrain === state.terrain &&
    ((defender.terrainSeedStat === 'def' && move.targetsDef) || (defender.terrainSeedStat === 'spd' && !move.targetsDef))
  );
  // Critical hits ignore positive defensive boosts (including Terrain Seed +1 Def/SpD!)
  const seedActive = seedMatches && !isCrit;
  const moveIsSpreadNow = Boolean(
    move.isSpread || (move.name === 'Expanding Force' && state.terrain === 'psychic' && isGrounded(form.types, form.ability))
  );
  const singleFlag = Boolean(moveIsSpreadNow && state.singleTarget);

  const baseRolls = lookupPrecomputedRolls(
    fmKey, defIdx, profKey, move, state.weather, state.terrain, singleFlag, seedActive
  );
  if (!baseRolls || baseRolls[15] === 0) {{
    return {{ rolls: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0], eff: 0, mType, reason: inferZeroReason(move, mType, form, defender), seedActive: false, berryUsed: false }};
  }}

  // Apply interactive tactical toggles using exact Champions 4096-scale rounding
  const isPhys = move.category === 'Physical';
  const effAtkStage = (defender.ability === 'Unaware' || (isCrit && stage < 0)) ? 0 : stage;
  const effDefStage = (isCrit && (opts.defStageBonus || 0) > 0) ? 0 : (opts.defStageBonus || 0);
  const applyHelpingHand = Boolean(opts.isHelpingHand);
  const applyCrit = Boolean(opts.isCrit && !move.willCrit && defender.ability !== 'Battle Armor' && defender.ability !== 'Shell Armor');
  const applyBurn = Boolean(opts.isBurn && isPhys && form.ability !== 'Guts' && !move.isFacade);
  const applyScreens = Boolean(state.screens && !isCrit && form.ability !== 'Infiltrator' && !move.breaksScreens);
  const applyMultiscale = Boolean(opts.atFullHp && (defender.ability === 'Multiscale' || defender.ability === 'Shadow Shield'));
  const berryUsed = Boolean(
    opts.canUseResistBerry &&
    defender.resistBerry &&
    defender.resistBerryType === mType &&
    (eff > 1 || (defender.resistBerry === 'Chilan Berry' && mType === 'Normal'))
  );

  // Fast path: when all binary tactical toggles are neutral, return the exact Smogon rolls untouched!
  if (
    effAtkStage === 0 && effDefStage === 0 && !applyHelpingHand && !applyCrit &&
    !applyBurn && !applyScreens && !applyMultiscale && !berryUsed
  ) {{
    return {{ rolls: baseRolls, eff, mType, reason: null, seedActive, berryUsed: false }};
  }}

  const rolls = new Array(16);
  for (let i = 0; i < 16; i++) {{
    let d = baseRolls[i];
    if (effAtkStage > 0) d = Math.floor(d * (2 + effAtkStage) / 2);
    else if (effAtkStage < 0) d = Math.floor(d * 2 / (2 - effAtkStage));
    if (effDefStage > 0) d = Math.floor(d * 2 / (2 + effDefStage));
    if (applyHelpingHand) d = pokeRound(d, 6144);
    if (applyCrit) d = pokeRound(d, 6144);
    if (applyBurn) d = pokeRound(d, 2048);
    if (applyScreens) d = pokeRound(d, 2732);
    if (applyMultiscale) d = pokeRound(d, 2048);
    if (berryUsed) d = pokeRound(d, 2048);
    rolls[i] = Math.max(1, d);
  }}
  return {{ rolls, eff, mType, reason: null, seedActive, berryUsed }};
}}

function evaluateAgainstProfile(defender, defIdx, profKey) {{
  const profile = defender.profiles[profKey];
  const mainMove = DATA.allMoves.find(m => m.uid === state.selectedMoveUid);
  const partnerMove = state.partnerMoveUid !== 'none' ? DATA.allMoves.find(m => m.uid === state.partnerMoveUid) : null;
  const hp = profile.hp;

  const hasSitrus = state.simItems && (defender.defaultItem === 'Sitrus Berry' || defender.sitrusPct >= 30);
  const hasSash = state.simItems && (defender.defaultItem === 'Focus Sash' || defender.ability === 'Sturdy');
  const hasResistBerry = state.simItems && Boolean(defender.resistBerry && (defender.defaultItem === defender.resistBerry || defender.resistBerryPct >= 15));
  const sitrusThresh = Math.floor(hp / 2);
  const sitrusHeal = Math.floor(hp / 4);

  if (!partnerMove) {{
    const res = getAdjustedRolls(mainMove, state.atkStage, defender, defIdx, profKey, {{
      isCrit: state.crit,
      isBurn: state.burn,
      isHelpingHand: state.helpingHand,
      atFullHp: true,
      canUseResistBerry: hasResistBerry,
      defStageBonus: 0,
    }});
    if (res.eff === 0 || res.rolls[15] === 0) {{
      return {{
        minPct: 0, maxPct: 0, minDmg: 0, maxDmg: 0,
        ohkoCount: 0, totalCombos: 16, ohkoPct: 0, twoHkoCount: 0,
        tier: 'surv', eff: 0, reason: res.reason, sitrusProcs: 0, sashProcs: 0,
        berryUsed: false, seedActive: false,
      }};
    }}

    let ohko = 0, twoHko = 0, sitrusProcs = 0, sashProcs = 0;
    for (const d of res.rolls) {{
      let rem = hp - d;
      if (hasSash && d >= hp) {{
        rem = 1;
        sashProcs++;
      }} else if (rem > 0 && hasSitrus && rem <= sitrusThresh) {{
        sitrusProcs++;
        rem = Math.min(hp, rem + sitrusHeal);
      }}
      if (rem <= 0) {{
        ohko++;
        twoHko++;
      }} else if (rem - d <= 0) {{
        twoHko++;
      }}
    }}

    const minDmg = res.rolls[0], maxDmg = res.rolls[15];
    const minPct = (minDmg / hp) * 100, maxPct = (maxDmg / hp) * 100;
    const ohkoPct = (ohko / 16) * 100;
    const tier = ohko === 16 ? 'ohko' : (ohko > 0 ? 'roll' : (twoHko >= 8 ? '2hko' : 'surv'));
    return {{
      minPct, maxPct, minDmg, maxDmg,
      ohkoCount: ohko, totalCombos: 16, ohkoPct, twoHkoCount: twoHko,
      tier, eff: res.eff, reason: null, sitrusProcs, sashProcs,
      berryUsed: res.berryUsed, seedActive: res.seedActive,
    }};
  }} else {{
    // 2-Mon Partner Combo Pin: Hit 1 (partnerMove) -> Hit 2 (mainMove)
    const res1 = getAdjustedRolls(partnerMove, state.partnerStage, defender, defIdx, profKey, {{
      isCrit: false,
      isBurn: false,
      isHelpingHand: false,
      atFullHp: true,
      canUseResistBerry: hasResistBerry,
      defStageBonus: 0,
    }});
    const hit1Dealt = res1.rolls[15] > 0;
    const staminaTriggered = (defender.ability === 'Stamina' && hit1Dealt);
    const defBonus2 = (staminaTriggered && mainMove.targetsDef) ? 1 : 0;

    const res2 = getAdjustedRolls(mainMove, state.atkStage, defender, defIdx, profKey, {{
      isCrit: state.crit,
      isBurn: state.burn,
      isHelpingHand: state.helpingHand,
      atFullHp: !hit1Dealt,
      canUseResistBerry: hasResistBerry && !res1.berryUsed,
      defStageBonus: defBonus2,
    }});

    if (!hit1Dealt && res2.rolls[15] === 0) {{
      return {{
        minPct: 0, maxPct: 0, minDmg: 0, maxDmg: 0,
        ohkoCount: 0, totalCombos: 256, ohkoPct: 0, twoHkoCount: 0,
        tier: 'surv', eff: 0, reason: res2.reason || res1.reason,
        sitrusProcs: 0, sashProcs: 0, berryUsed: false, seedActive: false,
      }};
    }}

    let ohko = 0, sitrusProcs = 0, sashProcs = 0;
    let minTotalEff = 99999, maxTotalEff = 0;
    for (const d1 of res1.rolls) {{
      let rem1 = hp - d1;
      let sitrusUsed1 = false;
      if (hasSash && d1 >= hp) {{
        rem1 = 1;
        sashProcs++;
      }} else if (rem1 > 0 && hasSitrus && rem1 <= sitrusThresh) {{
        sitrusProcs++;
        rem1 = Math.min(hp, rem1 + sitrusHeal);
        sitrusUsed1 = true;
      }}
      for (const d2 of res2.rolls) {{
        let rem2 = rem1 - d2;
        if (rem1 > 0 && rem2 > 0 && hasSitrus && !sitrusUsed1 && rem2 <= sitrusThresh) {{
          rem2 = Math.min(hp, rem2 + sitrusHeal);
        }}
        const netDealt = hp - rem2;
        if (netDealt < minTotalEff) minTotalEff = netDealt;
        if (netDealt > maxTotalEff) maxTotalEff = netDealt;
        if (rem2 <= 0) ohko++;
      }}
    }}

    const minPct = (minTotalEff / hp) * 100;
    const maxPct = (maxTotalEff / hp) * 100;
    const ohkoPct = (ohko / 256) * 100;
    const tier = ohko === 256 ? 'ohko' : (ohko > 0 ? 'roll' : (maxPct >= 50 ? '2hko' : 'surv'));
    return {{
      minPct, maxPct, minDmg: minTotalEff, maxDmg: maxTotalEff,
      h1MinPct: (res1.rolls[0] / hp) * 100, h1MaxPct: (res1.rolls[15] / hp) * 100,
      h2MinPct: (res2.rolls[0] / hp) * 100, h2MaxPct: (res2.rolls[15] / hp) * 100,
      ohkoCount: ohko, totalCombos: 256, ohkoPct, twoHkoCount: maxPct >= 50 ? 256 : 0,
      tier, eff: res2.eff, reason: null, sitrusProcs, sashProcs,
      berryUsed: res1.berryUsed || res2.berryUsed,
      seedActive: res1.seedActive || res2.seedActive,
    }};
  }}
}}

function setWeather(w) {{ state.weather = w; render(); }}
function setTerrain(t) {{ state.terrain = t; render(); }}
function toggleFlag(k) {{ state[k] = !state[k]; render(); }}
function toggleMegaForm(atkId, e) {{
  e.stopPropagation();
  state.megaForm[atkId] = !state.megaForm[atkId];
  render();
}}
function selectMove(uid) {{ state.selectedMoveUid = uid; render(); }}
function setKoFilter(f) {{ state.koFilter = (state.koFilter === f) ? 'all' : f; render(); }}
function closeModal() {{ document.getElementById('modalBackdrop').classList.remove('open'); }}

function populatePartnerSelect() {{
  const sel = document.getElementById('selPartnerMove');
  let out = `<option value="none">${{escapeHtml(I18N.partner_none)}}</option>`;
  for (const atk of DATA.attackers) {{
    if (!atk.moves.length) continue;
    out += `<optgroup label="${{escapeHtml(atk.label)}}">`;
    for (const mv of atk.moves) {{
      out += `<option value="${{mv.uid}}">+ ${{escapeHtml(atk.label.split(' ')[0])}}: ${{escapeHtml(mv.name)}} (${{mv.bp}} BP)</option>`;
    }}
    out += `</optgroup>`;
  }}
  sel.innerHTML = out;
}}

function renderAttackerGrid() {{
  const mainMove = DATA.allMoves.find(m => m.uid === state.selectedMoveUid);
  document.getElementById('attackerGrid').innerHTML = DATA.attackers.map(atk => {{
    const {{ form, isMega }} = getAttackerForm(atk.id);
    const isActiveMon = mainMove && mainMove.attackerId === atk.id;
    const formBtn = atk.mega ? `
      <button class="form-btn" onclick="toggleMegaForm('${{atk.id}}', event)">
        ${{isMega ? '🧬 Mega' : 'Base'}}
      </button>
    ` : '';
    const mPills = atk.moves.map(mv => {{
      const dispType = getEffectiveMoveType(mv, form);
      let dispBp = mv.bp;
      if (mv.name === 'Weather Ball' && state.weather !== 'none') dispBp = 100;
      if (mv.name === 'Expanding Force' && state.terrain === 'psychic' && isGrounded(form.types, form.ability)) dispBp = 120;
      const col = TYPE_COLORS[dispType] || '#38bdf8';
      const selCls = mv.uid === state.selectedMoveUid ? 'selected' : '';
      const extraTag = mv.chargeSpABoost ? ' (+1)' : (mv.isSpread ? ' · Sp' : '');
      return `
        <button class="mv-btn ${{selCls}}" style="--mcol:${{col}}" onclick="selectMove('${{mv.uid}}')">
          <span>${{escapeHtml(mv.name)}}</span>
          <span class="mv-bp">${{dispBp}}${{extraTag}}</span>
        </button>
      `;
    }}).join('');
    return `
      <div class="atk-card ${{isActiveMon ? 'active-mon' : ''}}" style="--mon-color:${{atk.color}}">
        <div class="atk-top">
          <div class="atk-top-l">
            <img src="${{SPRITES[form.spriteKey] || ''}}" alt="${{escapeHtml(form.name)}}" />
            <div style="min-width:0;">
              <div class="atk-name">${{escapeHtml(atk.label)}}</div>
              <div class="atk-stat">Atk ${{form.stats.atk}} • SpA ${{form.stats.spa}}</div>
            </div>
          </div>
          ${{formBtn}}
        </div>
        <div class="move-pills">${{mPills}}</div>
      </div>
    `;
  }}).join('');
}}

function openDefenderModal(rankIdx) {{
  const def = DATA.defenders[rankIdx];
  const mainMove = DATA.allMoves.find(m => m.uid === state.selectedMoveUid);
  const partnerMove = state.partnerMoveUid !== 'none' ? DATA.allMoves.find(m => m.uid === state.partnerMoveUid) : null;
  const order = ['min0', 'hp32', 'bal', 'balDef', 'balSpd', 'maxDef', 'maxSpd'];

  const rowsHtml = order.map(k => {{
    const prof = def.profiles[k];
    const ev = evaluateAgainstProfile(def, rankIdx, k);
    const isMeta = k === def.metaKey;
    const koCls = ev.tier === 'ohko' ? 'color:#86efac;font-weight:900;' : (ev.tier === 'roll' ? 'color:#fde68a;font-weight:800;' : 'color:var(--muted);');
    const koStr = ev.eff === 0 ? `0× (${{escapeHtml(ev.reason)}})` : `${{ev.ohkoCount}}/${{ev.totalCombos}} (${{ev.ohkoPct.toFixed(1)}}%)`;
    const itemNotes = [];
    if (ev.seedActive && def.terrainSeed) itemNotes.push(def.terrainSeed);
    if (ev.sitrusProcs > 0) itemNotes.push(`Sitrus ${{ev.sitrusProcs}}/16`);
    if (ev.sashProcs > 0) itemNotes.push('Sash');
    if (ev.berryUsed && def.resistBerry) itemNotes.push(def.resistBerry);
    return `
      <tr class="${{isMeta ? 'is-meta-row' : ''}}">
        <td>${{escapeHtml(prof.label)}} ${{isMeta ? '<span style="color:#38bdf8;">★ META</span>' : ''}}</td>
        <td>${{prof.hp}} / ${{prof.def}} / ${{prof.spd}}</td>
        <td>${{ev.minPct.toFixed(1)}}%–${{ev.maxPct.toFixed(1)}}%</td>
        <td>${{itemNotes.length ? escapeHtml(itemNotes.join(', ')) : '—'}}</td>
        <td style="${{koCls}}">${{koStr}}</td>
      </tr>
    `;
  }}).join('');

  const natStr = def.topNatures.map(n => `${{escapeHtml(n.name)}} <strong>${{n.pct}}%</strong>`).join(' · ');
  const itemStr = def.topItems.map(i => `${{escapeHtml(i.name)}} <strong>${{i.pct}}%</strong>`).join(' · ');
  const moveTitle = partnerMove
    ? `${{partnerMove.attackerLabel.split(' ')[0]}} ${{partnerMove.name}} → ${{mainMove.attackerLabel.split(' ')[0]}} ${{mainMove.name}}`
    : `${{mainMove.attackerLabel}} — ${{mainMove.name}}`;

  document.getElementById('modalCard').innerHTML = `
    <div class="tt-head">
      <div class="tt-head-l">
        <img src="${{SPRITES[def.spriteKey] || ''}}" alt="${{escapeHtml(def.species)}}" />
        <div>
          <div class="tt-title">#${{def.rank}} ${{escapeHtml(def.species)}} (${{def.types.join('/')}})</div>
          <div class="tt-sub">Ability: <strong>${{escapeHtml(def.ability)}}</strong> (${{def.abilityPct}}%) • Default Item: <strong>${{escapeHtml(def.defaultItem || 'None')}}</strong></div>
        </div>
      </div>
      <button class="close-btn" onclick="closeModal()">✕</button>
    </div>
    <div style="font-size:0.78rem; margin-bottom:6px; color:#38bdf8; font-weight:800;">💥 ${{escapeHtml(moveTitle)}}</div>
    <div style="font-size:0.73rem; color:var(--muted); margin-bottom:4px;">DuckDB Natures: ${{natStr}}</div>
    <div style="font-size:0.73rem; color:var(--muted); margin-bottom:8px;">DuckDB Items: ${{itemStr}}</div>
    ${{def.hasBulletproofAlt ? `<div style="font-size:0.72rem; color:#fde047; margin-bottom:6px;">⚠️ ${{def.bulletproofPct}}% run <strong>Bulletproof</strong> (blocks Ball/Bomb moves).</div>` : ''}}
    <table class="modal-tbl">
      <thead>
        <tr>
          <th>${{I18N.modal_spread}}</th>
          <th>HP/Def/SpD</th>
          <th>${{I18N.modal_net}}</th>
          <th>${{I18N.modal_item}}</th>
          <th>${{I18N.modal_ko}}</th>
        </tr>
      </thead>
      <tbody>${{rowsHtml}}</tbody>
    </table>
  `;
  document.getElementById('modalBackdrop').classList.add('open');
}}

function render() {{
  document.getElementById('totalTeamsLbl').textContent = DATA.totalTeams.toLocaleString();
  renderAttackerGrid();

  const mainMove = DATA.allMoves.find(m => m.uid === state.selectedMoveUid);
  if (!mainMove) {{
    document.getElementById('chartBody').innerHTML = '<div style="padding:18px;color:var(--muted);">No damaging moves found on team.</div>';
    return;
  }}

  document.getElementById('btnHH').className = 'toggle-btn' + (state.helpingHand ? ' on-gold' : '');
  document.getElementById('btnCrit').className = 'toggle-btn' + (state.crit ? ' on-red' : '');
  document.getElementById('btnBurn').className = 'toggle-btn' + (state.burn ? ' on-red' : '');
  const {{ form }} = getAttackerForm(mainMove.attackerId);
  const mainIsSpreadNow = Boolean(
    mainMove.isSpread || (mainMove.name === 'Expanding Force' && state.terrain === 'psychic' && isGrounded(form.types, form.ability))
  );
  const singleBtn = document.getElementById('btnSingleTarget');
  singleBtn.disabled = !mainIsSpreadNow;
  singleBtn.className = 'toggle-btn' + (mainIsSpreadNow && state.singleTarget ? ' on' : '');

  document.getElementById('btnWNone').className = 'toggle-btn' + (state.weather === 'none' ? ' on' : '');
  document.getElementById('btnWSun').className = 'toggle-btn' + (state.weather === 'sun' ? ' on-sun' : '');
  document.getElementById('btnWRain').className = 'toggle-btn' + (state.weather === 'rain' ? ' on' : '');
  document.getElementById('btnWSand').className = 'toggle-btn' + (state.weather === 'sand' ? ' on-gold' : '');
  document.getElementById('btnWSnow').className = 'toggle-btn' + (state.weather === 'snow' ? ' on-snow' : '');

  document.getElementById('btnTNone').className = 'toggle-btn' + (state.terrain === 'none' ? ' on' : '');
  document.getElementById('btnTElec').className = 'toggle-btn' + (state.terrain === 'electric' ? ' on-gold' : '');
  document.getElementById('btnTGrass').className = 'toggle-btn' + (state.terrain === 'grassy' ? ' on-green' : '');
  document.getElementById('btnTPsy').className = 'toggle-btn' + (state.terrain === 'psychic' ? ' on-purple' : '');
  document.getElementById('btnTMisty').className = 'toggle-btn' + (state.terrain === 'misty' ? ' on-pink' : '');

  document.getElementById('btnSimItems').className = 'toggle-btn' + (state.simItems ? ' on-gold' : '');
  document.getElementById('btnScreens').className = 'toggle-btn' + (state.screens ? ' on-purple' : '');

  const partnerMove = state.partnerMoveUid !== 'none' ? DATA.allMoves.find(m => m.uid === state.partnerMoveUid) : null;
  const maxBulkKey = mainMove.targetsDef ? 'maxDef' : 'maxSpd';

  const activeDefs = DATA.defenders.slice(0, state.topN);
  const rows = activeDefs.map((def, idx) => {{
    const profKey = state.bulkMode === 'meta' ? def.metaKey : state.bulkMode;
    const activeProf = def.profiles[profKey];
    const mainEv = evaluateAgainstProfile(def, idx, profKey);
    const minBulkEv = evaluateAgainstProfile(def, idx, 'min0');
    const maxBulkEv = evaluateAgainstProfile(def, idx, maxBulkKey);
    return {{ def, idx, activeProf, mainEv, minBulkEv, maxBulkEv }};
  }});

  let cntOhko = 0, cntRoll = 0, cnt2hko = 0, cntSurv = 0;
  for (const r of rows) {{
    if (r.mainEv.tier === 'ohko') cntOhko++;
    else if (r.mainEv.tier === 'roll') cntRoll++;
    else if (r.mainEv.tier === '2hko') cnt2hko++;
    else cntSurv++;
  }}

  const effStageForDisp = mainMove.chargeSpABoost ? Math.min(6, state.atkStage + 1) : state.atkStage;
  const atkStatVal = applyStatStage(mainMove.category === 'Physical' ? form.stats.atk : form.stats.spa, effStageForDisp);
  const comboPrefix = partnerMove ? `<strong>${{escapeHtml(partnerMove.attackerLabel.split(' ')[0])}} ${{escapeHtml(partnerMove.name)}}</strong> → ` : '';
  const spreadLabel = mainIsSpreadNow ? (state.singleTarget ? ' • 1.0× Single' : ' • 0.75× Spread') : '';
  const hhLabel = state.helpingHand ? ' • 1.5× HH' : '';
  document.getElementById('activeMoveSummary').innerHTML = `
    🎯 ${{comboPrefix}}<strong>${{escapeHtml(form.name)}}</strong> • <strong>${{escapeHtml(mainMove.name)}}</strong>
    <span style="color:var(--muted); font-size:0.78rem;">
      (${{mainMove.category}} • Eff. ${{mainMove.category === 'Physical' ? 'Atk' : 'SpA'}}: <strong>${{atkStatVal}}</strong>${{spreadLabel}}${{hhLabel}})
    </span>
  `;

  document.getElementById('filterPills').innerHTML = `
    <span class="fpill fpill-all ${{state.koFilter === 'all' ? 'active-filter' : ''}}" onclick="setKoFilter('all')">${{I18N.f_all}} (${{rows.length}})</span>
    <span class="fpill fpill-ohko ${{state.koFilter === 'ohko' ? 'active-filter' : ''}}" onclick="setKoFilter('ohko')">${{I18N.f_ohko}} (${{cntOhko}})</span>
    <span class="fpill fpill-roll ${{state.koFilter === 'roll' ? 'active-filter' : ''}}" onclick="setKoFilter('roll')">${{I18N.f_roll}} (${{cntRoll}})</span>
    <span class="fpill fpill-2hko ${{state.koFilter === '2hko' ? 'active-filter' : ''}}" onclick="setKoFilter('2hko')">${{I18N.f_2hko}} (${{cnt2hko}})</span>
    <span class="fpill fpill-surv ${{state.koFilter === 'surv' ? 'active-filter' : ''}}" onclick="setKoFilter('surv')">${{I18N.f_surv}} (${{cntSurv}})</span>
  `;

  let filtered = rows.filter(r => {{
    if (state.koFilter !== 'all' && r.mainEv.tier !== state.koFilter) return false;
    if (state.search && !r.def.species.toLowerCase().includes(state.search)) return false;
    return true;
  }});

  if (state.sortBy === 'ko') {{
    filtered.sort((a, b) => {{
      if (b.mainEv.ohkoPct !== a.mainEv.ohkoPct) return b.mainEv.ohkoPct - a.mainEv.ohkoPct;
      return b.mainEv.maxPct - a.mainEv.maxPct;
    }});
  }} else {{
    filtered.sort((a, b) => a.def.rank - b.def.rank);
  }}

  const toX = pctVal => Math.max(0, Math.min(100, (pctVal / 125) * 100));

  document.getElementById('chartBody').innerHTML = filtered.map(r => {{
    const d = r.def;
    const ev = r.mainEv;
    const wLeft = toX(r.maxBulkEv.minPct);
    const wWidth = Math.max(0.5, toX(r.minBulkEv.maxPct) - wLeft);
    const lowW = toX(ev.minPct);
    const rollW = Math.max(0.6, toX(ev.maxPct) - lowW);

    const barColor = ev.tier === 'ohko' ? '#22c55e' : (ev.tier === 'roll' ? '#f59e0b' : (ev.tier === '2hko' ? '#06b6d4' : '#64748b'));
    const maxPos = toX(ev.maxPct);
    const lblPos = maxPos > 76 ? `right:${{100 - maxPos + 1.5}}%` : `left:${{maxPos + 1.2}}%`;

    const rangeTxt = ev.eff === 0
      ? `0% (${{escapeHtml(ev.reason)}})`
      : (partnerMove
          ? `${{ev.minPct.toFixed(1)}}–${{ev.maxPct.toFixed(1)}}% (H1:${{ev.h1MinPct.toFixed(0)}}-${{ev.h1MaxPct.toFixed(0)}}% + H2:${{ev.h2MinPct.toFixed(0)}}-${{ev.h2MaxPct.toFixed(0)}}%)`
          : `${{ev.minPct.toFixed(1)}}%–${{ev.maxPct.toFixed(1)}}%`);

    let badgeHtml = '';
    if (ev.eff === 0) badgeHtml = `<span class="ko-badge kb-surv">0× ${{escapeHtml(ev.reason)}}</span>`;
    else if (ev.tier === 'ohko') badgeHtml = `<span class="ko-badge kb-ohko">✓ OHKO (${{ev.ohkoCount}}/${{ev.totalCombos}})</span>`;
    else if (ev.tier === 'roll') badgeHtml = `<span class="ko-badge kb-roll">⚡ ${{ev.ohkoPct.toFixed(1)}}% (${{ev.ohkoCount}}/${{ev.totalCombos}})</span>`;
    else if (ev.tier === '2hko') badgeHtml = `<span class="ko-badge kb-2hko">2HKO</span>`;
    else badgeHtml = `<span class="ko-badge kb-surv">${{I18N.survives}}</span>`;

    const itemNotes = [];
    if (ev.seedActive && d.terrainSeed) itemNotes.push(`${{d.terrainSeed}} (+1)`);
    if (ev.sashProcs > 0) itemNotes.push('Sash');
    if (ev.sitrusProcs > 0) itemNotes.push(`Sitrus ${{ev.sitrusProcs}}/16`);
    if (ev.berryUsed && d.resistBerry) itemNotes.push(`${{d.resistBerry}} 0.5×`);
    const noteHtml = itemNotes.length ? `<div class="item-proc-note">🍒 ${{escapeHtml(itemNotes.join(' · '))}}</div>` : '';

    const effBadge = ev.eff > 1 ? `<span class="eff-tag" style="color:#86efac">${{ev.eff}}×</span>`
                   : (ev.eff > 0 && ev.eff < 1 ? `<span class="eff-tag" style="color:#fda4af">${{ev.eff}}×</span>` : '');
    const defStatVal = mainMove.targetsDef ? r.activeProf.def : r.activeProf.spd;

    return `
      <div class="chart-row tier-${{ev.tier}}" onclick="openDefenderModal(${{r.idx}})">
        <div class="mon-cell">
          <span class="rank-num">#${{d.rank}}</span>
          <img src="${{SPRITES[d.spriteKey] || ''}}" alt="${{escapeHtml(d.species)}}" />
          <div class="mon-info">
            <div class="mon-name"><span>${{escapeHtml(d.species)}}</span>${{effBadge}}</div>
            <div class="mon-meta">${{escapeHtml(r.activeProf.label.split('(')[0].trim())}} (${{r.activeProf.hp}}/${{defStatVal}}) • ${{escapeHtml(d.defaultItem || 'No Item')}}</div>
          </div>
        </div>
        <div class="plot-cell">
          <div class="grid-line" style="left:20%"></div>
          <div class="thko-line"></div>
          <div class="grid-line" style="left:60%"></div>
          <div class="ko-line"></div>
          <div class="whisker-bar" style="left:${{wLeft}}%; width:${{wWidth}}%" title="Max Bulk to Min Bulk range"></div>
          <div class="dmg-bar-low" style="left:0%; width:${{lowW}}%; background:${{barColor}}"></div>
          <div class="dmg-bar-roll" style="left:${{lowW}}%; width:${{rollW}}%; background:${{barColor}}"></div>
          <div class="dmg-label" style="${{lblPos}}">${{rangeTxt}}</div>
        </div>
        <div class="verdict-cell">
          ${{badgeHtml}}
          ${{noteHtml}}
        </div>
      </div>
    `;
  }}).join('');
}}

populatePartnerSelect();
render();
</script>
</body>
</html>
"""


def build_speed_tiers_html(
    paste_text: str,
    team_name: str = "My Reg M-C Team",
    top_n: int = 50,
    lang: str = "en",
) -> tuple[str, SpeedTiersPayload]:
    """Build and render the offline Base64 Speed Tiers HTML from a Showdown paste."""
    payload = build_speed_tiers_payload(
        paste_text=paste_text,
        team_name=team_name,
        top_n=top_n,
    )
    return render_speed_tiers_html(payload, lang=lang), payload


def build_damage_matrix_html(
    paste_text: str,
    team_name: str = "My Reg M-C Team",
    top_n: int = 50,
    lang: str = "en",
) -> tuple[str, DamageMatrixPayload]:
    """Build and render the offline Base64 Damage & KO Matrix HTML from a Showdown paste."""
    payload = build_damage_matrix_payload(
        paste_text=paste_text,
        team_name=team_name,
        top_n=top_n,
    )
    return render_damage_matrix_html(payload, lang=lang), payload
