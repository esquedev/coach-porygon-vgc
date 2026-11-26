#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the Standalone Offline Base64 HTML Regulation M-D Meta Scout Report.

Cross-references:
  1. In-memory DuckDB telemetry across all ingested Regulation M-C tournaments
     (including LAIC 2027 — `LA002-m593TW3lr3apWb`) via `engine.db_registry.get_registry()`.
  2. Official Confirmed Regulation M-D additions (Dec 2, 2026 – Mar 3, 2027):
     Heatran, Mega Heatran (Water Compaction), Dondozo, Tatsugiri (Curly/Droopy/Stretchy),
     and Mega Tatsugiri (Premium Grade) — sprites from `assets/sprites/Reg_M-D/`.
  3. Rumored / Unconfirmed M-D forecast wave (`@OSAKA_POKEMON` community graphic) —
     sprites strictly isolated in `assets/sprites/Reg_M-D_rumored/` and visibly badged
     `RUMORED / UNCONFIRMED` so zero speculative specs are presented as confirmed.

Lives exclusively in `scripts/` (outside `src/engine/` and `apps/`) to keep the
core Regulation M-C engine 100% pure and anti-hallucination compliant.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from engine.db_registry import get_registry  # noqa: E402

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
    raw = path.read_bytes()
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def _l50_speed_range(base_spe: int) -> Tuple[int, int, int]:
    """Return Champions Lv.50 (31 IVs) speeds: (0-SP neutral, 32-SP neutral, 32-SP +Spe)."""
    # Champions Level 50: floor((Base + SP + 20) * NatureMult)
    s0 = base_spe + 20
    s32 = base_spe + 32 + 20
    s32_pos = int((base_spe + 32 + 20) * 1.1)
    return s0, s32, s32_pos


