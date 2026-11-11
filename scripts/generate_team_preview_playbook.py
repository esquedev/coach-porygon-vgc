#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Team Preview Playbook, 90s Execution Protocol & Live Telemetry Generator (Regulation M-C).

Analyzes a 6-Pokémon Regulation M-C roster, evaluates all 15 4-mon modes and 15 lead pairs,
benchmarks against 8 canonical Regulation M-C tournament archetypes, and ingests live practice
telemetry from `data/telemetry/battles_telemetry.csv`.

Outputs:
1. An interactive, offline-ready HTML Playbook featuring:
   - Deterministic sprite & item resolution via `assets/slug_map.json`.
   - A 4-Step 90-Second Team Preview Execution Protocol (Checklist).
   - An If-Then-Else Decision-Tree Rulebook with strictly move-grounded Turn 1 commands.
   - Live Practice Telemetry Tracker (empirical win rates, lead frequency, and coach notes).
   - All 15 Modes & 15 Leads evaluation matrices.
2. A Markdown cheat-sheet (`reports/<team>_cheatsheet.md`) for quick reference.
"""

from __future__ import annotations

import argparse
import base64
import csv
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "src" / "engine"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from engine.modes import (
    ArchetypeMatchupPlan,
    LeadEvaluation,
    LeadPair,
    ModeEvaluation,
    TeamMemberData,
    TeamMode,
    TeamModeAnalyzer,
    TournamentArchetype,
    TournamentArchetypeMatcher,
)

ASSETS_DIR = ROOT_DIR / "assets"
SLUG_MAP_PATH = ASSETS_DIR / "slug_map.json"

_SLUG_MAP_CACHE: Optional[Dict[str, Dict[str, str]]] = None


def _get_slug_map() -> Dict[str, Dict[str, str]]:
    """Loads `assets/slug_map.json` into memory (building it on the fly if missing)."""
    global _SLUG_MAP_CACHE
    if _SLUG_MAP_CACHE is not None:
        return _SLUG_MAP_CACHE

    if not SLUG_MAP_PATH.exists():
        from build_sprite_slug_map import build_slug_map
        payload = build_slug_map()
        SLUG_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
        SLUG_MAP_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        _SLUG_MAP_CACHE = payload
        return _SLUG_MAP_CACHE

    _SLUG_MAP_CACHE = json.loads(SLUG_MAP_PATH.read_text(encoding="utf-8"))
    return _SLUG_MAP_CACHE


def _norm_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def resolve_sprite_path(species: str, mega_form: Optional[str] = None) -> Optional[Path]:
    """Deterministically resolves a Pokémon species or Mega forme via `assets/slug_map.json`."""
    smap = _get_slug_map().get("species", {})
    candidates: List[str] = []
    if mega_form:
        candidates.extend([mega_form, mega_form.lower(), _norm_key(mega_form)])
    if species:
        candidates.extend([species, species.lower(), _norm_key(species)])

    for cand in candidates:
        rel = smap.get(cand)
        if rel:
            full_path = ROOT_DIR / rel
            if full_path.exists():
                return full_path
    return None


def resolve_item_path(item_name: str) -> Optional[Path]:
    """Deterministically resolves an item or Mega Stone via `assets/slug_map.json`."""
    if not item_name:
        return None
    imap = _get_slug_map().get("items", {})
    for cand in (item_name, item_name.lower(), item_name.lower().replace(" ", "-"), _norm_key(item_name)):
        rel = imap.get(cand)
        if rel:
            full_path = ROOT_DIR / rel
            if full_path.exists():
                return full_path
    return None


def encode_image_base64(path: Optional[Path], fallback_label: str = "?") -> str:
    """Encodes an image file to a base64 data URI, or generates a crisp SVG badge fallback."""
    if path and path.exists():
        data = path.read_bytes()
        ext = path.suffix.lstrip(".").lower()
        mime = "image/png" if ext == "png" else "image/svg+xml"
        return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"

    initials = (fallback_label[:2] if fallback_label else "PK").upper()
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48">'
        f'<rect width="48" height="48" rx="10" fill="#1e293b" stroke="#06b6d4" stroke-width="2"/>'
        f'<text x="24" y="29" font-family="sans-serif" font-size="14" font-weight="bold" '
        f'fill="#f8fafc" text-anchor="middle">{initials}</text></svg>'
    )
    return f"data:image/svg+xml;base64,{base64.b64encode(svg.encode('utf-8')).decode('ascii')}"


@dataclass
class MatchTelemetrySummary:
    """Aggregated summary of a single recorded battle from telemetry CSV."""

    match_id: str
    timestamp: str
    trainer_1: str
    trainer_2: str
    trainer_1_lead: Tuple[str, str]
    trainer_2_lead: Tuple[str, str]
    brought_mons: Set[str]
    turn_1_moves: str
    winner: str
    won: bool
    total_turns: int
    comments: List[str]


@dataclass
class LiveTelemetryStats:
    """Aggregated empirical telemetry statistics across all logged practice matches."""

    total_matches: int = 0
    wins: int = 0
    losses: int = 0
    lead_stats: Dict[FrozenSet[str], Dict[str, int]] = field(default_factory=dict)  # {frozenset: {played, wins}}
    mode_stats: Dict[FrozenSet[str], Dict[str, int]] = field(default_factory=dict)
    recent_matches: List[MatchTelemetrySummary] = field(default_factory=list)


def parse_telemetry_csv(csv_path: Optional[Path]) -> LiveTelemetryStats:
    """Reads `battles_telemetry.csv` and aggregates empirical lead/mode performance."""
    stats = LiveTelemetryStats()
    if not csv_path or not csv_path.exists():
        return stats

    rows_by_match: Dict[str, List[Dict[str, str]]] = {}
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mid = row.get("match_id", "").strip()
            if mid:
                rows_by_match.setdefault(mid, []).append(row)

    for mid, rows in rows_by_match.items():
        rows.sort(key=lambda r: int(r.get("turn", "1") or 1))
        first = rows[0]
        t1 = first.get("trainer_1", "trainer_1").strip()
        t2 = first.get("trainer_2", "trainer_2").strip()
        winner = rows[-1].get("winner", "").strip() or first.get("winner", "").strip()
        won = bool(winner and winner.lower() == t1.lower())

        # Extract base species name (strip nicknames orformes if needed)
        def _clean_mon(raw: str) -> str:
            s = raw.strip()
            if "(" in s and ")" in s:
                s = s[s.find("(") + 1 : s.find(")")]
            return s.split("-Mega")[0].strip()

        l1 = _clean_mon(first.get("trainer_1_active_1", ""))
        l2 = _clean_mon(first.get("trainer_1_active_2", ""))
        opp1 = first.get("trainer_2_active_1", "").strip()
        opp2 = first.get("trainer_2_active_2", "").strip()

        brought: Set[str] = set()
        comments: List[str] = []
        for r in rows:
            for k in ("trainer_1_active_1", "trainer_1_active_2"):
                m_clean = _clean_mon(r.get(k, ""))
                if m_clean:
                    brought.add(m_clean)
            c = r.get("comment", "").strip()
            if c:
                comments.append(f"T{r.get('turn', '?')}: {c}")

        stats.total_matches += 1
        if won:
            stats.wins += 1
        elif winner:
            stats.losses += 1

        if l1 and l2:
            lead_key = frozenset({l1.lower(), l2.lower()})
            entry = stats.lead_stats.setdefault(lead_key, {"played": 0, "wins": 0})
            entry["played"] += 1
            if won:
                entry["wins"] += 1

        if len(brought) >= 3:
            mode_key = frozenset(m.lower() for m in brought)
            m_entry = stats.mode_stats.setdefault(mode_key, {"played": 0, "wins": 0})
            m_entry["played"] += 1
            if won:
                m_entry["wins"] += 1

        stats.recent_matches.append(
            MatchTelemetrySummary(
                match_id=mid,
                timestamp=first.get("timestamp", ""),
                trainer_1=t1,
                trainer_2=t2,
                trainer_1_lead=(l1, l2),
                trainer_2_lead=(opp1, opp2),
                brought_mons=brought,
                turn_1_moves=first.get("trainer_1_moves", ""),
                winner=winner or "Unfinished",
                won=won,
                total_turns=len(rows),
                comments=comments,
            )
        )

    return stats


def generate_mermaid_cheatsheet(
    team_name: str,
    plans: List[ArchetypeMatchupPlan],
    modes: List[ModeEvaluation],
    leads: List[LeadEvaluation],
    telemetry: LiveTelemetryStats,
) -> str:
    """Generates a Markdown Playbook featuring the 4-Step Protocol & If-Then-Else Rulebook."""
    md: List[str] = [
        f"# 🏆 Team Preview Execution Protocol & Rulebook: {team_name}",
        "",
        "> **Format**: Regulation M-C (Champions Level 50, 66 Stat Points, Mega Evolution Enabled)",
        "> **Sprites & Assets**: Deterministically indexed via `assets/slug_map.json`",
        f"> **Live Telemetry Status**: {telemetry.total_matches} Recorded Matches ({telemetry.wins}W - {telemetry.losses}L)",
        "",
        "---",
        "",
        "## 1. The 90-Second Team Preview Execution Protocol (4-Step Checklist)",
        "",
        "Execute these 4 steps sequentially during your 90-second Team Preview clock:",
        "",
        "1. **[00s – 15s] Step 1: Opponent Speed & Field Mechanism Scan**",
        "   - Identify their primary field setter: **Tailwind** (Whimsicott), **Rain** (Pelipper/Archaludon), **Sun** (Venusaur/Charizard/Torkoal), **Psychic Terrain / Trick Room** (Indeedee-F/Farigiraf), **Intimidate Balance** (Incineroar/Rillaboom/Sneasler), **Sand** (Tyranitar/Excadrill), or **Snow** (Ninetales-Alola).",
        "2. **[15s – 40s] Step 2: Lock Your Bring-4 Mode (Leave Liability Behind)**",
        "   - Never bring all 6 in your head; immediately cross off the 2 Pokémon that lose to their speed/weather mechanic and lock the textbook 4-mon Mode below.",
        "3. **[40s – 65s] Step 3: Lock Your Lead Pair & Reserve Backline**",
        "   - Place your active disruption/weather-override pair in Slots 1 & 2, keeping your late-game cleaner (e.g., **Kingambit** or **Milotic**) protected in the back.",
        "4. **[65s – 90s] Step 4: Pre-Commit Turn 1 Verified Move Commands**",
        "   - Decide both Turn 1 moves *before* Turn 1 begins using the verified command matrix below, including your Branch B response if they hard-switch.",
        "",
        "---",
        "",
        "## 2. If-Then-Else Decision-Tree Rulebook (By Tournament Archetype)",
        "",
    ]

    for idx, plan in enumerate(plans, start=1):
        arch = plan.archetype
        p1 = plan.recommended_lead.pokemon_1.species
        p2 = plan.recommended_lead.pokemon_2.species
        b_names = " + ".join(m.species for m in plan.backline)
        cmd_lines = " | ".join(f"**{k}**: `{v}`" for k, v in plan.step_4_turn_1_matrix.items())

        md.extend([
            f"### Rule {idx}: `{plan.if_condition}`",
            f"- **Archetype**: **{arch.name}** (`{arch.tier}` • `{arch.tournament_frequency_pct}%` Regional Usage)",
            f"- **Step 1 (Scan)**: {plan.step_1_threat_scan}",
            f"- **Step 2 (THEN Lock Mode)**: **{plan.recommended_mode.name}**",
            f"- **Step 3 (THEN Lead & Back)**: **Lead**: `{p1} + {p2}` ➔ **Backline**: `{b_names}`",
            f"- **Step 4 (Turn 1 Verified Commands)**: {cmd_lines}",
            f"  - *Primary Line (Plan A)*: {plan.turn_1_plan_a}",
            f"  - *Contingency (Branch B)*: {plan.turn_1_plan_b}",
            f"  - *Win Condition*: {plan.win_condition}",
            "",
        ])

    md.extend([
        "---",
        "",
        "## 3. All 15 4-Mon Modes Matrix",
        "",
        "| Mode ID | Core Composition | SE Coverage | Shared Weaknesses | Speed Tools | Disruption Tools | Score |",
        "| :---: | :--- | :---: | :--- | :--- | :--- | :---: |",
    ])

    for me in modes:
        names = " + ".join(f"**{m.species}**" for m in me.mode.members)
        cov_str = f"{me.coverage_count}/18 ({round(me.coverage_score*100)}%)"
        weak_str = ", ".join(f"{t}({c})" for t, c in me.shared_weaknesses[:2]) if me.shared_weaknesses else "None"
        speed_str = ", ".join(me.speed_control_tools[:2]) if me.speed_control_tools else "Neutral"
        disr_str = ", ".join(me.disruption_tools[:2]) if me.disruption_tools else "None"
        md.append(f"| Mode {me.mode.mode_id} | {names} | `{cov_str}` | {weak_str} | {speed_str} | {disr_str} | **{me.composite_score}** |")

    md.extend([
        "",
        "---",
        "",
        "## 4. All 15 Lead Pairs Ranking (Strictly Verified Moves)",
        "",
        "| Lead Pair | Spe Tiers | Initiative | Verified Tactical Strengths | Shared Weaknesses | Empirical Record |",
        "| :--- | :---: | :---: | :--- | :--- | :---: |",
    ])

    for le in leads:
        p1 = le.lead.pokemon_1.species
        p2 = le.lead.pokemon_2.species
        pair_str = f"**{p1}** + **{p2}**"
        spe_str = f"{le.combined_speed_tiers[0]} / {le.combined_speed_tiers[1]}"
        vuln_str = ", ".join(le.shared_weaknesses) if le.shared_weaknesses else "None"
        lkey = frozenset({p1.lower(), p2.lower()})
        emp = telemetry.lead_stats.get(lkey)
        emp_str = f"{emp['wins']}W / {emp['played']}G" if emp else "0G"
        md.append(f"| {pair_str} | `{spe_str}` | **{le.initiative_score}** | {le.tactical_summary} | {vuln_str} | `{emp_str}` |")

    return "\n".join(md)


def generate_html_playbook(
    team_name: str,
    members: List[TeamMemberData],
    plans: List[ArchetypeMatchupPlan],
    modes: List[ModeEvaluation],
    leads: List[LeadEvaluation],
    telemetry: LiveTelemetryStats,
) -> str:
    """Generates the interactive HTML Playbook with Protocol, Rulebook, and Live Telemetry."""
    member_sprites: Dict[str, str] = {}
    member_items: Dict[str, str] = {}

    for m in members:
        s_path = resolve_sprite_path(m.species, m.mega_form)
        member_sprites[m.species] = encode_image_base64(s_path, m.species)
        i_path = resolve_item_path(m.item)
        member_items[m.species] = encode_image_base64(i_path, m.item)

    opponent_sprites: Dict[str, str] = {}
    for p in plans:
        for s in p.archetype.core_species:
            if s not in opponent_sprites:
                opponent_sprites[s] = encode_image_base64(resolve_sprite_path(s), s)
        for l1, l2 in p.archetype.typical_leads:
            for s in (l1, l2):
                if s not in opponent_sprites:
                    opponent_sprites[s] = encode_image_base64(resolve_sprite_path(s), s)

    wr_pct = round((telemetry.wins / telemetry.total_matches) * 100, 1) if telemetry.total_matches > 0 else 0.0

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Coach Porygon — Team Preview Protocol & Playbook: {team_name}</title>
  <style>
    :root {{
      --bg-dark: #090d16;
      --card-bg: #111827;
      --card-border: #1f293d;
      --cyan: #06b6d4;
      --indigo: #6366f1;
      --emerald: #10b981;
      --amber: #f59e0b;
      --rose: #f43f5e;
      --text-main: #f3f4f6;
      --text-muted: #9ca3af;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
    body {{ background: var(--bg-dark); color: var(--text-main); line-height: 1.5; padding: 24px; }}
    .container {{ max-width: 1340px; margin: 0 auto; }}
    
    header {{ display: flex; align-items: center; justify-content: space-between; padding-bottom: 20px; border-bottom: 1px solid var(--card-border); margin-bottom: 24px; flex-wrap: wrap; gap: 12px; }}
    .brand {{ display: flex; align-items: center; gap: 16px; }}
    .brand-icon {{ width: 44px; height: 44px; background: linear-gradient(135deg, var(--cyan), var(--indigo)); border-radius: 12px; display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 20px; color: #fff; box-shadow: 0 0 20px rgba(99,102,241,0.4); }}
    .brand h1 {{ font-size: 22px; font-weight: 800; letter-spacing: -0.5px; }}
    .brand p {{ color: var(--text-muted); font-size: 13px; }}
    .header-badges {{ display: flex; gap: 10px; align-items: center; }}
    .badge-vgc {{ background: rgba(6,182,212,0.15); color: var(--cyan); border: 1px solid rgba(6,182,212,0.3); padding: 5px 12px; border-radius: 9999px; font-size: 12px; font-weight: 700; text-transform: uppercase; }}
    .badge-telemetry {{ background: rgba(16,185,129,0.15); color: var(--emerald); border: 1px solid rgba(16,185,129,0.3); padding: 5px 12px; border-radius: 9999px; font-size: 12px; font-weight: 700; }}

    /* Roster Strip */
    .roster-strip {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(195px, 1fr)); gap: 12px; margin-bottom: 24px; }}
    .mon-card {{ background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; padding: 12px; display: flex; align-items: center; gap: 12px; }}
    .mon-sprite {{ width: 56px; height: 56px; object-fit: contain; filter: drop-shadow(0 4px 6px rgba(0,0,0,0.5)); }}
    .mon-info h4 {{ font-size: 14px; font-weight: 700; display: flex; align-items: center; gap: 6px; }}
    .mon-info p {{ font-size: 11px; color: var(--text-muted); }}
    .mon-moves {{ font-size: 10px; color: var(--cyan); margin-top: 3px; }}
    .item-icon {{ width: 18px; height: 18px; object-fit: contain; vertical-align: middle; }}

    /* Tabs */
    .nav-tabs {{ display: flex; gap: 8px; margin-bottom: 20px; border-bottom: 1px solid var(--card-border); padding-bottom: 10px; flex-wrap: wrap; }}
    .tab-btn {{ background: transparent; border: 1px solid transparent; color: var(--text-muted); font-size: 13px; font-weight: 600; padding: 8px 16px; border-radius: 8px; cursor: pointer; transition: all 0.2s; }}
    .tab-btn:hover {{ color: var(--text-main); background: rgba(255,255,255,0.05); }}
    .tab-btn.active {{ color: #fff; background: var(--indigo); box-shadow: 0 0 12px rgba(99,102,241,0.5); }}

    /* 4-Step Protocol Banner */
    .protocol-banner {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; margin-bottom: 24px; }}
    .proto-step {{ background: linear-gradient(180deg, rgba(31,41,61,0.6), rgba(17,24,39,0.9)); border: 1px solid var(--card-border); border-top: 3px solid var(--cyan); border-radius: 12px; padding: 14px; }}
    .proto-step .step-time {{ font-size: 11px; font-weight: 800; color: var(--cyan); text-transform: uppercase; letter-spacing: 0.5px; }}
    .proto-step h3 {{ font-size: 15px; font-weight: 800; margin: 4px 0 6px; }}
    .proto-step p {{ font-size: 12px; color: var(--text-muted); }}

    /* Rulebook Cards */
    .section-title {{ font-size: 18px; font-weight: 700; margin-bottom: 14px; display: flex; align-items: center; gap: 8px; }}
    .rulebook-grid {{ display: flex; flex-direction: column; gap: 16px; }}
    .rule-card {{ background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 14px; padding: 18px; display: flex; flex-direction: column; gap: 14px; }}
    .rule-header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 10px; flex-wrap: wrap; gap: 8px; }}
    .if-clause {{ font-family: monospace; font-size: 13px; font-weight: 700; color: var(--amber); background: rgba(245,158,11,0.12); border: 1px solid rgba(245,158,11,0.3); padding: 4px 10px; border-radius: 6px; }}
    .arch-badge {{ font-size: 11px; font-weight: 700; text-transform: uppercase; padding: 3px 9px; border-radius: 4px; }}
    .tier-s {{ background: rgba(244,63,94,0.15); color: var(--rose); border: 1px solid rgba(244,63,94,0.3); }}
    .tier-a {{ background: rgba(245,158,11,0.15); color: var(--amber); border: 1px solid rgba(245,158,11,0.3); }}
    .tier-b {{ background: rgba(16,185,129,0.15); color: var(--emerald); border: 1px solid rgba(16,185,129,0.3); }}

    .rule-steps {{ display: grid; grid-template-columns: 240px 230px 200px 1fr; gap: 12px; align-items: stretch; }}
    @media (max-width: 1100px) {{ .rule-steps {{ grid-template-columns: 1fr; }} }}
    .step-box {{ background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06); border-radius: 10px; padding: 12px; display: flex; flex-direction: column; gap: 6px; }}
    .box-label {{ font-size: 10px; text-transform: uppercase; font-weight: 800; color: var(--cyan); letter-spacing: 0.5px; }}
    .pair-display {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
    .pair-display img {{ width: 42px; height: 42px; object-fit: contain; }}
    .pair-names {{ font-size: 13px; font-weight: 700; }}

    .cmd-box {{ background: rgba(0,0,0,0.3); border-radius: 10px; padding: 12px; border-left: 3px solid var(--emerald); display: flex; flex-direction: column; gap: 6px; }}
    .cmd-line {{ font-size: 12px; color: var(--text-main); }}
    .cmd-line code {{ color: var(--emerald); font-weight: 700; background: rgba(16,185,129,0.1); padding: 1px 5px; border-radius: 4px; }}
    .plan-b {{ font-size: 12px; color: var(--text-muted); font-style: italic; }}
    .win-con {{ font-size: 11px; color: var(--cyan); font-weight: 600; }}
    .risk-tag {{ display: inline-flex; font-size: 10px; color: var(--rose); background: rgba(244,63,94,0.1); padding: 2px 6px; border-radius: 4px; margin-right: 4px; }}

    /* Tables */
    .table-container {{ overflow-x: auto; background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 14px; padding: 16px; margin-bottom: 24px; }}
    table {{ width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; }}
    th {{ padding: 10px 14px; color: var(--text-muted); font-weight: 700; border-bottom: 1px solid var(--card-border); text-transform: uppercase; font-size: 11px; }}
    td {{ padding: 12px 14px; border-bottom: 1px solid rgba(255,255,255,0.04); vertical-align: middle; }}
    tr:hover td {{ background: rgba(255,255,255,0.02); }}
    .score-badge {{ background: rgba(99,102,241,0.2); color: var(--indigo); font-weight: 800; padding: 4px 8px; border-radius: 6px; display: inline-block; }}
    .emp-badge {{ background: rgba(16,185,129,0.15); color: var(--emerald); font-weight: 700; font-size: 11px; padding: 3px 7px; border-radius: 6px; display: inline-block; }}
    .table-sprites {{ display: flex; gap: 6px; align-items: center; }}
    .table-sprites img {{ width: 34px; height: 34px; object-fit: contain; }}

    footer {{ text-align: center; color: var(--text-muted); font-size: 12px; padding-top: 24px; border-top: 1px solid var(--card-border); }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand">
        <div class="brand-icon">CP</div>
        <div>
          <h1>Team Preview Execution Protocol & Rulebook: {team_name}</h1>
          <p>Regulation M-C Certified • Deterministic Slug Mapping • Zero-Hallucination Move Grounding</p>
        </div>
      </div>
      <div class="header-badges">
        <span class="badge-telemetry">📊 Telemetry: {telemetry.total_matches} Matches ({telemetry.wins}W-{telemetry.losses}L • {wr_pct}%)</span>
        <span class="badge-vgc">Regulation M-C</span>
      </div>
    </header>

    <!-- 6-Mon Roster Strip with Verified Moves -->
    <div class="roster-strip">
"""

    for m in members:
        s_b64 = member_sprites.get(m.species, "")
        i_b64 = member_items.get(m.species, "")
        spe = m.effective_stats.get("spe", 100)
        types_str = "/".join(m.types)
        moves_str = " • ".join(m.moves)
        html += f"""
      <div class="mon-card">
        <img class="mon-sprite" src="{s_b64}" alt="{m.species}">
        <div class="mon-info">
          <h4>{m.species} <img class="item-icon" src="{i_b64}" alt="{m.item}" title="{m.item}"></h4>
          <p>{types_str} • Spe: <strong>{spe}</strong> • {m.ability}</p>
          <div class="mon-moves">{moves_str}</div>
        </div>
      </div>
"""

    html += """
    </div>

    <!-- Navigation Tabs -->
    <div class="nav-tabs">
      <button class="tab-btn active" onclick="showTab('protocol')">📋 90s Execution Protocol & Rulebook</button>
      <button class="tab-btn" onclick="showTab('telemetry')">📈 Live Practice Telemetry</button>
      <button class="tab-btn" onclick="showTab('modes')">🔢 15 Modes Full Matrix</button>
      <button class="tab-btn" onclick="showTab('leads')">⚡ 15 Leads Ranking</button>
    </div>

    <!-- TAB 1: 90S EXECUTION PROTOCOL & IF-THEN-ELSE RULEBOOK -->
    <div id="tab-protocol">
      <div class="section-title">
        <span>⏱️ Part A: 90-Second Team Preview Sequential Checklist</span>
      </div>
      <div class="protocol-banner">
        <div class="proto-step">
          <div class="step-time">Step 1 • 00s – 15s</div>
          <h3>1. Scan Speed & Field Setter</h3>
          <p>Identify opponent's speed/weather engine: Tailwind (Whimsicott), Rain (Pelipper/Archaludon), Sun (Venusaur/Charizard), Trick Room/Psyspam (Indeedee-F/Farigiraf), or Balance (Incineroar/Rillaboom).</p>
        </div>
        <div class="proto-step">
          <div class="step-time">Step 2 • 15s – 40s</div>
          <h3>2. Lock Bring-4 Mode</h3>
          <p>Match the IF condition below to lock your 4-mon mini-core. Immediately bench the 2 members that give the opponent free tempo or weather advantage.</p>
        </div>
        <div class="proto-step">
          <div class="step-time">Step 3 • 40s – 65s</div>
          <h3>3. Lock Lead Pair & Reserve</h3>
          <p>Select your Slot 1 & Slot 2 leads to contest Turn 1 field state. Keep your win-condition cleaner (Kingambit / Milotic) safe in the backline.</p>
        </div>
        <div class="proto-step">
          <div class="step-time">Step 4 • 65s – 90s</div>
          <h3>4. Pre-Commit Turn 1 Moves</h3>
          <p>Verify both Turn 1 move selections from the Command Matrix before the timer expires, including your Branch B reaction if they switch.</p>
        </div>
      </div>

      <div class="section-title">
        <span>🧭 Part B: If-Then-Else Decision-Tree Rulebook (Strictly Move-Grounded)</span>
      </div>
      <div class="rulebook-grid">
"""

    for idx, plan in enumerate(plans, start=1):
        arch = plan.archetype
        tier_class = "tier-s" if "S" in arch.tier else ("tier-a" if "A" in arch.tier else "tier-b")
        p1 = plan.recommended_lead.pokemon_1.species
        p2 = plan.recommended_lead.pokemon_2.species
        p1_b64 = member_sprites.get(p1, "")
        p2_b64 = member_sprites.get(p2, "")

        # Empirical record for this recommended lead
        lkey = frozenset({p1.lower(), p2.lower()})
        emp = telemetry.lead_stats.get(lkey)
        emp_html = f'<span class="emp-badge">Live Record: {emp["wins"]}W / {emp["played"]}G</span>' if emp else ""

        opp_icons = '<div class="pair-display">'
        for s in arch.core_species[:4]:
            s_b64 = opponent_sprites.get(s, "")
            opp_icons += f'<img src="{s_b64}" title="{s}" alt="{s}">'
        opp_icons += "</div>"

        back_html = '<div class="pair-display">'
        for bm in plan.backline:
            b_b64 = member_sprites.get(bm.species, "")
            back_html += f'<img src="{b_b64}" title="{bm.species}" alt="{bm.species}">'
        back_html += f'<div class="pair-names">{" + ".join(bm.species for bm in plan.backline)}</div></div>'

        cmd_items_html = ""
        for mon_name, cmd_desc in plan.step_4_turn_1_matrix.items():
            cmd_items_html += f'<div class="cmd-line">• <strong>{mon_name}</strong> ➔ <code>{cmd_desc}</code></div>'

        risk_html = "".join(f'<span class="risk-tag">⚠️ {r}</span>' for r in plan.risk_factors[:2])

        html += f"""
        <div class="rule-card">
          <div class="rule-header">
            <div>
              <span class="if-clause">RULE #{idx}: {plan.if_condition}</span>
              <span style="margin-left:10px;font-weight:800;font-size:15px;">{arch.name}</span>
            </div>
            <div style="display:flex;gap:8px;align-items:center;">
              {emp_html}
              <span class="arch-badge {tier_class}">{arch.tier} • {arch.tournament_frequency_pct}% Regional Usage</span>
            </div>
          </div>

          <div class="rule-steps">
            <div class="step-box">
              <div class="box-label">Step 1: Threat Scan</div>
              {opp_icons}
              <div style="font-size:11px;color:var(--text-muted);">{plan.step_1_threat_scan}</div>
            </div>

            <div class="step-box">
              <div class="box-label">Step 2 & 3: THEN Lead Pair</div>
              <div class="pair-display">
                <img src="{p1_b64}" alt="{p1}" title="{p1}">
                <img src="{p2_b64}" alt="{p2}" title="{p2}">
                <div class="pair-names">{p1}<br>+ {p2}</div>
              </div>
              <div style="font-size:11px;color:var(--text-muted);">{plan.recommended_mode.name}</div>
            </div>

            <div class="step-box">
              <div class="box-label">Step 3: Reserve Backline</div>
              {back_html}
              <div style="font-size:11px;color:var(--text-muted);">Cleaners & defensive pivots</div>
            </div>

            <div class="cmd-box">
              <div class="box-label" style="color:var(--emerald);">Step 4: Turn 1 Verified Move Matrix</div>
              {cmd_items_html}
              <div class="plan-b"><strong>Branch B (Switch/Protect):</strong> {plan.turn_1_plan_b}</div>
              <div class="win-con">🎯 Win-Con: {plan.win_condition}</div>
              <div>{risk_html}</div>
            </div>
          </div>
        </div>
"""

    html += """
      </div>
    </div>

    <!-- TAB 2: LIVE PRACTICE TELEMETRY -->
    <div id="tab-telemetry" style="display:none;">
      <div class="section-title">
        <span>📈 Live Practice Telemetry Tracker (Auto-Synced from battles_telemetry.csv)</span>
      </div>
      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th>Match ID</th>
              <th>Opponent</th>
              <th>Our Turn 1 Lead</th>
              <th>Opponent Turn 1 Lead</th>
              <th>Turn 1 Moves Executed</th>
              <th>Result</th>
              <th>Coach Post-Mortem Notes</th>
            </tr>
          </thead>
          <tbody>
"""

    if telemetry.recent_matches:
        for m_rec in reversed(telemetry.recent_matches):
            res_badge = (
                '<span class="emp-badge">WIN</span>'
                if m_rec.won
                else f'<span class="arch-badge tier-s">LOSS ({m_rec.winner})</span>'
            )
            notes_str = "<br>".join(m_rec.comments) if m_rec.comments else '<span style="color:var(--text-muted);">No comments logged yet</span>'
            html += f"""
            <tr>
              <td><code>{m_rec.match_id}</code></td>
              <td><strong>{m_rec.trainer_2}</strong></td>
              <td><strong>{m_rec.trainer_1_lead[0]} + {m_rec.trainer_1_lead[1]}</strong></td>
              <td>{m_rec.trainer_2_lead[0]} + {m_rec.trainer_2_lead[1]}</td>
              <td><code>{m_rec.turn_1_moves}</code></td>
              <td>{res_badge} ({m_rec.total_turns}T)</td>
              <td>{notes_str}</td>
            </tr>
"""
    else:
        html += """
            <tr>
              <td colspan="7" style="text-align:center;color:var(--text-muted);padding:24px;">
                No practice matches recorded yet in <code>data/telemetry/battles_telemetry.csv</code>.
                Run <code>scripts/dump_battle_telemetry.py</code> or invoke the <code>battle-telemetry-feedback</code> skill to auto-populate!
              </td>
            </tr>
"""

    html += """
          </tbody>
        </table>
      </div>
    </div>

    <!-- TAB 3: 15 MODES MATRIX -->
    <div id="tab-modes" style="display:none;">
      <div class="section-title">
        <span>🔢 All 15 4-Mon Mode Combinations (Combinatorics C(6,4))</span>
      </div>
      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>4-Mon Mode Members</th>
              <th>SE Coverage</th>
              <th>Shared Weaknesses</th>
              <th>Verified Speed Control</th>
              <th>Verified Disruption Tools</th>
              <th>Live Record</th>
              <th>Score</th>
            </tr>
          </thead>
          <tbody>
"""

    for me in modes:
        mode_sprites = '<div class="table-sprites">'
        for m in me.mode.members:
            s_b64 = member_sprites.get(m.species, "")
            mode_sprites += f'<img src="{s_b64}" title="{m.species}" alt="{m.species}">'
        mode_sprites += "</div>"

        cov_str = f"{me.coverage_count}/18 ({round(me.coverage_score*100)}%)"
        weak_str = ", ".join(f"{t} ({c})" for t, c in me.shared_weaknesses) if me.shared_weaknesses else '<span style="color:var(--emerald);">Balanced</span>'
        speed_str = ", ".join(me.speed_control_tools) if me.speed_control_tools else "None"
        disr_str = ", ".join(me.disruption_tools) if me.disruption_tools else "None"
        mkey = frozenset(m.species.lower() for m in me.mode.members)
        m_emp = telemetry.mode_stats.get(mkey)
        m_emp_str = f'<span class="emp-badge">{m_emp["wins"]}W / {m_emp["played"]}G</span>' if m_emp else "—"

        html += f"""
            <tr>
              <td><strong>#{me.mode.mode_id}</strong></td>
              <td>{mode_sprites} <div style="font-size:11px;font-weight:700;margin-top:2px;">{me.mode.name}</div></td>
              <td><code>{cov_str}</code></td>
              <td>{weak_str}</td>
              <td>{speed_str}</td>
              <td>{disr_str}</td>
              <td>{m_emp_str}</td>
              <td><span class="score-badge">{me.composite_score}</span></td>
            </tr>
"""

    html += """
          </tbody>
        </table>
      </div>
    </div>

    <!-- TAB 4: 15 LEADS RANKING -->
    <div id="tab-leads" style="display:none;">
      <div class="section-title">
        <span>⚡ All 15 Lead Combinations Ranked by Turn 1 Field Initiative (Zero-Hallucination Verified)</span>
      </div>
      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th>Rank</th>
              <th>Lead Pair</th>
              <th>Speed Tiers</th>
              <th>Initiative Score</th>
              <th>Verified Tactical Strengths & Tools</th>
              <th>Shared Weaknesses</th>
              <th>Live Record</th>
            </tr>
          </thead>
          <tbody>
"""

    for idx, le in enumerate(leads, start=1):
        p1 = le.lead.pokemon_1.species
        p2 = le.lead.pokemon_2.species
        p1_b64 = member_sprites.get(p1, "")
        p2_b64 = member_sprites.get(p2, "")
        pair_sprites = f'<div class="table-sprites"><img src="{p1_b64}" title="{p1}" alt="{p1}"><img src="{p2_b64}" title="{p2}" alt="{p2}"> <strong>{p1} + {p2}</strong></div>'
        spe_str = f"{le.combined_speed_tiers[0]} / {le.combined_speed_tiers[1]}"
        vuln_str = ", ".join(le.shared_weaknesses) if le.shared_weaknesses else '<span style="color:var(--emerald);">None</span>'
        lkey = frozenset({p1.lower(), p2.lower()})
        l_emp = telemetry.lead_stats.get(lkey)
        l_emp_str = f'<span class="emp-badge">{l_emp["wins"]}W / {l_emp["played"]}G</span>' if l_emp else "—"

        html += f"""
            <tr>
              <td><strong>#{idx}</strong></td>
              <td>{pair_sprites}</td>
              <td><code>{spe_str}</code></td>
              <td><span class="score-badge">{le.initiative_score}</span></td>
              <td>{le.tactical_summary}</td>
              <td>{vuln_str}</td>
              <td>{l_emp_str}</td>
            </tr>
"""

    html += """
          </tbody>
        </table>
      </div>
    </div>

    <footer>
      Coach Porygon VGC • Powered by In-Memory DuckDB & Deterministic Slug Registry • Regulation M-C
    </footer>
  </div>

  <script>
    function showTab(tabName) {
      const tabs = ['protocol', 'telemetry', 'modes', 'leads'];
      tabs.forEach((t, idx) => {
        document.getElementById('tab-' + t).style.display = t === tabName ? 'block' : 'none';
        document.querySelectorAll('.tab-btn')[idx].className = t === tabName ? 'tab-btn active' : 'tab-btn';
      });
    }
  </script>
</body>
</html>
"""
    return html


