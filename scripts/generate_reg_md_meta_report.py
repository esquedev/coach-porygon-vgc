#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the Community-Grade Standalone Offline Base64 HTML Regulation M-D Prep Dossier.

Cross-references:
  1. Live in-memory DuckDB telemetry across all ingested Regulation M-C tournaments
     (including LAIC 2027 — `LA002-m593TW3lr3apWb`) via `engine.db_registry.get_registry()`.
  2. Official Confirmed Regulation M-D additions (Dec 2, 2026 – Mar 3, 2027):
     Heatran, Mega Heatran (Water Compaction), Dondozo, Tatsugiri (Curly/Droopy/Stretchy),
     and Mega Tatsugiri (Premium Grade) — sprites from `assets/sprites/Reg_M-D/`.
  3. Full Expected / Rumored M-D wave (`@OSAKA_POKEMON` community graphic: Amoonguss,
     Mega Latios, Mega Latias, Terrakion, Porygon-Z, Flamigo, Cobalion, Virizion,
     Alolan Marowak, Crobat, Dachsbun, Grafaiai, etc.) — sprites strictly isolated in
     `assets/sprites/Reg_M-D_rumored/` and transparently badged.
  4. Exact Champions Level-50 (31 IVs, 66-SP) 16-roll damage benchmarks, Top-20 Reg M-C
     Meta Impact Matrix, Comparative Speed Tiers Ladder, 4 Counterplay Playbooks,
     Interactive 6-Mon M-D Readiness Checker, and 6 Copy-Pasteable LAIC 2027 Blueprints.

Lives exclusively in `scripts/` (outside `src/engine/` and `apps/`) to keep the
core Regulation M-C engine 100% pure and anti-hallucination compliant.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import html
import json
import math
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from engine.db_registry import get_registry  # noqa: E402
from engine.game_rules import TYPE_CHART  # noqa: E402

ASSETS_DIR = REPO_ROOT / "assets"
SPRITES_MC = ASSETS_DIR / "sprites" / "Reg_M-C"
SPRITES_MD = ASSETS_DIR / "sprites" / "Reg_M-D"
SPRITES_MD_RUMORED = ASSETS_DIR / "sprites" / "Reg_M-D_rumored"
MEGASTONES_DIR = ASSETS_DIR / "megastones"
COMMUNITY_DIR = ASSETS_DIR / "community"
SLUG_MAP_PATH = ASSETS_DIR / "slug_map.json"
DEFAULT_OUT = REPO_ROOT / "reports" / "reg_md_meta_scout.html"


def _b64_png(path: Path) -> str:
    """Read a PNG file into a `data:image/png;base64,...` URI (or empty string)."""
    if not path.is_file():
        return ""
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _l50_hp(base_hp: int, sp: int) -> int:
    """Exact Champions Lv.50 HP (31 IVs): `Base + SP + 75`."""
    return int(base_hp) + int(sp) + 75


def _l50_stat(base_val: int, sp: int, nature_mult: float = 1.0) -> int:
    """Exact Champions Lv.50 non-HP stat (31 IVs): `floor((Base + SP + 20) * NatureMult)`."""
    return int(math.floor((int(base_val) + int(sp) + 20) * float(nature_mult)))


def _l50_speed_range(base_spe: int) -> Tuple[int, int, int, int]:
    """Return Champions Lv.50 speeds: `(0-SP -Spe, 0-SP neutral, 32-SP neutral, 32-SP +Spe)`."""
    return (
        _l50_stat(base_spe, 0, 0.9),
        _l50_stat(base_spe, 0, 1.0),
        _l50_stat(base_spe, 32, 1.0),
        _l50_stat(base_spe, 32, 1.1),
    )


def _stage_mult(stage: int) -> float:
    s = max(-6, min(6, int(stage)))
    return (2.0 + s) / 2.0 if s >= 0 else 2.0 / (2.0 - s)


def _type_effectiveness(move_type: str, def_types: Sequence[str]) -> float:
    mult = 1.0
    row = TYPE_CHART.get(move_type, {})
    for dt in def_types:
        mult *= float(row.get(dt, 1.0))
    return mult


def _calc_champions_16_rolls(
    *,
    att_stats: Sequence[int],
    att_types: Sequence[str],
    att_sp: int,
    att_nature: float,
    att_stage: int,
    def_stats: Sequence[int],
    def_types: Sequence[str],
    def_hp_sp: int,
    def_def_sp: int,
    def_nature: float,
    def_stage: int,
    move_bp: int,
    move_type: str,
    category: str,
    is_spread: bool = False,
    weather_mult: float = 1.0,
    terrain_mult: float = 1.0,
    item_mult: float = 1.0,
    ability_mult: float = 1.0,
    adaptability: bool = False,
    sand_rock_spd: bool = False,
    snow_ice_def: bool = False,
) -> Dict[str, Any]:
    """Compute exact Gen 9 / Pokémon Champions Lv.50 16-roll discrete damage distribution."""
    is_phys = category.lower() == "physical"
    a_base = att_stats[1] if is_phys else att_stats[3]
    d_base = def_stats[2] if is_phys else def_stats[4]

    atk_raw = _l50_stat(a_base, att_sp, att_nature)
    def_raw = _l50_stat(d_base, def_def_sp, def_nature)
    def_hp = _l50_hp(def_stats[0], def_hp_sp)

    eff_a = max(1, int(math.floor(atk_raw * _stage_mult(att_stage))))
    eff_d = max(1, int(math.floor(def_raw * _stage_mult(def_stage))))
    if (not is_phys) and sand_rock_spd and ("Rock" in def_types):
        eff_d = int(math.floor(eff_d * 1.5))
    if is_phys and snow_ice_def and ("Ice" in def_types):
        eff_d = int(math.floor(eff_d * 1.5))

    base_dmg = int(math.floor((22 * int(move_bp) * eff_a) / eff_d / 50)) + 2
    type_eff = _type_effectiveness(move_type, def_types)
    if type_eff == 0.0:
        return {
            "rolls": [0] * 16,
            "min_dmg": 0,
            "max_dmg": 0,
            "min_pct": 0.0,
            "max_pct": 0.0,
            "def_hp": def_hp,
            "ohko_pct": 0.0,
            "twohko_pct": 0.0,
            "verdict_es": "Inmune (0%)",
            "verdict_en": "Immune (0%)",
            "tier_cls": "calc-immune",
        }

    is_stab = move_type in att_types
    stab_mult = (2.0 if adaptability else 1.5) if is_stab else 1.0

    rolls: List[int] = []
    for r in range(85, 101):
        d = float(base_dmg)
        if is_spread:
            d = math.floor(d * 0.75)
        if weather_mult != 1.0:
            d = math.floor(d * weather_mult)
        d = math.floor(d * (r / 100.0))
        if stab_mult != 1.0:
            d = math.floor(d * stab_mult)
        d = math.floor(d * type_eff)
        if terrain_mult != 1.0:
            d = math.floor(d * terrain_mult)
        if item_mult != 1.0:
            d = math.floor(d * item_mult)
        if ability_mult != 1.0:
            d = math.floor(d * ability_mult)
        rolls.append(max(1, int(d)))

    min_d, max_d = rolls[0], rolls[-1]
    min_p = round(100.0 * min_d / def_hp, 1)
    max_p = round(100.0 * max_d / def_hp, 1)
    ohko_cnt = sum(1 for x in rolls if x >= def_hp)
    ohko_pct = round(100.0 * ohko_cnt / 16.0, 1)

    twohko_cnt = sum(1 for x in rolls for y in rolls if (x + y) >= def_hp)
    twohko_pct = round(100.0 * twohko_cnt / 256.0, 1)

    if ohko_cnt == 16:
        v_es, v_en, cls = "OHKO garantizado (16/16)", "Guaranteed OHKO (16/16)", "calc-ohko"
    elif ohko_cnt > 0:
        v_es = f"OHKO {ohko_pct:.1f}% ({ohko_cnt}/16 rolls)"
        v_en = f"{ohko_pct:.1f}% OHKO ({ohko_cnt}/16 rolls)"
        cls = "calc-roll-ohko"
    elif twohko_cnt == 256:
        v_es, v_en, cls = "2HKO garantizado", "Guaranteed 2HKO", "calc-2hko"
    elif twohko_cnt > 0:
        v_es = f"2HKO {twohko_pct:.1f}%"
        v_en = f"{twohko_pct:.1f}% 2HKO"
        cls = "calc-roll-2hko"
    else:
        v_es, v_en, cls = "3HKO+ (sobrevive fácil)", "3HKO+ (safe survival)", "calc-safe"

    return {
        "rolls": rolls,
        "min_dmg": min_d,
        "max_dmg": max_d,
        "min_pct": min_p,
        "max_pct": max_p,
        "def_hp": def_hp,
        "ohko_pct": ohko_pct,
        "twohko_pct": twohko_pct,
        "verdict_es": v_es,
        "verdict_en": v_en,
        "tier_cls": cls,
    }


# =============================================================================
# 1. UNIFIED REGULATION M-D CATALOG (CONFIRMED M-D + FULL EXPECTED WAVE)
# =============================================================================

MD_CATALOG: List[Dict[str, Any]] = [
    # --- S TIER ---
    {
        "name": "Heatran-Mega",
        "display": "Mega Heatran",
        "status": "confirmed",
        "tier": "S",
        "sprite": ("md", "heatran-mega.png"),
        "stone": "heatranite.png",
        "types": ["Fire", "Steel"],
        "stats": [91, 120, 106, 175, 141, 67],
        "ability": "Water Compaction (Confirmed M-D)",
        "roles": ["mega", "offense", "tr"],
        "es": "Monstruo de 175 SpA / 141 SpD con 67 Spe (-10 vs base), dominante tanto en Trick Room como en Bulky Balance. Water Compaction (+2 Def al recibir Agua) castiga Flip Turn / Muddy Water / Politoed y abre combos de Body Press.",
        "en": "175 SpA / 141 SpD juggernaut dropping to 67 Spe (-10 vs base), dominant in Trick Room and Bulky Balance. Water Compaction (+2 Def on Water hit) punishes Rain/Flip Turn and unlocks Body Press snowballs.",
        "partners": ["Rillaboom", "Farigiraf", "Politoed", "Torkoal", "Amoonguss"],
        "checks": ["Garchomp-Mega-Z", "Swampert-Mega", "Sneasler", "Terrakion"],
    },
    {
        "name": "Heatran",
        "display": "Heatran",
        "status": "confirmed",
        "tier": "S",
        "sprite": ("md", "heatran.png"),
        "types": ["Fire", "Steel"],
        "stats": [91, 90, 106, 130, 106, 77],
        "ability": "Flash Fire / Flame Body",
        "roles": ["offense", "support"],
        "es": "Check directo al trío Rillaboom, Gholdengo y Charizard-Mega-Y + Floette-Mega. Sin gastar Mega mantiene Flash Fire (inmune a Heat Wave bajo Sol y al Mega Heatran rival) mientras presiona con Heat Wave / Earth Power / Substitute.",
        "en": "Direct answer to Rillaboom, Gholdengo, Charizard-Mega-Y, and Floette-Mega without spending the Mega slot. Flash Fire blanks opposing Sun & Mega Heatran Fire spread while threatening Earth Power and Heat Wave.",
        "partners": ["Rillaboom", "Latias-Mega", "Whimsicott", "Milotic", "Amoonguss"],
        "checks": ["Garchomp-Mega-Z", "Basculegion", "Sneasler", "Terrakion"],
    },
    {
        "name": "Dondozo",
        "display": "Dondozo",
        "status": "confirmed",
        "tier": "S",
        "sprite": ("md", "dondozo.png"),
        "types": ["Water"],
        "stats": [150, 100, 115, 65, 65, 35],
        "ability": "Unaware / Oblivious",
        "roles": ["offense", "tr"],
        "es": "Vuelve el eje DozoGiri (+2 omni-boost vía Commander) en un formato sin Terastallize. Unaware ignora boosts de Kingambit / Gholdengo / Sneasler; el counterplay obligatorio será Haze (Milotic/Crobat), Clear Smog (Amoonguss), Perish Trap (Mega Gengar) y Grassy Glide.",
        "en": "Brings back the +2 omni-boost Commander archetype in a Tera-free Champions format. Unaware blanks Kingambit/Gholdengo setup; mandatory counterplay revolves around Haze (Milotic/Crobat), Clear Smog (Amoonguss), Mega Gengar Perish Trap, and Grassy Glide.",
        "partners": ["Tatsugiri", "Tatsugiri-Mega", "Flamigo", "Incineroar", "Gengar-Mega"],
        "checks": ["Milotic", "Amoonguss", "Gengar-Mega", "Rillaboom", "Raichu-Mega-Y"],
    },
    {
        "name": "Tatsugiri-Mega",
        "display": "Mega Tatsugiri (Curly / Droopy / Stretchy)",
        "status": "confirmed",
        "tier": "S",
        "sprite": ("md", "tatsugiri-mega.png"),
        "alt_sprites": [("md", "tatsugiri-droopy-mega.png"), ("md", "tatsugiri-stretchy-mega.png")],
        "stone": "tatsugirinite.png",
        "types": ["Dragon", "Water"],
        "stats": [68, 65, 90, 135, 125, 92],
        "ability": "Premium Grade (+1 SpA on entry — Confirmed M-D)",
        "roles": ["mega", "offense"],
        "es": "Habilidad oficial Premium Grade (Tokujō): +1 SpA automático al entrar / Megaevolucionar sobre 135 SpA y 92 Spe. Genera el mindgame más duro en Team Preview: Commander en Dondozo O breaker especial independiente a +1 SpA con Draco Meteor / Muddy Water.",
        "en": "Confirmed ability Premium Grade: automatic +1 SpA on entry/Mega atop 135 SpA and 92 Spe. Creates brutal Team-Preview mindgames: Commander into Dondozo OR standalone +1 SpA special nuke with Draco Meteor / Muddy Water.",
        "partners": ["Dondozo", "Pelipper", "Politoed", "Incineroar", "Amoonguss"],
        "checks": ["Floette-Mega", "Sylveon", "Sneasler", "Latios-Mega"],
    },
    {
        "name": "Amoonguss",
        "display": "Amoonguss",
        "status": "rumored",
        "tier": "S",
        "sprite": ("rumored", "amoonguss.png"),
        "types": ["Grass", "Poison"],
        "stats": [114, 85, 70, 85, 80, 30],
        "ability": "Regenerator (Expected Wave)",
        "roles": ["support", "tr"],
        "es": "[OLA ESPERADA] Cambia TODO el formato: sin Safety Goggles (objeto ilegal en Champions), Spore + Rage Powder + Pollen Puff + Clear Smog detienen a DozoGiri, protegen a Mega Heatran/Latios y obligan a todo equipo a llevar Grass-type, Gholdengo o Taunt.",
        "en": "[EXPECTED WAVE] Format-defining anchor: with Safety Goggles illegal in Champions, Spore + Rage Powder + Pollen Puff + Clear Smog check DozoGiri, shield Mega Heatran/Latios, and force Grass-types, Gholdengo, or fast Taunt on every roster.",
        "partners": ["Incineroar", "Heatran-Mega", "Farigiraf", "Kingambit", "Latias-Mega"],
        "checks": ["Charizard-Mega-Y", "Heatran-Mega", "Gholdengo", "Salamence-Mega"],
    },
    {
        "name": "Regieleki",
        "display": "Regieleki",
        "status": "rumored",
        "tier": "S",
        "sprite": ("rumored", "regieleki.png"),
        "types": ["Electric"],
        "stats": [80, 100, 50, 100, 50, 200],
        "ability": "Transistor (×1.3 Electric — Expected Wave)",
        "roles": ["offense", "support"],
        "es": "[OLA ESPERADA] 200 Spe base (252 con 32 SP Neutral / 277 +Spe): el Pokémon más rápido del formato sin Choice Scarf. Transistor (×1.3 en Gen 9/Champions) convierte Thunderbolt en presión de 46–54% incluso a través de +2 SpD Dondozo (y OHKO tras Haze/Clear Smog) y Electroweb en control de velocidad spread implacable. Sin Terastallize en Champions carece de Tera Ice para Ground-types, lo que eleva el valor de Garchomp-Mega-Z, Swampert-Mega y Lightning Rod.",
        "en": "[EXPECTED WAVE] 200 base Spe (252 at 32-SP Neutral / 277 +Spe): fastest unboosted Pokémon in the format. Transistor (1.3× in Gen 9/Champions) drives Thunderbolt to 46–54% even through +2 SpD Dondozo (clean OHKO post-Haze/Clear Smog) while Electroweb provides relentless spread speed control. Without Terastallization in Champions, Regieleki lacks Tera Ice for Ground-types, elevating Garchomp-Mega-Z, Swampert-Mega, and Lightning Rod checks.",
        "partners": ["Regidrago", "Heatran-Mega", "Primarina", "Incineroar", "Amoonguss", "Pelipper"],
        "checks": ["Garchomp-Mega-Z", "Swampert-Mega", "Marowak-Alola", "Rillaboom", "Raichu-Mega-Y"],
    },
    # --- A TIER ---
    {
        "name": "Regidrago",
        "display": "Regidrago",
        "status": "rumored",
        "tier": "A",
        "sprite": ("rumored", "regidrago.png"),
        "types": ["Dragon"],
        "stats": [200, 100, 50, 100, 50, 80],
        "ability": "Dragon's Maw (×1.5 Dragon — Expected Wave)",
        "roles": ["offense"],
        "es": "[OLA ESPERADA] 200 HP base + Dragon's Maw (×1.5 Dragón sin nerfeo) + Dragon Energy (150 BP spread al 100% HP). Con 32 SP +Spe (145) supera a Mega Tatsugiri Modest (144) y a todo Base 130 a -1 tras Electroweb (133). Acompañado de Amoonguss (Pollen Puff para restaurar 100% HP) y Mega Heatran (borra Hadas), castiga núcleos Balance; Earth Power cubre x4 a Mega Heatran.",
        "en": "[EXPECTED WAVE] 200 base HP + unnerfed Dragon's Maw (1.5× Dragon) + 150-BP spread Dragon Energy at full HP. Timid 32-SP (145 Spe) outpaces Modest Mega Tatsugiri (144) and every -1 Base-130 speedster after Electroweb (133). Paired with Amoonguss (Pollen Puff restoring 100% HP) and Mega Heatran (clearing Fairies), it demolishes neutral Balance cores while Earth Power hits Mega Heatran 4×.",
        "partners": ["Regieleki", "Heatran-Mega", "Amoonguss", "Whimsicott", "Incineroar", "Farigiraf"],
        "checks": ["Floette-Mega", "Primarina", "Sylveon", "Heatran-Mega", "Gholdengo"],
    },
    {
        "name": "Tatsugiri",
        "display": "Tatsugiri (Curly / Droopy / Stretchy)",
        "status": "confirmed",
        "tier": "A",
        "sprite": ("md", "tatsugiri.png"),
        "alt_sprites": [("md", "tatsugiri-droopy.png"), ("md", "tatsugiri-stretchy.png")],
        "types": ["Dragon", "Water"],
        "stats": [68, 50, 60, 120, 95, 82],
        "ability": "Commander / Storm Drain",
        "roles": ["support", "offense"],
        "es": "Habilitador obligatorio de Dondozo (Curly +Atk, Droopy +Def, Stretchy +Spe en Order Up). Con Focus Sash o Choice Scarf remata finales con Muddy Water, Icy Wind y Draco Meteor al caer Dondozo.",
        "en": "Mandatory Dondozo Commander partner (Curly +Atk, Droopy +Def, Stretchy +Spe Order Up). With Focus Sash or Choice Scarf, cleans endgames with Muddy Water, Icy Wind, and Draco Meteor once Dondozo drops.",
        "partners": ["Dondozo", "Flamigo", "Incineroar", "Sneasler", "Gholdengo"],
        "checks": ["Floette-Mega", "Rillaboom", "Salamence-Mega"],
    },
    {
        "name": "Latios-Mega",
        "display": "Mega Latios",
        "status": "rumored",
        "tier": "A",
        "sprite": ("rumored", "latios-mega.png"),
        "types": ["Dragon", "Psychic"],
        "stats": [80, 130, 100, 160, 120, 110],
        "ability": "Levitate (Expected Wave)",
        "roles": ["mega", "offense"],
        "es": "[OLA ESPERADA] 160 SpA + 110 Spe + Levitate: supera el bloque clave de 100–108 Spe (Charizard-Y, Staraptor-Mega, Terrakion) y pulveriza a Sneasler, Amoonguss y Archaludon con Luster Purge (50% -1 SpD), Draco Meteor y Tailwind.",
        "en": "[EXPECTED WAVE] 160 SpA / 110 Spe + Levitate outpaces the crowded 100–108 Spe tier (Charizard-Y, Staraptor-Mega, Terrakion) and shreds Sneasler, Amoonguss, and Archaludon with Luster Purge (50% -1 SpD), Draco Meteor, and Tailwind.",
        "partners": ["Incineroar", "Rillaboom", "Kingambit", "Heatran", "Amoonguss"],
        "checks": ["Floette-Mega", "Kingambit", "Sneasler", "Incineroar"],
    },
    {
        "name": "Latias-Mega",
        "display": "Mega Latias",
        "status": "rumored",
        "tier": "A",
        "sprite": ("rumored", "latias-mega.png"),
        "types": ["Dragon", "Psychic"],
        "stats": [80, 100, 120, 140, 150, 110],
        "ability": "Levitate (Expected Wave)",
        "roles": ["mega", "support", "offense"],
        "es": "[OLA ESPERADA] Bulk élite (80/120/150) + Levitate (inmune a Earth Power / Earthquake de Garchomp-Mega-Z y Heatran) + 110 Spe. Win-condition de Calm Mind + Recover + Mist Ball o soporte Tailwind en cores Balance con Incineroar + Amoonguss.",
        "en": "[EXPECTED WAVE] Elite 80/120/150 bulk + Levitate (immune to Garchomp-Mega-Z & Heatran Ground moves) at 110 Spe. Calm Mind + Recover + Mist Ball win-con or Tailwind anchor inside Incineroar + Amoonguss Balance.",
        "partners": ["Incineroar", "Rillaboom", "Heatran", "Kingambit", "Amoonguss"],
        "checks": ["Kingambit", "Floette-Mega", "Incineroar", "Gholdengo"],
    },
    {
        "name": "Flamigo",
        "display": "Flamigo",
        "status": "rumored",
        "tier": "A",
        "sprite": ("rumored", "flamigo.png"),
        "types": ["Flying", "Fighting"],
        "stats": [82, 115, 74, 75, 64, 90],
        "ability": "Costar / Scrappy",
        "roles": ["offense", "support"],
        "es": "[OLA ESPERADA] El socio icónico de DozoGiri: entra tras caer Tatsugiri y copia el +2 en TODOS los stats de Dondozo con Costar, aportando Feint (rompe Protect/Wide Guard), Wide Guard y Close Combat que borra a Kingambit / Incineroar / Heatran.",
        "en": "[EXPECTED WAVE] Iconic DozoGiri endgame closer: Costar copies Dondozo's +2 omni-boost on switch-in, pairing Feint (breaks Protect/Wide Guard) and Wide Guard with Close Combat to erase Kingambit, Incineroar, and Heatran.",
        "partners": ["Dondozo", "Tatsugiri", "Incineroar"],
        "checks": ["Raichu-Mega-Y", "Floette-Mega", "Latios-Mega"],
    },
    {
        "name": "Terrakion",
        "display": "Terrakion",
        "status": "rumored",
        "tier": "A",
        "sprite": ("rumored", "terrakion.png"),
        "types": ["Rock", "Fighting"],
        "stats": [91, 129, 90, 72, 90, 108],
        "ability": "Justified",
        "roles": ["offense"],
        "es": "[OLA ESPERADA] 108 Spe + 129 Atk con Rock Slide / Close Combat. Reactiva el combo Beat Up + Justified (+4 Atk Turno 1!) con Whimsicott y destruye a Incineroar, Charizard-Y y Mega Heatran (aunque teme a Amoonguss Rage Powder y Rillaboom Grassy Glide).",
        "en": "[EXPECTED WAVE] 108 Spe / 129 Atk Rock Slide + Close Combat menace. Re-enables Turn-1 +4 Atk Beat Up + Justified with Whimsicott while crushing Incineroar, Charizard-Y, and Mega Heatran (checked by Amoonguss Rage Powder & Grassy Glide).",
        "partners": ["Whimsicott", "Incineroar", "Tyranitar-Mega", "Farigiraf"],
        "checks": ["Rillaboom", "Amoonguss", "Sneasler", "Gholdengo", "Latios-Mega"],
    },
    {
        "name": "Porygon-Z",
        "display": "Porygon-Z",
        "status": "rumored",
        "tier": "A",
        "sprite": ("rumored", "porygon-z.png"),
        "types": ["Normal"],
        "stats": [85, 80, 70, 135, 75, 90],
        "ability": "Adaptability / Download",
        "roles": ["offense"],
        "es": "[OLA ESPERADA] Nuestra mascota de Coach Porygon: 135 SpA + Adaptability (STAB ×2.0 en Hyper Beam / Tri Attack) o Download + Ice Beam / Shadow Ball / Thunderbolt. Junto a Indeedee-F (Follow Me) o Whimsicott (Tailwind) borra objetivos neutrales en 1 golpe.",
        "en": "[EXPECTED WAVE] Coach Porygon's namesake nuke: 135 SpA + Adaptability (2.0× STAB Hyper Beam / Tri Attack) or Download Ice Beam / Shadow Ball coverage. Terrifying beside Indeedee-F Follow Me or Whimsicott Tailwind.",
        "partners": ["Indeedee-F", "Whimsicott", "Incineroar", "Amoonguss"],
        "checks": ["Sneasler", "Gholdengo", "Kingambit", "Heatran-Mega"],
    },
    {
        "name": "Latias",
        "display": "Latias",
        "status": "rumored",
        "tier": "A",
        "sprite": ("rumored", "latias.png"),
        "types": ["Dragon", "Psychic"],
        "stats": [80, 80, 90, 110, 130, 110],
        "ability": "Levitate",
        "roles": ["support"],
        "es": "[OLA ESPERADA] Soporte rápido de Tailwind / Helping Hand / Mist Ball / Ice Beam a 110 Spe sin gastar slot de Mega, inmune a Ground para acompañar a Mega Heatran, Archaludon o Gholdengo.",
        "en": "[EXPECTED WAVE] Fast 110-Spe non-Mega Tailwind / Helping Hand / Mist Ball / Ice Beam support with Ground immunity beside Mega Heatran, Archaludon, or Gholdengo.",
        "partners": ["Heatran-Mega", "Archaludon", "Gholdengo"],
        "checks": ["Kingambit", "Incineroar", "Floette-Mega"],
    },
    {
        "name": "Latios",
        "display": "Latios",
        "status": "rumored",
        "tier": "A",
        "sprite": ("rumored", "latios.png"),
        "types": ["Dragon", "Psychic"],
        "stats": [80, 90, 80, 130, 110, 110],
        "ability": "Levitate",
        "roles": ["offense"],
        "es": "[OLA ESPERADA] Breaker especial de 130 SpA / 110 Spe con Life Orb / Choice Specs + Tailwind + Luster Purge que presiona a Sneasler, Amoonguss y dragones sin ocupar Mega.",
        "en": "[EXPECTED WAVE] Fast 130 SpA / 110 Spe non-Mega special breaker with Life Orb / Tailwind + Luster Purge pressuring Sneasler, Amoonguss, and opposing Dragons.",
        "partners": ["Incineroar", "Rillaboom", "Heatran-Mega"],
        "checks": ["Kingambit", "Floette-Mega", "Gholdengo"],
    },
    # --- B TIER ---
    {
        "name": "Crobat",
        "display": "Crobat",
        "status": "rumored",
        "tier": "B",
        "sprite": ("rumored", "crobat.png"),
        "types": ["Poison", "Flying"],
        "stats": [85, 90, 80, 70, 80, 130],
        "ability": "Inner Focus",
        "roles": ["support"],
        "es": "[OLA ESPERADA] 130 Spe + Inner Focus (inmune a Fake Out e Intimidate!): Tailwind confiable, Haze anti-Dondozo, Taunt rápido anti-Amoonguss/Trick Room y Super Fang.",
        "en": "[EXPECTED WAVE] 130 Spe + Inner Focus (Fake Out & Intimidate immune!): reliable Tailwind, anti-Dondozo Haze, fast Taunt against Amoonguss/Trick Room, and Super Fang.",
        "partners": ["Heatran-Mega", "Garchomp-Mega-Z", "Kingambit"],
        "checks": ["Raichu-Mega-Y", "Gholdengo", "Archaludon"],
    },
    {
        "name": "Marowak-Alola",
        "display": "Alolan Marowak",
        "status": "rumored",
        "tier": "B",
        "sprite": ("rumored", "marowak-alola.png"),
        "types": ["Fire", "Ghost"],
        "stats": [60, 80, 110, 50, 80, 45],
        "ability": "Lightning Rod (Thick Club unconfirmed)",
        "roles": ["tr", "offense"],
        "es": "[OLA ESPERADA] 45 Spe + Lightning Rod: absorbe ataques Eléctricos de Raichu-Mega-Y protegiendo a Dondozo/Pelipper/Swampert-Mega. Su techo ofensivo en Trick Room depende de si Thick Club llega a Champions.",
        "en": "[EXPECTED WAVE] At 45 Spe with Lightning Rod, blanks Raichu-Mega-Y beside Dondozo or Rain cores. Offensive TR ceiling depends on Thick Club legality in Champions.",
        "partners": ["Farigiraf", "Indeedee-F", "Pelipper", "Dondozo"],
        "checks": ["Kingambit", "Incineroar", "Basculegion"],
    },
    {
        "name": "Cobalion",
        "display": "Cobalion",
        "status": "rumored",
        "tier": "B",
        "sprite": ("rumored", "cobalion.png"),
        "types": ["Steel", "Fighting"],
        "stats": [91, 90, 129, 90, 72, 108],
        "ability": "Justified",
        "roles": ["offense", "support"],
        "es": "[OLA ESPERADA] 108 Spe + 129 Def + Justified: check físico a Kingambit / Sneasler / Tyranitar con Sacred Sword (ignora +2 Def de Dondozo!), Coaching, Quick Guard y Body Press.",
        "en": "[EXPECTED WAVE] 108 Spe / 129 Def physical check to Kingambit, Sneasler, and Tyranitar with Sacred Sword (ignores Dondozo +2 Def!), Coaching, Quick Guard, and Body Press.",
        "partners": ["Whimsicott", "Rillaboom", "Milotic"],
        "checks": ["Charizard-Mega-Y", "Heatran-Mega", "Garchomp-Mega-Z"],
    },
    {
        "name": "Virizion",
        "display": "Virizion",
        "status": "rumored",
        "tier": "B",
        "sprite": ("rumored", "virizion.png"),
        "types": ["Grass", "Fighting"],
        "stats": [91, 90, 72, 90, 129, 108],
        "ability": "Justified",
        "roles": ["offense", "support"],
        "es": "[OLA ESPERADA] 108 Spe + 129 SpD + tipo Planta (inmune a Spore/Rage Powder de Amoonguss!): Sacred Sword atraviesa +2 Def de Dondozo mientras resiste Lluvia y Mega Tatsugiri.",
        "en": "[EXPECTED WAVE] 108 Spe / 129 SpD Grass-type (immune to Amoonguss Spore & Rage Powder!): Sacred Sword pierces +2 Def Dondozo while resisting Rain and Mega Tatsugiri.",
        "partners": ["Whimsicott", "Incineroar", "Heatran"],
        "checks": ["Salamence-Mega", "Staraptor-Mega", "Sneasler"],
    },
    {
        "name": "Dachsbun",
        "display": "Dachsbun",
        "status": "rumored",
        "tier": "B",
        "sprite": ("rumored", "dachsbun.png"),
        "types": ["Fairy"],
        "stats": [57, 80, 115, 50, 80, 95],
        "ability": "Well-Baked Body",
        "roles": ["support", "offense"],
        "es": "[OLA ESPERADA] Well-Baked Body convierte Lava Plume / Heat Wave de Mega Heatran y Charizard-Y en +2 Def gratis para Body Press + Snarl / Yawn / Helping Hand.",
        "en": "[EXPECTED WAVE] Well-Baked Body turns Mega Heatran Lava Plume & Charizard-Y Heat Wave into free +2 Def boosts for Body Press, Snarl, and Yawn.",
        "partners": ["Heatran", "Heatran-Mega", "Torkoal"],
        "checks": ["Gholdengo", "Sneasler", "Amoonguss"],
    },
    {
        "name": "Grafaiai",
        "display": "Grafaiai",
        "status": "rumored",
        "tier": "B",
        "sprite": ("rumored", "grafaiai.png"),
        "types": ["Poison", "Normal"],
        "stats": [63, 95, 65, 80, 72, 110],
        "ability": "Prankster / Unburden",
        "roles": ["support"],
        "es": "[OLA ESPERADA] Prankster Doodle (copia Unaware/Water Compaction), Parting Shot, Encore y Taunt prioritario anti-Amoonguss / Trick Room.",
        "en": "[EXPECTED WAVE] Prankster Doodle (ability-swap tech), Parting Shot, Encore, and priority Taunt against Amoonguss and Trick Room.",
        "partners": ["Slaking", "Dondozo", "Heatran-Mega"],
        "checks": ["Farigiraf", "Indeedee-F", "Gholdengo"],
    },
    # --- NICHE WATCHLIST ---
    {
        "name": "Cryogonal",
        "display": "Cryogonal",
        "status": "rumored",
        "tier": "Niche",
        "sprite": ("rumored", "cryogonal.png"),
        "types": ["Ice"],
        "stats": [80, 50, 50, 95, 135, 105],
        "ability": "Levitate",
        "roles": ["support"],
        "es": "[OLA ESPERADA] 105 Spe + 135 SpD + Levitate con Freeze-Dry (x4 a Swampert/Pelipper, x2 a Dondozo/Tatsugiri), Haze e Icy Wind.",
        "en": "[EXPECTED WAVE] 105 Spe / 135 SpD Levitate user with Freeze-Dry (4× Swampert/Pelipper, 2× Dondozo/Tatsugiri), Haze, and Icy Wind.",
        "partners": ["Ninetales-Alola", "Incineroar"],
        "checks": ["Sneasler", "Incineroar", "Heatran-Mega"],
    },
    {
        "name": "Carbink",
        "display": "Carbink",
        "status": "rumored",
        "tier": "Niche",
        "sprite": ("rumored", "carbink.png"),
        "types": ["Rock", "Fairy"],
        "stats": [50, 50, 150, 50, 150, 50],
        "ability": "Clear Body / Sturdy",
        "roles": ["support", "tr"],
        "es": "[OLA ESPERADA] Setter Trick Room ultra-tanque (150/150 defensas + Sturdy/Clear Body) con Body Press y Skill Swap.",
        "en": "[EXPECTED WAVE] Ultra-bulky Sturdy/Clear Body Trick Room setter (150/150 defenses) with Body Press and Skill Swap.",
        "partners": ["Heatran-Mega", "Torkoal", "Marowak-Alola"],
        "checks": ["Gholdengo", "Rillaboom", "Archaludon"],
    },
    {
        "name": "Throh",
        "display": "Throh",
        "status": "rumored",
        "tier": "Niche",
        "sprite": ("rumored", "throh.png"),
        "types": ["Fighting"],
        "stats": [120, 100, 85, 30, 85, 45],
        "ability": "Inner Focus / Guts",
        "roles": ["support", "tr"],
        "es": "[OLA ESPERADA] 45 Spe Inner Focus con Wide Guard, Helping Hand y Storm Throw (crítico garantizado que ignora +2 Def de Dondozo).",
        "en": "[EXPECTED WAVE] 45 Spe Inner Focus Wide Guard user with always-crit Storm Throw piercing Dondozo +2 Def boosts.",
        "partners": ["Farigiraf", "Heatran-Mega"],
        "checks": ["Floette-Mega", "Latios-Mega"],
    },
    {
        "name": "Marowak",
        "display": "Marowak",
        "status": "rumored",
        "tier": "Niche",
        "sprite": ("rumored", "marowak.png"),
        "types": ["Ground"],
        "stats": [60, 80, 110, 50, 80, 45],
        "ability": "Lightning Rod / Battle Armor",
        "roles": ["tr"],
        "es": "[OLA ESPERADA] 45 Spe Trick Room Lightning Rod; amenaza física Tierra a Mega Heatran si Thick Club vuelve.",
        "en": "[EXPECTED WAVE] 45 Spe Trick Room Lightning Rod Ground attacker; checks Mega Heatran if Thick Club returns.",
        "partners": ["Farigiraf", "Pelipper"],
        "checks": ["Rillaboom", "Amoonguss"],
    },
    {
        "name": "Grumpig",
        "display": "Grumpig",
        "status": "rumored",
        "tier": "Niche",
        "sprite": ("rumored", "grumpig.png"),
        "types": ["Psychic"],
        "stats": [80, 45, 65, 90, 110, 80],
        "ability": "Thick Fat / Own Tempo",
        "roles": ["support", "tr"],
        "es": "[OLA ESPERADA] Setter Trick Room / Simple Beam / Taunt con Thick Fat resistiendo Heat Wave de Mega Heatran y Charizard-Y.",
        "en": "[EXPECTED WAVE] Niche Thick Fat Trick Room / Simple Beam support resisting Mega Heatran and Charizard-Y Fire spread.",
        "partners": ["Heatran-Mega", "Incineroar"],
        "checks": ["Kingambit", "Gholdengo"],
    },
    {
        "name": "Sawk",
        "display": "Sawk",
        "status": "rumored",
        "tier": "Niche",
        "sprite": ("rumored", "sawk.png"),
        "types": ["Fighting"],
        "stats": [75, 125, 75, 30, 75, 85],
        "ability": "Inner Focus / Sturdy",
        "roles": ["offense"],
        "es": "[OLA ESPERADA] Breaker Sturdy / Inner Focus Close Combat con Coaching y Quick Guard.",
        "en": "[EXPECTED WAVE] Sturdy / Inner Focus Close Combat breaker with Coaching and Quick Guard.",
        "partners": ["Whimsicott", "Incineroar"],
        "checks": ["Floette-Mega", "Latios-Mega"],
    },
    {
        "name": "Zangoose",
        "display": "Zangoose",
        "status": "rumored",
        "tier": "Niche",
        "sprite": ("rumored", "zangoose.png"),
        "types": ["Normal"],
        "stats": [73, 115, 60, 60, 60, 90],
        "ability": "Immunity / Toxic Boost",
        "roles": ["offense"],
        "es": "[OLA ESPERADA] Sin Toxic Orb en Champions, rol de nicho con Quick Guard / Knock Off.",
        "en": "[EXPECTED WAVE] Without Toxic Orb in Champions, niche Quick Guard / Knock Off role.",
        "partners": ["Indeedee-F", "Whimsicott"],
        "checks": ["Sneasler", "Gholdengo"],
    },
    {
        "name": "Seviper",
        "display": "Seviper",
        "status": "rumored",
        "tier": "Niche",
        "sprite": ("rumored", "seviper.png"),
        "types": ["Poison"],
        "stats": [73, 100, 60, 100, 60, 65],
        "ability": "Infiltrator / Shed Skin",
        "roles": ["offense"],
        "es": "[OLA ESPERADA] Nicho Infiltrator con Haze, Glare y Acid Spray.",
        "en": "[EXPECTED WAVE] Niche Infiltrator pick with Haze, Glare, and Acid Spray.",
        "partners": ["Farigiraf", "Incineroar"],
        "checks": ["Garchomp-Mega-Z", "Gholdengo"],
    },
    {
        "name": "Kecleon",
        "display": "Kecleon",
        "status": "rumored",
        "tier": "Niche",
        "sprite": ("rumored", "kecleon.png"),
        "types": ["Normal"],
        "stats": [60, 90, 70, 60, 120, 40],
        "ability": "Protean",
        "roles": ["tr", "support"],
        "es": "[OLA ESPERADA] 40 Spe Trick Room Protean con Fake Out, Skill Swap y Shadow Sneak.",
        "en": "[EXPECTED WAVE] 40 Spe Trick Room Protean user with Fake Out, Skill Swap, and Shadow Sneak.",
        "partners": ["Farigiraf", "Torkoal"],
        "checks": ["Sneasler", "Incineroar"],
    },
    {
        "name": "Delibird",
        "display": "Delibird",
        "status": "rumored",
        "tier": "Niche",
        "sprite": ("rumored", "delibird.png"),
        "types": ["Ice", "Flying"],
        "stats": [45, 55, 45, 65, 45, 75],
        "ability": "Vital Spirit / Hustle",
        "roles": ["support"],
        "es": "[OLA ESPERADA] Utilidad de nicho Fake Out + Icy Wind + Tailwind + Vital Spirit (inmune a Spore).",
        "en": "[EXPECTED WAVE] Niche Fake Out + Icy Wind + Tailwind + Vital Spirit (Spore immunity).",
        "partners": ["Heatran-Mega"],
        "checks": ["Incineroar", "Raichu-Mega-Y"],
    },
]