# Unified Regulation M-D Addition Catalog (Confirmed M-D + Rumored Community Forecast)
# Every entry strictly specifies status ("confirmed" vs "rumored"), tier, types,
# base stats [hp, atk, def, spa, spd, spe], sprite file, role tags, and bilingual notes.
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
        "es": "Monstruo de 175 SpA / 141 SpD con 67 Spe (-10 vs base), ideal tanto en Trick Room como en Balance. Water Compaction (+2 Def al recibir Agua) castiga Flip Turn / Surf / Politoed y abre combos con Aqua Jet aliado o Body Press.",
        "en": "175 SpA / 141 SpD juggernaut dropping to 67 Spe (-10 vs base), dominant in Trick Room and Bulky Balance. Water Compaction (+2 Def on Water hit) punishes Rain/Flip Turn and unlocks self-Aqua Jet / Body Press tech.",
        "partners": ["Rillaboom", "Farigiraf", "Politoed", "Torkoal"],
        "checks": ["Garchomp-Mega-Z", "Swampert-Mega", "Sneasler"],
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
        "es": "Respuesta directa al 48.6% Rillaboom, 23.2% Gholdengo, 18.9% Charizard-Mega-Y y 14.5% Floette-Mega de Reg M-C. Sin usar slot de Mega mantiene Flash Fire para bloquear Heat Wave bajo Sol y presionar con Heat Wave / Earth Power.",
        "en": "Direct meta check to Reg M-C's 48.6% Rillaboom, 23.2% Gholdengo, 18.9% Charizard-Mega-Y, and 14.5% Floette-Mega. Keeps Flash Fire without spending the Mega slot to shut down Sun Heat Wave spam.",
        "partners": ["Rillaboom", "Salamence-Mega", "Whimsicott", "Milotic"],
        "checks": ["Garchomp", "Basculegion", "Sneasler"],
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
        "es": "Vuelve el eje DozoGiri con +2 omni-boost vía Commander. En un formato sin Clear Haze/Tera (Champions M-D), Unaware ignora boosts de Kingambit/Gholdengo/Sneasler; el counterplay clave será Clear Smog, Haze (Milotic) y Perish Trap (Gengar-Mega).",
        "en": "Brings back the +2 omni-boost Commander archetype in a Tera-free Champions format. Unaware blanks Kingambit/Gholdengo setup; key M-C counterplay pivots around Haze (Milotic), Clear Smog, Rillaboom Grassy Glide, and Mega Gengar Perish Trap.",
        "partners": ["Tatsugiri", "Incineroar", "Sneasler", "Gengar-Mega"],
        "checks": ["Rillaboom", "Raichu-Mega-Y", "Gengar-Mega", "Milotic"],
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
        "es": "Habilidad oficial Premium Grade (Tokujō): +1 SpA automático al entrar / Megaevolucionar sobre 135 SpA base y 92 Spe. Permite el modo dual más peligroso del formato: Commander con Dondozo o sweeper especial independiente con Draco Meteor / Muddy Water.",
        "en": "Confirmed ability Premium Grade (Tokujō): automatic +1 SpA on entry / Mega Evolution atop 135 SpA and 92 Spe. Unlocks brutal Team-Preview mindgames: Commander into Dondozo OR standalone +1 SpA special breaker under Rain/Tailwind.",
        "partners": ["Dondozo", "Pelipper", "Politoed", "Incineroar"],
        "checks": ["Floette-Mega", "Sylveon", "Sneasler"],
    },
    {
        "name": "Amoonguss",
        "display": "Amoonguss",
        "status": "rumored",
        "tier": "S",
        "sprite": ("rumored", "amoonguss.png"),
        "types": ["Grass", "Poison"],
        "stats": [114, 85, 70, 85, 80, 30],
        "ability": "Regenerator (Champions set unconfirmed)",
        "roles": ["support", "tr"],
        "es": "[RUMOR] Si entra en M-D, cambia por completo el meta: sin Safety Goggles (item ilegal en Champions), Rage Powder + Spore + Pollen Puff + Clear Smog detienen a DozoGiri y habilitan equipos de Trick Room y Mega Heatran.",
        "en": "[RUMORED] Immediate meta-warper if added: with Safety Goggles illegal in Champions, Rage Powder + Spore + Pollen Puff + Clear Smog hard-checks DozoGiri while anchoring Trick Room and Mega Heatran cores.",
        "partners": ["Incineroar", "Heatran-Mega", "Farigiraf", "Kingambit"],
        "checks": ["Charizard-Mega-Y", "Gholdengo", "Salamence-Mega", "Delphox-Mega"],
    },
    # --- A TIER ---
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
        "es": "Habilitador obligatorio de Dondozo (Commander +2 Atk/Def/Spe según forma en Order Up). Con Focus Sash o Choice Scarf sigue limpiando endgames con Muddy Water, Icy Wind y Draco Meteor cuando Dondozo cae.",
        "en": "Mandatory Dondozo Commander partner (Curly +Atk, Droopy +Def, Stretchy +Spe Order Up). With Focus Sash or Choice Scarf, cleans endgames with Muddy Water, Icy Wind, and Draco Meteor once Dondozo faints.",
        "partners": ["Dondozo", "Incineroar", "Sneasler", "Gholdengo"],
        "checks": ["Floette-Mega", "Rillaboom", "Salamence-Mega"],
    },
    {
        "name": "Latias-Mega",
        "display": "Mega Latias",
        "status": "rumored",
        "tier": "A",
        "sprite": ("rumored", "latias-mega.png"),
        "types": ["Dragon", "Psychic"],
        "stats": [80, 100, 120, 140, 150, 110],
        "ability": "Levitate (Champions Mega slot unconfirmed)",
        "roles": ["mega", "support", "offense"],
        "es": "[RUMOR] Uno de los 2 Megas aún sin confirmar de los 4 anunciados. 80/120/150 bulk + Levitate (inmune a Earth Power / Earthquake de Garchomp-Mega-Z y Heatran) + Tailwind / Mist Ball / Calm Mind encaja en cores Balance con Incineroar y Rillaboom.",
        "en": "[RUMORED] Top candidate among the 2 unrevealed M-D Megas. 80/120/150 bulk + Levitate (immune to Garchomp-Mega-Z & Heatran Ground moves) + Tailwind / Mist Ball / Calm Mind slots effortlessly into Incineroar + Rillaboom Balance.",
        "partners": ["Incineroar", "Rillaboom", "Heatran", "Kingambit"],
        "checks": ["Kingambit", "Floette-Mega", "Incineroar"],
    },
    {
        "name": "Latios-Mega",
        "display": "Mega Latios",
        "status": "rumored",
        "tier": "A",
        "sprite": ("rumored", "latios-mega.png"),
        "types": ["Dragon", "Psychic"],
        "stats": [80, 130, 100, 160, 120, 110],
        "ability": "Levitate (Champions Mega slot unconfirmed)",
        "roles": ["mega", "offense"],
        "es": "[RUMOR] 160 SpA + 110 Spe + Levitate: supera el tier de 100–105 Spe (Charizard-Y, Staraptor-Mega) y castiga a Sneasler, Archaludon y cores de Lluvia con Luster Purge + Draco Meteor + Tailwind.",
        "en": "[RUMORED] 160 SpA / 110 Spe + Levitate outpaces the crowded 100–105 Spe bracket (Charizard-Y, Staraptor-Mega) and blows through Sneasler and Rain cores with Luster Purge, Draco Meteor, and Tailwind.",
        "partners": ["Incineroar", "Rillaboom", "Kingambit", "Whimsicott"],
        "checks": ["Floette-Mega", "Kingambit", "Sneasler"],
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
        "es": "[RUMOR] Soporte veloz de Tailwind / Helping Hand / Mist Ball sin gastar Mega, inmune a Ground para acompañar a Heatran, Archaludon o Gholdengo.",
        "en": "[RUMORED] Fast non-Mega Tailwind / Helping Hand / Mist Ball support with Ground immunity beside Heatran, Archaludon, or Gholdengo.",
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
        "es": "[RUMOR] Atacante especial rápido con Life Orb / Soul Dew + Tailwind que presiona a Sneasler y dragones sin ocupar slot de Mega.",
        "en": "[RUMORED] Fast non-Mega special breaker with Life Orb / Tailwind that pressures Sneasler and opposing Dragons.",
        "partners": ["Incineroar", "Rillaboom", "Heatran-Mega"],
        "checks": ["Kingambit", "Floette-Mega", "Gholdengo"],
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
        "es": "[RUMOR] 108 Spe + 129 Atk con Rock Slide / Close Combat. Reactiva el clásico Beat Up + Justified junto a Whimsicott (8.3% uso DuckDB) y destroza a Incineroar, Charizard-Y y Heatran.",
        "en": "[RUMORED] 108 Spe / 129 Atk Rock Slide + Close Combat menace. Re-enables classic Beat Up + Justified with Whimsicott (8.3% DuckDB usage) while crushing Incineroar, Charizard-Y, and Heatran.",
        "partners": ["Whimsicott", "Incineroar", "Tyranitar-Mega", "Farigiraf"],
        "checks": ["Rillaboom", "Sneasler", "Gholdengo", "Floette-Mega"],
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
        "es": "[RUMOR] Nuestra mascota de Coach Porygon: 135 SpA + Adaptability Hyper Beam / Tri Attack o Download + Ice Beam / Shadow Ball / Thunderbolt. En modo Tailwind o Psychic Terrain (Indeedee-F) revienta casi cualquier neutral.",
        "en": "[RUMORED] Coach Porygon's namesake powerhouse: 135 SpA + Adaptability Hyper Beam / Tri Attack or Download Ice Beam / Shadow Ball coverage. Terrifying beside Indeedee-F Follow Me or Whimsicott Tailwind.",
        "partners": ["Indeedee-F", "Whimsicott", "Incineroar", "Rillaboom"],
        "checks": ["Sneasler", "Gholdengo", "Kingambit"],
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
        "es": "[RUMOR] El socio icónico de DozoGiri: entra tras Tatsugiri y copia el +2 omni-boost de Dondozo con Costar, más Feint (rompe Protect), Wide Guard y Close Combat que destruye a Kingambit / Incineroar.",
        "en": "[RUMORED] Iconic DozoGiri endgame closer: Costar copies Dondozo's +2 omni-boost on switch-in, bringing Feint, Wide Guard, and Close Combat to shred Incineroar and Kingambit.",
        "partners": ["Dondozo", "Tatsugiri", "Incineroar"],
        "checks": ["Raichu-Mega-Y", "Floette-Mega", "Salamence-Mega"],
    },
    # --- B TIER ---
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
        "es": "[RUMOR] 108 Spe + 129 Def + Justified: check físico sólido a Kingambit/Sneasler/Tyranitar con Coaching, Quick Guard, Sacred Sword e Iron Defense + Body Press.",
        "en": "[RUMORED] 108 Spe / 129 Def physical check to Kingambit, Sneasler, and Tyranitar with Coaching, Quick Guard, Sacred Sword, and Body Press.",
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
        "es": "[RUMOR] 108 Spe + 129 SpD: resiste combos de Lluvia (Swampert-Mega / Politoed / Basculegion) y amenaza a Dondozo/Kingambit con Leaf Blade + Sacred Sword + Coaching.",
        "en": "[RUMORED] 108 Spe / 129 SpD anti-Rain answer threatening Swampert-Mega, Basculegion, Dondozo, and Kingambit with Leaf Blade + Sacred Sword.",
        "partners": ["Whimsicott", "Incineroar", "Heatran"],
        "checks": ["Salamence-Mega", "Staraptor-Mega", "Sneasler"],
    },
    {
        "name": "Marowak-Alola",
        "display": "Alolan Marowak",
        "status": "rumored",
        "tier": "B",
        "sprite": ("rumored", "marowak-alola.png"),
        "types": ["Fire", "Ghost"],
        "stats": [60, 80, 110, 50, 80, 45],
        "ability": "Lightning Rod (Thick Club legality unconfirmed)",
        "roles": ["tr", "offense"],
        "es": "[RUMOR] Con 45 Spe y Lightning Rod, absorbe Electric de Raichu-Mega-Y (25.3% uso!) protegiendo a Dondozo/Pelipper/Swampert-Mega. Su techo ofensivo depende de si Thick Club entra en Champions.",
        "en": "[RUMORED] At 45 Spe with Lightning Rod, blanks Raichu-Mega-Y (25.3% DuckDB usage!) beside Dondozo or Rain cores. Offensive ceiling hinges on Thick Club availability in Champions.",
        "partners": ["Farigiraf", "Indeedee-F", "Pelipper", "Dondozo"],
        "checks": ["Kingambit", "Incineroar", "Basculegion"],
    },
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
        "es": "[RUMOR] 130 Spe + Inner Focus (inmune a Fake Out de Incineroar/Rillaboom/Sneasler): Tailwind confiable, Haze anti-Dondozo, Super Fang y Taunt anti-Trick Room.",
        "en": "[RUMORED] 130 Spe + Inner Focus (Fake Out immune!): reliable Tailwind, anti-Dondozo Haze, Super Fang, and anti-Trick Room Taunt.",
        "partners": ["Heatran-Mega", "Garchomp-Mega-Z", "Kingambit"],
        "checks": ["Raichu-Mega-Y", "Gholdengo", "Archaludon"],
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
        "es": "[RUMOR] Well-Baked Body convierte Lava Plume / Heat Wave de Heatran y Charizard-Y en +2 Def gratis para Body Press + Yawn / Snarl / Helping Hand.",
        "en": "[RUMORED] Well-Baked Body turns Heatran Lava Plume & Charizard-Y Heat Wave into free +2 Def boosts for Body Press, Snarl, and Yawn.",
        "partners": ["Heatran", "Heatran-Mega", "Torkoal"],
        "checks": ["Gholdengo", "Sneasler", "Archaludon"],
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
        "es": "[RUMOR] Prankster Doodle (copia habilidades como Unaware o Water Compaction), Parting Shot, Encore y Taunt rápido a 110 Spe.",
        "en": "[RUMORED] Prankster Doodle (ability-swap tech), Parting Shot, Encore, and fast Taunt at 110 base Speed.",
        "partners": ["Slaking", "Dondozo", "Heatran-Mega"],
        "checks": ["Farigiraf", "Indeedee-F", "Gholdengo"],
    },
    # --- NICHE / SPECULATIVE WATCHLIST ---
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
        "es": "[RUMOR] Setter de Trick Room ultra-tanque (150/150 defensas + Sturdy/Clear Body) con Body Press y Skill Swap.",
        "en": "[RUMORED] Ultra-bulky Sturdy/Clear Body Trick Room setter (150/150 defenses) with Body Press and Skill Swap.",
        "partners": ["Heatran-Mega", "Torkoal", "Marowak-Alola"],
        "checks": ["Gholdengo", "Rillaboom", "Archaludon"],
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
        "es": "[RUMOR] Lightning Rod físico de 45 Spe en Trick Room; amenaza directa a Heatran si Thick Club vuelve.",
        "en": "[RUMORED] 45 Spe Trick Room Lightning Rod Ground attacker; checks Heatran if Thick Club returns.",
        "partners": ["Farigiraf", "Pelipper"],
        "checks": ["Rillaboom", "Basculegion"],
    },
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
        "es": "[RUMOR] 105 Spe + 135 SpD + Levitate con Freeze-Dry (golpea x4 a Swampert-Mega/Pelipper y x2 a Dondozo), Icy Wind y Haze.",
        "en": "[RUMORED] 105 Spe / 135 SpD Levitate user with Freeze-Dry (destroys Rain/Dondozo), Icy Wind, and Haze.",
        "partners": ["Ninetales-Alola", "Incineroar"],
        "checks": ["Sneasler", "Incineroar", "Heatran-Mega"],
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
        "es": "[RUMOR] Setter de Trick Room / Simple Beam / Taunt con Thick Fat que resiste Fuego de Heatran y Charizard-Y.",
        "en": "[RUMORED] Niche Thick Fat Trick Room / Simple Beam support resisting Heatran and Charizard-Y Fire spread.",
        "partners": ["Heatran-Mega", "Incineroar"],
        "checks": ["Kingambit", "Gholdengo"],
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
        "es": "[RUMOR] 45 Spe Inner Focus con Wide Guard, Helping Hand y Storm Throw (crítico garantizado que ignora +2 Def de Dondozo).",
        "en": "[RUMORED] 45 Spe Inner Focus Wide Guard user with always-crit Storm Throw piercing Dondozo Defense boosts.",
        "partners": ["Farigiraf", "Heatran-Mega"],
        "checks": ["Floette-Mega", "Salamence-Mega"],
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
        "es": "[RUMOR] Sturdy / Inner Focus Close Combat breaker con Coaching y Quick Guard.",
        "en": "[RUMORED] Sturdy / Inner Focus Close Combat breaker with Coaching and Quick Guard.",
        "partners": ["Whimsicott", "Incineroar"],
        "checks": ["Floette-Mega", "Sneasler"],
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
        "es": "[RUMOR] Sin Toxic Orb en Champions, depende de envenenamiento aliado o sets Quick Guard / Knock Off.",
        "en": "[RUMORED] Without Toxic Orb in Champions, relies on partner poison setup or niche Quick Guard / Knock Off.",
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
        "es": "[RUMOR] Atacante mixto Infiltrator con Haze, Glare y Acid Spray para bajar SpD en equipos de nicho.",
        "en": "[RUMORED] Mixed Infiltrator niche pick with Haze, Glare, and Acid Spray support.",
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
        "es": "[RUMOR] 40 Spe Trick Room Protean con Fake Out, Skill Swap, Shadow Sneak y Sucker Punch.",
        "en": "[RUMORED] 40 Spe Trick Room Protean user with Fake Out, Skill Swap, and Shadow Sneak.",
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
        "es": "[RUMOR] Utilidad de nicho con Fake Out, Icy Wind, Tailwind y Vital Spirit (inmune a Spore si entra Amoonguss).",
        "en": "[RUMORED] Niche Fake Out + Icy Wind + Tailwind utility with Vital Spirit (Spore immunity if Amoonguss arrives).",
        "partners": ["Heatran-Mega"],
        "checks": ["Incineroar", "Raichu-Mega-Y"],
    },
]