def refresh_playbook(
    paste_path: Path,
    out_html_path: Path,
    out_md_path: Path,
    telemetry_path: Optional[Path] = None,
) -> None:
    """Executes full team analysis, merges live telemetry, and writes HTML and Markdown reports."""
    paste_text = paste_path.read_text(encoding="utf-8")
    team_name = paste_path.stem

    analyzer = TeamModeAnalyzer()
    members, modes, leads = analyzer.analyze_team(paste_text)
    matcher = TournamentArchetypeMatcher()
    plans = matcher.generate_all_plans(modes, leads)

    if telemetry_path is None:
        default_tel = ROOT_DIR / "data" / "telemetry" / "battles_telemetry.csv"
        if default_tel.exists():
            telemetry_path = default_tel

    telemetry = parse_telemetry_csv(telemetry_path)

    out_html_path.parent.mkdir(parents=True, exist_ok=True)
    html_content = generate_html_playbook(team_name, members, plans, modes, leads, telemetry)
    out_html_path.write_text(html_content, encoding="utf-8")

    out_md_path.parent.mkdir(parents=True, exist_ok=True)
    md_content = generate_mermaid_cheatsheet(team_name, plans, modes, leads, telemetry)
    out_md_path.write_text(md_content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Team Preview Execution Protocol, Rulebook & Live Telemetry Playbook.",
    )
    parser.add_argument(
        "--paste",
        type=str,
        default="data/teams/char_y_v3.txt",
        help="Path to 6-Pokémon Showdown team paste file (default: data/teams/char_y_v3.txt)",
    )
    parser.add_argument(
        "--telemetry",
        type=str,
        default="data/telemetry/battles_telemetry.csv",
        help="Path to battle telemetry CSV (default: data/telemetry/battles_telemetry.csv)",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="reports/char_y_v3_playbook.html",
        help="Path to output HTML visualizer (default: reports/char_y_v3_playbook.html)",
    )
    parser.add_argument(
        "--cheatsheet",
        type=str,
        default="reports/char_y_v3_cheatsheet.md",
        help="Path to output Markdown cheat-sheet (default: reports/char_y_v3_cheatsheet.md)",
    )

    args = parser.parse_args()
    paste_path = Path(args.paste)
    if not paste_path.exists():
        print(f"Error: Paste file '{paste_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    telemetry_path = Path(args.telemetry) if args.telemetry else None
    out_html = Path(args.out)
    out_md = Path(args.cheatsheet)

    print(f"[Coach Porygon] Generating Playbook & 90s Execution Protocol for '{paste_path}'...")
    refresh_playbook(paste_path, out_html, out_md, telemetry_path)
    print(f"[Coach Porygon] Updated HTML Playbook: '{out_html}'")
    print(f"[Coach Porygon] Updated Markdown Rulebook: '{out_md}'")


if __name__ == "__main__":
    main()