# =============================================================================
# 2. EXACT CHAMPIONS LV.50 16-ROLL BENCHMARK SCENARIOS
# =============================================================================

DAMAGE_BENCHMARK_SPECS: List[Dict[str, Any]] = [
    # --- Group 1: Mega Heatran & Base Heatran ---
    {
        "group": "heatran",
        "status": "confirmed",
        "att": "Heatran-Mega",
        "att_kind": ("md", "heatran-mega.png"),
        "att_label": "32 SpA+ Mega Heatran",
        "move": "Heat Wave (Spread)",
        "bp": 95,
        "mtype": "Fire",
        "cat": "Special",
        "spread": True,
        "att_sp": 32,
        "att_nat": 1.1,
        "att_stg": 0,
        "def": "Rillaboom",
        "def_label": "32 HP / 12 SpD AV-less Rillaboom",
        "def_hp_sp": 32,
        "def_def_sp": 12,
        "def_nat": 1.0,
        "def_stg": 0,
        "ctx_es": "Sin Sol (neutral); bajo Sol es OHKO garantizado incluso vs Assault Vest.",
        "ctx_en": "No Sun (neutral); in Sun this becomes a clean OHKO even through Assault Vest.",
    },
    {
        "group": "heatran",
        "status": "confirmed",
        "att": "Heatran-Mega",
        "att_kind": ("md", "heatran-mega.png"),
        "att_label": "32 SpA+ Mega Heatran (Sun)",
        "move": "Heat Wave (Sun Spread)",
        "bp": 95,
        "mtype": "Fire",
        "cat": "Special",
        "spread": True,
        "weather": 1.5,
        "att_sp": 32,
        "att_nat": 1.1,
        "att_stg": 0,
        "def": "Gholdengo",
        "def_label": "20 HP / 12 SpD Gholdengo",
        "def_hp_sp": 20,
        "def_def_sp": 12,
        "def_nat": 1.0,
        "def_stg": 0,
        "ctx_es": "Bajo Sol de Torkoal/Charizard-Y borra a Gholdengo incluso en spread.",
        "ctx_en": "Under Torkoal/Charizard-Y Sun, erases bulky Gholdengo through spread reduction.",
    },
    {
        "group": "heatran",
        "status": "confirmed",
        "att": "Heatran-Mega",
        "att_kind": ("md", "heatran-mega.png"),
        "att_label": "32 SpA+ Mega Heatran",
        "move": "Earth Power",
        "bp": 90,
        "mtype": "Ground",
        "cat": "Special",
        "att_sp": 32,
        "att_nat": 1.1,
        "att_stg": 0,
        "def": "Incineroar",
        "def_label": "32 HP / 16 SpD+ Incineroar",
        "def_hp_sp": 32,
        "def_def_sp": 16,
        "def_nat": 1.1,
        "def_stg": 0,
        "ctx_es": "2HKO limpio; Incineroar necesita Parting Shot o Snarl para evitar perder la pelea.",
        "ctx_en": "Clean 2HKO; Incineroar must Parting Shot or Snarl to avoid losing the trade.",
    },
    {
        "group": "heatran",
        "status": "confirmed",
        "att": "Heatran-Mega",
        "att_kind": ("md", "heatran-mega.png"),
        "att_label": "32 SpA+ Mega Heatran",
        "move": "Flash Cannon",
        "bp": 80,
        "mtype": "Steel",
        "cat": "Special",
        "att_sp": 32,
        "att_nat": 1.1,
        "att_stg": 0,
        "def": "Floette-Mega",
        "def_label": "24 HP / 4 SpD Floette-Mega",
        "def_hp_sp": 24,
        "def_def_sp": 4,
        "def_nat": 1.0,
        "def_stg": 0,
        "ctx_es": "Floette-Mega tiene 128 SpD base; sobrevive 1 Flash Cannon si invierte en HP.",
        "ctx_en": "Floette-Mega's 128 base SpD survives 1 Flash Cannon with HP investment — watch Light of Ruin.",
    },
    {
        "group": "heatran",
        "status": "confirmed",
        "att": "Garchomp-Mega-Z",
        "att_kind": ("mc", None),
        "att_label": "32 SpA Garchomp-Mega-Z",
        "move": "Earth Power",
        "bp": 90,
        "mtype": "Ground",
        "cat": "Special",
        "att_sp": 32,
        "att_nat": 1.0,
        "att_stg": 0,
        "def": "Heatran-Mega",
        "def_kind": ("md", "heatran-mega.png"),
        "def_label": "32 HP / 0 SpD Mega Heatran",
        "def_hp_sp": 32,
        "def_def_sp": 0,
        "def_nat": 1.0,
        "def_stg": 0,
        "ctx_es": "Debilidad x4 a Tierra: Earth Power ignora Water Compaction (+2 Def) y amenaza OHKO.",
        "ctx_en": "4× Ground weakness: Special Earth Power completely ignores +2 Def Water Compaction!",
    },
    {
        "group": "heatran",
        "status": "confirmed",
        "att": "Swampert-Mega",
        "att_kind": ("mc", None),
        "att_label": "32 Atk+ Swampert-Mega (Rain)",
        "move": "Wave Crash vs +2 Def",
        "bp": 120,
        "mtype": "Water",
        "cat": "Physical",
        "weather": 1.5,
        "att_sp": 32,
        "att_nat": 1.1,
        "att_stg": 0,
        "def": "Heatran-Mega",
        "def_kind": ("md", "heatran-mega.png"),
        "def_label": "32 HP / 12 Def Mega Heatran (+2 Def)",
        "def_hp_sp": 32,
        "def_def_sp": 12,
        "def_nat": 1.0,
        "def_stg": 2,
        "ctx_es": "Si Water Compaction ya se activó (+2 Def), Swampert necesita High Horsepower (x4) en lugar de Agua.",
        "ctx_en": "Once Water Compaction triggers (+2 Def), Swampert MUST click High Horsepower instead of Water STAB.",
    },
    # --- Group 2: +2 Commander Dondozo ---
    {
        "group": "dozo",
        "status": "confirmed",
        "att": "Dondozo",
        "att_kind": ("md", "dondozo.png"),
        "att_label": "+2 Atk 32 Atk+ Dondozo",
        "move": "Wave Crash",
        "bp": 120,
        "mtype": "Water",
        "cat": "Physical",
        "att_sp": 32,
        "att_nat": 1.1,
        "att_stg": 2,
        "def": "Incineroar",
        "def_label": "32 HP / 20 Def+ Incineroar",
        "def_hp_sp": 32,
        "def_def_sp": 20,
        "def_nat": 1.1,
        "def_stg": 0,
        "ctx_es": "Incluso tras Intimidate (+1 neto) Wave Crash destruye a Incineroar defensivo.",
        "ctx_en": "Wave Crash obliterates physically defensive Incineroar (even at +1 post-Intimidate it's lethal).",
    },
    {
        "group": "dozo",
        "status": "confirmed",
        "att": "Dondozo",
        "att_kind": ("md", "dondozo.png"),
        "att_label": "+2 Atk 32 Atk+ Dondozo",
        "move": "Order Up (Dragon)",
        "bp": 80,
        "mtype": "Dragon",
        "cat": "Physical",
        "att_sp": 32,
        "att_nat": 1.1,
        "att_stg": 2,
        "def": "Rillaboom",
        "def_label": "32 HP / 12 Def Rillaboom",
        "def_hp_sp": 32,
        "def_def_sp": 12,
        "def_nat": 1.0,
        "def_stg": 0,
        "ctx_es": "Sin STAB aún pega fuerte + gana +1 adicional según forma de Tatsugiri.",
        "ctx_en": "Chunks Rillaboom for 2HKO while stacking an extra +1 Atk/Def/Spe boost from Tatsugiri form.",
    },
    {
        "group": "dozo",
        "status": "confirmed",
        "att": "Rillaboom",
        "att_kind": ("mc", None),
        "att_label": "32 Atk+ Rillaboom (Grassy Terrain)",
        "move": "Wood Hammer vs +2 Def",
        "bp": 120,
        "mtype": "Grass",
        "cat": "Physical",
        "terrain": 1.3,
        "att_sp": 32,
        "att_nat": 1.1,
        "att_stg": 0,
        "def": "Dondozo",
        "def_kind": ("md", "dondozo.png"),
        "def_label": "12 HP / 12 Def +2 Commander Dondozo",
        "def_hp_sp": 12,
        "def_def_sp": 12,
        "def_nat": 1.0,
        "def_stg": 2,
        "ctx_es": "Wood Hammer presiona 2HKO real incluso contra +2 Def (mejor que Grassy Glide tras Haze).",
        "ctx_en": "Wood Hammer forces real 2HKO pressure even through +2 Def — pair with Haze/Clear Smog to close.",
    },
    {
        "group": "dozo",
        "status": "confirmed",
        "att": "Raichu-Mega-Y",
        "att_kind": ("mc", None),
        "att_label": "32 SpA Raichu-Mega-Y",
        "move": "Thunderbolt vs +2 SpD",
        "bp": 90,
        "mtype": "Electric",
        "cat": "Special",
        "att_sp": 32,
        "att_nat": 1.0,
        "att_stg": 0,
        "def": "Dondozo",
        "def_kind": ("md", "dondozo.png"),
        "def_label": "12 HP / 20 SpD +2 Commander Dondozo",
        "def_hp_sp": 12,
        "def_def_sp": 20,
        "def_nat": 1.0,
        "def_stg": 2,
        "ctx_es": "La baja SpD base (65) de Dondozo lo deja vulnerable a presión especial incluso a +2 SpD.",
        "ctx_en": "Dondozo's low 65 base SpD still takes heavy chunking from Raichu-Mega-Y even at +2 SpD.",
    },
    # --- Group 3: +1 Premium Grade Mega Tatsugiri ---
    {
        "group": "tatsugiri",
        "status": "confirmed",
        "att": "Tatsugiri-Mega",
        "att_kind": ("md", "tatsugiri-mega.png"),
        "att_label": "+1 SpA 32 SpA Mega Tatsugiri",
        "move": "Draco Meteor",
        "bp": 130,
        "mtype": "Dragon",
        "cat": "Special",
        "att_sp": 32,
        "att_nat": 1.0,
        "att_stg": 1,
        "def": "Archaludon",
        "def_label": "28 HP / 16 SpD Archaludon",
        "def_hp_sp": 28,
        "def_def_sp": 16,
        "def_nat": 1.0,
        "def_stg": 0,
        "ctx_es": "Premium Grade (+1 SpA gratis) convierte Draco Meteor en un proyectil devastador contra objetivos neutrales.",
        "ctx_en": "Free +1 SpA from Premium Grade turns Draco Meteor into a lethal nuke vs. neutral Steel/Dragons.",
    },
    {
        "group": "tatsugiri",
        "status": "confirmed",
        "att": "Tatsugiri-Mega",
        "att_kind": ("md", "tatsugiri-mega.png"),
        "att_label": "+1 SpA 32 SpA Mega Tatsugiri",
        "move": "Muddy Water (Spread)",
        "bp": 90,
        "mtype": "Water",
        "cat": "Special",
        "spread": True,
        "att_sp": 32,
        "att_nat": 1.0,
        "att_stg": 1,
        "def": "Incineroar",
        "def_label": "32 HP / 16 SpD+ Incineroar",
        "def_hp_sp": 32,
        "def_def_sp": 16,
        "def_nat": 1.1,
        "def_stg": 0,
        "ctx_es": "Presión spread masiva con 30% de bajar precisión; en Lluvia es OHKO directo a Incineroar.",
        "ctx_en": "Huge spread pressure with 30% accuracy-drop upside; becomes a clean OHKO on Incineroar in Rain.",
    },
    {
        "group": "tatsugiri",
        "status": "confirmed",
        "att": "Tatsugiri-Mega",
        "att_kind": ("md", "tatsugiri-mega.png"),
        "att_label": "+1 SpA 32 SpA Mega Tatsugiri",
        "move": "Draco Meteor",
        "bp": 130,
        "mtype": "Dragon",
        "cat": "Special",
        "att_sp": 32,
        "att_nat": 1.0,
        "att_stg": 1,
        "def": "Garchomp-Mega-Z",
        "def_label": "4 HP / 0 SpD Garchomp-Mega-Z",
        "def_hp_sp": 4,
        "def_def_sp": 0,
        "def_nat": 1.0,
        "def_stg": 0,
        "ctx_es": "OHKO absoluto si Mega Tatsugiri recibe Tailwind o sobrevive 1 golpe.",
        "ctx_en": "Clean OHKO whenever Mega Tatsugiri moves first under Tailwind or protects a speed edge.",
    },
    # --- Group 4: Amoonguss (Expected Wave — No Safety Goggles!) ---
    {
        "group": "amoonguss",
        "status": "rumored",
        "att": "Charizard-Mega-Y",
        "att_kind": ("mc", None),
        "att_label": "32 SpA Charizard-Mega-Y (Sun)",
        "move": "Heat Wave (Sun Spread)",
        "bp": 95,
        "mtype": "Fire",
        "cat": "Special",
        "spread": True,
        "weather": 1.5,
        "att_sp": 32,
        "att_nat": 1.0,
        "att_stg": 0,
        "def": "Amoonguss",
        "def_kind": ("rumored", "amoonguss.png"),
        "def_label": "32 HP / 20 SpD+ Amoonguss",
        "def_hp_sp": 32,
        "def_def_sp": 20,
        "def_nat": 1.1,
        "def_stg": 0,
        "ctx_es": "Sin Occa Berry, Amoonguss cae en 1 Heat Wave bajo Sol incluso con 32 HP / 20 SpD+.",
        "ctx_en": "Without Occa Berry, even max-bulk 32 HP / 20 SpD+ Amoonguss drops to Sun Heat Wave.",
    },
    {
        "group": "amoonguss",
        "status": "rumored",
        "att": "Incineroar",
        "att_kind": ("mc", None),
        "att_label": "8 Atk Incineroar",
        "move": "Flare Blitz",
        "bp": 120,
        "mtype": "Fire",
        "cat": "Physical",
        "att_sp": 8,
        "att_nat": 1.0,
        "att_stg": 0,
        "def": "Amoonguss",
        "def_kind": ("rumored", "amoonguss.png"),
        "def_label": "32 HP / 20 Def+ Amoonguss",
        "def_hp_sp": 32,
        "def_def_sp": 20,
        "def_nat": 1.1,
        "def_stg": 0,
        "ctx_es": "Amoonguss defensivo físico sobrevive Flare Blitz estándar y responde con Spore / Sitrus Berry.",
        "ctx_en": "Physically bulky Amoonguss lives standard Flare Blitz and answers with Spore + Sitrus/Regenerator.",
    },
    {
        "group": "amoonguss",
        "status": "rumored",
        "att": "Gholdengo",
        "att_kind": ("mc", None),
        "att_label": "32 SpA+ Life Orb Gholdengo",
        "move": "Make It Rain (Spread)",
        "bp": 120,
        "mtype": "Steel",
        "cat": "Special",
        "spread": True,
        "item": 1.3,
        "att_sp": 32,
        "att_nat": 1.1,
        "att_stg": 0,
        "def": "Amoonguss",
        "def_kind": ("rumored", "amoonguss.png"),
        "def_label": "32 HP / 16 SpD Amoonguss",
        "def_hp_sp": 32,
        "def_def_sp": 16,
        "def_nat": 1.0,
        "def_stg": 0,
        "ctx_es": "Good as Gold hace a Gholdengo 100% inmune a Spore (el único sustituto real de Safety Goggles).",
        "ctx_en": "Good as Gold gives Gholdengo 100% Spore immunity (the premier Safety-Goggles replacement in M-D).",
    },
    # --- Group 5: Mega Latios & Mega Latias (Expected Wave — 110 Spe Tier) ---
    {
        "group": "eons",
        "status": "rumored",
        "att": "Latios-Mega",
        "att_kind": ("rumored", "latios-mega.png"),
        "att_label": "32 SpA Mega Latios",
        "move": "Luster Purge",
        "bp": 95,
        "mtype": "Psychic",
        "cat": "Special",
        "att_sp": 32,
        "att_nat": 1.0,
        "att_stg": 0,
        "def": "Amoonguss",
        "def_kind": ("rumored", "amoonguss.png"),
        "def_label": "32 HP / 20 SpD+ Amoonguss",
        "def_hp_sp": 32,
        "def_def_sp": 20,
        "def_nat": 1.1,
        "def_stg": 0,
        "ctx_es": "Mega Latios castiga duramente a Amoonguss con 95 BP Luster Purge (50% -1 SpD).",
        "ctx_en": "Mega Latios punishes Amoonguss brutally with 95-BP STAB Luster Purge (50% SpD drop).",
    },
    {
        "group": "eons",
        "status": "rumored",
        "att": "Latios-Mega",
        "att_kind": ("rumored", "latios-mega.png"),
        "att_label": "32 SpA Mega Latios",
        "move": "Draco Meteor",
        "bp": 130,
        "mtype": "Dragon",
        "cat": "Special",
        "att_sp": 32,
        "att_nat": 1.0,
        "att_stg": 0,
        "def": "Rillaboom",
        "def_label": "32 HP / 12 SpD Rillaboom",
        "def_hp_sp": 32,
        "def_def_sp": 12,
        "def_nat": 1.0,
        "def_stg": 0,
        "ctx_es": "160 SpA a 110 Spe obliga a Rillaboom a invertir fuerte en SpD o Assault Vest.",
        "ctx_en": "160 SpA at 110 Spe forces heavy SpD or Assault Vest investment on Rillaboom.",
    },
    {
        "group": "eons",
        "status": "rumored",
        "att": "Kingambit",
        "att_kind": ("mc", None),
        "att_label": "32 Atk+ Kingambit",
        "move": "Sucker Punch",
        "bp": 70,
        "mtype": "Dark",
        "cat": "Physical",
        "att_sp": 32,
        "att_nat": 1.1,
        "att_stg": 0,
        "def": "Latias-Mega",
        "def_kind": ("rumored", "latias-mega.png"),
        "def_label": "32 HP / 16 Def Mega Latias",
        "def_hp_sp": 32,
        "def_def_sp": 16,
        "def_nat": 1.0,
        "def_stg": 0,
        "ctx_es": "Mega Latias (120 Def base) aguanta Sucker Punch de Kingambit cómodamente — excelente bulk mixto.",
        "ctx_en": "Mega Latias's 120 base Def comfortably lives unboosted Kingambit Sucker Punch — elite mixed bulk.",
    },
    # --- Group 6: Expected Wave Breakers (Terrakion, Porygon-Z, Flamigo) ---
    {
        "group": "breakers",
        "status": "rumored",
        "att": "Terrakion",
        "att_kind": ("rumored", "terrakion.png"),
        "att_label": "+4 Atk (Beat Up) Terrakion",
        "move": "Rock Slide (Spread)",
        "bp": 75,
        "mtype": "Rock",
        "cat": "Physical",
        "spread": True,
        "att_sp": 32,
        "att_nat": 1.0,
        "att_stg": 4,
        "def": "Incineroar",
        "def_label": "32 HP / 20 Def+ Incineroar",
        "def_hp_sp": 32,
        "def_def_sp": 20,
        "def_nat": 1.1,
        "def_stg": 0,
        "ctx_es": "Tras Beat Up (+4 Atk; +3 vs Intimidate), Rock Slide borra a Incineroar / Charizard-Y en 1 golpe.",
        "ctx_en": "Post Beat Up (+4 Atk), Rock Slide wipes Incineroar & Charizard-Y instantly — Fake Out or Follow Me required!",
    },
    {
        "group": "breakers",
        "status": "rumored",
        "att": "Porygon-Z",
        "att_kind": ("rumored", "porygon-z.png"),
        "att_label": "32 SpA+ Adaptability Life Orb Porygon-Z",
        "move": "Tri Attack (STAB 2.0×)",
        "bp": 80,
        "mtype": "Normal",
        "cat": "Special",
        "item": 1.3,
        "adaptability": True,
        "att_sp": 32,
        "att_nat": 1.1,
        "att_stg": 0,
        "def": "Incineroar",
        "def_label": "32 HP / 16 SpD+ Incineroar",
        "def_hp_sp": 32,
        "def_def_sp": 16,
        "def_nat": 1.1,
        "def_stg": 0,
        "ctx_es": "Adaptability (STAB 2.0×) + Life Orb convierte incluso Tri Attack (80 BP) en casi OHKO; Hyper Beam borra todo.",
        "ctx_en": "Adaptability (2.0× STAB) + Life Orb turns 80-BP Tri Attack into massive burst; Hyper Beam OHKOs virtually any neutral target.",
    },
    {
        "group": "breakers",
        "status": "rumored",
        "att": "Flamigo",
        "att_kind": ("rumored", "flamigo.png"),
        "att_label": "+2 Atk (Costar) 32 Atk Flamigo",
        "move": "Close Combat",
        "bp": 120,
        "mtype": "Fighting",
        "cat": "Physical",
        "att_sp": 32,
        "att_nat": 1.0,
        "att_stg": 2,
        "def": "Heatran-Mega",
        "def_kind": ("md", "heatran-mega.png"),
        "def_label": "32 HP / 12 Def Mega Heatran",
        "def_hp_sp": 32,
        "def_def_sp": 12,
        "def_nat": 1.0,
        "def_stg": 0,
        "ctx_es": "Tras copiar +2 de Dondozo vía Costar, Flamigo remata a Mega Heatran / Kingambit / Incineroar en 1 golpe.",
        "ctx_en": "After copying Dondozo's +2 boosts via Costar, Flamigo OHKOs Mega Heatran, Kingambit, and Incineroar cleanly.",
    },
    # --- Group 7: Regieleki (Transistor 1.3×) & Regidrago (Dragon's Maw 1.5×) ---
    {
        "group": "regis",
        "status": "rumored",
        "att": "Regieleki",
        "att_kind": ("rumored", "regieleki.png"),
        "att_label": "32 SpA+ Transistor Regieleki",
        "move": "Thunderbolt vs +2 SpD",
        "bp": 90,
        "mtype": "Electric",
        "cat": "Special",
        "ability_mult": 1.3,
        "att_sp": 32,
        "att_nat": 1.1,
        "att_stg": 0,
        "def": "Dondozo",
        "def_kind": ("md", "dondozo.png"),
        "def_label": "12 HP / 20 SpD +2 Commander Dondozo",
        "def_hp_sp": 12,
        "def_def_sp": 20,
        "def_nat": 1.0,
        "def_stg": 2,
        "ctx_es": "Transistor (×1.3 en Champions) pega 46–54% (31% 2HKO) incluso contra +2 SpD Dondozo 20-SpD a 252 Spe — y tras Haze/Clear Smog lo borra en 1 golpe.",
        "ctx_en": "Transistor (1.3× in Champions) deals 46–54% (31% 2HKO) even through 20-SpD +2 Commander Dondozo at 252 Spe — and OHKOs cleanly after Haze/Clear Smog.",
    },
    {
        "group": "regis",
        "status": "rumored",
        "att": "Regieleki",
        "att_kind": ("rumored", "regieleki.png"),
        "att_label": "32 SpA+ Transistor Regieleki",
        "move": "Electroweb (Spread)",
        "bp": 55,
        "mtype": "Electric",
        "cat": "Special",
        "spread": True,
        "ability_mult": 1.3,
        "att_sp": 32,
        "att_nat": 1.1,
        "att_stg": 0,
        "def": "Pelipper",
        "def_label": "24 HP / 4 SpD Pelipper",
        "def_hp_sp": 24,
        "def_def_sp": 4,
        "def_nat": 1.0,
        "def_stg": 0,
        "ctx_es": "OHKO garantizado (16/16) a Pelipper mientras baja -1 Spe al compañero para que Regidrago / Heatran tomen turno primero.",
        "ctx_en": "Guaranteed 16/16 OHKO on Pelipper while dropping its partner -1 Spe so Regidrago / Mega Heatran move first.",
    },
    {
        "group": "regis",
        "status": "rumored",
        "att": "Regidrago",
        "att_kind": ("rumored", "regidrago.png"),
        "att_label": "32 SpA Dragon Fang Dragon's Maw Regidrago",
        "move": "Dragon Energy (150 BP Spread)",
        "bp": 150,
        "mtype": "Dragon",
        "cat": "Special",
        "spread": True,
        "item": 1.2,
        "ability_mult": 1.5,
        "att_sp": 32,
        "att_nat": 1.0,
        "att_stg": 0,
        "def": "Incineroar",
        "def_label": "32 HP / 16 SpD+ Incineroar",
        "def_hp_sp": 32,
        "def_def_sp": 16,
        "def_nat": 1.1,
        "def_stg": 0,
        "ctx_es": "Dragon's Maw (×1.5) + Dragon Fang (×1.2) pulveriza a Incineroar defensivo especial en daño spread — y Pollen Puff recarga al 100% HP.",
        "ctx_en": "Dragon's Maw (1.5×) + Dragon Fang (1.2×) chunks max-SpD Incineroar through spread reduction — Pollen Puff resets 150 BP.",
    },
    {
        "group": "regis",
        "status": "rumored",
        "att": "Regidrago",
        "att_kind": ("rumored", "regidrago.png"),
        "att_label": "32 SpA Regidrago",
        "move": "Earth Power",
        "bp": 90,
        "mtype": "Ground",
        "cat": "Special",
        "att_sp": 32,
        "att_nat": 1.0,
        "att_stg": 0,
        "def": "Heatran-Mega",
        "def_kind": ("md", "heatran-mega.png"),
        "def_label": "24 HP / 4 SpD Mega Heatran",
        "def_hp_sp": 24,
        "def_def_sp": 4,
        "def_nat": 1.0,
        "def_stg": 0,
        "ctx_es": "Cobertura x4 Tierra especial que ignora Water Compaction (+2 Def) y pone a Mega Heatran en rango inmediato de remate.",
        "ctx_en": "4× Special Ground coverage that bypasses +2 Def Water Compaction and puts Mega Heatran into instant KO range.",
    },
]