# Real DuckDB Top Cut Regulation M-C shells & proposed Regulation M-D adaptation blueprints
TEAM_BLUEPRINTS: List[Dict[str, Any]] = [
    {
        "id": "laic1_rain_heatran",
        "badge_status": "confirmed",
        "source_label": "LAIC 2027 #1 Champion — Masahiro Taoka (14-2)",
        "title_es": "Lluvia + Mega Heatran (Water Compaction) & Mega Gengar",
        "title_en": "Rain Balance + Mega Heatran (Water Compaction) & Mega Gengar",
        "base_shell": ["Swampert-Mega", "Archaludon", "Politoed", "Incineroar", "Rillaboom", "Gengar-Mega"],
        "swap_out": ["Swampert-Mega", "Archaludon"],
        "swap_in": ["Heatran-Mega", "Dondozo"],
        "adapted_team": [
            ("Heatran-Mega", "md", "heatran-mega.png"),
            ("Politoed", "mc", None),
            ("Incineroar", "mc", None),
            ("Rillaboom", "mc", None),
            ("Gengar-Mega", "mc", None),
            ("Dondozo", "mc_or_md", "dondozo.png"),
        ],
        "note_es": "Mantiene el núcleo ganador de LAIC (Politoed + Incineroar + Rillaboom + Mega Gengar Perish Trap). Mega Heatran entra con Water Compaction (+2 Def si recibe un movimiento Agua) y cubre Grass/Fairy/Steel, mientras Mega Gengar atrapa a DozoGiri rivales con Perish Song.",
        "note_en": "Preserves LAIC's winning Politoed + Incineroar + Rillaboom + Mega Gengar Perish Trap skeleton. Mega Heatran brings Water Compaction (+2 Def on Water hits) and checks opposing Rillaboom/Floette/Gholdengo while Mega Gengar traps opposing DozoGiri via Perish Song.",
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
        "note_es": "Sustituye Delphox-Mega por Mega Heatran (67 Spe, 175 SpA): bajo Sol de Torkoal y Trick Room de Farigiraf, Heat Wave / Eruption + Earth Power alcanzan niveles de daño absurdos, y Sol reduce a la mitad la debilidad x2 a Agua activando Water Compaction con daño mínimo.",
        "note_en": "Swaps Delphox-Mega for Mega Heatran (67 Spe, 175 SpA): under Torkoal Sun + Farigiraf Trick Room, boosted Heat Wave reaches nuclear KOs, while Sun halves Water damage so Mega Heatran survives Water hits and banks +2 Def via Water Compaction.",
    },
    {
        "id": "laic5_dozogiri_flex",
        "badge_status": "confirmed",
        "source_label": "LAIC 2027 Top 8 — Kandai Nagatome (12-2)",
        "title_es": "Núcleo Rilla-Incin-Sneasler + Modo Dual DozoGiri / Mega Tatsugiri",
        "title_en": "Rilla-Incin-Sneasler Core + Dual DozoGiri / Mega Tatsugiri Mode",
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
        "note_es": "Explota el trío de mayor uso de DuckDB (Rillaboom 48.6% + Sneasler 39.0% + Incineroar 35.1%) como modo 2-2-2: en Team Preview el rival debe adivinar si juegas Commander Dondozo o Mega Tatsugiri (+1 SpA Premium Grade) sin sacrificar presión de Salamence-Mega.",
        "note_en": "Leverages DuckDB's #1–#3 meta core (Rillaboom 48.6%, Sneasler 39.0%, Incineroar 35.1%) as a 2-2-2 shell: opponents face a brutal Team Preview guess between Commander Dondozo OR standalone +1 SpA Premium Grade Mega Tatsugiri.",
    },
    {
        "id": "laic4_balance_latias_heatran",
        "badge_status": "rumored",
        "source_label": "LAIC 2027 Top 4 — Samuel Pereira (12-3)",
        "title_es": "Balance Anti-Intimidate + Heatran & Mega Latias (si entra Eon Duo)",
        "title_en": "Anti-Intimidate Balance + Heatran & Mega Latias (Eon Duo Forecast)",
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
        "note_es": "[PROYECCIÓN CON RUMOR] Heatran reemplaza a Arcanine-Hisui con inmunidad Flash Fire y sinergia perfecta con Milotic (Haze anti-Dondozo + Competitive) y Mega Latias (Levitate inmune a Ground + Tailwind/Calm Mind).",
        "note_en": "[INCLUDES RUMORED WAVE] Heatran upgrades the Fire slot with Flash Fire alongside Milotic (Haze anti-Dondozo + Competitive) and Levitate Mega Latias (Ground immunity + Tailwind/Calm Mind).",
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
        "note_es": "[PROYECCIÓN CON RUMOR] Evolución natural del Hard TR de Camerupt-Mega: sin Safety Goggles en Champions, Amoonguss (Spore + Rage Powder + Clear Smog anti-Dondozo) y Lightning Rod Alolan Marowak (bloquea Raichu-Mega-Y) protegen el sweep de Mega Heatran.",
        "note_en": "[INCLUDES RUMORED WAVE] Natural upgrade to Camerupt-Mega Hard TR: with Safety Goggles illegal in Champions, Amoonguss (Spore + Rage Powder + anti-Dondozo Clear Smog) and Lightning Rod Alolan Marowak shield Mega Heatran sweeps.",
    },
    {
        "id": "dozo_flamigo_porygonz",
        "badge_status": "rumored",
        "source_label": "DuckDB Regional Hyper-Offense Core (Whimsicott + Indeedee-F)",
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
        "note_es": "[PROYECCIÓN CON RUMOR] Dos planes de victoria letales: Modo A (DozoGiri + Costar Flamigo copiando +2 en todos los stats) o Modo B (Indeedee-F Follow Me + Porygon-Z Adaptability / Mega Tatsugiri +1 SpA sin prioridad rival en Campo Psíquico).",
        "note_en": "[INCLUDES RUMORED WAVE] Dual-win-condition offense: Mode A (DozoGiri + Costar Flamigo inheriting +2 omni-boosts) or Mode B (Indeedee-F Psychic Terrain Follow Me + Adaptability Porygon-Z / +1 SpA Mega Tatsugiri).",
    },
]


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


