# -*- coding: utf-8 -*-
"""Zero-AI Regulation M-C Speed Tiers Payload Builder.

Parses any 6-Pokémon Regulation M-C Showdown paste (66-SP or EV-less OTS),
resolves Base & Mega Evolution forms dynamically via DuckDB (including Champions
Z-Megas), computes exact Level 50 Champions speeds (mandatory 31 IVs), and
auto-detects team-specific speed modifiers (`Chlorophyll`, `Swift Swim`,
`Sand Rush`, `Slush Rush`, `Surge Surfer`, `Unburden`, `Choice Scarf`) with
zero hardcoded team names or species assumptions.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Dict, List, Optional, Tuple

from engine.parser.models import ParsedPokemon
from engine.parser.showdown_parser import parse_showdown_paste
from engine.prep_tools.meta_snapshot import (
    SPEED_DOUBLER_ABILITIES,
    calc_champions_stat,
    get_nature_multiplier,
    get_top_n_meta_snapshot,
    load_sprites_dict,
    query_pokedex_entry,
    resolve_mega_form_for_item,
)

# High-contrast team accent palette for up to 6 Pokémon reference lines
TEAM_COLOR_PALETTE: Tuple[str, ...] = (
    "#facc15",  # Amber Gold
    "#38bdf8",  # Sky Cyan
    "#f97316",  # Solar Orange
    "#4ade80",  # Emerald Green
    "#a78bfa",  # Violet
    "#2dd4bf",  # Teal
)

# Map each speed-doubling ability to its canonical toggle ID and display cue
TEAM_MOD_CATALOG: Dict[str, Dict[str, str]] = {
    "Chlorophyll": {"key": "sun", "icon": "☀️", "en": "Sun", "es": "Sol", "style": "on-sun"},
    "Swift Swim": {"key": "rain", "icon": "🌧️", "en": "Rain", "es": "Lluvia", "style": "on"},
    "Sand Rush": {"key": "sand", "icon": "🏜️", "en": "Sand", "es": "Arena", "style": "on-gold"},
    "Slush Rush": {"key": "snow", "icon": "❄️", "en": "Snow", "es": "Nieve", "style": "on"},
    "Surge Surfer": {"key": "electric", "icon": "⚡", "en": "Elec Terrain", "es": "Campo Eléc.", "style": "on-gold"},
    "Unburden": {"key": "unburden", "icon": "🪶", "en": "Unburden", "es": "Liviano", "style": "on-purple"},
}


@dataclass(frozen=True)
class SpeedTiersPayload:
    """Structured data payload consumed by `html_renderer.render_speed_tiers_html`."""

    team_name: str
    total_teams: int
    top_n: int
    data: Dict[str, Any]
    sprites: Dict[str, str]


def _extract_unique_team(paste_text: str) -> List[ParsedPokemon]:
    """Parse a Showdown paste and return unique Pokémon entries in roster order."""
    parsed = parse_showdown_paste(paste_text)
    unique: List[ParsedPokemon] = []
    seen: set[int] = set()
    for mon in parsed.values():
        if id(mon) not in seen:
            seen.add(id(mon))
            unique.append(mon)
    if not unique:
        raise ValueError("Showdown paste did not contain any valid Pokémon sets.")
    return unique[:6]


def _format_sp_line(mon: ParsedPokemon) -> str:
    """Format a Pokémon's 66-SP allocation string cleanly."""
    parts: List[str] = []
    for label, val in (
        ("HP", mon.spread.hp),
        ("Atk", mon.spread.atk),
        ("Def", mon.spread.def_),
        ("SpA", mon.spread.spa),
        ("SpD", mon.spread.spd),
        ("Spe", mon.spread.spe),
    ):
        if int(val) > 0:
            parts.append(f"{int(val)} {label}")
    return " / ".join(parts) if parts else "0 SP (Uninvested)"


def _short_display_label(mon: ParsedPokemon, mega_name: Optional[str]) -> str:
    """Create a concise card label respecting nicknames and Mega suffixes."""
    sp_label = mega_name or mon.species
    if mega_name and "-Mega-" in mega_name:
        parts = mega_name.split("-Mega-")
        sp_short = f"{parts[0]}-{parts[1]}"
    elif mega_name and mega_name.endswith("-Mega"):
        sp_short = f"M-{mega_name[:-5]}"
    else:
        sp_short = sp_label
    if mon.nickname and mon.nickname.strip().lower() != mon.species.strip().lower():
        return f"{mon.nickname.strip()} ({sp_short})"
    return sp_short