# =============================================================================
# 3. TOP-20 REG M-C -> REG M-D META SHIFT MATRIX (STOCK UP / DOWN / PIVOT)
# =============================================================================

MC_SHIFT_NOTES: Dict[str, Dict[str, str]] = {
    "Rillaboom": {
        "trend": "pivot",
        "es": "Inmune a Spore/Rage Powder de Amoonguss y gran check a Dondozo/Tatsugiri y Regieleki con Wood Hammer / resistencia Eléctrica, pero sufre mucho ante Mega Heatran y Mega Latios — requiere más High Horsepower / Knock Off.",
        "en": "Immune to Amoonguss Spore/Rage Powder and resists Regieleki while checking DozoGiri with Wood Hammer, but pressured hard by Mega Heatran & Mega Latios — demands High Horsepower / bulky AV pivots.",
    },
    "Sneasler": {
        "trend": "pivot",
        "es": "Close Combat destroza a Heatran/Terrakion/Porygon-Z, pero pierde terreno frente a Amoonguss Rage Powder, Mega Latios (110 Spe) y Unaware Dondozo.",
        "en": "Close Combat shreds Heatran/Terrakion/Porygon-Z, yet loses tempo into Amoonguss Rage Powder, 110-Spe Mega Latios, and Unaware Dondozo.",
    },
    "Incineroar": {
        "trend": "up",
        "es": "Rey indiscutible del Balance M-D: chequea a Mega Latios/Latias, presiona a Amoonguss con Taunt/Flare Blitz, habilita a DozoGiri y frena a Heatran con Parting Shot.",
        "en": "Undisputed M-D Balance king: checks Mega Latios/Latias, pressures Amoonguss with Taunt/Flare Blitz, enables DozoGiri, and pivots around Heatran via Parting Shot.",
    },
    "Raichu-Mega-Y": {
        "trend": "up",
        "es": "Uno de los mejores checks ofensivos rápidos a Dondozo, Tatsugiri y Flamigo; además su forma base Lightning Rod frena en seco a Regieleki (sin Tera Ice en Champions) y Fake Out corta Beat Up Terrakion.",
        "en": "Premier fast offensive check to Dondozo, Tatsugiri, and Flamigo; base Lightning Rod hard-walls Tera-free Regieleki while Fake Out stops Beat Up Terrakion.",
    },
    "Gholdengo": {
        "trend": "up",
        "es": "STOCK AL ALZA: Good as Gold lo convierte en el rey anti-Spore en un formato sin Safety Goggles. Eso sí, ahora debe respetar a Mega Heatran/Flash Fire Heatran.",
        "en": "MAJOR STOCK UP: Good as Gold makes it the #1 anti-Spore anchor in a Safety-Goggles-free format, though it must pack Shadow Ball/partners for Mega Heatran.",
    },
    "Charizard-Mega-Y": {
        "trend": "down",
        "es": "Presionado por Flash Fire Heatran, Mega Heatran (que sobrevive y escala bajo Sol), Regieleki (200 Spe), Terrakion Rock Slide y Mega Latios (110 Spe). Aún brilla borrando a Amoonguss.",
        "en": "Squeezed by Flash Fire Heatran, Mega Heatran abusing Sun, 200-Spe Regieleki, Terrakion Rock Slide, and 110-Spe Mega Latios — still excels at incinerating Amoonguss.",
    },
    "Garchomp-Mega-Z": {
        "trend": "up",
        "es": "El counter #1 a Mega Heatran Y muro absoluto contra Regieleki (inmune x0 a Eléctrico sin Tera Ice en Champions): Earth Power especial ignora Water Compaction (+2 Def) y pega x4.",
        "en": "#1 offensive counter to Mega Heatran AND hard immunity wall vs. Tera-free Regieleki: Special Earth Power ignores Water Compaction (+2 Def) for 4× damage.",
    },
    "Archaludon": {
        "trend": "down",
        "es": "Sufre competencia directa de Mega Heatran en el slot Steel/Tank y pierde frente a Earth Power de Heatran/Regidrago, Close Combat de Terrakion/Flamigo y Draco Meteor de Mega Latios/Tatsugiri.",
        "en": "Faces fierce slot competition from Mega Heatran and takes heavy damage from Heatran/Regidrago Earth Power, Terrakion/Flamigo Close Combat, and Mega Latios/Tatsugiri Draco Meteor.",
    },
    "Floette-Mega": {
        "trend": "pivot",
        "es": "Inmunidad Hada (0×) clave frente a Regidrago (Dragon Energy), Mega Latios/Latias y Mega Tatsugiri, pero Mega Heatran (Fire/Steel) y Amoonguss frenan su spam de Light of Ruin.",
        "en": "Crucial 0× Fairy immunity into Regidrago Dragon Energy, Mega Latios/Latias, and Mega Tatsugiri, though Mega Heatran and Amoonguss wall careless Light of Ruin spam.",
    },
    "Kingambit": {
        "trend": "pivot",
        "es": "Excelente check a Mega Latios/Latias con Sucker Punch / Kowtow Cleave, pero Unaware Dondozo, Mega Heatran, Terrakion y Flamigo lo castigan severamente sin Tera.",
        "en": "Great check to Mega Latios/Latias via Sucker Punch / Kowtow Cleave, yet Unaware Dondozo, Mega Heatran, Terrakion, and Flamigo punish it heavily in a Tera-free format.",
    },
    "Milotic": {
        "trend": "up",
        "es": "GRAN GANADOR DE M-D: Haze borra el +2 de Dondozo en 1 turno, Competitive castiga Intimidate/Snarl/Icy Wind y resiste a Mega Heatran — cuidado con activar Water Compaction gratis.",
        "en": "HUGE M-D WINNER: Haze erases +2 Dondozo in one click, Competitive punishes Intimidate/Icy Wind, and Water typing walls Fire STAB (just avoid feeding Water Compaction carelessly).",
    },
    "Gengar-Mega": {
        "trend": "up",
        "es": "Shadow Tag + Perish Song es el win-con más limpio del juego contra DozoGiri (Dondozo no puede cambiar mientras Tatsugiri está dentro). También amenaza a Mega Latios/Latias.",
        "en": "Shadow Tag + Perish Song is the cleanest auto-win line into DozoGiri (Dondozo is locked in while Tatsugiri is inside), and threatens Mega Latios/Latias.",
    },
    "Swampert-Mega": {
        "trend": "pivot",
        "es": "High Horsepower x4 revienta a Mega Heatran, pero el arquetipo Lluvia debe evitar regalar Water Compaction (+2 Def) y ahora enfrenta a Amoonguss + Virizion + Dondozo.",
        "en": "4× High Horsepower crushes Mega Heatran, but Rain teams must stop blind Water-spread clicks into Water Compaction and tech for Amoonguss + Dondozo.",
    },
    "Politoed": {
        "trend": "up",
        "es": "Haze + Perish Song + Helping Hand + Drizzle lo convierten en soporte élite anti-Dondozo y socio perfecto de Mega Tatsugiri (+1 SpA Muddy Water bajo Lluvia).",
        "en": "Haze + Perish Song + Helping Hand + Drizzle make Politoed an elite anti-Dondozo tech AND prime partner for +1 SpA Rain Mega Tatsugiri.",
    },
    "Farigiraf": {
        "trend": "up",
        "es": "Armor Tail frena Fake Out, Sucker Punch y Grassy Glide mientras habilita Trick Room para Mega Heatran (67 Spe), Amoonguss (30 Spe) y Alolan Marowak (45 Spe).",
        "en": "Armor Tail blocks Fake Out, Sucker Punch, and Grassy Glide while setting Trick Room for Mega Heatran (67 Spe), Amoonguss (30 Spe), and Alolan Marowak (45 Spe).",
    },
    "Whimsicott": {
        "trend": "up",
        "es": "Explosión de valor: habilita Beat Up + Justified Terrakion, aporta Encore anti-Dondozo/Protect, Taunt anti-Amoonguss/TR y Tailwind para Mega Tatsugiri / Porygon-Z.",
        "en": "Value skyrockets: enables Beat Up + Justified Terrakion, locks Dondozo/Protect with Encore, shuts down Amoonguss/TR with Taunt, and fuels Tailwind for Mega Tatsugiri & Porygon-Z.",
    },
    "Salamence-Mega": {
        "trend": "down",
        "es": "120 Spe sigue superando a Mega Latios/Latias (110 Spe) y destruye a Amoonguss, pero compite por el slot de Mega y queda expuesto ante Mega Heatran y Unaware Dondozo.",
        "en": "120 Spe still outspeeds Mega Latios/Latias (110 Spe) and destroys Amoonguss, yet faces stiff Mega-slot competition and struggles into Mega Heatran & Unaware Dondozo.",
    },
    "Indeedee-F": {
        "trend": "up",
        "es": "Follow Me + Psychic Terrain protege a Porygon-Z / Mega Heatran / Mega Tatsugiri contra Fake Out y Grassy Glide, y bloquea Beat Up + prioridad.",
        "en": "Follow Me + Psychic Terrain shields Porygon-Z, Mega Heatran, and Mega Tatsugiri from Fake Out / Grassy Glide while disrupting priority lines.",
    },
    "Torkoal": {
        "trend": "up",
        "es": "Bajo Sol + Trick Room, Torkoal + Mega Heatran (67 Spe) + Amoonguss forman uno de los modos TR más destructivos del formato (y Clear Smog en Torkoal responde a Dondozo).",
        "en": "Under Sun + Trick Room, Torkoal + Mega Heatran (67 Spe) + Amoonguss form a terrifying TR core — and Torkoal's Clear Smog doubles as emergency anti-Dondozo tech.",
    },
    "Basculegion": {
        "trend": "down",
        "es": "Compite directamente con Dondozo / Mega Tatsugiri por el rol ofensivo Agua, y Water Compaction Mega Heatran + Amoonguss frenan Wave Crash / Last Respects.",
        "en": "Directly contested by Dondozo / Mega Tatsugiri for the Water offense slot, while Water Compaction Mega Heatran & Amoonguss blunt Wave Crash.",
    },
}


# =============================================================================
# 4. COMPARATIVE SPEED TIERS LADDER (M-D + TOP M-C STAPLES)
# =============================================================================

SPEED_LADDER_ENTRIES: List[Tuple[str, int, str, str]] = [
    # (species, base_spe, origin_tag, note_short)
    ("Regieleki", 200, "rumored", "Fastest unboosted mon · Transistor Electroweb / Tbolt"),
    ("Crobat", 130, "rumored", "Inner Focus TW / Haze / Taunt"),
    ("Gengar-Mega", 130, "mc", "Perish Trap vs DozoGiri"),
    ("Raichu-Mega-Y", 130, "mc", "Fast Fake Out / Elec vs Dozo"),
    ("Salamence-Mega", 120, "mc", "Aerilate Hyper Voice vs Amoonguss"),
    ("Sneasler", 120, "mc", "Unburden ×2 / Close Combat"),
    ("Whimsicott", 116, "mc", "Prankster TW / Beat Up / Encore"),
    ("Latios-Mega", 110, "rumored", "160 SpA Luster Purge / TW"),
    ("Latias-Mega", 110, "rumored", "120/150 Bulk Levitate / CM"),
    ("Grafaiai", 110, "rumored", "Prankster Doodle / Taunt"),
    ("Terrakion", 108, "rumored", "Beat Up Justified Rock Slide"),
    ("Cobalion", 108, "rumored", "Sacred Sword ignores +2 Def"),
    ("Virizion", 108, "rumored", "Spore-immune + Sacred Sword"),
    ("Staraptor-Mega", 105, "mc", "Intimidate / Tailwind / CC"),
    ("Cryogonal", 105, "rumored", "Levitate Freeze-Dry / Haze"),
    ("Garchomp-Mega-Z", 102, "mc", "#1 Mega Heatran Earth Power check"),
    ("Charizard-Mega-Y", 100, "mc", "Drought Heat Wave vs Amoonguss"),
    ("Floette-Mega", 102, "mc", "Checks Eon Dragons & Tatsugiri"),
    ("Dachsbun", 95, "rumored", "Well-Baked Body vs Heatran"),
    ("Tatsugiri-Mega", 92, "confirmed", "+1 SpA Premium Grade breaker"),
    ("Porygon-Z", 90, "rumored", "Adaptability 2.0× STAB nuke"),
    ("Flamigo", 90, "rumored", "Costar copies +2 Dozo boosts"),
    ("Archaludon", 85, "mc", "Stamina Electro Shot / Draco"),
    ("Rillaboom", 85, "mc", "Spore-immune Grassy Glide / WH"),
    ("Gholdengo", 84, "mc", "Good as Gold Spore-immune"),
    ("Tatsugiri", 82, "confirmed", "Commander / Scarf Muddy Water"),
    ("Milotic", 81, "mc", "Haze anti-Dozo + Competitive"),
    ("Regidrago", 80, "rumored", "Dragon's Maw 150-BP Energy (145 Timid > M-Tatsugiri!)"),
    ("Heatran", 77, "confirmed", "Flash Fire Heat Wave / EP"),
    ("Swampert-Mega", 70, "mc", "Swift Swim ×2 / High Horsepower"),
    ("Politoed", 70, "mc", "Drizzle + Haze + Perish Song"),
    ("Heatran-Mega", 67, "confirmed", "175 SpA Water Compaction (TR!)"),
    ("Farigiraf", 60, "mc", "Armor Tail TR Setter"),
    ("Incineroar", 60, "mc", "Intimidate / Fake Out / Parting"),
    ("Kingambit", 50, "mc", "Sucker Punch vs Eon Dragons"),
    ("Marowak-Alola", 45, "rumored", "TR Lightning Rod vs Raichu-Y"),
    ("Dondozo", 35, "confirmed", "+2 Commander (70 effective base!)"),
    ("Amoonguss", 30, "rumored", "TR Spore / Rage Powder / Clear Smog"),
    ("Torkoal", 20, "mc", "TR Drought Eruption / Clear Smog"),
]


# =============================================================================
# 5. FOUR DEEP TOURNAMENT COUNTERPLAY PLAYBOOKS
# =============================================================================