def generate_report(out_path: Path = DEFAULT_OUT) -> Path:
    """Query DuckDB, embed Base64 sprites, and write standalone `reg_md_meta_scout.html`."""
    reg = get_registry()
    con = reg.con
    slug_map = json.loads(SLUG_MAP_PATH.read_text(encoding="utf-8"))

    # Live DuckDB metrics across all ingested tournaments (including LAIC 2027)
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
        LIMIT 12
        """,
        [max(1, total_players)],
    ).fetchall()

    # Pre-encode community logos
    pokemmunity_b64 = _b64_png(COMMUNITY_DIR / "pokemmunity.png")
    pokemex_b64 = _b64_png(COMMUNITY_DIR / "pokemex.png")

    # Build top-12 DuckDB incumbent strip
    incumbent_cards_html: List[str] = []
    for sp, cnt, pct in top_mc_rows:
        sp_b64 = _b64_png(_resolve_sprite_path("mc", None, sp, slug_map))
        incumbent_cards_html.append(
            f"""<div class="inc-chip">
              <img src="{sp_b64}" alt="{html.escape(sp)}" />
              <div>
                <div class="inc-name">{html.escape(sp)}</div>
                <div class="inc-pct">{pct:.1f}% <span class="muted">({cnt})</span></div>
              </div>
            </div>"""
        )

    # Build Unified Tier List cards
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
            sp_b64 = _b64_png(_resolve_sprite_path(kind, fname, m["name"], slug_map))
            alt_imgs = ""
            for ak, af in m.get("alt_sprites", []):
                ab64 = _b64_png(_resolve_sprite_path(ak, af, m["name"], slug_map))
                if ab64:
                    alt_imgs += f'<img class="alt-spr" src="{ab64}" alt="{html.escape(m["display"])}" />'
            stone_img = ""
            if m.get("stone"):
                sb64 = _b64_png(MEGASTONES_DIR / m["stone"])
                if sb64:
                    stone_img = f'<img class="stone-ico" src="{sb64}" alt="Mega Stone" title="{html.escape(m["stone"].replace(".png", "").title())}" />'

            is_conf = m["status"] == "confirmed"
            badge_cls = "badge-confirmed" if is_conf else "badge-rumored"
            badge_es = "✅ CONFIRMADO M-D" if is_conf else "🔮 RUMOR / SIN CONFIRMAR"
            badge_en = "✅ CONFIRMED M-D" if is_conf else "🔮 RUMORED / UNCONFIRMED"
            types_html = "".join(
                f'<span class="type-pill" style="border-color:{TYPE_COLORS.get(t, "#64748b")};color:{TYPE_COLORS.get(t, "#e2e8f0")}">{html.escape(t)}</span>'
                for t in m["types"]
            )
            hp, atk, df, spa, spd, spe = m["stats"]
            bst = sum(m["stats"])
            s0, s32, s32p = _l50_speed_range(spe)

            partner_chips = "".join(
                f'<span class="mini-tag">{html.escape(p)}</span>' for p in m["partners"]
            )
            check_chips = "".join(
                f'<span class="mini-tag danger">{html.escape(c)}</span>' for c in m["checks"]
            )
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
                    <b>{s0}</b> (0 SP) · <b>{s32}</b> (32 SP) · <b>{s32p}</b> (+Spe)
                  </div>
                  <p class="mon-note" data-es="{html.escape(m['es'])}" data-en="{html.escape(m['en'])}">{html.escape(m['es'])}</p>
                  <div class="mon-meta-rows">
                    <div><span class="meta-lbl" data-es="Socios M-C:" data-en="M-C Partners:">Socios M-C:</span> {partner_chips}</div>
                    <div><span class="meta-lbl" data-es="Checks M-C:" data-en="M-C Checks:">Checks M-C:</span> {check_chips}</div>
                  </div>
                </article>"""
            )
        tier_label_es = {"S": "Tier S — Pilares del Meta Proyectado M-D", "A": "Tier A — Amenazas y Socios Top Cut", "B": "Tier B — Roles Especializados y Techs", "Niche": "Watchlist — Opciones de Nicho (Rumor)"}[tier]
        tier_label_en = {"S": "Tier S — Projected Reg M-D Meta Pillars", "A": "Tier A — Top Cut Threats & Enablers", "B": "Tier B — Specialized Roles & Techs", "Niche": "Watchlist — Niche / Speculative Picks"}[tier]
        tier_sections_html.append(
            f"""<section class="tier-section" data-tier="{tier}">
              <h2 class="tier-heading tier-{tier.lower()}" data-es="{tier_label_es}" data-en="{tier_label_en}">{tier_label_es}</h2>
              <div class="mon-grid">{''.join(cards)}</div>
            </section>"""
        )

    # Build DuckDB Team Adaptation Blueprints
    blueprint_cards_html: List[str] = []
    for bp in TEAM_BLUEPRINTS:
        is_conf = bp["badge_status"] == "confirmed"
        b_cls = "badge-confirmed" if is_conf else "badge-rumored"
        b_es = "✅ SOLO CONFIRMADOS M-D" if is_conf else "🔮 INCLUYE OLA DE RUMOR"
        b_en = "✅ CONFIRMED M-D ONLY" if is_conf else "🔮 INCLUDES RUMORED WAVE"
        team_slots_html: List[str] = []
        for sp, skind, sfname in bp["adapted_team"]:
            p = _resolve_sprite_path(skind, sfname, sp, slug_map)
            sb64 = _b64_png(p)
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
        blueprint_cards_html.append(
            f"""<article class="bp-card" data-status="{bp['badge_status']}">
              <div class="bp-head">
                <span class="status-badge {b_cls}" data-es="{b_es}" data-en="{b_en}">{b_es}</span>
                <span class="bp-source">DuckDB · {html.escape(bp['source_label'])}</span>
              </div>
              <h3 class="bp-title" data-es="{html.escape(bp['title_es'])}" data-en="{html.escape(bp['title_en'])}">{html.escape(bp['title_es'])}</h3>
              <div class="bp-swap-pill"><strong>Swap:</strong> {html.escape(swaps_str)}</div>
              <div class="bp-team-row">{''.join(team_slots_html)}</div>
              <p class="bp-note" data-es="{html.escape(bp['note_es'])}" data-en="{html.escape(bp['note_en'])}">{html.escape(bp['note_es'])}</p>
            </article>"""
        )

    gen_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    doc = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Coach Porygon VGC — Regulation M-D Meta Scout (Offline Base64)</title>
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
      font-size: 13px; line-height: 1.48;
      background-image: radial-gradient(ellipse 80% 45% at 15% -5%, rgba(34,211,238,0.09), transparent 65%),
                        radial-gradient(ellipse 65% 40% at 88% 0%, rgba(244,63,94,0.08), transparent 60%);
    }}
    .ribbon {{ height: 3px; background: linear-gradient(90deg, var(--cyan), #3b82f6, var(--magenta), var(--gold), var(--cyan)); }}
    .wrap {{ max-width: 1260px; margin: 0 auto; padding: 18px 16px 36px; }}
    .hero {{
      background: linear-gradient(135deg, rgba(13,21,38,0.96), rgba(19,31,55,0.92));
      border: 1px solid var(--border); border-radius: 14px; padding: 18px 20px; margin-bottom: 16px;
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
    .lang-btn {{
      background: transparent; color: var(--muted); border: 0; padding: 5px 11px; font-weight: 700; cursor: pointer; font-size: 11.5px;
    }}
    .lang-btn.active {{ background: var(--cyan); color: #06101d; }}
    h1 {{ margin: 4px 0 6px; font-size: 22px; letter-spacing: -0.02em; }}
    .hero-sub {{ margin: 0; color: var(--muted); max-width: 920px; }}
    .callout-warn {{
      margin-top: 12px; padding: 10px 13px; border-radius: 10px;
      background: rgba(250,204,21,0.08); border: 1px solid rgba(250,204,21,0.32); font-size: 12px; color: #fef08a;
    }}
    .inc-panel {{
      background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px; margin-bottom: 16px;
    }}
    .sec-title {{ font-size: 13px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.05em; color: var(--cyan); margin: 0 0 10px; }}
    .inc-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; }}
    .inc-chip {{
      display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 9px;
      background: var(--surface-2); border: 1px solid var(--border);
    }}
    .inc-chip img {{ width: 34px; height: 34px; object-fit: contain; }}
    .inc-name {{ font-weight: 700; font-size: 11.5px; }}
    .inc-pct {{ font-size: 11px; color: var(--gold); font-weight: 700; }}
    .muted {{ color: var(--muted); font-weight: 400; }}
    .toolbar {{
      display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px;
      background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 10px 14px; margin-bottom: 16px;
      position: sticky; top: 8px; z-index: 20; backdrop-filter: blur(10px);
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
    .tier-section {{ margin-bottom: 22px; }}
    .tier-heading {{
      font-size: 15px; font-weight: 800; margin: 0 0 10px; padding: 7px 12px; border-radius: 9px;
      border-left: 4px solid var(--cyan); background: rgba(13,21,38,0.9);
    }}
    .tier-s {{ border-left-color: var(--gold); color: var(--gold); }}
    .tier-a {{ border-left-color: var(--cyan); color: var(--cyan); }}
    .tier-b {{ border-left-color: var(--indigo); color: #a5b4fc; }}
    .tier-niche {{ border-left-color: #94a3b8; color: #cbd5e1; }}
    .mon-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(310px, 1fr)); gap: 12px; }}
    .mon-card {{
      background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 12px;
      display: flex; flex-direction: column; gap: 7px;
    }}
    .badge-confirmed-card {{ border-color: rgba(34,197,94,0.42); box-shadow: inset 0 0 0 1px rgba(34,197,94,0.12); }}
    .badge-rumored-card {{ border-color: rgba(129,140,248,0.34); }}
    .mon-head {{ display: flex; gap: 10px; align-items: center; }}
    .mon-spr-wrap {{ position: relative; width: 66px; height: 66px; flex-shrink: 0; background: #080e1c; border-radius: 10px; display: flex; align-items: center; justify-content: center; border: 1px solid var(--border); }}
    .main-spr {{ width: 60px; height: 60px; object-fit: contain; }}
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
    .bp-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 12px; margin-bottom: 24px; }}
    .bp-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 13px; display: flex; flex-direction: column; gap: 8px; }}
    .bp-head {{ display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 6px; }}
    .bp-source {{ font-size: 10.5px; color: var(--gold); font-weight: 700; }}
    .bp-title {{ margin: 0; font-size: 14.5px; }}
    .bp-swap-pill {{ font-size: 11.5px; color: #86efac; background: rgba(34,197,94,0.09); border: 1px solid rgba(34,197,94,0.28); padding: 4px 8px; border-radius: 7px; }}
    .bp-team-row {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 5px; }}
    .team-slot {{
      position: relative; background: #080e1c; border: 1px solid var(--border); border-radius: 8px; padding: 6px 3px 5px;
      display: flex; flex-direction: column; align-items: center; text-align: center; gap: 3px; font-size: 9.5px; color: #cbd5e1;
    }}
    .team-slot.is-new {{ border-color: var(--gold); background: rgba(250,204,21,0.08); color: #fef08a; font-weight: 700; }}
    .team-slot img {{ width: 42px; height: 42px; object-fit: contain; }}
    .new-pill {{ position: absolute; top: 2px; right: 2px; font-size: 8px; font-weight: 800; background: var(--gold); color: #060a14; padding: 0 4px; border-radius: 4px; }}
    .bp-note {{ margin: 0; font-size: 12px; color: #cbd5e1; }}
    .footer {{
      border-top: 1px solid var(--border); padding-top: 14px; font-size: 11px; color: var(--muted);
      display: flex; flex-direction: column; gap: 8px;
    }}
    .thanks-strip {{
      display: flex; flex-wrap: wrap; align-items: center; gap: 10px; padding: 8px 12px;
      background: rgba(34,211,238,0.06); border: 1px solid rgba(34,211,238,0.22); border-radius: 10px;
    }}
    .thanks-strip img {{ width: 26px; height: 26px; border-radius: 50%; object-fit: cover; border: 1px solid rgba(255,255,255,0.25); }}
    .hidden {{ display: none !important; }}
    @media (max-width: 640px) {{
      .bp-team-row {{ grid-template-columns: repeat(3, 1fr); }}
      .mon-grid, .bp-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="ribbon"></div>
  <div class="wrap">
    <header class="hero">
      <div class="hero-top">
        <div class="pill-row">
          <span class="pill">POKÉMON CHAMPIONS · REG M-D SCOUT</span>
          <span class="pill gold">DEC 2, 2026 – MAR 3, 2027</span>
          <span class="pill mag">DuckDB: {n_tournaments} Regionals · {total_players:,} Teams ({total_slots:,} Slots)</span>
        </div>
        <div class="lang-toggle" role="group" aria-label="Language">
          <button class="lang-btn active" id="btn-es" type="button">ES</button>
          <button class="lang-btn" id="btn-en" type="button">EN</button>
        </div>
      </div>
      <h1 data-es="🔮 Coach Porygon VGC — Scout Proyectado de Regulation M-D (Offline Base64)" data-en="🔮 Coach Porygon VGC — Regulation M-D Projected Meta Scout (Offline Base64)">🔮 Coach Porygon VGC — Scout Proyectado de Regulation M-D (Offline Base64)</h1>
      <p class="hero-sub" data-es="Tier List unificada combinando los añadidos oficiales confirmados de Regulation M-D (Heatran, Mega Heatran Water Compaction, Dondozo, Tatsugiri y Mega Tatsugiri Premium Grade) con la ola de pronóstico comunitario (@OSAKA_POKEMON), cruzados contra equipos Top Cut reales de nuestros {n_tournaments} torneos en DuckDB (incluyendo LAIC 2027)." data-en="Unified Tier List combining officially confirmed Regulation M-D additions (Heatran, Water Compaction Mega Heatran, Dondozo, Tatsugiri & Premium Grade Mega Tatsugiri) with the community forecast wave (@OSAKA_POKEMON), grounded against real Top Cut rosters across all {n_tournaments} DuckDB tournaments (including LAIC 2027).">
        Tier List unificada combinando los añadidos oficiales confirmados de Regulation M-D (Heatran, Mega Heatran Water Compaction, Dondozo, Tatsugiri y Mega Tatsugiri Premium Grade) con la ola de pronóstico comunitario (@OSAKA_POKEMON), cruzados contra equipos Top Cut reales de nuestros {n_tournaments} torneos en DuckDB (incluyendo LAIC 2027).
      </p>
      <div class="callout-warn" data-es="⚠️ Transparencia Anti-Alucinación: Cada tarjeta marca explícitamente ✅ CONFIRMADO M-D (datos oficiales de Pokémon Champions / Pokéos) frente a 🔮 RUMOR / SIN CONFIRMAR (especulación comunitaria de los 24 Pokémon / 4 Megas anunciados). El motor principal Tensor Core permanece 100% bloqueado en Regulation M-C hasta el lanzamiento oficial." data-en="⚠️ Anti-Hallucination Transparency: Every card unmistakably distinguishes ✅ CONFIRMED M-D (official Pokémon Champions / Pokéos announcements) from 🔮 RUMORED / UNCONFIRMED (community speculation for the announced 24 species / 4 Megas). The core Tensor Core engine remains strictly Regulation M-C until official launch.">
        ⚠️ Transparencia Anti-Alucinación: Cada tarjeta marca explícitamente ✅ CONFIRMADO M-D (datos oficiales de Pokémon Champions / Pokéos) frente a 🔮 RUMOR / SIN CONFIRMAR (especulación comunitaria de los 24 Pokémon / 4 Megas anunciados). El motor principal Tensor Core permanece 100% bloqueado en Regulation M-C hasta el lanzamiento oficial.
      </div>
    </header>

    <section class="inc-panel">
      <h2 class="sec-title" data-es="📊 Meta Base DuckDB ({n_tournaments} Torneos Reg M-C incl. LAIC 2027 — Top 12 Incumbentes)" data-en="📊 DuckDB Reg M-C Baseline ({n_tournaments} Tournaments incl. LAIC 2027 — Top 12 Incumbents)">📊 Meta Base DuckDB ({n_tournaments} Torneos Reg M-C incl. LAIC 2027 — Top 12 Incumbentes)</h2>
      <div class="inc-grid">{''.join(incumbent_cards_html)}</div>
    </section>

    <div class="toolbar">
      <div class="filter-row" id="filter-row">
        <button class="f-btn active" data-filter="all" type="button" data-es="Todos ({len(MD_CATALOG)})" data-en="All ({len(MD_CATALOG)})">Todos ({len(MD_CATALOG)})</button>
        <button class="f-btn" data-filter="confirmed" type="button" data-es="✅ Confirmados M-D ({confirmed_count})" data-en="✅ Confirmed M-D ({confirmed_count})">✅ Confirmados M-D ({confirmed_count})</button>
        <button class="f-btn" data-filter="rumored" type="button" data-es="🔮 Rumor / Pronóstico ({rumored_count})" data-en="🔮 Rumored Wave ({rumored_count})">🔮 Rumor / Pronóstico ({rumored_count})</button>
        <button class="f-btn" data-filter="mega" type="button" data-es="💎 Megas ({mega_count})" data-en="💎 Megas ({mega_count})">💎 Megas ({mega_count})</button>
        <button class="f-btn" data-filter="tr" type="button" data-es="🌀 Trick Room / Bulk" data-en="🌀 Trick Room / Bulk">🌀 Trick Room / Bulk</button>
        <button class="f-btn" data-filter="offense" type="button" data-es="⚔ Ofensiva" data-en="⚔ Offense">⚔ Ofensiva</button>
      </div>
      <input class="search-inp" id="search-inp" type="search" placeholder="Buscar Pokémon, tipo o habilidad..." />
    </div>

    <main id="tier-root">
      {''.join(tier_sections_html)}
    </main>

    <section style="margin-top:26px">
      <h2 class="tier-heading tier-a" data-es="🧩 Equipos de Torneo DuckDB (LAIC 2027 & Regionales) Adaptados a Regulation M-D" data-en="🧩 Real DuckDB Tournament Shells (LAIC 2027 & Regionals) Adapted for Regulation M-D">🧩 Equipos de Torneo DuckDB (LAIC 2027 &amp; Regionales) Adaptados a Regulation M-D</h2>
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
        Credits: Pokéos (sprites &amp; M-D catalog) · MunchStats (9 Regional/IC datasets incl. LAIC 2027) · Pokémon Showdown (Champions mod data) · DuckDB.
      </div>
    </footer>
  </div>
  <script>
    (function() {{
      let activeFilter = "all";
      let lang = "es";
      function applyFilters() {{
        const q = (document.getElementById("search-inp").value || "").trim().toLowerCase();
        document.querySelectorAll(".mon-card").forEach((card) => {{
          const roles = (card.dataset.roles || "").split(/\\s+/);
          const matchFilter = activeFilter === "all" || roles.includes(activeFilter);
          const matchSearch = !q || (card.dataset.search || "").includes(q);
          card.classList.toggle("hidden", !(matchFilter && matchSearch));
        }});
        document.querySelectorAll(".tier-section").forEach((sec) => {{
          const vis = sec.querySelectorAll(".mon-card:not(.hidden)").length;
          sec.classList.toggle("hidden", vis === 0);
        }});
      }}
      function applyLang(nextLang) {{
        lang = nextLang;
        document.getElementById("btn-es").classList.toggle("active", lang === "es");
        document.getElementById("btn-en").classList.toggle("active", lang === "en");
        document.querySelectorAll("[data-es][data-en]").forEach((el) => {{
          el.textContent = el.getAttribute(lang === "es" ? "data-es" : "data-en");
        }});
        document.getElementById("search-inp").placeholder =
          lang === "es" ? "Buscar Pokémon, tipo o habilidad..." : "Search Pokémon, type, or ability...";
      }}
      document.querySelectorAll(".f-btn").forEach((btn) => {{
        btn.addEventListener("click", () => {{
          activeFilter = btn.dataset.filter || "all";
          document.querySelectorAll(".f-btn").forEach((b) => b.classList.toggle("active", b === btn));
          applyFilters();
        }});
      }});
      document.getElementById("search-inp").addEventListener("input", applyFilters);
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
        f"[OK] Generated Regulation M-D Meta Scout Base64 HTML: {out_path} "
        f"({out_path.stat().st_size / 1024:.1f} KB, {len(MD_CATALOG)} Pokémon, {len(TEAM_BLUEPRINTS)} DuckDB blueprints)"
    )
    return out_path


if __name__ == "__main__":
    generate_report()