def build_speed_tiers_payload(
    paste_text: str,
    team_name: str = "My Reg M-C Team",
    top_n: int = 50,
) -> SpeedTiersPayload:
    """Build the complete Speed Tiers data & Base64 sprite payload for any Reg M-C team."""
    team_mons = _extract_unique_team(paste_text)
    snapshot = get_top_n_meta_snapshot(top_n=max(top_n, 50))
    entries = snapshot.entries[: max(1, min(int(top_n), len(snapshot.entries)))]

    trainer_1_team: List[Dict[str, Any]] = []
    sprite_keys_needed: List[str] = []
    detected_mod_holders: Dict[str, List[str]] = {}

    for idx, mon in enumerate(team_mons):
        base_dex = query_pokedex_entry(mon.species)
        if base_dex is None:
            raise ValueError(f"Unknown Regulation M-C species in DuckDB pokedex: '{mon.species}'")
        mega_dex = resolve_mega_form_for_item(base_dex["name"], mon.item)

        nature = (mon.nature or "Serious").replace("Naïve", "Naive").strip()
        spe_sp = max(0, min(32, int(mon.spread.spe)))
        spe_mult = get_nature_multiplier(nature, "spe")
        has_scarf = (mon.item or "").strip().lower() == "choice scarf"

        base_spe_raw = calc_champions_stat(base_dex["baseStats"]["spe"], spe_sp, spe_mult)
        base_spe_eff = int(math.floor(base_spe_raw * 1.5)) if has_scarf else base_spe_raw
        base_ab = mon.ability or (base_dex["abilities"][0] if base_dex["abilities"] else "None")
        base_mod = TEAM_MOD_CATALOG[base_ab]["key"] if base_ab in TEAM_MOD_CATALOG else None

        mega_payload: Optional[Dict[str, Any]] = None
        if mega_dex is not None:
            mega_spe_raw = calc_champions_stat(mega_dex["baseStats"]["spe"], spe_sp, spe_mult)
            mega_ab = mega_dex["abilities"][0] if mega_dex["abilities"] else base_ab
            mega_mod = TEAM_MOD_CATALOG[mega_ab]["key"] if mega_ab in TEAM_MOD_CATALOG else None
            mega_payload = {
                "species": mega_dex["name"],
                "ability": mega_ab,
                "baseSpe": int(mega_dex["baseStats"]["spe"]),
                "speed": mega_spe_raw,
                "rawSpeed": mega_spe_raw,
                "speedModKey": mega_mod,
                "spriteKey": mega_dex["name"],
            }
            sprite_keys_needed.append(mega_dex["name"])

        sprite_keys_needed.append(base_dex["name"])

        label = _short_display_label(mon, mega_dex["name"] if mega_dex else None)
        short_name = label.split(" ")[0]
        for ab_cand in (base_ab, mega_payload["ability"] if mega_payload else None):
            if ab_cand and ab_cand in TEAM_MOD_CATALOG:
                mod_key = TEAM_MOD_CATALOG[ab_cand]["key"]
                detected_mod_holders.setdefault(mod_key, [])
                if short_name not in detected_mod_holders[mod_key]:
                    detected_mod_holders[mod_key].append(short_name)

        mon_id = "".join(ch for ch in (mega_dex["name"] if mega_dex else base_dex["name"]).lower() if ch.isalnum())
        mon_id = f"{mon_id}_{idx}"

        trainer_1_team.append(
            {
                "id": mon_id,
                "species": mega_dex["name"] if mega_dex else base_dex["name"],
                "baseSpecies": base_dex["name"],
                "label": label,
                "item": mon.item or "None",
                "nature": nature,
                "speSp": spe_sp,
                "hasScarf": has_scarf,
                "evLine": _format_sp_line(mon),
                "moves": list(mon.moves[:4]),
                "color": TEAM_COLOR_PALETTE[idx % len(TEAM_COLOR_PALETTE)],
                "hasMega": mega_payload is not None,
                "defaultMega": mega_payload is not None,
                "base": {
                    "species": base_dex["name"],
                    "ability": base_ab,
                    "baseSpe": int(base_dex["baseStats"]["spe"]),
                    "speed": base_spe_eff,
                    "rawSpeed": base_spe_raw,
                    "speedModKey": base_mod,
                    "spriteKey": base_dex["name"],
                },
                "mega": mega_payload,
            }
        )

    # Dynamic team speed modifier buttons — only show buttons relevant to this team!
    team_mod_buttons: List[Dict[str, Any]] = []
    for ab_name in SPEED_DOUBLER_ABILITIES:
        meta_cfg = TEAM_MOD_CATALOG[ab_name]
        holders = detected_mod_holders.get(meta_cfg["key"])
        if holders:
            team_mod_buttons.append(
                {
                    "key": meta_cfg["key"],
                    "ability": ab_name,
                    "icon": meta_cfg["icon"],
                    "labelEn": f"{meta_cfg['en']} ({', '.join(holders)} 2×)",
                    "labelEs": f"{meta_cfg['es']} ({', '.join(holders)} 2×)",
                    "style": meta_cfg["style"],
                    "holders": holders,
                }
            )

    top_meta_rows: List[Dict[str, Any]] = []
    for entry in entries:
        sprite_keys_needed.append(entry.sprite_key)
        top_meta_rows.append(
            {
                "rank": entry.rank,
                "species": entry.species,
                "usagePct": entry.usage_pct,
                "count": entry.count,
                "top32Count": entry.top32_count,
                "baseSpe": entry.base_stats["spe"],
                "types": list(entry.types),
                "spriteKey": entry.sprite_key,
                "plusPct": entry.plus_spe_pct,
                "neuPct": entry.neu_spe_pct,
                "minusPct": entry.minus_spe_pct,
                "hasPlus": entry.has_plus_spe,
                "hasNeu": entry.has_neu_spe,
                "hasMinus": entry.has_minus_spe,
                "scarfPct": entry.scarf_pct,
                "hasScarf": entry.has_scarf,
                "doublerAbil": entry.doubler_ability,
                "doublerPct": entry.doubler_pct,
                "topNatures": list(entry.top_natures),
                "speeds": dict(entry.speeds),
            }
        )

    sprites = load_sprites_dict(sprite_keys_needed)
    payload_data: Dict[str, Any] = {
        "teamName": team_name,
        "totalTeams": snapshot.total_teams,
        "defaultTopN": int(top_n),
        "trainer1Team": trainer_1_team,
        "teamModButtons": team_mod_buttons,
        "topMeta": top_meta_rows,
    }
    return SpeedTiersPayload(
        team_name=team_name,
        total_teams=snapshot.total_teams,
        top_n=int(top_n),
        data=payload_data,
        sprites=sprites,
    )