PLAYBOOKS: List[Dict[str, Any]] = [
    {
        "id": "pb_dozo",
        "icon": "🐋",
        "tag_es": "PLAYBOOK #1 · CONFIRMADO + FLAMIGO",
        "tag_en": "PLAYBOOK #1 · CONFIRMED + FLAMIGO",
        "title_es": "Cómo Ganar a +2 DozoGiri & Costar Flamigo (Sin Tera)",
        "title_en": "How to Beat +2 DozoGiri & Costar Flamigo (Tera-Free)",
        "summary_es": "Sin Terastallize para cambiar el tipo Agua puro de Dondozo, DozoGiri es MUCHO más castigable si preparas al menos 2 de los 5 pilares anti-Dozo.",
        "summary_en": "Without Terastallization to shed Dondozo's pure Water typing, DozoGiri is far more punishable when your 6-mon roster packs at least 2 of these 5 counterplay pillars.",
        "bullets_es": [
            "<b>1. Reset Inmediato (Haze / Clear Smog):</b> Milotic (Haze), Politoed (Haze), Crobat (130 Spe Inner Focus Haze) o Amoonguss (Clear Smog) anulan el +2/+2/+2/+2/+2 en un solo turno, convirtiendo a Dondozo en un 2v1 fácil.",
            "<b>2. Perish Trap (Mega Gengar / Politoed):</b> Mientras Tatsugiri está dentro de Dondozo, el rival NO puede cambiar a Dondozo. Shadow Tag + Perish Song + Protect/Fake Out sella el KO automático en 3 turnos.",
            "<b>3. Presión Especial & Grassy Terrain:</b> Dondozo solo tiene 65 SpD base. Raichu-Mega-Y (Thunderbolt) + Rillaboom (Wood Hammer en Grassy Terrain) fuerzan daño letal incluso antes de Haze.",
            "<b>4. Castigo a Costar Flamigo:</b> Si el rival trae Flamigo detrás, NO dejes caer a Tatsugiri gratis con Dondozo vivo a +2; usa Haze ANTES de que Flamigo entre para evitar heredar el +2 omni-boost.",
            "<b>5. Sacred Sword / Crits / Encore:</b> Cobalion y Virizion atraviesan +2 Def con Sacred Sword; Whimsicott Encore encierra a Dondozo en Protect para ganar 2 turnos libres.",
        ],
        "bullets_en": [
            "<b>1. Instant Stat Reset (Haze / Clear Smog):</b> Milotic, Politoed, 130-Spe Inner Focus Crobat (Haze), or Amoonguss (Clear Smog) erase the +2 omni-boost in one click, turning Dozo into an easy 2v1.",
            "<b>2. Perish Trap (Mega Gengar / Politoed):</b> While Tatsugiri is inside Dondozo, the opponent CANNOT switch Dondozo out. Shadow Tag + Perish Song + Protect/Fake Out forces a guaranteed 3-turn KO.",
            "<b>3. Special & Grassy Pressure:</b> Dondozo's 65 base SpD still melts under Raichu-Mega-Y Thunderbolt + Rillaboom Grassy Terrain Wood Hammer.",
            "<b>4. Denying Costar Flamigo:</b> Always click Haze/Clear Smog BEFORE KOing Tatsugiri or letting Flamigo enter so Flamigo never copies a +2 omni-boost.",
            "<b>5. Boost-Ignoring Lines:</b> Cobalion/Virizion Sacred Sword ignores +2 Def; Whimsicott Encore punishes Dondozo Protect turns.",
        ],
    },
    {
        "id": "pb_heatran",
        "icon": "🌋",
        "tag_es": "PLAYBOOK #2 · CONFIRMADO M-D",
        "tag_en": "PLAYBOOK #2 · CONFIRMED M-D",
        "title_es": "Neutralizar a Mega Heatran (Water Compaction) y Heatran Base",
        "title_en": "Neutralizing Mega Heatran (Water Compaction) & Base Heatran",
        "summary_es": "Mega Heatran (175 SpA / 141 SpD / 67 Spe) castiga a cualquiera que haga spam ciego de Agua (Flip Turn, Muddy Water, Surf) regalándole +2 Def para Body Press.",
        "summary_en": "Mega Heatran (175 SpA / 141 SpD / 67 Spe) punishes careless Water clicks (Flip Turn, Muddy Water, Surf) by banking free +2 Def boosts for Body Press.",
        "bullets_es": [
            "<b>1. Tierra Especial > Agua Física:</b> Garchomp-Mega-Z (Earth Power) y Heatran rival (Earth Power) pegan x4 e ignoran por completo los boosts de +2 Def de Water Compaction.",
            "<b>2. Tierra Física Limpia (antes de activar +2 Def):</b> Swampert-Mega (High Horsepower), Garchomp (Stomping Tantrum) y Rillaboom (High Horsepower) deben ir directo por Tierra — NUNCA toques con Agua antes.",
            "<b>3. Close Combat / Fighting STAB:</b> Sneasler, Terrakion, Cobalion (Sacred Sword ignora +2 Def!) y Flamigo presionan OHKO limpio.",
            "<b>4. Controla Trick Room (67 Spe):</b> Mega Heatran baja de 77 a 67 Spe al Megaevolucionar — exactamente en la banda letal bajo Trick Room con Farigiraf/Amoonguss. Prioriza Taunt / Imprison / Fake Out sobre el setter de TR.",
            "<b>5. Respeta Flash Fire en Heatran Base:</b> No regales boost ×1.5 de Fuego a Heatran no-Mega con Heat Wave ciego; presiona primero con Ground/Fighting o Snarl/Parting Shot.",
        ],
        "bullets_en": [
            "<b>1. Special Ground > Physical Water:</b> Garchomp-Mega-Z and opposing Heatran Earth Power hit 4× super-effectively and completely bypass +2 Def Water Compaction.",
            "<b>2. Click Ground First:</b> Swampert-Mega (High Horsepower), Garchomp (Stomping Tantrum), and Rillaboom (High Horsepower) must open with Ground — never chip with Flip Turn/Water first.",
            "<b>3. Fighting Breakers:</b> Sneasler, Terrakion, Flamigo, and Cobalion (Sacred Sword ignores +2 Def!) threaten clean OHKOs.",
            "<b>4. Respect 67-Spe Trick Room Mode:</b> Dropping from 77 to 67 Spe makes Mega Heatran a premier Trick Room sweeper beside Farigiraf/Amoonguss — deny TR with Taunt, Imprison, or double-ups.",
            "<b>5. Track Flash Fire on Base Heatran:</b> Never blindly click Heat Wave into non-Mega Heatran; pivot with Ground/Fighting or Snarl/Parting Shot.",
        ],
    },
    {
        "id": "pb_amoonguss",
        "icon": "🍄",
        "tag_es": "PLAYBOOK #3 · OLA ESPERADA (SIN SAFETY GOGGLES)",
        "tag_en": "PLAYBOOK #3 · EXPECTED WAVE (NO SAFETY GOGGLES)",
        "title_es": "Jugar Contra Amoonguss en Champions Sin Safety Goggles",
        "title_en": "Playing Around Amoonguss Without Safety Goggles in Champions",
        "summary_es": "Safety Goggles es ILEGAL en Pokémon Champions. Si entra Amoonguss, Spore (100% precisión) y Rage Powder redefinen el teambuilding de los 6 slots.",
        "summary_en": "Safety Goggles is ILLEGAL in Pokémon Champions. With Amoonguss arriving, 100%-accurate Spore and Rage Powder reshape every 6-mon roster.",
        "bullets_es": [
            "<b>1. Mínimo 2 Inmunidades a Polvo en tu Roster:</b> Combina al menos dos entre Rillaboom, Venusaur, Virizion (Grass-type inmune a Spore + Rage Powder), Gholdengo (Good as Gold inmune a Spore), o setters de Electric/Misty Terrain.",
            "<b>2. Castiga Rage Powder con Daño Spread / Fuego / Psíquico:</b> Charizard-Mega-Y (Sun Heat Wave), Mega Heatran (Heat Wave) y Mega Latios (Luster Purge) castigan a Amoonguss antes de que ciclen Regenerator.",
            "<b>3. Taunt Veloz & Fake Out:</b> Incineroar (Taunt), Whimsicott (Prankster Taunt), Crobat (130 Spe Inner Focus Taunt) y Grafaiai cortan Spore + Rage Powder de raíz.",
            "<b>4. Cuenta la Sitrus Berry y el Regenerator (33% HP):</b> No dejes a Amoonguss en rango de 35% si puede cambiar gratis; enfoca el KO limpio en un turno o impide su entrada con presión de posición.",
        ],
        "bullets_en": [
            "<b>1. Pack at Least 2 Powder-Immune Slots:</b> Combine at least two of Rillaboom, Venusaur, Virizion (Grass-type ignores BOTH Spore & Rage Powder), Gholdengo (Good as Gold ignores Spore), or Electric/Misty Terrain.",
            "<b>2. Punish Rage Powder with Spread / Fire / Psychic:</b> Charizard-Mega-Y Sun Heat Wave, Mega Heatran Heat Wave, and Mega Latios Luster Purge melt Amoonguss before Regenerator loops start.",
            "<b>3. Fast Taunt & Fake Out:</b> Incineroar Taunt, Prankster Whimsicott/Grafaiai Taunt, and 130-Spe Inner Focus Crobat Taunt shut down Spore and Rage Powder cleanly.",
            "<b>4. Deny Free Regenerator (33% HP) Cycles:</b> Commit to clean 1-turn KOs rather than chipping Amoonguss into free Regenerator pivots.",
        ],
    },
    {
        "id": "pb_eons_tatsu",
        "icon": "✈️",
        "tag_es": "PLAYBOOK #4 · M-TATSUGIRI + EON DUO + TERRAKION",
        "tag_en": "PLAYBOOK #4 · M-TATSUGIRI + EON DUO + TERRAKION",
        "title_es": "Mindgames de Mega Tatsugiri (+1 SpA), 110-Spe Eon Duo y Beat Up Terrakion",
        "title_en": "Handling Dual-Mode Mega Tatsugiri, 110-Spe Eon Duo & Beat Up Terrakion",
        "summary_es": "Tres amenazas ofensivas rápidas de M-D castigan a los equipos lentos de Balance que dependen solo de Intimidate + Fake Out.",
        "summary_en": "Three fast M-D offensive engines punish slow Balance squads that rely exclusively on Intimidate + Fake Out.",
        "bullets_es": [
            "<b>1. Lee el Modo de Tatsugiri en Team Preview:</b> Si el rival tiene otro Mega claro (ej. Salamence-Mega / Heatran-Mega), Tatsugiri suele ir Sash/Scarf Commander; si es el único Mega, prepárate para +1 SpA Premium Grade Turno 1.",
            "<b>2. Respeta el Escalón de 110 Spe (Mega Latios / Latias):</b> 110 Spe supera a Terrakion (108), Staraptor-Mega (105), Garchomp-Mega-Z (102) y Charizard-Y (100). Floette-Mega, Kingambit (Sucker Punch), Incineroar (Snarl/Knock Off) y Icy Wind/Tailwind son obligatorios.",
            "<b>3. Rompe Beat Up + Justified Terrakion Turno 1:</b> Whimsicott (116) + Terrakion (108) gana +4 Atk Turno 1 si no intervienes. Usa Fake Out sobre Terrakion/Whimsicott, Follow Me / Rage Powder (redirige Beat Up!), o Grassy Glide Rillaboom / Sneasler para rematarlo.",
            "<b>4. Bloquea Porygon-Z + Indeedee-F:</b> Si ves Indeedee-F + Porygon-Z, el plan es Follow Me + Adaptability Hyper Beam/Tri Attack. Usa daño spread (Heat Wave / Rock Slide / Make It Rain), cambia el Terreno con Rillaboom o presiona con Gholdengo/Heatran (resisten Normal!).",
        ],
        "bullets_en": [
            "<b>1. Read Tatsugiri's Mode at Team Preview:</b> If the opponent brings another dedicated Mega (Salamence/Heatran), Tatsugiri is usually Sash/Scarf Commander; if Tatsugiri is the lone Mega, respect Turn-1 +1 SpA Premium Grade!",
            "<b>2. Respect the 110-Spe Cliff (Mega Latios / Latias):</b> Outpaces Terrakion (108), Staraptor-Mega (105), Garchomp-Mega-Z (102), and Charizard-Y (100). Anchor with Floette-Mega, Kingambit Sucker Punch, Incineroar Snarl/Knock Off, or Tailwind/Icy Wind.",
            "<b>3. Break Turn-1 Beat Up Terrakion:</b> Whimsicott (116) + Terrakion (108) snowballs to +4 Atk unless disrupted via Fake Out, Follow Me / Rage Powder (redirects Beat Up!), or Grassy Glide / Sneasler.",
            "<b>4. Shut Down Indeedee-F + Porygon-Z:</b> Answer Follow Me + Adaptability Hyper Beam with spread damage (Heat Wave, Make It Rain, Rock Slide), Terrain overwrite (Rillaboom), and Steel/Ghost resistances (Gholdengo, Heatran).",
        ],
    },
    {
        "id": "pb_regis",
        "icon": "⚡",
        "tag_es": "PLAYBOOK #5 · REGIELEKI (200 SPE) & REGIDRAGO SIN TERA",
        "tag_en": "PLAYBOOK #5 · TERA-FREE REGIELEKI (200 SPE) & REGIDRAGO",
        "title_es": "Dominar (y Contrarrestar) a Regieleki 200-Spe y Regidrago en Champions",
        "title_en": "Mastering (and Countering) Tera-Free Regieleki & Regidrago in Champions",
        "summary_es": "Sin Terastallize (ni Tera Ice ni Tera Dragon), ambos Regis son cañones de cristal con inmunidades duras: quien controla el tablero de Ground/Fairy gana la serie.",
        "summary_en": "Without Terastallization (no Tera Ice or Tera Dragon), both Regis are surgical glass cannons gated by hard type immunities: whoever owns the Ground/Fairy board controls the set.",
        "bullets_es": [
            "<b>1. Explota la Falta de Tera Ice en Regieleki:</b> Garchomp-Mega-Z, Swampert-Mega y Lightning Rod (Raichu base / Alolan Marowak) anulan por completo Thunderbolt, Electroweb y Volt Switch — nunca te dejes encerrar sin respuesta Tierra o Lightning Rod.",
            "<b>2. Respeta la Matemática de Electroweb (200 → 133 Spe):</b> A 252+ Spe, Regieleki baja a -1 a los Base 130 (Raichu-Mega-Y, Gengar-Mega, Crobat: 200 → 133), permitiendo que socios de Base 80 Timid como Regidrago (145 Spe) muevan primero Turno 1.",
            "<b>3. Rompe el Techo de 150 BP de Dragon Energy:</b> La potencia de Dragon Energy escala linealmente con el % de HP de Regidrago. Prioridad (Fake Out, Grassy Glide, Sucker Punch) y daño residual cortan su salida ofensiva; al jugar CON Regidrago, cúralo con Pollen Puff de Amoonguss.",
            "<b>4. Inmunidad Hada (0×) Obligatoria vs Regidrago:</b> Primarina, Floette-Mega y Sylveon niegan por completo Dragon Energy / Draco Meteor y obligan al rival a pivotar a Mega Heatran o Gholdengo.",
        ],
        "bullets_en": [
            "<b>1. Punish Regieleki's Lack of Tera Ice:</b> Garchomp-Mega-Z, Swampert-Mega, and Lightning Rod (base Raichu / Alolan Marowak) completely blank Thunderbolt, Electroweb, and Volt Switch.",
            "<b>2. Respect Electroweb Speed Math (200 → 133 Spe):</b> At 252+ Spe, Regieleki drops Base-130 threats (Raichu-Y, Gengar-Mega, Crobat: 200 → 133), letting Base-80 Timid partners like Regidrago (145 Spe) move first immediately.",
            "<b>3. Break Regidrago's 150-BP HP Scaling:</b> Dragon Energy scales linearly with Regidrago's current HP%. Priority chip (Fake Out, Grassy Glide, Sucker Punch) guts its damage — while playing WITH Regidrago, pair it with Amoonguss Pollen Puff healing.",
            "<b>4. Pack a Hard 0× Fairy Immunity:</b> Primarina, Floette-Mega, and Sylveon shut down Dragon Energy / Draco Meteor spam and force awkward pivots to Steel/Fire partners.",
        ],
    },
]


# =============================================================================
# 6. SIX COPY-PASTEABLE LAIC 2027 -> M-D 6-MON BLUEPRINTS
# =============================================================================

TEAM_BLUEPRINTS: List[Dict[str, Any]] = [
    {
        "id": "laic1_rain_heatran",
        "badge_status": "confirmed",
        "source_label": "LAIC 2027 #1 Champion — Masahiro Taoka (14-2)",
        "title_es": "Lluvia + Mega Heatran (Water Compaction) & Mega Gengar Perish",
        "title_en": "Rain Balance + Mega Heatran (Water Compaction) & Mega Gengar Perish",
        "base_shell": ["Swampert-Mega", "Archaludon", "Politoed", "Incineroar", "Rillaboom", "Gengar-Mega"],
        "swap_out": ["Swampert-Mega", "Archaludon"],
        "swap_in": ["Heatran-Mega", "Dondozo"],
        "adapted_team": [
            ("Heatran-Mega", "md", "heatran-mega.png"),
            ("Politoed", "mc", None),
            ("Incineroar", "mc", None),
            ("Rillaboom", "mc", None),
            ("Gengar-Mega", "mc", None),
            ("Dondozo", "md", "dondozo.png"),
        ],
        "note_es": "Conserva el núcleo campeón de LAIC (Politoed + Incineroar + Rillaboom + Mega Gengar Perish Trap). Mega Heatran cubre Grass/Fairy/Steel y escala con Water Compaction, mientras Politoed Haze + Mega Gengar destruyen a DozoGiri rivales.",
        "note_en": "Keeps LAIC's championship Politoed + Incineroar + Rillaboom + Mega Gengar Perish Trap core. Mega Heatran covers Grass/Fairy/Steel while Politoed Haze + Mega Gengar lock out opposing DozoGiri.",
        "paste": """Heatran @ Heatranite
Ability: Flash Fire
Level: 50
Modest Nature
- Heat Wave
- Earth Power
- Flash Cannon
- Protect

Politoed @ Sitrus Berry
Ability: Drizzle
Level: 50
Calm Nature
- Weather Ball
- Haze
- Perish Song
- Protect

Incineroar @ Chople Berry
Ability: Intimidate
Level: 50
Careful Nature
- Fake Out
- Flare Blitz
- Parting Shot
- Taunt

Rillaboom @ Assault Vest
Ability: Grassy Surge
Level: 50
Adamant Nature
- Fake Out
- Grassy Glide
- Wood Hammer
- High Horsepower

Gengar @ Gengarite
Ability: Cursed Body
Level: 50
Timid Nature
- Shadow Ball
- Sludge Bomb
- Perish Song
- Protect

Dondozo @ Leftovers
Ability: Unaware
Level: 50
Impish Nature
- Wave Crash
- Body Press
- Yawn
- Protect""",
    },
    {
        "id": "laic2_sun_tr_heatran",
        "badge_status": "confirmed",
        "source_label": "LAIC 2027 #2 Finalist — Emilio Forbes (14-2)",
        "title_es": "Sol + Trick Room Doble Mega (Mega Heatran + Garchomp-Mega-Z)",
        "title_en": "Sun + Trick Room Dual Mega (Mega Heatran + Garchomp-Mega-Z)",
        "base_shell": ["Garchomp-Mega-Z", "Delphox-Mega", "Venusaur", "Kingambit", "Farigiraf", "Torkoal"],
        "swap_out": ["Delphox-Mega"],
        "swap_in": ["Heatran-Mega"],
        "adapted_team": [
            ("Garchomp-Mega-Z", "mc", None),
            ("Heatran-Mega", "md", "heatran-mega.png"),
            ("Venusaur", "mc", None),
            ("Kingambit", "mc", None),
            ("Farigiraf", "mc", None),
            ("Torkoal", "mc", None),
        ],
        "note_es": "Mega Heatran (67 Spe, 175 SpA) bajo Sol de Torkoal y Trick Room de Farigiraf alcanza OHKOs nucleares con Heat Wave, y Sol reduce el daño Agua a la mitad regalando +2 Def de Water Compaction. Torkoal aporta Clear Smog anti-Dondozo.",
        "note_en": "Mega Heatran (67 Spe, 175 SpA) under Torkoal Sun + Farigiraf Trick Room delivers nuclear Heat Wave KOs while Sun halves Water hits for safe +2 Def Water Compaction procs; Torkoal packs Clear Smog vs. Dondozo.",
        "paste": """Heatran @ Heatranite
Ability: Flash Fire
Level: 50
Quiet Nature
- Heat Wave
- Earth Power
- Flash Cannon
- Protect

Garchomp @ Garchompite Z
Ability: Rough Skin
Level: 50
Timid Nature
- Earth Power
- Draco Meteor
- Flamethrower
- Protect

Venusaur @ Focus Sash
Ability: Chlorophyll
Level: 50
Modest Nature
- Leaf Storm
- Sludge Bomb
- Sleep Powder
- Protect

Kingambit @ Black Glasses
Ability: Defiant
Level: 50
Brave Nature
- Kowtow Cleave
- Sucker Punch
- Iron Head
- Protect

Farigiraf @ Throat Spray
Ability: Armor Tail
Level: 50
Quiet Nature
- Hyper Voice
- Psychic
- Trick Room
- Helping Hand

Torkoal @ Charcoal
Ability: Drought
Level: 50
Quiet Nature
- Eruption
- Heat Wave
- Clear Smog
- Protect""",
    },
    {
        "id": "laic5_dozogiri_flex",
        "badge_status": "confirmed",
        "source_label": "LAIC 2027 Top 8 — Kandai Nagatome (12-2)",
        "title_es": "Modo Dual DozoGiri / Mega Tatsugiri + Rilla-Incin-Sneasler",
        "title_en": "Dual-Mode DozoGiri / Mega Tatsugiri + Rilla-Incin-Sneasler",
        "base_shell": ["Basculegion", "Floette-Mega", "Salamence-Mega", "Sneasler", "Incineroar", "Rillaboom"],
        "swap_out": ["Basculegion", "Floette-Mega"],
        "swap_in": ["Dondozo", "Tatsugiri-Mega"],
        "adapted_team": [
            ("Dondozo", "md", "dondozo.png"),
            ("Tatsugiri-Mega", "md", "tatsugiri-mega.png"),
            ("Salamence-Mega", "mc", None),
            ("Sneasler", "mc", None),
            ("Incineroar", "mc", None),
            ("Rillaboom", "mc", None),
        ],
        "note_es": "Aprovecha el trío #1–#3 de DuckDB (Rillaboom + Sneasler + Incineroar) como modo 2-2-2: en Team Preview el rival debe adivinar entre Commander Dondozo O +1 SpA Mega Tatsugiri sin sacrificar Salamence-Mega.",
        "note_en": "Pairs DuckDB's #1–#3 meta core (Rillaboom + Sneasler + Incineroar) with a 2-2-2 flex shell: opponents must guess between Commander Dondozo OR standalone +1 SpA Mega Tatsugiri alongside Salamence-Mega.",
        "paste": """Dondozo @ Leftovers
Ability: Unaware
Level: 50
Adamant Nature
- Wave Crash
- Order Up
- Earthquake
- Protect

Tatsugiri @ Tatsugirinite
Ability: Commander
Level: 50
Timid Nature
- Draco Meteor
- Muddy Water
- Icy Wind
- Protect

Salamence @ Salamencite
Ability: Intimidate
Level: 50
Timid Nature
- Hyper Voice
- Draco Meteor
- Tailwind
- Protect

Sneasler @ Grassy Seed
Ability: Unburden
Level: 50
Adamant Nature
- Fake Out
- Close Combat
- Dire Claw
- Protect

Incineroar @ Sitrus Berry
Ability: Intimidate
Level: 50
Careful Nature
- Fake Out
- Flare Blitz
- Parting Shot
- Taunt

Rillaboom @ Assault Vest
Ability: Grassy Surge
Level: 50
Adamant Nature
- Fake Out
- Grassy Glide
- Wood Hammer
- High Horsepower""",
    },
    {
        "id": "laic4_balance_latias_heatran",
        "badge_status": "rumored",
        "source_label": "LAIC 2027 Top 4 — Samuel Pereira (12-3)",
        "title_es": "Balance Anti-Intimidate + Heatran & Mega Latias (Eon Wave)",
        "title_en": "Anti-Intimidate Balance + Heatran & Mega Latias (Eon Wave)",
        "base_shell": ["Arcanine-Hisui", "Staraptor-Mega", "Milotic", "Raichu-Mega-Y", "Rillaboom", "Gholdengo"],
        "swap_out": ["Arcanine-Hisui", "Staraptor-Mega"],
        "swap_in": ["Heatran", "Latias-Mega"],
        "adapted_team": [
            ("Heatran", "md", "heatran.png"),
            ("Latias-Mega", "rumored", "latias-mega.png"),
            ("Milotic", "mc", None),
            ("Raichu-Mega-Y", "mc", None),
            ("Rillaboom", "mc", None),
            ("Gholdengo", "mc", None),
        ],
        "note_es": "[OLA ESPERADA] Cubre los 5 pilares M-D: Milotic Haze (anti-Dozo), Rillaboom + Gholdengo (doble inmunidad a Spore), Heatran Flash Fire (anti-Sol/Heatran) y Mega Latias Levitate (110 Spe Tailwind / Calm Mind).",
        "note_en": "[EXPECTED WAVE] Hits all 5 M-D stress checks: Milotic Haze (anti-Dozo), Rillaboom + Gholdengo (double Spore immunity), Flash Fire Heatran, and Levitate Mega Latias (110-Spe Tailwind / Calm Mind).",
        "paste": """Heatran @ Leftovers
Ability: Flash Fire
Level: 50
Modest Nature
- Heat Wave
- Earth Power
- Substitute
- Protect

Latias @ Latiasite
Ability: Levitate
Level: 50
Timid Nature
- Mist Ball
- Ice Beam
- Tailwind
- Recover

Milotic @ Sitrus Berry
Ability: Competitive
Level: 50
Calm Nature
- Scald
- Icy Wind
- Haze
- Protect

Raichu @ Raichunite Y
Ability: Lightning Rod
Level: 50
Timid Nature
- Fake Out
- Thunderbolt
- Volt Switch
- Protect

Rillaboom @ Assault Vest
Ability: Grassy Surge
Level: 50
Adamant Nature
- Fake Out
- Grassy Glide
- Wood Hammer
- High Horsepower

Gholdengo @ Life Orb
Ability: Good as Gold
Level: 50
Modest Nature
- Make It Rain
- Shadow Ball
- Nasty Plot
- Protect""",
    },
    {
        "id": "laic11_hard_tr_amoonguss",
        "badge_status": "rumored",
        "source_label": "LAIC 2027 Top 16 — Rohan Muthukumar (10-3)",
        "title_es": "Hard Trick Room: Mega Heatran + Amoonguss + Alolan Marowak",
        "title_en": "Hard Trick Room: Mega Heatran + Amoonguss + Alolan Marowak",
        "base_shell": ["Incineroar", "Rillaboom", "Raichu-Mega-Y", "Sylveon", "Farigiraf", "Camerupt-Mega"],
        "swap_out": ["Camerupt-Mega", "Rillaboom", "Raichu-Mega-Y"],
        "swap_in": ["Heatran-Mega", "Amoonguss", "Marowak-Alola"],
        "adapted_team": [
            ("Heatran-Mega", "md", "heatran-mega.png"),
            ("Amoonguss", "rumored", "amoonguss.png"),
            ("Marowak-Alola", "rumored", "marowak-alola.png"),
            ("Farigiraf", "mc", None),
            ("Incineroar", "mc", None),
            ("Sylveon", "mc", None),
        ],
        "note_es": "[OLA ESPERADA] Evolución directa del Hard TR de Camerupt-Mega: sin Safety Goggles, Amoonguss (Spore + Rage Powder + Clear Smog anti-Dozo) y Lightning Rod Alolan Marowak blindan el sweep de Mega Heatran bajo Trick Room.",
        "note_en": "[EXPECTED WAVE] Direct evolution of Camerupt-Mega Hard TR: in a Safety-Goggles-free format, Amoonguss (Spore + Rage Powder + anti-Dozo Clear Smog) and Lightning Rod Alolan Marowak shield Mega Heatran TR sweeps.",
        "paste": """Heatran @ Heatranite
Ability: Flash Fire
Level: 50
Quiet Nature
- Heat Wave
- Earth Power
- Flash Cannon
- Protect

Amoonguss @ Sitrus Berry
Ability: Regenerator
Level: 50
Sassy Nature
- Spore
- Rage Powder
- Pollen Puff
- Clear Smog

Marowak-Alola @ Life Orb
Ability: Lightning Rod
Level: 50
Brave Nature
- Flare Blitz
- Poltergeist
- Bonemerang
- Protect

Farigiraf @ Mental Herb
Ability: Armor Tail
Level: 50
Quiet Nature
- Hyper Voice
- Psychic
- Trick Room
- Helping Hand

Incineroar @ Chople Berry
Ability: Intimidate
Level: 50
Relaxed Nature
- Fake Out
- Flare Blitz
- Parting Shot
- Knock Off

Sylveon @ Throat Spray
Ability: Pixilate
Level: 50
Quiet Nature
- Hyper Voice
- Quick Attack
- Shadow Ball
- Protect""",
    },
    {
        "id": "dozo_flamigo_porygonz",
        "badge_status": "rumored",
        "source_label": "DuckDB Hyper-Offense Core (Whimsicott + Indeedee-F)",
        "title_es": "DozoGiri + Costar Flamigo & Adaptability Porygon-Z Hyper-Offense",
        "title_en": "DozoGiri + Costar Flamigo & Adaptability Porygon-Z Hyper-Offense",
        "base_shell": ["Whimsicott", "Indeedee-F", "Gholdengo", "Incineroar", "Sneasler", "Salamence-Mega"],
        "swap_out": ["Whimsicott", "Gholdengo", "Sneasler", "Salamence-Mega"],
        "swap_in": ["Dondozo", "Tatsugiri-Mega", "Flamigo", "Porygon-Z"],
        "adapted_team": [
            ("Dondozo", "md", "dondozo.png"),
            ("Tatsugiri-Mega", "md", "tatsugiri-mega.png"),
            ("Flamigo", "rumored", "flamigo.png"),
            ("Porygon-Z", "rumored", "porygon-z.png"),
            ("Indeedee-F", "mc", None),
            ("Incineroar", "mc", None),
        ],
        "note_es": "[OLA ESPERADA] Doble win-con brutal: Modo A (DozoGiri + Costar Flamigo copiando +2 omni-boost + Feint) o Modo B (Indeedee-F Follow Me + Adaptability Porygon-Z / +1 SpA Mega Tatsugiri bloqueando Fake Out y Grassy Glide).",
        "note_en": "[EXPECTED WAVE] Dual hyper-offense win-cons: Mode A (DozoGiri + Costar Flamigo inheriting +2 omni-boosts + Feint) or Mode B (Indeedee-F Follow Me + Adaptability Porygon-Z / +1 SpA Mega Tatsugiri blocking Fake Out & Grassy Glide).",
        "paste": """Dondozo @ Leftovers
Ability: Unaware
Level: 50
Adamant Nature
- Wave Crash
- Order Up
- Earthquake
- Protect

Tatsugiri @ Tatsugirinite
Ability: Commander
Level: 50
Timid Nature
- Draco Meteor
- Muddy Water
- Icy Wind
- Protect

Flamigo @ Focus Sash
Ability: Costar
Level: 50
Jolly Nature
- Close Combat
- Brave Bird
- Feint
- Wide Guard

Porygon-Z @ Life Orb
Ability: Adaptability
Level: 50
Modest Nature
- Tri Attack
- Hyper Beam
- Ice Beam
- Protect

Indeedee-F @ Psychic Seed
Ability: Psychic Surge
Level: 50
Bold Nature
- Follow Me
- Helping Hand
- Psychic
- Trick Room

Incineroar @ Sitrus Berry
Ability: Intimidate
Level: 50
Careful Nature
- Fake Out
- Flare Blitz
- Parting Shot
- Taunt""",
    },
]


# =============================================================================
# 7. INTERACTIVE 6-MON M-D READINESS CHECKER METADATA
# =============================================================================

# Capability tags per Pokémon for deterministic 5-axis M-D stress testing:
# dozo = Haze/Clear Smog/Perish/Strong Grass-Elec/Sacred Sword
# heatran = Ground/Fighting breaker or Flash Fire
# spore = Grass-type / Good as Gold / Taunt / Electric-Misty Terrain / Fire-Flying spread
# eon_terra = Fairy / Dark / Ice / Follow Me / Rage Powder / Fake Out
# speed = Tailwind / Trick Room / Icy Wind / Priority Speed Control
READINESS_ROSTER_POOL: List[Dict[str, Any]] = [
    {"sp": "Rillaboom", "kind": ("mc", None), "tags": ["dozo", "heatran", "spore", "eon_terra"]},
    {"sp": "Incineroar", "kind": ("mc", None), "tags": ["spore", "eon_terra"]},
    {"sp": "Sneasler", "kind": ("mc", None), "tags": ["heatran", "eon_terra"]},
    {"sp": "Raichu-Mega-Y", "kind": ("mc", None), "tags": ["dozo", "eon_terra", "speed"]},
    {"sp": "Gholdengo", "kind": ("mc", None), "tags": ["spore", "eon_terra"]},
    {"sp": "Charizard-Mega-Y", "kind": ("mc", None), "tags": ["spore"]},
    {"sp": "Garchomp-Mega-Z", "kind": ("mc", None), "tags": ["heatran"]},
    {"sp": "Archaludon", "kind": ("mc", None), "tags": ["dozo"]},
    {"sp": "Floette-Mega", "kind": ("mc", None), "tags": ["eon_terra"]},
    {"sp": "Kingambit", "kind": ("mc", None), "tags": ["eon_terra"]},
    {"sp": "Milotic", "kind": ("mc", None), "tags": ["dozo", "speed"]},
    {"sp": "Gengar-Mega", "kind": ("mc", None), "tags": ["dozo", "eon_terra"]},
    {"sp": "Swampert-Mega", "kind": ("mc", None), "tags": ["heatran"]},
    {"sp": "Politoed", "kind": ("mc", None), "tags": ["dozo", "heatran"]},
    {"sp": "Farigiraf", "kind": ("mc", None), "tags": ["speed", "eon_terra"]},
    {"sp": "Whimsicott", "kind": ("mc", None), "tags": ["dozo", "spore", "speed"]},
    {"sp": "Indeedee-F", "kind": ("mc", None), "tags": ["eon_terra", "speed"]},
    {"sp": "Torkoal", "kind": ("mc", None), "tags": ["dozo", "spore"]},
    {"sp": "Venusaur", "kind": ("mc", None), "tags": ["dozo", "spore"]},
    {"sp": "Salamence-Mega", "kind": ("mc", None), "tags": ["spore", "speed"]},
    {"sp": "Heatran-Mega", "kind": ("md", "heatran-mega.png"), "tags": ["heatran", "spore", "eon_terra"]},
    {"sp": "Heatran", "kind": ("md", "heatran.png"), "tags": ["heatran", "spore", "eon_terra"]},
    {"sp": "Dondozo", "kind": ("md", "dondozo.png"), "tags": ["heatran"]},
    {"sp": "Tatsugiri-Mega", "kind": ("md", "tatsugiri-mega.png"), "tags": ["heatran", "speed"]},
    {"sp": "Amoonguss", "kind": ("rumored", "amoonguss.png"), "tags": ["dozo", "spore", "eon_terra", "speed"]},
    {"sp": "Regieleki", "kind": ("rumored", "regieleki.png"), "tags": ["dozo", "speed"]},
    {"sp": "Regidrago", "kind": ("rumored", "regidrago.png"), "tags": ["heatran", "eon_terra"]},
    {"sp": "Primarina", "kind": ("mc", None), "tags": ["dozo", "heatran", "eon_terra"]},
    {"sp": "Latios-Mega", "kind": ("rumored", "latios-mega.png"), "tags": ["spore", "speed"]},
    {"sp": "Latias-Mega", "kind": ("rumored", "latias-mega.png"), "tags": ["heatran", "speed"]},
    {"sp": "Terrakion", "kind": ("rumored", "terrakion.png"), "tags": ["heatran"]},
    {"sp": "Flamigo", "kind": ("rumored", "flamigo.png"), "tags": ["heatran", "eon_terra"]},
    {"sp": "Crobat", "kind": ("rumored", "crobat.png"), "tags": ["dozo", "spore", "speed"]},
    {"sp": "Virizion", "kind": ("rumored", "virizion.png"), "tags": ["dozo", "heatran", "spore"]},
    {"sp": "Porygon-Z", "kind": ("rumored", "porygon-z.png"), "tags": ["eon_terra"]},
]


# =============================================================================
# 8. COACH PORYGON SIGNATURE REGULATION M-D TEAM ("IRON-VOLT CROWN")
# =============================================================================
# Double Fantasy Core (Fire/Water/Grass + Dragon/Steel/Fairy) engineered with
# strict Champions Level-50 66-SP math (31 IVs, <=32 SP/stat, zero Tera, 100%
# DuckDB-verified Champions-legal items — no Safety Goggles / Choice Specs!).

def _sp_to_ev(sp: int) -> int:
    """Convert Champions Stat Points (0..32) to exact Level-50 Showdown EVs."""
    return 0 if int(sp) <= 0 else 4 + 8 * (int(sp) - 1)


_NATURE_MULT_MAP: Dict[str, Tuple[Optional[str], Optional[str]]] = {
    "Modest": ("spa", "atk"),
    "Timid": ("spe", "atk"),
    "Bold": ("def", "atk"),
    "Careful": ("spd", "spa"),
    "Adamant": ("atk", "spa"),
    "Jolly": ("spe", "spa"),
    "Quiet": ("spa", "spe"),
}

COACH_PORYGON_SIGNATURE_TEAM: Dict[str, Any] = {
    "codename_es": "Corona Hierro-Voltio — Doble Núcleo Fantasía (F/W/G + D/S/F)",
    "codename_en": "Iron-Volt Crown — Double Fantasy Core (F/W/G + D/S/F)",
    "subtitle_es": "Equipo original diseñado por Coach Porygon VGC para Regulation M-D usando 66 SP exactos, 31 IVs, cero Terastallize y objetos 100% legales en Pokémon Champions (verificados vía DuckDB).",
    "subtitle_en": "Original Regulation M-D team crafted by Coach Porygon VGC using exact 66-SP Champions Level-50 math, 31 IVs, zero Terastallization, and 100% DuckDB-verified Champions-legal items.",
    "pillars_es": [
        "<b>1. Doble Núcleo Fantasía Sin Tera:</b> Combina simultáneamente Fuego–Agua–Planta (<i>Mega Heatran / Incineroar – Primarina – Amoonguss</i>) y Dragón–Acero–Hada (<i>Regidrago – Mega Heatran – Primarina</i>), cubriendo todas las inmunidades clave (0× Dragón, 0× Spore, Water Compaction) en un formato sin Terastallize.",
        "<b>2. Escalera Dual de Velocidad (252 Spe → 50 Spe):</b> <i>Regieleki</i> (252 Spe) usa Electroweb para bajar a los Base 130 de 200 a 133 Spe — debajo de <i>Regidrago</i> Timid (145 Spe, que además supera a Mega Tatsugiri Modest en 144) — mientras <i>Amoonguss</i> (50) + <i>Primarina</i> (84) + <i>Mega Heatran</i> (103) castigan Trick Room.",
        "<b>3. Motor Pollen Puff → 150 BP Dragon Energy:</b> <i>Amoonguss</i> desvía ataques con Rage Powder y restaura +50% HP a <i>Regidrago</i> con Pollen Puff para mantener Dragon Energy al techo de 150 BP spread (×1.5 Dragon's Maw ×1.2 Dragon Fang).",
        "<b>4. Triple Bloqueo a +2 DozoGiri & Costar Flamigo:</b> <i>Amoonguss</i> (Clear Smog), <i>Primarina</i> (Haze sobreviviendo +2 Wave Crash en 54.5–64.7%) y <i>Regieleki</i> (Transistor Thunderbolt pega 46–54% aún contra +2 SpD y borra en 1 golpe tras Haze) convierten DozoGiri en matchup favorable.",
    ],
    "pillars_en": [
        "<b>1. Tera-Free Double Fantasy Core:</b> Simultaneously completes Fire–Water–Grass (<i>Mega Heatran / Incineroar – Primarina – Amoonguss</i>) and Dragon–Steel–Fairy (<i>Regidrago – Mega Heatran – Primarina</i>), locking in hard defensive immunities (0× Dragon, 0× Spore, Water Compaction) in a Tera-free format.",
        "<b>2. Dual-Speed Architecture (252 Spe → 50 Spe):</b> <i>Regieleki</i> (252 Spe) Electroweb drops Base-130 speedsters from 200 to 133 Spe — below Timid <i>Regidrago</i> (145 Spe, also outspeeding Modest Mega Tatsugiri's 144!) — while <i>Amoonguss</i> (50) + <i>Primarina</i> (84) + <i>Mega Heatran</i> (103) hijack Trick Room.",
        "<b>3. Pollen Puff → 150-BP Dragon Energy Engine:</b> <i>Amoonguss</i> absorbs single-target hits via Rage Powder and heals <i>Regidrago</i> +50% HP with Pollen Puff to keep spread Dragon Energy firing at full 150 BP (1.5× Dragon's Maw × 1.2× Dragon Fang).",
        "<b>4. Triple Anti-DozoGiri & Costar Firewall:</b> <i>Amoonguss</i> (Clear Smog), <i>Primarina</i> (Haze living +2 Wave Crash at 54.5–64.7%), and <i>Regieleki</i> (Transistor Thunderbolt hitting 46–54% even through +2 SpD and OHKOing post-Haze) turn DozoGiri into a winning matchup.",
    ],
    "roster": [
        {
            "species": "Heatran-Mega",
            "paste_species": "Heatran",
            "display": "Mega Heatran",
            "sprite": ("md", "heatran-mega.png"),
            "stone": "heatranite.png",
            "item": "Heatranite",
            "ability": "Flash Fire → Water Compaction",
            "paste_ability": "Flash Fire",
            "nature": "Modest",
            "sp": {"hp": 24, "atk": 0, "def": 4, "spa": 18, "spd": 4, "spe": 16},
            "moves": ["Heat Wave", "Earth Power", "Flash Cannon", "Protect"],
            "role_es": "Ancla Acero/Fuego · Rompe-Hadas & Anti-Amoonguss",
            "role_en": "Steel/Fire Anchor · Fairy-Breaker & Anti-Amoonguss",
            "rationale_es": "18 SpA Modest garantiza OHKO (16/16) con Earth Power sobre Mega Heatran rival (24 HP / 4 SpD). 16 Spe (103) supera a Milotic/Tatsugiri 0-SP y a Garchomp-Mega-Z neutral a -1 tras Electroweb (102). Absorbe Dragon Energy de Regidrago rival en ~32% HP.",
            "rationale_en": "18 SpA Modest guarantees a 16/16 Earth Power OHKO on opposing 24 HP / 4 SpD Mega Heatran. 16 Spe (103) outpaces 0-SP Milotic/Tatsugiri and -1 neutral Garchomp-Mega-Z after Electroweb (102), while tanking opposing Regidrago Dragon Energy for ~32%.",
        },
        {
            "species": "Regidrago",
            "paste_species": "Regidrago",
            "display": "Regidrago",
            "sprite": ("rumored", "regidrago.png"),
            "item": "Dragon Fang",
            "ability": "Dragon's Maw (×1.5 Dragon)",
            "paste_ability": "Dragon's Maw",
            "nature": "Timid",
            "sp": {"hp": 0, "atk": 0, "def": 2, "spa": 32, "spd": 0, "spe": 32},
            "moves": ["Dragon Energy", "Draco Meteor", "Earth Power", "Protect"],
            "role_es": "Cañón Spread 150 BP · Presión a Núcleos Balance",
            "role_en": "150-BP Spread Breaker · Balance Shredder",
            "rationale_es": "Timid 32 Spe (145) vence a Mega Tatsugiri Modest (144) y a TODOS los Base 130 a -1 tras Electroweb (133). Dragon Fang (100% legal en Champions) amplifica Dragon Energy ×1.2 sin encerrarte en Choice, habilitando Protect y Earth Power contra Mega Heatran.",
            "rationale_en": "Timid 32 Spe (145) beats Modest Mega Tatsugiri (144) and EVERY -1 Base-130 threat after Electroweb (133). Champions-legal Dragon Fang boosts Dragon Energy 1.2× without Choice-locking, preserving Protect and 4× Earth Power vs. Mega Heatran.",
        },
        {
            "species": "Regieleki",
            "paste_species": "Regieleki",
            "display": "Regieleki",
            "sprite": ("rumored", "regieleki.png"),
            "item": "Focus Sash",
            "ability": "Transistor (×1.3 Electric)",
            "paste_ability": "Transistor",
            "nature": "Modest",
            "sp": {"hp": 2, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 32},
            "moves": ["Thunderbolt", "Electroweb", "Volt Switch", "Protect"],
            "role_es": "Control de Velocidad 252 Spe · Anti-Dozo & Pelipper",
            "role_en": "252-Spe Speed Engine · Anti-Dozo & Rain Punisher",
            "rationale_es": "Modest 32 SpA (167) presiona 46–54% con Transistor Thunderbolt incluso sobre +2 SpD Dondozo (OHKO tras Haze/Clear Smog) y logra OHKO 16/16 con Electroweb a Pelipper. 252 Spe supera a todo el meta sin Scarf; Focus Sash asegura control o pivote con Volt Switch.",
            "rationale_en": "Modest 32 SpA (167) chunks 46–54% with Transistor Thunderbolt even through +2 SpD Dondozo (OHKO post-Haze/Clear Smog) and scores a 16/16 Electroweb OHKO on Pelipper. 252 Spe outruns every unboosted threat while Focus Sash guarantees tempo.",
        },
        {
            "species": "Amoonguss",
            "paste_species": "Amoonguss",
            "display": "Amoonguss",
            "sprite": ("rumored", "amoonguss.png"),
            "item": "Rocky Helmet",
            "ability": "Regenerator",
            "paste_ability": "Regenerator",
            "nature": "Bold",
            "sp": {"hp": 32, "atk": 0, "def": 18, "spa": 0, "spd": 16, "spe": 0},
            "moves": ["Spore", "Rage Powder", "Pollen Puff", "Clear Smog"],
            "role_es": "Redirección · Curador Pollen Puff · Anti-Dozo & Anti-TR",
            "role_en": "Redirection · Pollen Puff Healer · Anti-Dozo & TR Hijack",
            "rationale_es": "32 HP / 18 Def+ / 16 SpD aguanta +2 Order Up de Dondozo (Clear Smog resetea Commander al instante) y castiga Fake Out / Wave Crash / Close Combat con Rocky Helmet. Inmune a Spore rival y recarga a Regidrago al 100% HP vía Pollen Puff.",
            "rationale_en": "32 HP / 18 Def+ / 16 SpD tanks +2 Dondozo Order Up (Clear Smog wipes Commander immediately) while Rocky Helmet punishes Fake Out, Wave Crash, and Close Combat. Naturally Spore-immune and heals Regidrago back to 100% HP with Pollen Puff.",
        },
        {
            "species": "Primarina",
            "paste_species": "Primarina",
            "display": "Primarina",
            "sprite": ("mc", None),
            "item": "Leftovers",
            "ability": "Liquid Voice",
            "paste_ability": "Liquid Voice",
            "nature": "Modest",
            "sp": {"hp": 32, "atk": 0, "def": 16, "spa": 14, "spd": 0, "spe": 4},
            "moves": ["Hyper Voice", "Moonblast", "Haze", "Protect"],
            "role_es": "Inmunidad 0× Dragón · Haze Anti-Dozo · Remate Spread",
            "role_en": "0× Dragon Immunity · Anti-Dozo Haze · Spread Closer",
            "rationale_es": "16 Def + 32 HP sobrevive cómodamente +2 Wave Crash de Dondozo (54.5–64.7%) para pulsar Haze sin miedo. Inmunidad total 0× a Regidrago/Eons: 14 SpA+ Moonblast logra 15/16 OHKO sobre Regidrago (98.2–116.4%) y 13/16 sobre Garchomp-Mega-Z, y 4 Spe (84) supera a Incineroar 0-SP.",
            "rationale_en": "32 HP / 16 Def cleanly lives +2 Dondozo Wave Crash (54.5–64.7%) to click Haze safely. Hard 0× immunity to opposing Regidrago & Eon Draco Meteors: 14 SpA+ Moonblast hits 15/16 OHKO on Regidrago (98.2–116.4%) and 13/16 on Garchomp-Mega-Z while 4 Spe (84) creeps Incineroar.",
        },
        {
            "species": "Incineroar",
            "paste_species": "Incineroar",
            "display": "Incineroar",
            "sprite": ("mc", None),
            "item": "Sitrus Berry",
            "ability": "Intimidate",
            "paste_ability": "Intimidate",
            "nature": "Careful",
            "sp": {"hp": 32, "atk": 4, "def": 14, "spa": 0, "spd": 12, "spe": 4},
            "moves": ["Fake Out", "Flare Blitz", "Parting Shot", "Taunt"],
            "role_es": "Pivote Intimidate · Fake Out · Taunt Anti-Amoonguss/TR",
            "role_en": "Intimidate Pivot · Fake Out · Anti-Amoonguss/TR Taunt",
            "rationale_es": "Sitrus Berry (100% legal en Champions, a diferencia de Safety Goggles) + 32 HP / 12 SpD+ sobrevive Earth Power de Mega Heatran (62–74%) y activa curación. Taunt frena a Amoonguss y Farigiraf, mientras Parting Shot da entrada limpia a Regidrago.",
            "rationale_en": "Champions-legal Sitrus Berry (no illegal Safety Goggles!) + 32 HP / 12 SpD+ lives Mega Heatran Earth Power (62–74%) and heals back up. Taunt shuts down Amoonguss & Farigiraf while Parting Shot grants free switch-ins to Regidrago.",
        },
    ],
    "proof_calcs": [
        {
            "att": "Heatran-Mega", "att_sp": 18, "att_nat": 1.1, "att_stg": 0,
            "def": "Heatran-Mega", "def_hp_sp": 24, "def_def_sp": 4, "def_nat": 1.0, "def_stg": 0,
            "move": "Earth Power", "bp": 90, "mtype": "Ground", "cat": "Special",
            "label_es": "Nuestro Mega Heatran (18 SpA+) → Mega Heatran rival (24 HP/4 SpD)",
            "label_en": "Our Mega Heatran (18 SpA+) → Opposing Mega Heatran (24 HP/4 SpD)",
        },
        {
            "att": "Regidrago", "att_sp": 32, "att_nat": 1.0, "att_stg": 0, "item": 1.2, "ability_mult": 1.5, "spread": True,
            "def": "Amoonguss", "def_hp_sp": 32, "def_def_sp": 16, "def_nat": 1.0, "def_stg": 0,
            "move": "Dragon Energy (150 BP Spread)", "bp": 150, "mtype": "Dragon", "cat": "Special",
            "label_es": "Nuestro Regidrago (Dragon Fang) → Amoonguss (32 HP/16 SpD)",
            "label_en": "Our Regidrago (Dragon Fang) → Amoonguss (32 HP/16 SpD)",
        },
        {
            "att": "Regieleki", "att_sp": 32, "att_nat": 1.1, "att_stg": 0, "ability_mult": 1.3,
            "def": "Dondozo", "def_hp_sp": 12, "def_def_sp": 20, "def_nat": 1.0, "def_stg": 2,
            "move": "Thunderbolt vs +2 SpD", "bp": 90, "mtype": "Electric", "cat": "Special",
            "label_es": "Nuestro Regieleki (Modest Transistor) → +2 SpD Dondozo",
            "label_en": "Our Regieleki (Modest Transistor) → +2 SpD Dondozo",
        },
        {
            "att": "Primarina", "att_sp": 14, "att_nat": 1.1, "att_stg": 0,
            "def": "Regidrago", "def_hp_sp": 0, "def_def_sp": 0, "def_nat": 1.0, "def_stg": 0,
            "move": "Moonblast", "bp": 95, "mtype": "Fairy", "cat": "Special",
            "label_es": "Nuestra Primarina (14 SpA+) → Regidrago rival (0 HP/0 SpD)",
            "label_en": "Our Primarina (14 SpA+) → Opposing Regidrago (0 HP/0 SpD)",
        },
        {
            "att": "Primarina", "att_sp": 14, "att_nat": 1.1, "att_stg": 0,
            "def": "Garchomp-Mega-Z", "def_hp_sp": 4, "def_def_sp": 0, "def_nat": 1.0, "def_stg": 0,
            "move": "Moonblast", "bp": 95, "mtype": "Fairy", "cat": "Special",
            "label_es": "Nuestra Primarina (14 SpA+) → Garchomp-Mega-Z (4 HP/0 SpD)",
            "label_en": "Our Primarina (14 SpA+) → Garchomp-Mega-Z (4 HP/0 SpD)",
        },
        {
            "att": "Dondozo", "att_sp": 32, "att_nat": 1.1, "att_stg": 2,
            "def": "Primarina", "def_hp_sp": 32, "def_def_sp": 16, "def_nat": 1.0, "def_stg": 0,
            "move": "Wave Crash (+2 Atk)", "bp": 120, "mtype": "Water", "cat": "Physical",
            "label_es": "DEFENSIVO: +2 Dondozo Wave Crash → Nuestra Primarina (32 HP/16 Def)",
            "label_en": "DEFENSIVE: +2 Dondozo Wave Crash → Our Primarina (32 HP/16 Def)",
        },
        {
            "att": "Regidrago", "att_sp": 32, "att_nat": 1.0, "att_stg": 0, "item": 1.2, "ability_mult": 1.5, "spread": True,
            "def": "Heatran-Mega", "def_hp_sp": 24, "def_def_sp": 4, "def_nat": 1.0, "def_stg": 0,
            "move": "Dragon Energy (150 BP Spread)", "bp": 150, "mtype": "Dragon", "cat": "Special",
            "label_es": "DEFENSIVO: Regidrago rival Dragon Energy → Nuestro Mega Heatran",
            "label_en": "DEFENSIVE: Opposing Regidrago Dragon Energy → Our Mega Heatran",
        },
        {
            "att": "Heatran-Mega", "att_sp": 32, "att_nat": 1.1, "att_stg": 0,
            "def": "Incineroar", "def_hp_sp": 32, "def_def_sp": 12, "def_nat": 1.1, "def_stg": 0,
            "move": "Earth Power", "bp": 90, "mtype": "Ground", "cat": "Special",
            "label_es": "DEFENSIVO: 32 SpA+ Mega Heatran Earth Power → Nuestro Incineroar",
            "label_en": "DEFENSIVE: 32 SpA+ Mega Heatran Earth Power → Our Incineroar",
        },
    ],
    "lead_modes": [
        {
            "lead": ["Regieleki", "Regidrago"],
            "back": ["Heatran-Mega", "Amoonguss"],
            "vs_es": "vs. Balance / Tailwind / Mega Tatsugiri / Rain",
            "vs_en": "vs. Balance / Tailwind / Mega Tatsugiri / Rain",
            "plan_es": "Electroweb Turno 1 baja a los Base 130 a 133 Spe para que Regidrago (145) lance Dragon Energy al 100% HP. Si hay Hada/Acero en campo, Volt Switch hacia Amoonguss o Mega Heatran y recicla Pollen Puff.",
            "plan_en": "Turn-1 Electroweb drops Base-130 foes to 133 Spe so Timid Regidrago (145) nukes at full 150-BP Dragon Energy. Against Fairy/Steel leads, Volt Switch into Amoonguss or Mega Heatran and loop Pollen Puff.",
        },
        {
            "lead": ["Regieleki", "Primarina"],
            "back": ["Amoonguss", "Incineroar"],
            "vs_es": "vs. +2 DozoGiri & Costar Flamigo",
            "vs_en": "vs. +2 DozoGiri & Costar Flamigo",
            "plan_es": "Doble presión inmediata: Regieleki amenaza Transistor Thunderbolt (2HKO a través de +2 SpD) mientras Primarina sobrevive +2 Wave Crash para pulsar Haze y Amoonguss espera atrás con Clear Smog + Rocky Helmet.",
            "plan_en": "Immediate dual lock: Regieleki threatens Transistor Thunderbolt (guaranteed 2HKO through +2 SpD) while Primarina tanks +2 Wave Crash for Haze and Amoonguss backs it up with Clear Smog + Rocky Helmet.",
        },
        {
            "lead": ["Incineroar", "Amoonguss"],
            "back": ["Heatran-Mega", "Primarina"],
            "vs_es": "vs. Hard Trick Room (Farigiraf / Mega Heatran / Amoonguss)",
            "vs_en": "vs. Hard Trick Room (Farigiraf / Mega Heatran / Amoonguss)",
            "plan_es": "Fake Out + Taunt sobre el setter de TR o Spore bajo Trick Room (Amoonguss 50 Spe secuestra el tablero). Mega Heatran (16 Spe) garantiza OHKO 16/16 en espejo de Heatran con Earth Power.",
            "plan_en": "Fake Out + Taunt denies TR setters, or Amoonguss (50 Spe) hijacks Trick Room with Spore + Pollen Puff. Our Mega Heatran (103 Spe) wins the Heatran mirror with a guaranteed 16/16 Earth Power OHKO.",
        },
        {
            "lead": ["Heatran-Mega", "Primarina"],
            "back": ["Incineroar", "Regidrago"],
            "vs_es": "vs. Regieleki + Regidrago / Mega Latios + Terrakion",
            "vs_en": "vs. Regieleki + Regidrago / Mega Latios + Terrakion",
            "plan_es": "Doble núcleo Dragón-Acero-Hada: Primarina bloquea 0× a Regidrago y OHKOa con Moonblast mientras Mega Heatran aplasta Hadas/Aceros y resiste Dragon Energy / Luster Purge. Incineroar entra con Intimidate sobre Terrakion.",
            "plan_en": "Dragon-Steel-Fairy lock: Primarina hard-blanks opposing Regidrago (0×) and OHKOs back with Moonblast while Mega Heatran crushes Fairies/Steels and resists Dragon Energy / Luster Purge. Incineroar checks Terrakion via Intimidate.",
        },
    ],
}


TYPE_COLORS: Dict[str, str] = {
    "Fire": "#f97316",
    "Steel": "#94a3b8",
    "Water": "#38bdf8",
    "Dragon": "#818cf8",
    "Grass": "#22c55e",
    "Poison": "#c084fc",
    "Psychic": "#f472b6",
    "Rock": "#d97706",
    "Fighting": "#ef4444",
    "Normal": "#cbd5e1",
    "Flying": "#7dd3fc",
    "Ghost": "#a855f7",
    "Fairy": "#f9a8d4",
    "Ground": "#eab308",
    "Ice": "#67e8f9",
    "Electric": "#facc15",
    "Dark": "#94a3b8",
    "Bug": "#a3e635",
}


def _resolve_sprite_path(kind: str, fname: Optional[str], species: str, slug_map: Dict[str, Any]) -> Path:
    if kind == "md" and fname:
        return SPRITES_MD / fname
    if kind == "rumored" and fname:
        return SPRITES_MD_RUMORED / fname
    if kind == "mc_or_md" and fname:
        p_md = SPRITES_MD / fname
        if p_md.is_file():
            return p_md
    rel = slug_map.get("species", {}).get(species) or slug_map.get("species", {}).get(species.lower())
    if rel:
        return REPO_ROOT / rel
    return SPRITES_MC / f"{species.lower()}.png"


def _lookup_species_stats_types(
    species: str,
    md_by_name: Dict[str, Dict[str, Any]],
    reg: Any,
) -> Tuple[List[int], List[str]]:
    """Resolve `(stats_6, types)` from `MD_CATALOG` or in-memory DuckDB `pokedex`."""
    if species in md_by_name:
        return list(md_by_name[species]["stats"]), list(md_by_name[species]["types"])
    row = reg.get_pokemon(species)
    if row:
        bs = row.get("baseStats") or {}
        stats = [
            int(bs.get("hp", 80)),
            int(bs.get("atk", 80)),
            int(bs.get("def", 80)),
            int(bs.get("spa", 80)),
            int(bs.get("spd", 80)),
            int(bs.get("spe", 80)),
        ]
        types = [str(t) for t in (row.get("types") or ["Normal"])]
        return stats, types
    return [80, 80, 80, 80, 80, 80], ["Normal"]


def generate_report(out_path: Path = DEFAULT_OUT) -> Path:
    """Query DuckDB, run exact Champions 16-roll benchmarks, embed Base64 sprites, and write HTML."""
    reg = get_registry()
    con = reg.con
    slug_map = json.loads(SLUG_MAP_PATH.read_text(encoding="utf-8"))
    md_by_name = {m["name"]: m for m in MD_CATALOG}

    # Live DuckDB telemetry across all ingested tournaments (including LAIC 2027)
    tourn_rows = con.execute(
        """
        SELECT tournament_id, COUNT(DISTINCT player_name) AS players, COUNT(*) AS slots
        FROM tournament_team_slots
        GROUP BY tournament_id
        ORDER BY tournament_id
        """
    ).fetchall()
    n_tournaments = len(tourn_rows)
    total_players = sum(int(r[1]) for r in tourn_rows)
    total_slots = sum(int(r[2]) for r in tourn_rows)

    top_mc_rows = con.execute(
        """
        SELECT species, COUNT(*) AS cnt,
               ROUND(100.0 * COUNT(*) / ?, 2) AS pct
        FROM tournament_team_slots
        GROUP BY species
        ORDER BY cnt DESC
        LIMIT 24
        """,
        [max(1, total_players)],
    ).fetchall()
    mc_usage_map = {str(sp): (int(cnt), float(pct)) for sp, cnt, pct in top_mc_rows}

    # Pre-encode community logos & reusable sprite URI cache
    pokemmunity_b64 = _b64_png(COMMUNITY_DIR / "pokemmunity.png")
    pokemex_b64 = _b64_png(COMMUNITY_DIR / "pokemex.png")
    sprite_uri_cache: Dict[str, str] = {}

    def get_spr(species: str, kind: str = "mc", fname: Optional[str] = None) -> str:
        cache_k = f"{kind}:{fname or species}"
        if cache_k not in sprite_uri_cache:
            sprite_uri_cache[cache_k] = _b64_png(_resolve_sprite_path(kind, fname, species, slug_map))
        return sprite_uri_cache[cache_k]

    # -------------------------------------------------------------------------
    # SECTION A: Top-20 Reg M-C -> M-D Meta Impact Matrix
    # -------------------------------------------------------------------------
    shift_rows_html: List[str] = []
    shift_species_ordered = [sp for sp, _cnt, _pct in top_mc_rows if sp in MC_SHIFT_NOTES]
    for sp in MC_SHIFT_NOTES:
        if sp not in shift_species_ordered:
            shift_species_ordered.append(sp)
    for sp in shift_species_ordered[:20]:
        info = MC_SHIFT_NOTES[sp]
        cnt, pct = mc_usage_map.get(sp, (0, 0.0))
        if cnt == 0:
            row_u = con.execute(
                "SELECT COUNT(*) FROM tournament_team_slots WHERE species = ?;", [sp]
            ).fetchone()
            cnt = int(row_u[0]) if row_u else 0
            pct = round(100.0 * cnt / max(1, total_players), 1)
        tr = info["trend"]
        tr_badge_es = {"up": "📈 SUBE", "down": "📉 BAJA", "pivot": "🔄 AJUSTE TECH"}[tr]
        tr_badge_en = {"up": "📈 STOCK UP", "down": "📉 STOCK DOWN", "pivot": "🔄 TECH PIVOT"}[tr]
        tr_cls = f"trend-{tr}"
        sp_b64 = get_spr(sp, "mc", None)
        shift_rows_html.append(
            f"""<tr class="shift-row" data-trend="{tr}">
              <td class="shift-mon-cell"><img src="{sp_b64}" alt="{html.escape(sp)}" /><strong>{html.escape(sp)}</strong></td>
              <td class="num"><strong>{pct:.1f}%</strong> <span class="muted">({cnt})</span></td>
              <td><span class="trend-pill {tr_cls}" data-es="{tr_badge_es}" data-en="{tr_badge_en}">{tr_badge_es}</span></td>
              <td data-es="{html.escape(info['es'])}" data-en="{html.escape(info['en'])}">{html.escape(info['es'])}</td>
            </tr>"""
        )

    # -------------------------------------------------------------------------
    # SECTION B: Exact Champions Lv.50 16-Roll Damage Benchmarks
    # -------------------------------------------------------------------------
    calc_cards_html: List[str] = []
    for spec in DAMAGE_BENCHMARK_SPECS:
        a_stats, a_types = _lookup_species_stats_types(spec["att"], md_by_name, reg)
        d_stats, d_types = _lookup_species_stats_types(spec["def"], md_by_name, reg)
        res = _calc_champions_16_rolls(
            att_stats=a_stats,
            att_types=a_types,
            att_sp=spec["att_sp"],
            att_nature=spec["att_nat"],
            att_stage=spec["att_stg"],
            def_stats=d_stats,
            def_types=d_types,
            def_hp_sp=spec["def_hp_sp"],
            def_def_sp=spec["def_def_sp"],
            def_nature=spec["def_nat"],
            def_stage=spec["def_stg"],
            move_bp=spec["bp"],
            move_type=spec["mtype"],
            category=spec["cat"],
            is_spread=bool(spec.get("spread", False)),
            weather_mult=float(spec.get("weather", 1.0)),
            terrain_mult=float(spec.get("terrain", 1.0)),
            item_mult=float(spec.get("item", 1.0)),
            ability_mult=float(spec.get("ability_mult", 1.0)),
            adaptability=bool(spec.get("adaptability", False)),
        )
        ak, af = spec["att_kind"]
        dk, df = spec.get("def_kind", ("mc", None))
        a_spr = get_spr(spec["att"], ak, af)
        d_spr = get_spr(spec["def"], dk, df)
        m_col = TYPE_COLORS.get(spec["mtype"], "#38bdf8")
        bar_w = min(100.0, res["max_pct"])
        min_w = min(100.0, res["min_pct"])
        st_cls = "badge-confirmed" if spec["status"] == "confirmed" else "badge-rumored"
        st_es = "✅ CONFIRMADO" if spec["status"] == "confirmed" else "🔮 OLA ESPERADA"
        st_en = "✅ CONFIRMED" if spec["status"] == "confirmed" else "🔮 EXPECTED WAVE"
        calc_cards_html.append(
            f"""<article class="calc-card" data-calc-group="{spec['group']}" data-status="{spec['status']}">
              <div class="calc-head">
                <span class="status-badge {st_cls}" data-es="{st_es}" data-en="{st_en}">{st_es}</span>
                <span class="type-pill" style="border-color:{m_col};color:{m_col}">{html.escape(spec['move'])} ({spec['bp']} BP)</span>
              </div>
              <div class="calc-matchup">
                <div class="calc-side"><img src="{a_spr}" alt="{html.escape(spec['att'])}" /><span>{html.escape(spec['att_label'])}</span></div>
                <span class="calc-vs">→</span>
                <div class="calc-side"><img src="{d_spr}" alt="{html.escape(spec['def'])}" /><span>{html.escape(spec['def_label'])}</span></div>
              </div>
              <div class="calc-bar-wrap">
                <div class="calc-bar-track">
                  <div class="calc-bar-max {res['tier_cls']}" style="width:{bar_w:.1f}%"></div>
                  <div class="calc-bar-min {res['tier_cls']}" style="width:{min_w:.1f}%"></div>
                </div>
                <div class="calc-nums">
                  <strong>{res['min_pct']:.1f}% – {res['max_pct']:.1f}%</strong>
                  <span class="muted">({res['min_dmg']}–{res['max_dmg']} / {res['def_hp']} HP)</span>
                  <span class="calc-verdict {res['tier_cls']}" data-es="{html.escape(res['verdict_es'])}" data-en="{html.escape(res['verdict_en'])}">{html.escape(res['verdict_es'])}</span>
                </div>
              </div>
              <div class="calc-ctx" data-es="{html.escape(spec['ctx_es'])}" data-en="{html.escape(spec['ctx_en'])}">{html.escape(spec['ctx_es'])}</div>
            </article>"""
        )

    # -------------------------------------------------------------------------
    # SECTION C: Interactive Comparative Speed Tiers Ladder Data (JSON embedded)
    # -------------------------------------------------------------------------
    speed_ladder_data: List[Dict[str, Any]] = []
    for sp, base_spe, origin, note in SPEED_LADDER_ENTRIES:
        s_neg, s0, s32, s32p = _l50_speed_range(base_spe)
        if origin == "confirmed" and sp in md_by_name:
            k, f = md_by_name[sp]["sprite"]
        elif origin == "rumored" and sp in md_by_name:
            k, f = md_by_name[sp]["sprite"]
        else:
            k, f = "mc", None
        speed_ladder_data.append(
            {
                "sp": sp,
                "base": base_spe,
                "origin": origin,
                "note": note,
                "spr": get_spr(sp, k, f),
                "s_neg": s_neg,
                "s0": s0,
                "s32": s32,
                "s32p": s32p,
                "tw_32": s32 * 2,
                "tw_32p": s32p * 2,
                "scarf_32": int(math.floor(s32 * 1.5)),
                "scarf_32p": int(math.floor(s32p * 1.5)),
            }
        )

    # -------------------------------------------------------------------------
    # SECTION D: 4 Deep Counterplay Playbooks
    # -------------------------------------------------------------------------
    playbooks_html: List[str] = []
    for pb in PLAYBOOKS:
        b_es_html = "".join(f"<li>{item}</li>" for item in pb["bullets_es"])
        b_en_html = "".join(f"<li>{item}</li>" for item in pb["bullets_en"])
        playbooks_html.append(
            f"""<article class="pb-card">
              <div class="pb-tag" data-es="{html.escape(pb['tag_es'])}" data-en="{html.escape(pb['tag_en'])}">{html.escape(pb['tag_es'])}</div>
              <h3 class="pb-title">{pb['icon']} <span data-es="{html.escape(pb['title_es'])}" data-en="{html.escape(pb['title_en'])}">{html.escape(pb['title_es'])}</span></h3>
              <p class="pb-summary" data-es="{html.escape(pb['summary_es'])}" data-en="{html.escape(pb['summary_en'])}">{html.escape(pb['summary_es'])}</p>
              <ul class="pb-list lang-es-only">{b_es_html}</ul>
              <ul class="pb-list lang-en-only hidden">{b_en_html}</ul>
            </article>"""
        )

    # -------------------------------------------------------------------------
    # SECTION E: Interactive 6-Mon M-D Readiness Checker Pool
    # -------------------------------------------------------------------------
    readiness_pool_data: List[Dict[str, Any]] = []
    for item in READINESS_ROSTER_POOL:
        k, f = item["kind"]
        readiness_pool_data.append(
            {
                "sp": item["sp"],
                "spr": get_spr(item["sp"], k, f),
                "tags": item["tags"],
                "is_md": k != "mc",
            }
        )

    # -------------------------------------------------------------------------
    # SECTION F: Unified Tier List Cards
    # -------------------------------------------------------------------------
    tier_order = ["S", "A", "B", "Niche"]
    tier_sections_html: List[str] = []
    confirmed_count = sum(1 for m in MD_CATALOG if m["status"] == "confirmed")
    rumored_count = sum(1 for m in MD_CATALOG if m["status"] == "rumored")
    mega_count = sum(1 for m in MD_CATALOG if "mega" in m["roles"])

    for tier in tier_order:
        mons = [m for m in MD_CATALOG if m["tier"] == tier]
        if not mons:
            continue
        cards: List[str] = []
        for m in mons:
            kind, fname = m["sprite"]
            sp_b64 = get_spr(m["name"], kind, fname)
            alt_imgs = ""
            for ak, af in m.get("alt_sprites", []):
                ab64 = get_spr(f"{m['name']}:{af}", ak, af)
                if ab64:
                    alt_imgs += f'<img class="alt-spr" src="{ab64}" alt="{html.escape(m["display"])}" />'
            stone_img = ""
            if m.get("stone"):
                sb64 = _b64_png(MEGASTONES_DIR / m["stone"])
                if sb64:
                    stone_img = f'<img class="stone-ico" src="{sb64}" alt="Mega Stone" title="{html.escape(m["stone"].replace(".png", "").title())}" />'

            is_conf = m["status"] == "confirmed"
            badge_cls = "badge-confirmed" if is_conf else "badge-rumored"
            badge_es = "✅ CONFIRMADO M-D" if is_conf else "🔮 OLA ESPERADA (RUMOR)"
            badge_en = "✅ CONFIRMED M-D" if is_conf else "🔮 EXPECTED WAVE (RUMORED / UNCONFIRMED)"
            types_html = "".join(
                f'<span class="type-pill" style="border-color:{TYPE_COLORS.get(t, "#64748b")};color:{TYPE_COLORS.get(t, "#e2e8f0")}">{html.escape(t)}</span>'
                for t in m["types"]
            )
            hp, atk, df, spa, spd, spe = m["stats"]
            bst = sum(m["stats"])
            s_neg, s0, s32, s32p = _l50_speed_range(spe)

            partner_chips = "".join(f'<span class="mini-tag">{html.escape(p)}</span>' for p in m["partners"])
            check_chips = "".join(f'<span class="mini-tag danger">{html.escape(c)}</span>' for c in m["checks"])
            roles_attr = " ".join(m["roles"] + [m["status"]])

            cards.append(
                f"""<article class="mon-card {badge_cls}-card" data-status="{m['status']}" data-roles="{roles_attr}" data-search="{html.escape((m['display'] + ' ' + m['name'] + ' ' + ' '.join(m['types']) + ' ' + m['ability']).lower())}">
                  <div class="mon-head">
                    <div class="mon-spr-wrap">
                      <img class="main-spr" src="{sp_b64}" alt="{html.escape(m['display'])}" />
                      {stone_img}
                    </div>
                    <div class="mon-title-col">
                      <div class="mon-badges-row">
                        <span class="status-badge {badge_cls}" data-es="{badge_es}" data-en="{badge_en}">{badge_es}</span>
                        <span class="bst-chip">BST {bst}</span>
                      </div>
                      <h3 class="mon-name">{html.escape(m['display'])}</h3>
                      <div class="type-row">{types_html}{alt_imgs}</div>
                    </div>
                  </div>
                  <div class="mon-ability"><strong>Ability:</strong> {html.escape(m['ability'])}</div>
                  <div class="stat-grid">
                    <span>HP <b>{hp}</b></span><span>Atk <b>{atk}</b></span><span>Def <b>{df}</b></span>
                    <span>SpA <b>{spa}</b></span><span>SpD <b>{spd}</b></span><span>Spe <b>{spe}</b></span>
                  </div>
                  <div class="spe-bench">
                    <span data-es="Vel Lv.50 (31 IV):" data-en="Lv.50 Spe (31 IV):">Vel Lv.50 (31 IV):</span>
                    <b>{s_neg}</b> (-Spe) · <b>{s0}</b> (0 SP) · <b>{s32}</b> (32 SP) · <b>{s32p}</b> (+Spe)
                  </div>
                  <p class="mon-note" data-es="{html.escape(m['es'])}" data-en="{html.escape(m['en'])}">{html.escape(m['es'])}</p>
                  <div class="mon-meta-rows">
                    <div><span class="meta-lbl" data-es="Socios M-C:" data-en="M-C Partners:">Socios M-C:</span> {partner_chips}</div>
                    <div><span class="meta-lbl" data-es="Checks M-C:" data-en="M-C Checks:">Checks M-C:</span> {check_chips}</div>
                  </div>
                </article>"""
            )
        tier_label_es = {
            "S": "Tier S — Pilares del Meta Regulation M-D",
            "A": "Tier A — Amenazas y Socios Top Cut",
            "B": "Tier B — Roles Especializados y Techs",
            "Niche": "Watchlist — Opciones de Nicho",
        }[tier]
        tier_label_en = {
            "S": "Tier S — Regulation M-D Meta Pillars",
            "A": "Tier A — Top Cut Threats & Enablers",
            "B": "Tier B — Specialized Roles & Techs",
            "Niche": "Watchlist — Niche / Tech Picks",
        }[tier]
        tier_sections_html.append(
            f"""<section class="tier-section" data-tier="{tier}">
              <h2 class="tier-heading tier-{tier.lower()}" data-es="{tier_label_es}" data-en="{tier_label_en}">{tier_label_es}</h2>
              <div class="mon-grid">{''.join(cards)}</div>
            </section>"""
        )

    # -------------------------------------------------------------------------
    # SECTION G: 6 Copy-Pasteable LAIC 2027 -> M-D Team Blueprints
    # -------------------------------------------------------------------------
    blueprint_cards_html: List[str] = []
    for bp in TEAM_BLUEPRINTS:
        is_conf = bp["badge_status"] == "confirmed"
        b_cls = "badge-confirmed" if is_conf else "badge-rumored"
        b_es = "✅ SOLO CONFIRMADOS M-D" if is_conf else "🔮 INCLUYE OLA ESPERADA"
        b_en = "✅ CONFIRMED M-D ONLY" if is_conf else "🔮 INCLUDES EXPECTED WAVE"
        team_slots_html: List[str] = []
        for sp, skind, sfname in bp["adapted_team"]:
            sb64 = get_spr(sp, skind, sfname)
            is_new = sp in bp["swap_in"]
            slot_cls = "team-slot is-new" if is_new else "team-slot"
            new_tag = '<span class="new-pill">NEW</span>' if is_new else ""
            team_slots_html.append(
                f"""<div class="{slot_cls}">
                  {new_tag}
                  <img src="{sb64}" alt="{html.escape(sp)}" />
                  <span>{html.escape(sp)}</span>
                </div>"""
            )
        swaps_str = f"{', '.join(bp['swap_out'])} → {', '.join(bp['swap_in'])}"
        paste_escaped = html.escape(bp["paste"])
        blueprint_cards_html.append(
            f"""<article class="bp-card" data-status="{bp['badge_status']}">
              <div class="bp-head">
                <span class="status-badge {b_cls}" data-es="{b_es}" data-en="{b_en}">{b_es}</span>
                <span class="bp-source">DuckDB · {html.escape(bp['source_label'])}</span>
              </div>
              <h3 class="bp-title" data-es="{html.escape(bp['title_es'])}" data-en="{html.escape(bp['title_en'])}">{html.escape(bp['title_es'])}</h3>
              <div class="bp-swap-row">
                <span class="bp-swap-pill"><strong>Swap:</strong> {html.escape(swaps_str)}</span>
                <button class="copy-paste-btn" type="button" data-paste="{paste_escaped}" data-es="📋 Copiar Showdown Paste" data-en="📋 Copy Showdown Paste">📋 Copiar Showdown Paste</button>
              </div>
              <div class="bp-team-row">{''.join(team_slots_html)}</div>
              <p class="bp-note" data-es="{html.escape(bp['note_es'])}" data-en="{html.escape(bp['note_en'])}">{html.escape(bp['note_es'])}</p>
            </article>"""
        )

    # -------------------------------------------------------------------------
    # SECTION H: Coach Porygon's Signature Regulation M-D Team ("Iron-Volt Crown")
    # -------------------------------------------------------------------------
    sig_team = COACH_PORYGON_SIGNATURE_TEAM
    sig_paste_blocks: List[str] = []
    sig_roster_cards_html: List[str] = []
    for mon in sig_team["roster"]:
        sp_map = mon["sp"]
        sp_total = sum(int(v) for v in sp_map.values())
        assert sp_total == 66, f"Signature mon {mon['species']} SP sum={sp_total} != 66"
        assert all(0 <= int(v) <= 32 for v in sp_map.values()), f"Signature mon {mon['species']} SP out of [0,32]"
        assert all("tera blast" not in mv.lower() for mv in mon["moves"]), "Tera Blast forbidden in Champions!"

        base_stats, mon_types = _lookup_species_stats_types(mon["species"], md_by_name, reg)
        nat_plus, nat_minus = _NATURE_MULT_MAP.get(mon["nature"], (None, None))
        stat_keys = ["hp", "atk", "def", "spa", "spd", "spe"]
        l50_vals: Dict[str, int] = {}
        ev_parts: List[str] = []
        sp_parts: List[str] = []
        ev_labels = {"hp": "HP", "atk": "Atk", "def": "Def", "spa": "SpA", "spd": "SpD", "spe": "Spe"}
        for idx, k in enumerate(stat_keys):
            sp_v = int(sp_map.get(k, 0))
            if k == "hp":
                l50_vals[k] = _l50_hp(base_stats[0], sp_v)
            else:
                mult = 1.1 if nat_plus == k else (0.9 if nat_minus == k else 1.0)
                l50_vals[k] = _l50_stat(base_stats[idx], sp_v, mult)
            if sp_v > 0:
                ev_parts.append(f"{_sp_to_ev(sp_v)} {ev_labels[k]}")
                sp_parts.append(f"{sp_v} {ev_labels[k]}")

        paste_lines = [
            f"{mon['paste_species']} @ {mon['item']}",
            f"Ability: {mon['paste_ability']}",
            "Level: 50",
            f"EVs: {' / '.join(ev_parts)}",
            f"{mon['nature']} Nature",
        ] + [f"- {mv}" for mv in mon["moves"]]
        sig_paste_blocks.append("\n".join(paste_lines))

        sk, sf = mon["sprite"]
        sp_b64 = get_spr(mon["species"], sk, sf)
        stone_img = ""
        if mon.get("stone"):
            sb64 = _b64_png(MEGASTONES_DIR / mon["stone"])
            if sb64:
                stone_img = f'<img class="stone-ico" src="{sb64}" alt="Mega Stone" />'
        types_html = "".join(
            f'<span class="type-pill" style="border-color:{TYPE_COLORS.get(t, "#64748b")};color:{TYPE_COLORS.get(t, "#e2e8f0")}">{html.escape(t)}</span>'
            for t in mon_types
        )
        moves_html = "".join(f'<span class="sig-move-pill">{html.escape(mv)}</span>' for mv in mon["moves"])
        sig_roster_cards_html.append(
            f"""<article class="sig-mon-card">
              <div class="mon-head">
                <div class="mon-spr-wrap">
                  <img class="main-spr" src="{sp_b64}" alt="{html.escape(mon['display'])}" />
                  {stone_img}
                </div>
                <div class="mon-title-col">
                  <div class="mon-badges-row">
                    <span class="status-badge badge-gold">66 SP ✓</span>
                    <span class="bst-chip">@ {html.escape(mon['item'])}</span>
                  </div>
                  <h3 class="mon-name">{html.escape(mon['display'])}</h3>
                  <div class="type-row">{types_html}</div>
                </div>
              </div>
              <div class="sig-role" data-es="{html.escape(mon['role_es'])}" data-en="{html.escape(mon['role_en'])}">{html.escape(mon['role_es'])}</div>
              <div class="mon-ability"><strong>Ability:</strong> {html.escape(mon['ability'])} · <strong>{html.escape(mon['nature'])}</strong></div>
              <div class="sig-sp-line"><strong>66 SP:</strong> {html.escape(' / '.join(sp_parts))}</div>
              <div class="stat-grid">
                <span>HP <b>{l50_vals['hp']}</b></span><span>Atk <b>{l50_vals['atk']}</b></span><span>Def <b>{l50_vals['def']}</b></span>
                <span>SpA <b>{l50_vals['spa']}</b></span><span>SpD <b>{l50_vals['spd']}</b></span><span>Spe <b>{l50_vals['spe']}</b></span>
              </div>
              <div class="sig-moves-row">{moves_html}</div>
              <p class="mon-note" data-es="{html.escape(mon['rationale_es'])}" data-en="{html.escape(mon['rationale_en'])}">{html.escape(mon['rationale_es'])}</p>
            </article>"""
        )

    sig_full_paste = "\n\n".join(sig_paste_blocks)
    sig_full_paste_esc = html.escape(sig_full_paste)

    sig_proof_rows_html: List[str] = []
    for pspec in sig_team["proof_calcs"]:
        a_st, a_ty = _lookup_species_stats_types(pspec["att"], md_by_name, reg)
        d_st, d_ty = _lookup_species_stats_types(pspec["def"], md_by_name, reg)
        pres = _calc_champions_16_rolls(
            att_stats=a_st,
            att_types=a_ty,
            att_sp=pspec["att_sp"],
            att_nature=pspec["att_nat"],
            att_stage=pspec["att_stg"],
            def_stats=d_st,
            def_types=d_ty,
            def_hp_sp=pspec["def_hp_sp"],
            def_def_sp=pspec["def_def_sp"],
            def_nature=pspec["def_nat"],
            def_stage=pspec["def_stg"],
            move_bp=pspec["bp"],
            move_type=pspec["mtype"],
            category=pspec["cat"],
            is_spread=bool(pspec.get("spread", False)),
            item_mult=float(pspec.get("item", 1.0)),
            ability_mult=float(pspec.get("ability_mult", 1.0)),
        )
        m_col = TYPE_COLORS.get(pspec["mtype"], "#38bdf8")
        sig_proof_rows_html.append(
            f"""<tr>
              <td data-es="{html.escape(pspec['label_es'])}" data-en="{html.escape(pspec['label_en'])}">{html.escape(pspec['label_es'])}</td>
              <td><span class="type-pill" style="border-color:{m_col};color:{m_col}">{html.escape(pspec['move'])}</span></td>
              <td class="num"><strong>{pres['min_pct']:.1f}% – {pres['max_pct']:.1f}%</strong> <span class="muted">({pres['min_dmg']}–{pres['max_dmg']}/{pres['def_hp']})</span></td>
              <td><span class="calc-verdict {pres['tier_cls']}" data-es="{html.escape(pres['verdict_es'])}" data-en="{html.escape(pres['verdict_en'])}">{html.escape(pres['verdict_es'])}</span></td>
            </tr>"""
        )

    sig_sprite_lookup = {m["species"]: m["sprite"] for m in sig_team["roster"]}
    sig_modes_html: List[str] = []
    for lm in sig_team["lead_modes"]:
        lead_imgs = "".join(
            f'<div class="sig-mini-mon"><img src="{get_spr(sp, *sig_sprite_lookup[sp])}" alt="{html.escape(sp)}" /><span>{html.escape(sp)}</span></div>'
            for sp in lm["lead"]
        )
        back_imgs = "".join(
            f'<div class="sig-mini-mon back"><img src="{get_spr(sp, *sig_sprite_lookup[sp])}" alt="{html.escape(sp)}" /><span>{html.escape(sp)}</span></div>'
            for sp in lm["back"]
        )
        sig_modes_html.append(
            f"""<article class="sig-mode-card">
              <div class="pb-tag" data-es="{html.escape(lm['vs_es'])}" data-en="{html.escape(lm['vs_en'])}">{html.escape(lm['vs_es'])}</div>
              <div class="sig-mode-sprites">
                <div class="sig-mode-group"><span class="meta-lbl">LEAD</span>{lead_imgs}</div>
                <span class="calc-vs">+</span>
                <div class="sig-mode-group"><span class="meta-lbl">BACK</span>{back_imgs}</div>
              </div>
              <p class="bp-note" data-es="{html.escape(lm['plan_es'])}" data-en="{html.escape(lm['plan_en'])}">{html.escape(lm['plan_es'])}</p>
            </article>"""
        )

    sig_pillars_es_html = "".join(f"<li>{p}</li>" for p in sig_team["pillars_es"])
    sig_pillars_en_html = "".join(f"<li>{p}</li>" for p in sig_team["pillars_en"])

    gen_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    speed_json = json.dumps(speed_ladder_data, ensure_ascii=False).replace("</", "<\\/")
    readiness_json = json.dumps(readiness_pool_data, ensure_ascii=False).replace("</", "<\\/")

    doc = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Coach Porygon VGC — Regulation M-D Tournament Prep Dossier (Offline Base64)</title>
  <style>
    :root {{
      --bg: #060a14; --surface: #0d1526; --surface-2: #131f37;
      --border: #1e2d4d; --text: #f1f5f9; --muted: #94a3b8;
      --cyan: #22d3ee; --magenta: #f43f5e; --gold: #facc15; --emerald: #22c55e; --indigo: #818cf8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; padding: 0; background: var(--bg); color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
      font-size: 13px; line-height: 1.5;
      background-image: radial-gradient(ellipse 80% 45% at 15% -5%, rgba(34,211,238,0.09), transparent 65%),
                        radial-gradient(ellipse 65% 40% at 88% 0%, rgba(244,63,94,0.08), transparent 60%);
    }}
    .ribbon {{ height: 3px; background: linear-gradient(90deg, var(--cyan), #3b82f6, var(--magenta), var(--gold), var(--cyan)); }}
    .wrap {{ max-width: 1280px; margin: 0 auto; padding: 18px 16px 40px; }}
    .hero {{
      background: linear-gradient(135deg, rgba(13,21,38,0.96), rgba(19,31,55,0.92));
      border: 1px solid var(--border); border-radius: 14px; padding: 18px 20px; margin-bottom: 14px;
      box-shadow: 0 12px 32px rgba(0,0,0,0.4);
    }}
    .hero-top {{ display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 8px; }}
    .pill-row {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }}
    .pill {{
      font-size: 10.5px; font-weight: 700; letter-spacing: 0.04em; padding: 3px 9px; border-radius: 999px;
      border: 1px solid rgba(34,211,238,0.35); background: rgba(34,211,238,0.1); color: var(--cyan);
    }}
    .pill.gold {{ border-color: rgba(250,204,21,0.4); background: rgba(250,204,21,0.12); color: var(--gold); }}
    .pill.mag {{ border-color: rgba(244,63,94,0.4); background: rgba(244,63,94,0.12); color: #fda4af; }}
    .lang-toggle {{ display: inline-flex; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }}
    .lang-btn {{ background: transparent; color: var(--muted); border: 0; padding: 5px 11px; font-weight: 700; cursor: pointer; font-size: 11.5px; }}
    .lang-btn.active {{ background: var(--cyan); color: #06101d; }}
    h1 {{ margin: 4px 0 6px; font-size: 22px; letter-spacing: -0.02em; }}
    .hero-sub {{ margin: 0; color: var(--muted); max-width: 980px; }}
    .callout-warn {{
      margin-top: 10px; padding: 9px 13px; border-radius: 10px;
      background: rgba(250,204,21,0.08); border: 1px solid rgba(250,204,21,0.32); font-size: 12px; color: #fef08a;
    }}
    .nav-tabs {{
      display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px;
      position: sticky; top: 8px; z-index: 30;
      background: rgba(6,10,20,0.92); backdrop-filter: blur(10px);
      border: 1px solid var(--border); border-radius: 12px; padding: 8px 10px;
    }}
    .nav-tab {{
      background: var(--surface-2); color: var(--text); border: 1px solid var(--border);
      border-radius: 8px; padding: 6px 12px; font-size: 12px; font-weight: 700; cursor: pointer;
    }}
    .nav-tab.active {{ background: rgba(34,211,238,0.2); border-color: var(--cyan); color: var(--cyan); }}
    .dossier-panel {{ display: none; }}
    .dossier-panel.active {{ display: block; }}
    .sec-card {{
      background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; margin-bottom: 16px;
    }}
    .sec-title {{ font-size: 13.5px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.05em; color: var(--cyan); margin: 0 0 8px; }}
    .muted {{ color: var(--muted); font-weight: 400; }}
    .toolbar {{
      display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px;
      margin-bottom: 14px;
    }}
    .filter-row {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    .f-btn {{
      background: var(--surface-2); color: var(--text); border: 1px solid var(--border); border-radius: 999px;
      padding: 5px 11px; font-size: 11.5px; font-weight: 700; cursor: pointer;
    }}
    .f-btn.active {{ background: rgba(34,211,238,0.2); border-color: var(--cyan); color: var(--cyan); }}
    .search-inp {{
      background: #080e1c; color: var(--text); border: 1px solid var(--border); border-radius: 8px;
      padding: 6px 10px; font-size: 12px; min-width: 210px;
    }}
    /* Damage Benchmark Cards */
    .calc-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 11px; }}
    .calc-card {{
      background: #080e1c; border: 1px solid var(--border); border-radius: 11px; padding: 11px 12px;
      display: flex; flex-direction: column; gap: 8px;
    }}
    .calc-head {{ display: flex; align-items: center; justify-content: space-between; gap: 6px; flex-wrap: wrap; }}
    .calc-matchup {{ display: flex; align-items: center; justify-content: space-between; gap: 8px; }}
    .calc-side {{ display: flex; align-items: center; gap: 6px; font-size: 11.5px; font-weight: 700; }}
    .calc-side img {{ width: 34px; height: 34px; object-fit: contain; }}
    .calc-vs {{ color: var(--gold); font-weight: 900; }}
    .calc-bar-track {{
      position: relative; height: 10px; background: var(--surface-2); border-radius: 999px; overflow: hidden; margin-bottom: 5px;
    }}
    .calc-bar-max {{ position: absolute; left: 0; top: 0; bottom: 0; opacity: 0.42; border-radius: 999px; }}
    .calc-bar-min {{ position: absolute; left: 0; top: 0; bottom: 0; border-radius: 999px; }}
    .calc-ohko {{ background: #ef4444; color: #fca5a5; }}
    .calc-roll-ohko {{ background: #f97316; color: #fdba74; }}
    .calc-2hko {{ background: #facc15; color: #fef08a; }}
    .calc-roll-2hko {{ background: #38bdf8; color: #bae6fd; }}
    .calc-safe {{ background: #22c55e; color: #86efac; }}
    .calc-nums {{ display: flex; align-items: center; justify-content: space-between; gap: 6px; flex-wrap: wrap; font-size: 11.5px; }}
    .calc-verdict {{ font-weight: 800; font-size: 11px; background: transparent !important; }}
    .calc-ctx {{ font-size: 11.5px; color: #cbd5e1; border-top: 1px dashed var(--border); padding-top: 6px; }}
    /* Meta Shift Table */
    .table-wrap {{ overflow-x: auto; }}
    .shift-table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    .shift-table th, .shift-table td {{ padding: 8px 9px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: middle; }}
    .shift-table th {{ color: var(--cyan); font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; background: #080e1c; }}
    .shift-mon-cell {{ display: flex; align-items: center; gap: 8px; white-space: nowrap; }}
    .shift-mon-cell img {{ width: 32px; height: 32px; object-fit: contain; }}
    .num {{ text-align: right !important; white-space: nowrap; font-variant-numeric: tabular-nums; }}
    .trend-pill {{ font-size: 10px; font-weight: 800; padding: 2px 8px; border-radius: 999px; white-space: nowrap; }}
    .trend-up {{ background: rgba(34,197,94,0.18); color: #86efac; border: 1px solid rgba(34,197,94,0.45); }}
    .trend-down {{ background: rgba(244,63,94,0.18); color: #fda4af; border: 1px solid rgba(244,63,94,0.45); }}
    .trend-pivot {{ background: rgba(250,204,21,0.15); color: #fef08a; border: 1px solid rgba(250,204,21,0.45); }}
    /* Speed Ladder */
    .speed-row {{
      display: grid; grid-template-columns: 190px 72px 1fr 220px; align-items: center; gap: 10px;
      padding: 6px 8px; border-bottom: 1px solid rgba(30,45,77,0.65); font-size: 12px;
    }}
    .speed-mon {{ display: flex; align-items: center; gap: 7px; font-weight: 700; }}
    .speed-mon img {{ width: 28px; height: 28px; object-fit: contain; }}
    .speed-val {{ font-family: ui-monospace, SFMono-Regular, monospace; font-weight: 800; color: var(--gold); text-align: right; }}
    .speed-track {{ height: 9px; background: #080e1c; border-radius: 999px; overflow: hidden; border: 1px solid var(--border); }}
    .speed-fill {{ height: 100%; border-radius: 999px; }}
    .speed-fill.confirmed {{ background: linear-gradient(90deg, #16a34a, #4ade80); }}
    .speed-fill.rumored {{ background: linear-gradient(90deg, #6366f1, #a5b4fc); }}
    .speed-fill.mc {{ background: linear-gradient(90deg, #0284c7, #38bdf8); }}
    .speed-note {{ font-size: 11px; color: var(--muted); }}
    /* Playbooks */
    .pb-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(540px, 1fr)); gap: 14px; }}
    .pb-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; }}
    .pb-tag {{ font-size: 10px; font-weight: 800; color: var(--gold); letter-spacing: 0.05em; margin-bottom: 4px; }}
    .pb-title {{ margin: 0 0 6px; font-size: 15.5px; color: var(--text); }}
    .pb-summary {{ margin: 0 0 10px; color: #cbd5e1; font-size: 12.5px; }}
    .pb-list {{ margin: 0; padding-left: 18px; display: flex; flex-direction: column; gap: 6px; font-size: 12px; color: #e2e8f0; }}
    /* Readiness Checker */
    .checker-pool {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(136px, 1fr)); gap: 7px; margin-bottom: 14px; }}
    .chk-mon {{
      display: flex; align-items: center; gap: 6px; padding: 5px 8px; border-radius: 8px;
      background: #080e1c; border: 1px solid var(--border); cursor: pointer; font-size: 11.5px; font-weight: 700; color: var(--text);
    }}
    .chk-mon img {{ width: 28px; height: 28px; object-fit: contain; }}
    .chk-mon.selected {{ border-color: var(--cyan); background: rgba(34,211,238,0.16); color: #cffafe; }}
    .chk-mon.is-md {{ border-style: dashed; }}
    .chk-results {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; margin-top: 12px; }}
    .chk-axis {{ background: #080e1c; border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; }}
    .chk-axis.pass {{ border-color: rgba(34,197,94,0.5); }}
    .chk-axis.warn {{ border-color: rgba(250,204,21,0.5); }}
    .chk-axis.fail {{ border-color: rgba(244,63,94,0.55); }}
    /* Tier List & Blueprints */
    .tier-section {{ margin-bottom: 20px; }}
    .tier-heading {{ font-size: 15px; font-weight: 800; margin: 0 0 10px; padding: 7px 12px; border-radius: 9px; border-left: 4px solid var(--cyan); background: rgba(13,21,38,0.9); }}
    .tier-s {{ border-left-color: var(--gold); color: var(--gold); }}
    .tier-a {{ border-left-color: var(--cyan); color: var(--cyan); }}
    .tier-b {{ border-left-color: var(--indigo); color: #a5b4fc; }}
    .tier-niche {{ border-left-color: #94a3b8; color: #cbd5e1; }}
    .mon-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(310px, 1fr)); gap: 12px; }}
    .mon-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 12px; display: flex; flex-direction: column; gap: 7px; }}
    .badge-confirmed-card {{ border-color: rgba(34,197,94,0.42); }}
    .badge-rumored-card {{ border-color: rgba(129,140,248,0.34); }}
    .mon-head {{ display: flex; gap: 10px; align-items: center; }}
    .mon-spr-wrap {{ position: relative; width: 64px; height: 64px; flex-shrink: 0; background: #080e1c; border-radius: 10px; display: flex; align-items: center; justify-content: center; border: 1px solid var(--border); }}
    .main-spr {{ width: 58px; height: 58px; object-fit: contain; }}
    .stone-ico {{ position: absolute; right: -4px; bottom: -4px; width: 22px; height: 22px; background: #0d1526; border-radius: 50%; border: 1px solid var(--gold); padding: 1px; }}
    .alt-spr {{ width: 24px; height: 24px; object-fit: contain; vertical-align: middle; margin-left: 4px; }}
    .mon-title-col {{ flex: 1; min-width: 0; }}
    .mon-badges-row {{ display: flex; flex-wrap: wrap; align-items: center; gap: 5px; margin-bottom: 3px; }}
    .status-badge {{ font-size: 9.5px; font-weight: 800; padding: 2px 7px; border-radius: 999px; letter-spacing: 0.03em; }}
    .badge-confirmed {{ background: rgba(34,197,94,0.18); color: #86efac; border: 1px solid rgba(34,197,94,0.5); }}
    .badge-rumored {{ background: rgba(129,140,248,0.18); color: #c7d2fe; border: 1px solid rgba(129,140,248,0.48); }}
    .bst-chip {{ font-size: 10px; font-weight: 700; color: var(--gold); background: rgba(250,204,21,0.1); padding: 1px 6px; border-radius: 6px; }}
    .mon-name {{ margin: 0 0 4px; font-size: 14.5px; }}
    .type-row {{ display: flex; flex-wrap: wrap; align-items: center; gap: 4px; }}
    .type-pill {{ font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 6px; border: 1px solid var(--border); background: rgba(255,255,255,0.03); }}
    .mon-ability {{ font-size: 11.5px; color: #cbd5e1; }}
    .stat-grid {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 4px; background: #080e1c; padding: 5px 6px; border-radius: 8px; text-align: center; font-size: 10.5px; color: var(--muted); }}
    .stat-grid b {{ display: block; color: var(--text); font-size: 12px; }}
    .spe-bench {{ font-size: 11px; color: var(--cyan); background: rgba(34,211,238,0.07); padding: 4px 8px; border-radius: 7px; }}
    .mon-note {{ margin: 0; font-size: 12px; color: #e2e8f0; }}
    .mon-meta-rows {{ display: flex; flex-direction: column; gap: 4px; font-size: 11px; margin-top: auto; padding-top: 4px; border-top: 1px dashed var(--border); }}
    .meta-lbl {{ color: var(--muted); font-weight: 700; margin-right: 4px; }}
    .mini-tag {{ display: inline-block; padding: 1px 6px; margin: 1px 2px 1px 0; border-radius: 5px; background: rgba(34,211,238,0.1); color: #bae6fd; font-size: 10.5px; }}
    .mini-tag.danger {{ background: rgba(244,63,94,0.14); color: #fda4af; }}
    .bp-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 12px; margin-bottom: 20px; }}
    .bp-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 13px; display: flex; flex-direction: column; gap: 8px; }}
    .bp-head {{ display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 6px; }}
    .bp-source {{ font-size: 10.5px; color: var(--gold); font-weight: 700; }}
    .bp-title {{ margin: 0; font-size: 14.5px; }}
    .bp-swap-row {{ display: flex; align-items: center; justify-content: space-between; gap: 6px; flex-wrap: wrap; }}
    .bp-swap-pill {{ font-size: 11px; color: #86efac; background: rgba(34,197,94,0.09); border: 1px solid rgba(34,197,94,0.28); padding: 3px 8px; border-radius: 7px; }}
    .copy-paste-btn {{
      background: rgba(34,211,238,0.14); border: 1px solid rgba(34,211,238,0.45); color: #cffafe;
      border-radius: 7px; padding: 4px 9px; font-size: 11px; font-weight: 700; cursor: pointer;
    }}
    .copy-paste-btn:hover {{ background: rgba(34,211,238,0.28); }}
    .bp-team-row {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 5px; }}
    .team-slot {{ position: relative; background: #080e1c; border: 1px solid var(--border); border-radius: 8px; padding: 6px 3px 5px; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 3px; font-size: 9.5px; color: #cbd5e1; }}
    .team-slot.is-new {{ border-color: var(--gold); background: rgba(250,204,21,0.08); color: #fef08a; font-weight: 700; }}
    .team-slot img {{ width: 42px; height: 42px; object-fit: contain; }}
    .new-pill {{ position: absolute; top: 2px; right: 2px; font-size: 8px; font-weight: 800; background: var(--gold); color: #060a14; padding: 0 4px; border-radius: 4px; }}
    .bp-note {{ margin: 0; font-size: 12px; color: #cbd5e1; }}
    /* Coach Porygon Signature Team Hero */
    .nav-tab.sig-tab {{ border-color: rgba(250,204,21,0.55); color: #fef08a; background: rgba(250,204,21,0.1); }}
    .nav-tab.sig-tab.active {{ background: linear-gradient(135deg, rgba(250,204,21,0.28), rgba(34,211,238,0.22)); border-color: var(--gold); color: #fff; }}
    .sig-hero-card {{
      background: linear-gradient(135deg, rgba(19,31,55,0.96), rgba(30,22,52,0.9));
      border: 1px solid rgba(250,204,21,0.45); border-radius: 14px; padding: 16px 18px; margin-bottom: 16px;
      box-shadow: 0 10px 28px rgba(0,0,0,0.38);
    }}
    .sig-hero-head {{ display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 10px; }}
    .sig-hero-title {{ margin: 4px 0 6px; font-size: 19px; color: #fef08a; letter-spacing: -0.01em; }}
    .badge-gold {{ background: rgba(250,204,21,0.18); color: #fef08a; border: 1px solid rgba(250,204,21,0.55); }}
    .sig-roster-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 12px; margin-bottom: 16px; }}
    .sig-mon-card {{
      background: var(--surface); border: 1px solid rgba(250,204,21,0.3); border-radius: 12px; padding: 13px;
      display: flex; flex-direction: column; gap: 7px;
    }}
    .sig-role {{ font-size: 11.5px; font-weight: 800; color: var(--cyan); }}
    .sig-sp-line {{ font-size: 11px; color: #fef08a; background: rgba(250,204,21,0.08); border: 1px solid rgba(250,204,21,0.25); padding: 4px 8px; border-radius: 7px; font-family: ui-monospace, SFMono-Regular, monospace; }}
    .sig-moves-row {{ display: flex; flex-wrap: wrap; gap: 5px; }}
    .sig-move-pill {{ font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 6px; background: #080e1c; border: 1px solid var(--border); color: #e2e8f0; }}
    .sig-modes-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(460px, 1fr)); gap: 12px; margin-top: 10px; }}
    .sig-mode-card {{ background: #080e1c; border: 1px solid var(--border); border-radius: 11px; padding: 12px; display: flex; flex-direction: column; gap: 8px; }}
    .sig-mode-sprites {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
    .sig-mode-group {{ display: flex; align-items: center; gap: 6px; }}
    .sig-mini-mon {{ display: flex; flex-direction: column; align-items: center; background: var(--surface); border: 1px solid rgba(34,211,238,0.35); border-radius: 8px; padding: 4px 6px; font-size: 10px; font-weight: 700; min-width: 68px; }}
    .sig-mini-mon.back {{ border-color: var(--border); opacity: 0.92; }}
    .sig-mini-mon img {{ width: 38px; height: 38px; object-fit: contain; }}
    .sig-paste-pre {{ background: #060a14; border: 1px solid var(--border); border-radius: 10px; padding: 12px; font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11.5px; color: #cbd5e1; overflow-x: auto; max-height: 290px; margin: 10px 0 0; }}
    .footer {{ border-top: 1px solid var(--border); padding-top: 14px; margin-top: 22px; font-size: 11px; color: var(--muted); display: flex; flex-direction: column; gap: 8px; }}
    .thanks-strip {{ display: flex; flex-wrap: wrap; align-items: center; gap: 10px; padding: 8px 12px; background: rgba(34,211,238,0.06); border: 1px solid rgba(34,211,238,0.22); border-radius: 10px; }}
    .thanks-strip img {{ width: 26px; height: 26px; border-radius: 50%; object-fit: cover; border: 1px solid rgba(255,255,255,0.25); }}
    .hidden {{ display: none !important; }}
    @media (max-width: 720px) {{
      .bp-team-row {{ grid-template-columns: repeat(3, 1fr); }}
      .mon-grid, .bp-grid, .calc-grid, .pb-grid {{ grid-template-columns: 1fr; }}
      .speed-row {{ grid-template-columns: 140px 58px 1fr; }}
      .speed-note {{ display: none; }}
    }}
  </style>
</head>
<body>
  <div class="ribbon"></div>
  <div class="wrap">
    <header class="hero">
      <div class="hero-top">
        <div class="pill-row">
          <span class="pill">POKÉMON CHAMPIONS · REG M-D PREP DOSSIER</span>
          <span class="pill gold">DEC 2, 2026 – MAR 3, 2027</span>
          <span class="pill mag">DuckDB: {n_tournaments} Tournaments · {total_players:,} Teams ({total_slots:,} Slots)</span>
        </div>
        <div class="lang-toggle" role="group" aria-label="Language">
          <button class="lang-btn active" id="btn-es" type="button">ES</button>
          <button class="lang-btn" id="btn-en" type="button">EN</button>
        </div>
      </div>
      <h1 data-es="🔮 Coach Porygon VGC — Dossier Competitivo Regulation M-D (Offline Base64)" data-en="🔮 Coach Porygon VGC — Regulation M-D Tournament Prep Dossier (Offline Base64)">🔮 Coach Porygon VGC — Dossier Competitivo Regulation M-D (Offline Base64)</h1>
      <p class="hero-sub" data-es="Análisis competitivo profundo integrando los confirmados de Regulation M-D (Mega Heatran, Heatran, Dondozo, Tatsugiri y Mega Tatsugiri) y la ola esperada (Regieleki, Regidrago, Amoonguss, Mega Latios/Latias, Terrakion, Porygon-Z, Flamigo y más): Equipo Firma 66-SP de Coach Porygon, {len(DAMAGE_BENCHMARK_SPECS)} cálculos exactos de 16 rolls Lv.50 Champions, Matriz de Impacto Top-20 M-C → M-D (DuckDB LAIC 2027), Escalera de Velocidades ({len(SPEED_LADDER_ENTRIES)}), {len(PLAYBOOKS)} Playbooks Anti-Meta, Evaluador Interactivo de Equipos y 6 Blueprints copiables." data-en="Deep competitive prep dossier integrating confirmed Regulation M-D headliners (Mega Heatran, Heatran, Dondozo, Tatsugiri & Mega Tatsugiri) and the expected wave (Regieleki, Regidrago, Amoonguss, Mega Latios/Latias, Terrakion, Porygon-Z, Flamigo & more): Coach Porygon's Signature 66-SP M-D Team, {len(DAMAGE_BENCHMARK_SPECS)} exact Lv.50 Champions 16-roll benchmarks, Top-20 Reg M-C → M-D Shift Matrix (DuckDB LAIC 2027), Speed Tiers Ladder ({len(SPEED_LADDER_ENTRIES)}), {len(PLAYBOOKS)} Counterplay Playbooks, Interactive 6-Mon Readiness Checker, and 6 copy-pasteable blueprints.">
        Análisis competitivo profundo integrando los confirmados de Regulation M-D (Mega Heatran, Heatran, Dondozo, Tatsugiri y Mega Tatsugiri) y la ola esperada (Regieleki, Regidrago, Amoonguss, Mega Latios/Latias, Terrakion, Porygon-Z, Flamigo y más): Equipo Firma 66-SP de Coach Porygon, {len(DAMAGE_BENCHMARK_SPECS)} cálculos exactos de 16 rolls Lv.50 Champions, Matriz de Impacto Top-20 M-C → M-D (DuckDB LAIC 2027), Escalera de Velocidades ({len(SPEED_LADDER_ENTRIES)}), {len(PLAYBOOKS)} Playbooks Anti-Meta, Evaluador Interactivo de Equipos y 6 Blueprints copiables.
      </p>
      <div class="callout-warn" data-es="⚠️ Transparencia de Datos: Cada cálculo usa la fórmula exacta de Pokémon Champions Lv.50 (31 IVs, 66 SP) y separa explícitamente ✅ CONFIRMADO M-D de 🔮 OLA ESPERADA (RUMOR). El motor principal Tensor Core permanece bloqueado en Regulation M-C hasta el lanzamiento oficial." data-en="⚠️ Data Transparency: Every benchmark uses exact Pokémon Champions Lv.50 math (31 IVs, 66 SP) and clearly distinguishes ✅ CONFIRMED M-D from 🔮 EXPECTED WAVE (RUMORED / UNCONFIRMED). The core Tensor Core engine stays strictly locked on Regulation M-C until official launch.">
        ⚠️ Transparencia de Datos: Cada cálculo usa la fórmula exacta de Pokémon Champions Lv.50 (31 IVs, 66 SP) y separa explícitamente ✅ CONFIRMADO M-D de 🔮 OLA ESPERADA (RUMOR). El motor principal Tensor Core permanece bloqueado en Regulation M-C hasta el lanzamiento oficial.
      </div>
    </header>

    <nav class="nav-tabs" id="dossier-nav" role="tablist">
      <button class="nav-tab sig-tab active" data-tab="signature" type="button" data-es="👑 Equipo Firma de Coach Porygon" data-en="👑 Coach Porygon's Signature Team">👑 Equipo Firma de Coach Porygon</button>
      <button class="nav-tab" data-tab="calcs" type="button" data-es="💥 Cálculos 16-Rolls ({len(DAMAGE_BENCHMARK_SPECS)})" data-en="💥 16-Roll Benchmarks ({len(DAMAGE_BENCHMARK_SPECS)})">💥 Cálculos 16-Rolls ({len(DAMAGE_BENCHMARK_SPECS)})</button>
      <button class="nav-tab" data-tab="shift" type="button" data-es="📊 Impacto Top-20 M-C → M-D" data-en="📊 Top-20 M-C → M-D Shift">📊 Impacto Top-20 M-C → M-D</button>
      <button class="nav-tab" data-tab="speed" type="button" data-es="⚡ Escalera de Velocidades ({len(SPEED_LADDER_ENTRIES)})" data-en="⚡ Speed Tiers Ladder ({len(SPEED_LADDER_ENTRIES)})">⚡ Escalera de Velocidades ({len(SPEED_LADDER_ENTRIES)})</button>
      <button class="nav-tab" data-tab="playbooks" type="button" data-es="📘 {len(PLAYBOOKS)} Playbooks Counterplay" data-en="📘 {len(PLAYBOOKS)} Counterplay Playbooks">📘 {len(PLAYBOOKS)} Playbooks Counterplay</button>
      <button class="nav-tab" data-tab="checker" type="button" data-es="🧪 Evaluador de tu Equipo (6)" data-en="🧪 6-Mon Readiness Checker">🧪 Evaluador de tu Equipo (6)</button>
      <button class="nav-tab" data-tab="tiers" type="button" data-es="🏆 Tier List Completa ({len(MD_CATALOG)})" data-en="🏆 Full Tier List ({len(MD_CATALOG)})">🏆 Tier List Completa ({len(MD_CATALOG)})</button>
      <button class="nav-tab" data-tab="blueprints" type="button" data-es="🧩 6 Blueprints LAIC 2027" data-en="🧩 6 LAIC 2027 Blueprints">🧩 6 Blueprints LAIC 2027</button>
    </nav>

    <!-- TAB 0 (HERO): COACH PORYGON SIGNATURE REGULATION M-D TEAM -->
    <section class="dossier-panel active" id="panel-signature">
      <div class="sig-hero-card">
        <div class="sig-hero-head">
          <div class="pill-row">
            <span class="status-badge badge-gold" data-es="👑 DISEÑO ORIGINAL DE COACH PORYGON VGC" data-en="👑 COACH PORYGON VGC ORIGINAL BUILD">👑 DISEÑO ORIGINAL DE COACH PORYGON VGC</span>
            <span class="pill">66 SP × 6 · 31 IVs · ZERO TERA</span>
            <span class="pill mag" data-es="100% Objetos Legales en Champions" data-en="100% Champions-Legal Items">100% Objetos Legales en Champions</span>
          </div>
          <div class="pill-row">
            <button class="copy-paste-btn" type="button" data-paste="{sig_full_paste_esc}" data-es="📋 Copiar Showdown Paste Completo (66-SP)" data-en="📋 Copy Full 66-SP Showdown Paste">📋 Copiar Showdown Paste Completo (66-SP)</button>
            <button class="f-btn" id="btn-sig-to-checker" type="button" data-es="🧪 Auditar 100/100 en Evaluador" data-en="🧪 Audit 100/100 in Readiness Checker">🧪 Auditar 100/100 en Evaluador</button>
          </div>
        </div>
        <h2 class="sig-hero-title" data-es="{html.escape(sig_team['codename_es'])}" data-en="{html.escape(sig_team['codename_en'])}">{html.escape(sig_team['codename_es'])}</h2>
        <p class="pb-summary" data-es="{html.escape(sig_team['subtitle_es'])}" data-en="{html.escape(sig_team['subtitle_en'])}">{html.escape(sig_team['subtitle_es'])}</p>
        <ul class="pb-list lang-es-only">{sig_pillars_es_html}</ul>
        <ul class="pb-list lang-en-only hidden">{sig_pillars_en_html}</ul>
      </div>

      <div class="sig-roster-grid">{''.join(sig_roster_cards_html)}</div>

      <div class="sec-card">
        <h3 class="sec-title" data-es="🎯 Pruebas Matemáticas de 16 Rolls (Champions Lv.50 · 31 IVs · Calculado en Vivo)" data-en="🎯 Live-Computed 16-Roll Champions Lv.50 Proofs (31 IVs · Exact 66-SP Spreads)">🎯 Pruebas Matemáticas de 16 Rolls (Champions Lv.50 · 31 IVs · Calculado en Vivo)</h3>
        <div class="table-wrap">
          <table class="shift-table">
            <thead>
              <tr>
                <th data-es="Cruce / Benchmark" data-en="Matchup / Benchmark">Cruce / Benchmark</th>
                <th data-es="Movimiento" data-en="Move">Movimiento</th>
                <th class="num" data-es="Rango Exacto (16 Rolls)" data-en="Exact Range (16 Rolls)">Rango Exacto (16 Rolls)</th>
                <th data-es="Veredicto" data-en="Verdict">Veredicto</th>
              </tr>
            </thead>
            <tbody>{''.join(sig_proof_rows_html)}</tbody>
          </table>
        </div>
      </div>

      <div class="sec-card">
        <h3 class="sec-title" data-es="🧭 4 Modos de Lead Turno 1 & Planes de Matchup Bo3" data-en="🧭 4 Turn-1 Lead Modes & Bo3 Matchup Gameplans">🧭 4 Modos de Lead Turno 1 &amp; Planes de Matchup Bo3</h3>
        <div class="sig-modes-grid">{''.join(sig_modes_html)}</div>
      </div>

      <div class="sec-card">
        <div class="bp-swap-row">
          <h3 class="sec-title" style="margin:0" data-es="📋 Exportación Showdown Paste (EVs Equivalentes Exactos a 66 SP)" data-en="📋 Showdown Paste Export (Exact 66-SP Equivalent EVs)">📋 Exportación Showdown Paste (EVs Equivalentes Exactos a 66 SP)</h3>
          <button class="copy-paste-btn" type="button" data-paste="{sig_full_paste_esc}" data-es="📋 Copiar Equipo" data-en="📋 Copy Team">📋 Copiar Equipo</button>
        </div>
        <pre class="sig-paste-pre">{sig_full_paste_esc}</pre>
      </div>
    </section>

    <!-- TAB 1: EXACT 16-ROLL CHAMPIONS BENCHMARKS -->
    <section class="dossier-panel" id="panel-calcs">
      <div class="sec-card">
        <h2 class="sec-title" data-es="💥 Benchmarks de Daño Exactos — Pokémon Champions Lv.50 (31 IVs, 16 Rolls)" data-en="💥 Exact Damage Benchmarks — Pokémon Champions Lv.50 (31 IVs, 16 Rolls)">💥 Benchmarks de Daño Exactos — Pokémon Champions Lv.50 (31 IVs, 16 Rolls)</h2>
        <div class="toolbar">
          <div class="filter-row" id="calc-filter-row">
            <button class="f-btn active" data-cgroup="all" type="button" data-es="Todos ({len(DAMAGE_BENCHMARK_SPECS)})" data-en="All ({len(DAMAGE_BENCHMARK_SPECS)})">Todos ({len(DAMAGE_BENCHMARK_SPECS)})</button>
            <button class="f-btn" data-cgroup="heatran" type="button" data-es="🌋 Mega Heatran" data-en="🌋 Mega Heatran">🌋 Mega Heatran</button>
            <button class="f-btn" data-cgroup="dozo" type="button" data-es="🐋 +2 DozoGiri" data-en="🐋 +2 DozoGiri">🐋 +2 DozoGiri</button>
            <button class="f-btn" data-cgroup="tatsugiri" type="button" data-es="🍣 +1 Mega Tatsugiri" data-en="🍣 +1 Mega Tatsugiri">🍣 +1 Mega Tatsugiri</button>
            <button class="f-btn" data-cgroup="amoonguss" type="button" data-es="🍄 Amoonguss" data-en="🍄 Amoonguss">🍄 Amoonguss</button>
            <button class="f-btn" data-cgroup="regis" type="button" data-es="⚡🐉 Regieleki &amp; Regidrago" data-en="⚡🐉 Regieleki &amp; Regidrago">⚡🐉 Regieleki &amp; Regidrago</button>
            <button class="f-btn" data-cgroup="eons" type="button" data-es="✈️ Mega Latios/Latias" data-en="✈️ Mega Latios/Latias">✈️ Mega Latios/Latias</button>
            <button class="f-btn" data-cgroup="breakers" type="button" data-es="⚔️ Terrakion / PZ / Flamigo" data-en="⚔️ Terrakion / PZ / Flamigo">⚔️ Terrakion / PZ / Flamigo</button>
          </div>
        </div>
        <div class="calc-grid">{''.join(calc_cards_html)}</div>
      </div>
    </section>

    <!-- TAB 2: TOP-20 M-C -> M-D SHIFT MATRIX -->
    <section class="dossier-panel" id="panel-shift">
      <div class="sec-card">
        <h2 class="sec-title" data-es="📊 Matriz de Impacto M-C → M-D sobre el Top 20 de DuckDB ({total_players:,} Equipos incl. LAIC 2027)" data-en="📊 Top-20 DuckDB Reg M-C → M-D Meta Impact Matrix ({total_players:,} Teams incl. LAIC 2027)">📊 Matriz de Impacto M-C → M-D sobre el Top 20 de DuckDB ({total_players:,} Equipos incl. LAIC 2027)</h2>
        <div class="toolbar">
          <div class="filter-row" id="shift-filter-row">
            <button class="f-btn active" data-strend="all" type="button" data-es="Todos (20)" data-en="All (20)">Todos (20)</button>
            <button class="f-btn" data-strend="up" type="button" data-es="📈 Sube Valor" data-en="📈 Stock Up">📈 Sube Valor</button>
            <button class="f-btn" data-strend="pivot" type="button" data-es="🔄 Ajuste Tech" data-en="🔄 Tech Pivot">🔄 Ajuste Tech</button>
            <button class="f-btn" data-strend="down" type="button" data-es="📉 Pierde Terreno" data-en="📉 Stock Down">📉 Pierde Terreno</button>
          </div>
        </div>
        <div class="table-wrap">
          <table class="shift-table">
            <thead>
              <tr>
                <th data-es="Pokémon (Reg M-C)" data-en="Pokémon (Reg M-C)">Pokémon (Reg M-C)</th>
                <th class="num" data-es="Uso DuckDB" data-en="DuckDB Usage">Uso DuckDB</th>
                <th data-es="Tendencia M-D" data-en="M-D Trend">Tendencia M-D</th>
                <th data-es="Por qué sube, baja o cambia de set en Regulation M-D" data-en="Why it rises, drops, or must pivot in Regulation M-D">Por qué sube, baja o cambia de set en Regulation M-D</th>
              </tr>
            </thead>
            <tbody>{''.join(shift_rows_html)}</tbody>
          </table>
        </div>
      </div>
    </section>

    <!-- TAB 3: INTERACTIVE COMPARATIVE SPEED TIERS LADDER -->
    <section class="dossier-panel" id="panel-speed">
      <div class="sec-card">
        <h2 class="sec-title" data-es="⚡ Escalera Comparativa de Velocidades M-C + M-D (Lv.50 Champions · 31 IVs)" data-en="⚡ Comparative M-C + M-D Speed Tiers Ladder (Lv.50 Champions · 31 IVs)">⚡ Escalera Comparativa de Velocidades M-C + M-D (Lv.50 Champions · 31 IVs)</h2>
        <div class="toolbar">
          <div class="filter-row" id="speed-mode-row">
            <button class="f-btn active" data-smode="s32p" type="button" data-es="Max +Spe (32 SP+)" data-en="Max +Spe (32 SP+)">Max +Spe (32 SP+)</button>
            <button class="f-btn" data-smode="s32" type="button" data-es="32 SP Neutral" data-en="32 SP Neutral">32 SP Neutral</button>
            <button class="f-btn" data-smode="s0" type="button" data-es="0 SP Neutral" data-en="0 SP Neutral">0 SP Neutral</button>
            <button class="f-btn" data-smode="tw_32p" type="button" data-es="Tailwind (×2 Max)" data-en="Tailwind (×2 Max)">Tailwind (×2 Max)</button>
            <button class="f-btn" data-smode="scarf_32p" type="button" data-es="Choice Scarf (×1.5)" data-en="Choice Scarf (×1.5)">Choice Scarf (×1.5)</button>
            <button class="f-btn" data-smode="tr" type="button" data-es="🌀 Trick Room (Más Lento Primero)" data-en="🌀 Trick Room (Slowest First)">🌀 Trick Room (Más Lento Primero)</button>
          </div>
          <div class="pill-row">
            <span class="status-badge badge-confirmed" data-es="Verde = Confirmado M-D" data-en="Green = Confirmed M-D">Verde = Confirmado M-D</span>
            <span class="status-badge badge-rumored" data-es="Índigo = Ola Esperada" data-en="Indigo = Expected Wave">Índigo = Ola Esperada</span>
            <span class="pill" data-es="Azul = Base M-C" data-en="Cyan = M-C Staple">Azul = Base M-C</span>
          </div>
        </div>
        <div id="speed-ladder-root"></div>
      </div>
    </section>

    <!-- TAB 4: 4 DEEP COUNTERPLAY PLAYBOOKS -->
    <section class="dossier-panel" id="panel-playbooks">
      <div class="pb-grid">{''.join(playbooks_html)}</div>
    </section>

    <!-- TAB 5: INTERACTIVE 6-MON M-D READINESS CHECKER -->
    <section class="dossier-panel" id="panel-checker">
      <div class="sec-card">
        <h2 class="sec-title" data-es="🧪 Evaluador Interactivo: ¿Está tu Equipo de 6 Listo para Regulation M-D?" data-en="🧪 Interactive 6-Mon Readiness Checker: Is Your Roster Ready for Regulation M-D?">🧪 Evaluador Interactivo: ¿Está tu Equipo de 6 Listo para Regulation M-D?</h2>
        <p class="muted" style="margin:0 0 10px" data-es="Haz clic en hasta 6 Pokémon (M-C o nuevos de M-D) para auditar tu cobertura frente a los 5 exámenes críticos de Regulation M-D." data-en="Click up to 6 Pokémon (M-C staples or M-D additions) to audit your roster across the 5 critical Regulation M-D stress tests.">
          Haz clic en hasta 6 Pokémon (M-C o nuevos de M-D) para auditar tu cobertura frente a los 5 exámenes críticos de Regulation M-D.
        </p>
        <div class="toolbar">
          <div id="checker-selected-summary" class="pill-row"></div>
          <div class="pill-row">
            <button class="f-btn" id="btn-checker-signature" type="button" data-es="👑 Cargar Equipo Firma Coach Porygon" data-en="👑 Load Coach Porygon Signature Team">👑 Cargar Equipo Firma Coach Porygon</button>
            <button class="f-btn" id="btn-checker-clear" type="button" data-es="Limpiar selección" data-en="Clear selection">Limpiar selección</button>
          </div>
        </div>
        <div class="checker-pool" id="checker-pool-root"></div>
        <div id="checker-score-banner"></div>
        <div class="chk-results" id="checker-results-root"></div>
      </div>
    </section>

    <!-- TAB 6: UNIFIED TIER LIST -->
    <section class="dossier-panel" id="panel-tiers">
      <div class="sec-card">
        <div class="toolbar">
          <div class="filter-row" id="filter-row">
            <button class="f-btn active" data-filter="all" type="button" data-es="Todos ({len(MD_CATALOG)})" data-en="All ({len(MD_CATALOG)})">Todos ({len(MD_CATALOG)})</button>
            <button class="f-btn" data-filter="confirmed" type="button" data-es="✅ Confirmados M-D ({confirmed_count})" data-en="✅ Confirmed M-D ({confirmed_count})">✅ Confirmados M-D ({confirmed_count})</button>
            <button class="f-btn" data-filter="rumored" type="button" data-es="🔮 Ola Esperada ({rumored_count})" data-en="🔮 Expected Wave ({rumored_count})">🔮 Ola Esperada ({rumored_count})</button>
            <button class="f-btn" data-filter="mega" type="button" data-es="💎 Megas ({mega_count})" data-en="💎 Megas ({mega_count})">💎 Megas ({mega_count})</button>
            <button class="f-btn" data-filter="tr" type="button" data-es="🌀 Trick Room / Bulk" data-en="🌀 Trick Room / Bulk">🌀 Trick Room / Bulk</button>
            <button class="f-btn" data-filter="offense" type="button" data-es="⚔ Ofensiva" data-en="⚔ Offense">⚔ Ofensiva</button>
          </div>
          <input class="search-inp" id="search-inp" type="search" placeholder="Buscar Pokémon, tipo o habilidad..." />
        </div>
        <div id="tier-root">{''.join(tier_sections_html)}</div>
      </div>
    </section>

    <!-- TAB 7: 6 COPY-PASTEABLE LAIC 2027 -> M-D BLUEPRINTS -->
    <section class="dossier-panel" id="panel-blueprints">
      <div class="bp-grid">{''.join(blueprint_cards_html)}</div>
    </section>

    <footer class="footer">
      <div class="thanks-strip">
        <img src="{pokemmunity_b64}" alt="Pokémmunity MÉXICO" />
        <img src="{pokemex_b64}" alt="PokéMex" />
        <span data-es="💚 Agradecimiento especial a los grupos Pokémmunity MÉXICO y PokéMex por su apoyo y comentarios para mejorar Coach Porygon VGC." data-en="💚 Special thanks to the Pokémmunity MÉXICO and PokéMex group chats for their support and feedback to improve Coach Porygon VGC.">
          💚 Agradecimiento especial a los grupos Pokémmunity MÉXICO y PokéMex por su apoyo y comentarios para mejorar Coach Porygon VGC.
        </span>
      </div>
      <div>
        <strong>Coach Porygon VGC</strong> · Generated {gen_date} (100% Offline Base64 HTML) · Fan-made, strictly non-commercial project (never monetized).
        Pokémon, Pokémon Champions, species names &amp; sprites © Nintendo / Creatures Inc. / GAME FREAK inc. / The Pokémon Company. Not affiliated or endorsed.
        Credits: Pokéos · MunchStats (9 Regional/IC datasets incl. LAIC 2027) · Pokémon Showdown · DuckDB.
      </div>
    </footer>
  </div>

  <script>
    (function() {{
      const SPEED_DATA = {speed_json};
      const READINESS_POOL = {readiness_json};
      let lang = "es";
      let activeTierFilter = "all";
      let activeSpeedMode = "s32p";
      const selectedRoster = new Set(["Rillaboom", "Incineroar", "Gholdengo", "Garchomp-Mega-Z", "Milotic", "Farigiraf"]);

      function setActiveTab(tabId) {{
        document.querySelectorAll(".nav-tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === tabId));
        document.querySelectorAll(".dossier-panel").forEach((p) => p.classList.toggle("active", p.id === "panel-" + tabId));
      }}
      document.querySelectorAll(".nav-tab").forEach((btn) => {{
        btn.addEventListener("click", () => setActiveTab(btn.dataset.tab));
      }});

      // Damage calc group filters
      document.querySelectorAll("#calc-filter-row .f-btn").forEach((btn) => {{
        btn.addEventListener("click", () => {{
          const g = btn.dataset.cgroup || "all";
          document.querySelectorAll("#calc-filter-row .f-btn").forEach((b) => b.classList.toggle("active", b === btn));
          document.querySelectorAll(".calc-card").forEach((c) => {{
            c.classList.toggle("hidden", g !== "all" && c.dataset.calcGroup !== g);
          }});
        }});
      }});

      // Shift matrix trend filters
      document.querySelectorAll("#shift-filter-row .f-btn").forEach((btn) => {{
        btn.addEventListener("click", () => {{
          const t = btn.dataset.strend || "all";
          document.querySelectorAll("#shift-filter-row .f-btn").forEach((b) => b.classList.toggle("active", b === btn));
          document.querySelectorAll(".shift-row").forEach((r) => {{
            r.classList.toggle("hidden", t !== "all" && r.dataset.trend !== t);
          }});
        }});
      }});

      // Speed ladder renderer
      function renderSpeedLadder() {{
        const root = document.getElementById("speed-ladder-root");
        if (!root) return;
        const isTr = activeSpeedMode === "tr";
        const key = isTr ? "s_neg" : activeSpeedMode;
        const rows = [...SPEED_DATA].sort((a, b) => isTr ? (a[key] - b[key]) : (b[key] - a[key]));
        const maxVal = Math.max(1, ...rows.map((r) => r[key]));
        root.innerHTML = rows.map((r) => {{
          const val = r[key];
          const pct = Math.max(8, Math.round((val / maxVal) * 100));
          return `<div class="speed-row">
            <div class="speed-mon"><img src="${{r.spr}}" alt="${{r.sp}}" /><span>${{r.sp}}</span></div>
            <div class="speed-val">${{val}}</div>
            <div class="speed-track"><div class="speed-fill ${{r.origin}}" style="width:${{pct}}%"></div></div>
            <div class="speed-note">${{r.note}} <span class="muted">(Base ${{r.base}})</span></div>
          </div>`;
        }}).join("");
      }}
      document.querySelectorAll("#speed-mode-row .f-btn").forEach((btn) => {{
        btn.addEventListener("click", () => {{
          activeSpeedMode = btn.dataset.smode || "s32p";
          document.querySelectorAll("#speed-mode-row .f-btn").forEach((b) => b.classList.toggle("active", b === btn));
          renderSpeedLadder();
        }});
      }});
      renderSpeedLadder();

      // Tier list filter & search
      function applyTierFilters() {{
        const q = (document.getElementById("search-inp").value || "").trim().toLowerCase();
        document.querySelectorAll(".mon-card").forEach((card) => {{
          const roles = (card.dataset.roles || "").split(/\\s+/);
          const matchFilter = activeTierFilter === "all" || roles.includes(activeTierFilter);
          const matchSearch = !q || (card.dataset.search || "").includes(q);
          card.classList.toggle("hidden", !(matchFilter && matchSearch));
        }});
        document.querySelectorAll(".tier-section").forEach((sec) => {{
          const vis = sec.querySelectorAll(".mon-card:not(.hidden)").length;
          sec.classList.toggle("hidden", vis === 0);
        }});
      }}
      document.querySelectorAll("#filter-row .f-btn").forEach((btn) => {{
        btn.addEventListener("click", () => {{
          activeTierFilter = btn.dataset.filter || "all";
          document.querySelectorAll("#filter-row .f-btn").forEach((b) => b.classList.toggle("active", b === btn));
          applyTierFilters();
        }});
      }});
      document.getElementById("search-inp").addEventListener("input", applyTierFilters);

      // Copy Showdown paste buttons
      document.querySelectorAll(".copy-paste-btn").forEach((btn) => {{
        btn.addEventListener("click", async () => {{
          const txt = btn.getAttribute("data-paste") || "";
          try {{
            await navigator.clipboard.writeText(txt);
            const orig = btn.textContent;
            btn.textContent = lang === "es" ? "✅ ¡Copiado!" : "✅ Copied!";
            setTimeout(() => {{ btn.textContent = orig; }}, 1400);
          }} catch (_) {{}}
        }});
      }});

      // Interactive 6-Mon M-D Readiness Checker
      const AXES = [
        {{ key: "dozo", es: "🐋 Anti-DozoGiri & Costar", en: "🐋 Anti-DozoGiri & Costar", tipEs: "Añade Milotic/Primarina (Haze), Politoed, Amoonguss (Clear Smog), Regieleki (Thunderbolt) o Mega Gengar.", tipEn: "Add Milotic/Primarina (Haze), Politoed, Amoonguss (Clear Smog), Regieleki (Thunderbolt), or Mega Gengar." }},
        {{ key: "heatran", es: "🌋 Respuesta a Mega Heatran", en: "🌋 Mega Heatran Answer", tipEs: "Añade Garchomp-Mega-Z (Earth Power), Regidrago (Earth Power), Swampert-Mega, Sneasler o Heatran propio.", tipEn: "Add Garchomp-Mega-Z (Earth Power), Regidrago (Earth Power), Swampert-Mega, Sneasler, or your own Heatran." }},
        {{ key: "spore", es: "🍄 Plan Anti-Amoonguss (Sin Goggles)", en: "🍄 Anti-Amoonguss (No Goggles)", tipEs: "Necesitas ≥2 respuestas: Amoonguss/Rillaboom/Venusaur, Gholdengo, Taunt Incineroar o Mega Heatran.", tipEn: "Pack ≥2 answers: Amoonguss/Rillaboom/Venusaur, Gholdengo, Taunt Incineroar, or Mega Heatran." }},
        {{ key: "eon_terra", es: "✈️🐉 Checks Regidrago, Eon Duo & Terrakion", en: "✈️🐉 Regidrago, Eon Duo & Terrakion Checks", tipEs: "Añade Primarina/Floette-Mega (0× Dragón), Kingambit, Incineroar, Amoonguss o Indeedee-F.", tipEn: "Add Primarina/Floette-Mega (0× Dragon), Kingambit, Incineroar, Amoonguss, or Indeedee-F." }},
        {{ key: "speed", es: "⚡ Control de Velocidad (incl. Regieleki 200 Spe)", en: "⚡ Speed Control (incl. 200-Spe Regieleki)", tipEs: "Añade Regieleki (Electroweb), Farigiraf/Amoonguss (TR), Whimsicott, Mega Latias/Latios o Crobat.", tipEn: "Add Regieleki (Electroweb), Farigiraf/Amoonguss (TR), Whimsicott, Mega Latias/Latios, or Crobat." }},
      ];

      function loadSignatureTeamIntoChecker() {{
        selectedRoster.clear();
        ["Heatran-Mega", "Regidrago", "Regieleki", "Amoonguss", "Primarina", "Incineroar"].forEach((sp) => selectedRoster.add(sp));
        renderChecker();
      }}

      function renderChecker() {{
        const poolRoot = document.getElementById("checker-pool-root");
        const sumRoot = document.getElementById("checker-selected-summary");
        const banRoot = document.getElementById("checker-score-banner");
        const resRoot = document.getElementById("checker-results-root");
        if (!poolRoot || !resRoot) return;
        const isEs = lang === "es";

        poolRoot.innerHTML = READINESS_POOL.map((m) => {{
          const sel = selectedRoster.has(m.sp) ? "selected" : "";
          const mdCls = m.is_md ? "is-md" : "";
          return `<button type="button" class="chk-mon ${{sel}} ${{mdCls}}" data-sp="${{m.sp}}"><img src="${{m.spr}}" alt="${{m.sp}}" /><span>${{m.sp}}</span></button>`;
        }}).join("");

        poolRoot.querySelectorAll(".chk-mon").forEach((btn) => {{
          btn.addEventListener("click", () => {{
            const sp = btn.dataset.sp;
            if (selectedRoster.has(sp)) {{
              selectedRoster.delete(sp);
            }} else if (selectedRoster.size < 6) {{
              selectedRoster.add(sp);
            }}
            renderChecker();
          }});
        }});

        const chosen = READINESS_POOL.filter((m) => selectedRoster.has(m.sp));
        sumRoot.innerHTML = `<span class="pill gold">${{chosen.length}} / 6 ${{isEs ? "seleccionados" : "selected"}}</span>` +
          chosen.map((m) => `<span class="mini-tag">${{m.sp}}</span>`).join("");

        let score = 0;
        resRoot.innerHTML = AXES.map((ax) => {{
          const hits = chosen.filter((m) => m.tags.includes(ax.key)).map((m) => m.sp);
          const needTwo = ax.key === "spore";
          const cls = hits.length >= (needTwo ? 2 : 1) ? (hits.length >= 2 ? "pass" : "warn") : "fail";
          if (cls === "pass") score += 20;
          else if (cls === "warn") score += 12;
          const badge = cls === "pass" ? (isEs ? "✅ Sólido" : "✅ Solid") : cls === "warn" ? (isEs ? "⚠️ Justo (1)" : "⚠️ Thin (1)") : (isEs ? "❌ Vulnerable" : "❌ Exposed");
          return `<div class="chk-axis ${{cls}}">
            <div style="font-weight:800;margin-bottom:4px">${{isEs ? ax.es : ax.en}}</div>
            <div style="font-size:11.5px;margin-bottom:4px"><strong>${{badge}}</strong> · ${{hits.length ? hits.join(", ") : (isEs ? "Ninguno" : "None")}}</div>
            <div class="muted" style="font-size:11px">${{cls === "pass" ? (isEs ? "Cobertura lista para Bo3." : "Bo3-ready coverage.") : (isEs ? ax.tipEs : ax.tipEn)}}</div>
          </div>`;
        }}).join("");

        banRoot.innerHTML = `<div class="callout-warn" style="margin:0 0 8px;border-color:${{score >= 80 ? "rgba(34,197,94,0.5)" : "rgba(250,204,21,0.4)"}};color:${{score >= 80 ? "#86efac" : "#fef08a"}}">
          <strong>${{isEs ? "Índice de Preparación Regulation M-D:" : "Regulation M-D Readiness Score:"}} ${{score}} / 100</strong>
          (${{score >= 85 ? (isEs ? "Listo para torneo Bo3" : "Tournament Bo3 ready") : score >= 60 ? (isEs ? "Base sólida — ajusta 1–2 techs" : "Solid shell — refine 1–2 tech slots") : (isEs ? "Requiere ajustes contra amenazas M-D" : "Needs key M-D counterplay upgrades")}})
        </div>`;
      }}
      document.getElementById("btn-checker-clear").addEventListener("click", () => {{
        selectedRoster.clear();
        renderChecker();
      }});
      const sigChkBtn = document.getElementById("btn-checker-signature");
      if (sigChkBtn) sigChkBtn.addEventListener("click", loadSignatureTeamIntoChecker);
      const sigJumpBtn = document.getElementById("btn-sig-to-checker");
      if (sigJumpBtn) sigJumpBtn.addEventListener("click", () => {{
        loadSignatureTeamIntoChecker();
        setActiveTab("checker");
      }});
      renderChecker();

      // Language toggle
      function applyLang(nextLang) {{
        lang = nextLang;
        document.getElementById("btn-es").classList.toggle("active", lang === "es");
        document.getElementById("btn-en").classList.toggle("active", lang === "en");
        document.querySelectorAll("[data-es][data-en]").forEach((el) => {{
          el.textContent = el.getAttribute(lang === "es" ? "data-es" : "data-en");
        }});
        document.querySelectorAll(".lang-es-only").forEach((el) => el.classList.toggle("hidden", lang !== "es"));
        document.querySelectorAll(".lang-en-only").forEach((el) => el.classList.toggle("hidden", lang !== "en"));
        document.getElementById("search-inp").placeholder =
          lang === "es" ? "Buscar Pokémon, tipo o habilidad..." : "Search Pokémon, type, or ability...";
        renderChecker();
      }}
      document.getElementById("btn-es").addEventListener("click", () => applyLang("es"));
      document.getElementById("btn-en").addEventListener("click", () => applyLang("en"));
    }})();
  </script>
</body>
</html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding="utf-8")
    print(
        f"[OK] Generated Regulation M-D Prep Dossier Base64 HTML: {out_path} "
        f"({out_path.stat().st_size / 1024:.1f} KB, {len(DAMAGE_BENCHMARK_SPECS)} 16-roll calcs, "
        f"{len(SPEED_LADDER_ENTRIES)} speed tiers, {len(PLAYBOOKS)} playbooks, "
        f"{len(MD_CATALOG)} Pokémon, {len(TEAM_BLUEPRINTS)} blueprints)"
    )
    return out_path


if __name__ == "__main__":
    generate_report()
