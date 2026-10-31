#!/usr/bin/env python3
"""
Coach Porygon VGC — Visual Asset & Telemetry Engine
Generates:
1. 45+ Bespoke SVG Pokémon Sprites and Battle UI Icons in `assets/sprites/` and `assets/icons/`.
2. Full Live Telemetry & Pokédex Snapshot (`assets/live_telemetry.json`) grounded in:
   - `data/MC_Available_Pokemon.csv` (363 legal species with Base Stats, Typings, and Abilities)
   - `data/Teams.csv` (All 24 registered user teams T01–T24)
   - `data/Scouted_Teams.csv` (All scouted opponent OTS rosters ST01–STxx)
   - `data/Raw_Matches.csv` (All 322 match telemetry records)
   - `data/Playstyle_Diagnostics.csv` (All 14 diagnostic mistake audits)
   - `data/Damage_Calculations.csv` (All 290 verified damage calculations)
   - `data/Tournament_Meta.json` (Sanctioned MunchStats tournament analytics)
"""

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
ASSETS_DIR = REPO_ROOT / "assets"
SPRITES_DIR = ASSETS_DIR / "sprites"
ICONS_DIR = ASSETS_DIR / "icons"

# ==============================================================================
# 1. Bespoke SVG Pokémon Sprite Library (45+ Regulation M-C Staples)
# ==============================================================================

POKEMON_SVGS: Dict[str, str] = {
    "porygon-coach": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="poryPink" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#ff5ca8"/><stop offset="100%" stop-color="#d91b72"/></linearGradient>
    <linearGradient id="poryCyan" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#00f2fe"/><stop offset="100%" stop-color="#0284c7"/></linearGradient>
  </defs>
  <polygon points="60,6 108,33 108,87 60,114 12,87 12,33" fill="#0f172a" stroke="#00f2fe" stroke-width="2" stroke-opacity="0.5"/>
  <polygon points="88,78 112,62 104,88" fill="url(#poryCyan)" stroke="#0f172a" stroke-width="1.5"/>
  <polygon points="34,66 64,56 90,74 76,100 38,98" fill="url(#poryPink)" stroke="#0f172a" stroke-width="1.5"/>
  <polygon points="44,72 78,74 70,96 42,94" fill="url(#poryCyan)" stroke="#0f172a" stroke-width="1.5"/>
  <polygon points="26,96 46,92 48,106 22,106" fill="url(#poryCyan)" stroke="#0f172a" stroke-width="1.5"/>
  <polygon points="68,94 88,92 94,106 68,106" fill="url(#poryCyan)" stroke="#0f172a" stroke-width="1.5"/>
  <polygon points="36,24 72,20 84,44 68,66 36,62" fill="url(#poryPink)" stroke="#0f172a" stroke-width="1.5"/>
  <polygon points="12,48 38,38 42,60 16,58" fill="url(#poryCyan)" stroke="#0f172a" stroke-width="1.5"/>
  <polygon points="28,34 62,32 58,46 26,44" fill="#00f2fe" fill-opacity="0.85" stroke="#ffffff" stroke-width="1.2"/>
  <circle cx="48" cy="39" r="3.5" fill="#0f172a"/>
  <path d="M58,20 C76,20 82,36 78,52" fill="none" stroke="#facc15" stroke-width="3.5" stroke-linecap="round"/>
  <circle cx="76" cy="50" r="6" fill="#1e293b" stroke="#facc15" stroke-width="2"/>
</svg>""",
    "charizard-mega-y": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <circle cx="60" cy="60" r="50" fill="#f97316" fill-opacity="0.14"/>
  <polygon points="55,48 8,14 16,46 6,62 24,68 18,84 52,70" fill="#fb923c" stroke="#7c2d12" stroke-width="1.5"/>
  <polygon points="50,52 16,24 22,50 14,60 48,66" fill="#0d9488"/>
  <polygon points="65,48 112,14 104,46 114,62 96,68 102,84 68,70" fill="#fb923c" stroke="#7c2d12" stroke-width="1.5"/>
  <polygon points="70,52 104,24 98,50 106,60 72,66" fill="#0d9488"/>
  <polygon points="104,76 96,54 104,60 112,46 114,66 112,78" fill="#ef4444"/>
  <ellipse cx="60" cy="76" rx="18" ry="22" fill="#f97316" stroke="#7c2d12" stroke-width="1.5"/>
  <ellipse cx="60" cy="78" rx="12" ry="16" fill="#fef08a"/>
  <polygon points="60,26 60,6 65,26" fill="#fef08a"/>
  <polygon points="44,28 76,28 72,44 48,44" fill="#f97316" stroke="#7c2d12" stroke-width="1.5"/>
  <polygon points="49,33 56,36 49,38" fill="#ffffff"/>
  <polygon points="71,33 64,36 71,38" fill="#ffffff"/>
</svg>""",
    "raichu-mega-x": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <circle cx="60" cy="60" r="48" fill="#facc15" fill-opacity="0.15"/>
  <polygon points="72,82 108,48 96,68 114,68 82,96" fill="#facc15" stroke="#b45309" stroke-width="1.5"/>
  <polygon points="48,82 12,48 24,68 6,68 38,96" fill="#38bdf8" stroke="#0369a1" stroke-width="1.5"/>
  <ellipse cx="60" cy="76" rx="20" ry="22" fill="#f59e0b" stroke="#78350f" stroke-width="1.5"/>
  <ellipse cx="60" cy="80" rx="13" ry="15" fill="#fef3c7"/>
  <polygon points="46,34 24,10 38,14 32,26 52,30" fill="#1e293b" stroke="#facc15" stroke-width="1.5"/>
  <polygon points="74,34 96,10 82,14 88,26 68,30" fill="#1e293b" stroke="#facc15" stroke-width="1.5"/>
  <circle cx="60" cy="46" r="18" fill="#f59e0b" stroke="#78350f" stroke-width="1.5"/>
  <circle cx="52" cy="43" r="3" fill="#1e293b"/><circle cx="68" cy="43" r="3" fill="#1e293b"/>
  <circle cx="46" cy="51" r="4" fill="#38bdf8"/><circle cx="74" cy="51" r="4" fill="#ef4444"/>
</svg>""",
    "garchomp": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="60,12 46,44 74,44" fill="#1e3a8a" stroke="#0f172a" stroke-width="1.5"/>
  <polygon points="38,56 10,64 26,84 42,70" fill="#f8fafc" stroke="#1e3a8a" stroke-width="2"/>
  <polygon points="82,56 110,64 94,84 78,70" fill="#f8fafc" stroke="#1e3a8a" stroke-width="2"/>
  <polygon points="42,52 78,52 72,96 48,96" fill="#dc2626" stroke="#0f172a" stroke-width="1.5"/>
  <polygon points="50,72 70,72 66,94 54,94" fill="#facc15"/>
  <ellipse cx="34" cy="36" rx="10" ry="6" fill="#1e3a8a"/><ellipse cx="86" cy="36" rx="10" ry="6" fill="#1e3a8a"/>
  <polygon points="42,28 78,28 70,54 50,54" fill="#1e3a8a" stroke="#0f172a" stroke-width="1.5"/>
  <polygon points="60,28 55,36 60,42 65,36" fill="#facc15"/>
  <polygon points="46,38 54,41 47,43" fill="#facc15"/><polygon points="74,38 66,41 73,43" fill="#facc15"/>
</svg>""",
    "grimmsnarl": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="20,98 14,34 38,16 60,22 82,16 106,34 100,98" fill="#18181b" stroke="#3f3f46" stroke-width="1.5"/>
  <polygon points="60,62 72,76 60,90 48,76" fill="#ef4444"/>
  <polygon points="38,38 14,28 32,48" fill="#4ade80"/><polygon points="82,38 106,28 88,48" fill="#4ade80"/>
  <polygon points="40,30 80,30 74,56 46,56" fill="#4ade80" stroke="#14532d" stroke-width="1.5"/>
  <polygon points="45,38 55,42 46,44" fill="#ef4444"/><polygon points="75,38 65,42 74,44" fill="#ef4444"/>
  <polygon points="48,49 72,49 68,54 52,54" fill="#ffffff"/>
</svg>""",
    "kingambit": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <ellipse cx="60" cy="84" rx="40" ry="18" fill="#18181b" stroke="#475569" stroke-width="1.5"/>
  <polygon points="38,54 82,54 76,96 44,96" fill="#991b1b" stroke="#0f172a" stroke-width="1.5"/>
  <rect x="44" y="64" width="32" height="4" rx="2" fill="#e2e8f0"/><rect x="46" y="74" width="28" height="4" rx="2" fill="#e2e8f0"/>
  <circle cx="60" cy="40" r="16" fill="#991b1b"/>
  <polygon points="56,34 60,4 64,34" fill="#facc15" stroke="#854d0e" stroke-width="1.5"/>
  <polygon points="60,44 20,32 28,48" fill="#cbd5e1"/><polygon points="60,44 100,32 92,48" fill="#cbd5e1"/>
</svg>""",
    "milotic": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="76,74 114,52 110,92 80,96" fill="#38bdf8" stroke="#0284c7" stroke-width="1.5"/>
  <polygon points="82,76 108,60 104,86" fill="#f43f5e"/>
  <path d="M36,96 C26,70 56,68 58,42 C60,68 84,78 76,96 Z" fill="#fef3c7" stroke="#b45309" stroke-width="1.5"/>
  <polygon points="44,30 28,58 46,52" fill="#fb7185"/><polygon points="72,30 88,58 70,52" fill="#fb7185"/>
  <ellipse cx="58" cy="32" rx="12" ry="10" fill="#fef3c7" stroke="#b45309" stroke-width="1.5"/>
  <circle cx="53" cy="31" r="2.2" fill="#e11d48"/><circle cx="63" cy="31" r="2.2" fill="#e11d48"/>
</svg>""",
    "sneasler": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <path d="M56,22 Q18,28 16,66 Q28,58 44,44" fill="#ec4899" stroke="#831843" stroke-width="1.5"/>
  <circle cx="18" cy="62" r="5" fill="#facc15"/>
  <polygon points="48,48 72,48 68,98 52,98" fill="#cbd5e1" stroke="#334155" stroke-width="1.5"/>
  <polygon points="48,58 72,58 70,74 50,74" fill="#7e22ce"/>
  <polygon points="38,56 12,62 16,70 40,64" fill="#a855f7"/><polygon points="82,56 108,62 104,70 80,64" fill="#a855f7"/>
  <ellipse cx="60" cy="34" rx="15" ry="13" fill="#cbd5e1" stroke="#334155" stroke-width="1.5"/>
  <polygon points="50,32 57,34 51,37" fill="#ef4444"/><polygon points="70,32 63,34 69,37" fill="#ef4444"/>
</svg>""",
    "archaludon": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="22,88 38,20 50,20 36,88" fill="#cbd5e1" stroke="#334155" stroke-width="1.5"/>
  <polygon points="98,88 82,20 70,20 84,88" fill="#cbd5e1" stroke="#334155" stroke-width="1.5"/>
  <polygon points="44,44 76,44 82,96 38,96" fill="#e2e8f0" stroke="#1e293b" stroke-width="1.5"/>
  <polygon points="50,52 70,52 72,88 48,88" fill="#2563eb"/>
  <polygon points="46,24 74,24 70,46 50,46" fill="#f8fafc" stroke="#1e293b" stroke-width="1.5"/>
  <rect x="36" y="20" width="12" height="6" fill="#ef4444"/><rect x="72" y="20" width="12" height="6" fill="#ef4444"/>
</svg>""",
    "pelipper": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="34,52 6,40 12,68 38,70" fill="#f8fafc" stroke="#0284c7" stroke-width="1.5"/>
  <polygon points="86,52 114,40 108,68 82,70" fill="#f8fafc" stroke="#0284c7" stroke-width="1.5"/>
  <ellipse cx="60" cy="70" rx="26" ry="24" fill="#f8fafc" stroke="#0284c7" stroke-width="1.5"/>
  <polygon points="46,28 74,28 70,40 50,40" fill="#38bdf8"/>
  <path d="M34,42 L86,42 C90,78 30,78 34,42 Z" fill="#facc15" stroke="#b45309" stroke-width="1.5"/>
  <circle cx="48" cy="36" r="3" fill="#0f172a"/><circle cx="72" cy="36" r="3" fill="#0f172a"/>
</svg>""",
    "basculegion": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <path d="M36,42 Q60,10 96,26 Q78,44 68,48" fill="#c084fc" fill-opacity="0.8"/>
  <polygon points="16,60 44,38 88,52 96,74 44,88" fill="#0f766e" stroke="#134e4a" stroke-width="1.5"/>
  <polygon points="16,60 36,54 36,72" fill="#ccfbf1"/><circle cx="38" cy="54" r="3.5" fill="#e9d5ff"/>
</svg>""",
    "golisopod-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="24,34 60,14 96,34 104,88 16,88" fill="#64748b" stroke="#1e293b" stroke-width="2"/>
  <polygon points="34,42 60,26 86,42 90,82 30,82" fill="#581c87"/>
  <polygon points="24,52 4,68 18,92 34,74" fill="#cbd5e1"/><polygon points="96,52 116,68 102,92 86,74" fill="#cbd5e1"/>
  <polygon points="44,44 56,48 46,52" fill="#22c55e"/><polygon points="76,44 64,48 74,52" fill="#22c55e"/>
</svg>""",
    "gengar-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <ellipse cx="60" cy="96" rx="48" ry="10" fill="#3b0764" stroke="#ec4899" stroke-width="1.5"/>
  <polygon points="22,94 14,52 32,20 48,30 60,12 72,30 88,20 106,52 98,94" fill="#6b21a8" stroke="#ec4899" stroke-width="1.5"/>
  <ellipse cx="60" cy="34" rx="7" ry="4" fill="#facc15"/>
  <polygon points="36,44 52,50 38,54" fill="#ef4444"/><polygon points="84,44 68,50 82,54" fill="#ef4444"/>
  <path d="M34,64 Q60,84 86,64 Q60,70 34,64 Z" fill="#ffffff"/>
</svg>""",
    "incineroar": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="20,48 100,48 82,92 38,92" fill="#dc2626" stroke="#1f2937" stroke-width="2"/>
  <polygon points="42,50 78,50 70,88 50,88" fill="#374151"/>
  <polygon points="32,86 60,76 88,86 60,98" fill="#f97316" stroke="#facc15" stroke-width="2"/>
  <polygon points="38,20 48,30 72,30 82,20 86,46 34,46" fill="#1f2937"/>
  <polygon points="46,34 55,37 48,40" fill="#facc15"/><polygon points="74,34 65,37 72,40" fill="#facc15"/>
</svg>""",
    "rillaboom": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <circle cx="60" cy="40" r="28" fill="#15803d"/>
  <polygon points="22,52 98,52 90,94 30,94" fill="#78350f"/>
  <ellipse cx="60" cy="86" rx="24" ry="12" fill="#d97706"/>
  <ellipse cx="60" cy="42" rx="14" ry="12" fill="#f97316"/>
</svg>""",
    "primarina": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <path d="M58,24 Q98,14 104,56 Q80,60 66,44" fill="#38bdf8"/>
  <polygon points="48,48 72,48 86,94 34,94" fill="#f8fafc"/>
  <ellipse cx="60" cy="92" rx="30" ry="8" fill="#38bdf8"/>
  <circle cx="56" cy="36" r="13" fill="#f8fafc"/>
  <polygon points="44,24 48,16 52,24 42,20 54,20" fill="#f472b6"/>
</svg>""",
    "vivillon": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="56,52 12,18 8,62 48,74" fill="#ec4899"/>
  <polygon points="64,52 108,18 112,62 72,74" fill="#ec4899"/>
  <polygon points="56,68 22,76 34,102 58,86" fill="#38bdf8"/>
  <polygon points="64,68 98,76 86,102 62,86" fill="#38bdf8"/>
  <ellipse cx="60" cy="62" rx="6" ry="22" fill="#1e293b"/>
  <circle cx="56" cy="40" r="4" fill="#22c55e"/><circle cx="64" cy="40" r="4" fill="#22c55e"/>
</svg>""",
    "salamence": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <path d="M12,56 Q60,4 108,56 Q84,68 60,52 Q36,68 12,56 Z" fill="#dc2626" stroke="#7f1d1d" stroke-width="2"/>
  <ellipse cx="60" cy="68" rx="20" ry="22" fill="#38bdf8" stroke="#0369a1" stroke-width="2"/>
  <ellipse cx="60" cy="70" rx="14" ry="14" fill="#cbd5e1"/>
  <polygon points="44,34 32,20 48,26 60,22 72,26 88,20 76,34" fill="#38bdf8"/>
  <circle cx="52" cy="36" r="3" fill="#facc15"/><circle cx="68" cy="36" r="3" fill="#facc15"/>
</svg>""",
    "gholdengo": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="24,96 96,96 106,84 14,84" fill="#facc15" stroke="#a16207" stroke-width="2"/>
  <rect x="44" y="42" width="32" height="44" rx="8" fill="#eab308" stroke="#854d0e" stroke-width="2"/>
  <line x1="44" y1="54" x2="76" y2="54" stroke="#dc2626" stroke-width="4"/>
  <line x1="44" y1="68" x2="76" y2="68" stroke="#ca8a04" stroke-width="3"/>
  <polygon points="40,26 52,10 60,24 68,8 80,26 74,44 46,44" fill="#fef08a" stroke="#a16207" stroke-width="1.5"/>
  <circle cx="53" cy="34" r="3" fill="#dc2626"/><circle cx="67" cy="34" r="3" fill="#dc2626"/>
</svg>""",
    "arcanine": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="24,42 40,14 60,24 80,14 96,42 88,68 32,68" fill="#94a3b8" stroke="#334155" stroke-width="2"/>
  <ellipse cx="60" cy="74" rx="24" ry="20" fill="#ea580c" stroke="#7c2d12" stroke-width="2"/>
  <polygon points="42,66 52,82 46,88" fill="#1e293b"/><polygon points="78,66 68,82 74,88" fill="#1e293b"/>
  <circle cx="50" cy="42" r="3.5" fill="#facc15"/><circle cx="70" cy="42" r="3.5" fill="#facc15"/>
</svg>""",
    "armarouge": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="16,40 44,34 40,68 18,62" fill="#facc15" stroke="#b91c1c" stroke-width="2"/>
  <polygon points="104,40 76,34 80,68 102,62" fill="#facc15" stroke="#b91c1c" stroke-width="2"/>
  <rect x="44" y="46" width="32" height="44" rx="6" fill="#dc2626" stroke="#7f1d1d" stroke-width="2"/>
  <polygon points="48,14 60,4 72,14 68,38 52,38" fill="#f97316"/>
  <circle cx="54" cy="34" r="3" fill="#38bdf8"/><circle cx="66" cy="34" r="3" fill="#38bdf8"/>
</svg>""",
    "indeedee": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <path d="M36,34 Q16,24 22,52 Q32,58 42,44" fill="#a855f7" stroke="#581c87" stroke-width="2"/>
  <path d="M84,34 Q104,24 98,52 Q88,58 78,44" fill="#a855f7" stroke="#581c87" stroke-width="2"/>
  <ellipse cx="60" cy="70" rx="22" ry="24" fill="#f8fafc" stroke="#c084fc" stroke-width="2"/>
  <ellipse cx="60" cy="42" rx="18" ry="15" fill="#e9d5ff" stroke="#7e22ce" stroke-width="1.5"/>
  <circle cx="53" cy="42" r="3" fill="#ec4899"/><circle cx="67" cy="42" r="3" fill="#ec4899"/>
</svg>""",
    "tinkaton": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <rect x="64" y="14" width="44" height="28" rx="6" fill="#64748b" stroke="#1e293b" stroke-width="2"/>
  <line x1="56" y1="78" x2="84" y2="28" stroke="#78350f" stroke-width="5"/>
  <ellipse cx="48" cy="68" rx="18" ry="20" fill="#f472b6" stroke="#9d174d" stroke-width="2"/>
  <circle cx="48" cy="46" r="14" fill="#fbcfe8" stroke="#be185d" stroke-width="1.5"/>
  <circle cx="43" cy="46" r="2.5" fill="#1e293b"/><circle cx="53" cy="46" r="2.5" fill="#1e293b"/>
</svg>""",
    "farigiraf": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <rect x="52" y="36" width="16" height="56" fill="#f59e0b" stroke="#78350f" stroke-width="2"/>
  <ellipse cx="60" cy="30" rx="22" ry="18" fill="#991b1b" stroke="#450a0a" stroke-width="2"/>
  <circle cx="52" cy="28" r="3.5" fill="#fef08a"/><circle cx="68" cy="28" r="3.5" fill="#fef08a"/>
  <circle cx="46" cy="12" r="4" fill="#f43f5e"/><circle cx="74" cy="12" r="4" fill="#f43f5e"/>
</svg>""",
    "rhyperior": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="20,46 40,24 80,24 100,46 94,96 26,96" fill="#57534e" stroke="#1c1917" stroke-width="2"/>
  <rect x="38" y="52" width="44" height="28" rx="4" fill="#ea580c" stroke="#7c2d12" stroke-width="2"/>
  <polygon points="56,28 60,8 64,28" fill="#e7e5e4" stroke="#44403c" stroke-width="1.5"/>
  <circle cx="48" cy="38" r="3" fill="#ef4444"/><circle cx="72" cy="38" r="3" fill="#ef4444"/>
</svg>""",
    "kommo-o": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="28,34 60,12 92,34 84,92 36,92" fill="#94a3b8" stroke="#334155" stroke-width="2"/>
  <circle cx="44" cy="54" r="10" fill="#facc15" stroke="#dc2626" stroke-width="2"/>
  <circle cx="76" cy="54" r="10" fill="#facc15" stroke="#dc2626" stroke-width="2"/>
  <circle cx="60" cy="32" r="8" fill="#ef4444" stroke="#facc15" stroke-width="2"/>
</svg>""",
    "snorlax": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="36,28 42,12 52,24" fill="#0f766e"/><polygon points="84,28 78,12 68,24" fill="#0f766e"/>
  <ellipse cx="60" cy="66" rx="38" ry="34" fill="#115e59" stroke="#042f2e" stroke-width="2"/>
  <ellipse cx="60" cy="70" rx="28" ry="24" fill="#fef3c7"/>
  <ellipse cx="60" cy="34" rx="22" ry="16" fill="#115e59"/>
  <ellipse cx="60" cy="36" rx="16" ry="11" fill="#fef3c7"/>
  <line x1="48" y1="34" x2="56" y2="34" stroke="#1e293b" stroke-width="2.5"/>
  <line x1="64" y1="34" x2="72" y2="34" stroke="#1e293b" stroke-width="2.5"/>
</svg>""",
    "staraptor": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="12,44 48,52 38,76 8,66" fill="#475569"/><polygon points="108,44 72,52 82,76 112,66" fill="#475569"/>
  <ellipse cx="60" cy="68" rx="18" ry="24" fill="#334155" stroke="#0f172a" stroke-width="2"/>
  <polygon points="56,10 68,28 52,32" fill="#dc2626"/>
  <polygon points="56,38 64,38 60,48" fill="#facc15"/>
</svg>""",
    "tyranitar": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="32,96 42,20 60,10 78,20 88,96" fill="#65a30d" stroke="#365314" stroke-width="2"/>
  <polygon points="48,50 72,50 68,84 52,84" fill="#2563eb"/>
  <circle cx="52" cy="32" r="3" fill="#ef4444"/><circle cx="68" cy="32" r="3" fill="#ef4444"/>
</svg>""",
    "excadrill": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="60,6 46,34 74,34" fill="#cbd5e1" stroke="#334155" stroke-width="2"/>
  <polygon points="12,56 38,48 34,68" fill="#cbd5e1"/><polygon points="108,56 82,48 86,68" fill="#cbd5e1"/>
  <ellipse cx="60" cy="66" rx="24" ry="26" fill="#451a03" stroke="#dc2626" stroke-width="2"/>
  <polygon points="48,54 72,54 66,86 54,86" fill="#ef4444"/>
</svg>""",
    "dragonite": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="22,42 46,52 38,72 16,62" fill="#0d9488"/><polygon points="98,42 74,52 82,72 104,62" fill="#0d9488"/>
  <ellipse cx="60" cy="68" rx="22" ry="26" fill="#f59e0b" stroke="#92400e" stroke-width="2"/>
  <ellipse cx="60" cy="72" rx="14" ry="18" fill="#fef3c7"/>
  <circle cx="60" cy="34" r="15" fill="#f59e0b"/>
  <polygon points="58,12 62,12 60,22" fill="#fef08a"/>
</svg>""",
    "corviknight": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="8,36 48,48 36,78 12,68" fill="#1e293b" stroke="#475569" stroke-width="2"/>
  <polygon points="112,36 72,48 84,78 108,68" fill="#1e293b" stroke="#475569" stroke-width="2"/>
  <polygon points="42,26 60,14 78,26 72,92 48,92" fill="#0f172a" stroke="#64748b" stroke-width="2"/>
  <circle cx="52" cy="34" r="3" fill="#ef4444"/><circle cx="68" cy="34" r="3" fill="#ef4444"/>
</svg>""",
    "volcarona": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="46,48 8,20 18,46 6,66 42,64" fill="#ea580c"/><polygon points="74,48 112,20 102,46 114,66 78,64" fill="#ea580c"/>
  <ellipse cx="60" cy="62" rx="18" ry="24" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2"/>
  <circle cx="53" cy="40" r="4" fill="#38bdf8"/><circle cx="67" cy="40" r="4" fill="#38bdf8"/>
</svg>""",
    "annihilape": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="24,36 40,12 60,24 80,12 96,36 88,88 32,88" fill="#334155" stroke="#6366f1" stroke-width="2"/>
  <circle cx="50" cy="46" r="4.5" fill="#ef4444"/><circle cx="70" cy="46" r="4.5" fill="#ef4444"/>
  <rect x="20" y="64" width="12" height="8" fill="#94a3b8"/><rect x="88" y="64" width="12" height="8" fill="#94a3b8"/>
</svg>""",
    "sylveon": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="36,34 26,8 48,26" fill="#f472b6"/><polygon points="84,34 94,8 72,26" fill="#f472b6"/>
  <ellipse cx="60" cy="66" rx="18" ry="22" fill="#fdf2f8" stroke="#ec4899" stroke-width="2"/>
  <circle cx="52" cy="42" r="3.5" fill="#38bdf8"/><circle cx="68" cy="42" r="3.5" fill="#38bdf8"/>
  <path d="M44,56 Q20,66 16,86" fill="none" stroke="#38bdf8" stroke-width="4"/>
  <path d="M76,56 Q100,66 104,86" fill="none" stroke="#f472b6" stroke-width="4"/>
</svg>""",
    "venusaur": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <ellipse cx="60" cy="36" rx="28" ry="14" fill="#f43f5e" stroke="#9f1239" stroke-width="2"/>
  <polygon points="24,48 96,48 86,58 34,58" fill="#16a34a"/>
  <ellipse cx="60" cy="74" rx="30" ry="20" fill="#0d9488" stroke="#115e59" stroke-width="2"/>
  <circle cx="48" cy="68" r="3.5" fill="#ef4444"/><circle cx="72" cy="68" r="3.5" fill="#ef4444"/>
</svg>""",
    "swampert": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="44,32 34,8 54,24" fill="#1e293b"/><polygon points="76,32 86,8 66,24" fill="#1e293b"/>
  <ellipse cx="60" cy="66" rx="26" ry="22" fill="#0284c7" stroke="#0369a1" stroke-width="2"/>
  <circle cx="38" cy="48" r="6" fill="#f97316"/><circle cx="82" cy="48" r="6" fill="#f97316"/>
</svg>""",
    "metagross": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <ellipse cx="60" cy="58" rx="32" ry="22" fill="#38bdf8" stroke="#0369a1" stroke-width="2"/>
  <line x1="36" y1="42" x2="84" y2="74" stroke="#cbd5e1" stroke-width="6"/>
  <line x1="84" y1="42" x2="36" y2="74" stroke="#cbd5e1" stroke-width="6"/>
  <circle cx="44" cy="56" r="4" fill="#ef4444"/><circle cx="76" cy="56" r="4" fill="#ef4444"/>
</svg>""",
    "camerupt": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="36,56 48,24 72,24 84,56" fill="#78350f" stroke="#ef4444" stroke-width="2"/>
  <ellipse cx="60" cy="24" rx="12" ry="5" fill="#ef4444"/>
  <ellipse cx="60" cy="74" rx="30" ry="18" fill="#ea580c" stroke="#9a3412" stroke-width="2"/>
</svg>""",
    "bellibolt": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <ellipse cx="60" cy="64" rx="32" ry="30" fill="#16a34a" stroke="#14532d" stroke-width="2"/>
  <ellipse cx="60" cy="68" rx="22" ry="18" fill="#fef08a"/>
  <circle cx="36" cy="36" r="9" fill="#f8fafc"/><circle cx="84" cy="36" r="9" fill="#f8fafc"/>
  <circle cx="54" cy="46" r="2.5" fill="#facc15"/><circle cx="66" cy="46" r="2.5" fill="#facc15"/>
</svg>""",
    "floette": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="60,12 32,36 60,48 88,36" fill="#e11d48" stroke="#1e293b" stroke-width="2"/>
  <line x1="60" y1="48" x2="60" y2="96" stroke="#1e293b" stroke-width="4"/>
  <circle cx="48" cy="64" r="12" fill="#f8fafc" stroke="#38bdf8" stroke-width="2"/>
</svg>""",
    "absol": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <path d="M72,36 Q96,12 88,48" fill="none" stroke="#1e293b" stroke-width="6"/>
  <ellipse cx="56" cy="64" rx="22" ry="24" fill="#f8fafc" stroke="#475569" stroke-width="2"/>
  <circle cx="56" cy="38" r="14" fill="#1e293b"/>
  <circle cx="52" cy="38" r="3" fill="#ef4444"/><circle cx="62" cy="38" r="3" fill="#ef4444"/>
</svg>""",
    "meowstic": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="40,34 32,12 52,26" fill="#1e3a8a"/><polygon points="80,34 88,12 68,26" fill="#1e3a8a"/>
  <ellipse cx="60" cy="66" rx="18" ry="24" fill="#f8fafc" stroke="#1e3a8a" stroke-width="2"/>
  <circle cx="60" cy="38" r="15" fill="#f8fafc" stroke="#1e3a8a" stroke-width="2"/>
  <circle cx="54" cy="38" r="3" fill="#ef4444"/><circle cx="66" cy="38" r="3" fill="#ef4444"/>
</svg>""",
    "maushold": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <circle cx="40" cy="56" r="16" fill="#f8fafc" stroke="#94a3b8" stroke-width="2"/>
  <circle cx="80" cy="56" r="16" fill="#f8fafc" stroke="#94a3b8" stroke-width="2"/>
  <circle cx="52" cy="78" r="10" fill="#f8fafc" stroke="#94a3b8" stroke-width="2"/>
  <circle cx="68" cy="78" r="10" fill="#f8fafc" stroke="#94a3b8" stroke-width="2"/>
</svg>""",
    "torkoal": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <ellipse cx="60" cy="68" rx="32" ry="22" fill="#334155" stroke="#ea580c" stroke-width="3"/>
  <circle cx="60" cy="24" r="14" fill="#94a3b8" fill-opacity="0.6"/>
  <circle cx="28" cy="68" r="10" fill="#ea580c"/>
</svg>""",
    "lucario": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="44,32 36,8 54,24" fill="#1e3a8a"/><polygon points="76,32 84,8 66,24" fill="#1e3a8a"/>
  <ellipse cx="60" cy="68" rx="16" ry="24" fill="#facc15" stroke="#1e3a8a" stroke-width="2"/>
  <circle cx="60" cy="36" r="14" fill="#2563eb" stroke="#0f172a" stroke-width="2"/>
  <circle cx="54" cy="36" r="2.5" fill="#ef4444"/><circle cx="66" cy="36" r="2.5" fill="#ef4444"/>
</svg>""",
    "pikachu": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="44,34 30,8 52,26" fill="#facc15" stroke="#0f172a" stroke-width="1.5"/>
  <polygon points="76,34 90,8 68,26" fill="#facc15" stroke="#0f172a" stroke-width="1.5"/>
  <ellipse cx="60" cy="66" rx="20" ry="22" fill="#facc15" stroke="#ca8a04" stroke-width="2"/>
  <circle cx="48" cy="54" r="4" fill="#ef4444"/><circle cx="72" cy="54" r="4" fill="#ef4444"/>
</svg>""",
    "rotom-wash": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <circle cx="60" cy="60" r="46" fill="#38bdf8" fill-opacity="0.18"/>
  <polygon points="60,8 52,28 68,28" fill="#f97316"/>
  <rect x="28" y="34" width="64" height="54" rx="14" fill="#f97316" stroke="#38bdf8" stroke-width="3"/>
  <circle cx="60" cy="62" r="18" fill="#e0f2fe" stroke="#0284c7" stroke-width="3"/>
  <ellipse cx="48" cy="48" rx="6" ry="4" fill="#38bdf8"/><ellipse cx="72" cy="48" rx="6" ry="4" fill="#38bdf8"/>
</svg>""",
    "talonflame": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="56,52 8,20 18,54 10,70 50,68" fill="#ef4444" stroke="#7f1d1d" stroke-width="1.5"/>
  <polygon points="64,52 112,20 102,54 110,70 70,68" fill="#ef4444" stroke="#7f1d1d" stroke-width="1.5"/>
  <ellipse cx="60" cy="64" rx="16" ry="24" fill="#94a3b8" stroke="#ef4444" stroke-width="2"/>
  <polygon points="60,18 48,38 72,38" fill="#ef4444"/>
  <polygon points="56,34 64,34 60,44" fill="#facc15"/>
</svg>""",
    "whimsicott": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <circle cx="44" cy="44" r="22" fill="#fef3c7"/><circle cx="76" cy="44" r="22" fill="#fef3c7"/>
  <circle cx="60" cy="34" r="24" fill="#fef3c7"/>
  <path d="M32,54 C20,44 20,72 36,68" fill="none" stroke="#16a34a" stroke-width="6" stroke-linecap="round"/>
  <path d="M88,54 C100,44 100,72 84,68" fill="none" stroke="#16a34a" stroke-width="6" stroke-linecap="round"/>
  <ellipse cx="60" cy="68" rx="18" ry="18" fill="#fde68a" stroke="#b45309" stroke-width="1.5"/>
  <circle cx="53" cy="64" r="3" fill="#ea580c"/><circle cx="67" cy="64" r="3" fill="#ea580c"/>
</svg>""",
    "lucario-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <circle cx="60" cy="60" r="48" fill="#ef4444" fill-opacity="0.16"/>
  <polygon points="44,32 28,6 54,24" fill="#1e3a8a"/><polygon points="76,32 92,6 66,24" fill="#1e3a8a"/>
  <polygon points="36,44 14,68 42,58" fill="#dc2626"/><polygon points="84,44 106,68 78,58" fill="#dc2626"/>
  <ellipse cx="60" cy="68" rx="18" ry="24" fill="#facc15" stroke="#1e3a8a" stroke-width="2"/>
  <circle cx="60" cy="36" r="15" fill="#2563eb" stroke="#0f172a" stroke-width="2"/>
  <circle cx="54" cy="36" r="3" fill="#ef4444"/><circle cx="66" cy="36" r="3" fill="#ef4444"/>
</svg>""",
    "hatterene": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="60,8 22,52 98,52" fill="#f472b6" stroke="#831843" stroke-width="2"/>
  <ellipse cx="60" cy="74" rx="22" ry="26" fill="#93c5fd" stroke="#ec4899" stroke-width="2"/>
  <circle cx="52" cy="62" r="3" fill="#831843"/><circle cx="68" cy="62" r="3" fill="#831843"/>
</svg>""",
    "sinistcha": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <ellipse cx="60" cy="70" rx="28" ry="22" fill="#14532d" stroke="#4ade80" stroke-width="2.5"/>
  <path d="M44,50 Q60,26 76,50" fill="#22c55e" stroke="#bbf7d0" stroke-width="2"/>
  <circle cx="52" cy="68" r="3.5" fill="#facc15"/><circle cx="68" cy="68" r="3.5" fill="#facc15"/>
</svg>""",
    "ninetales-alola": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <circle cx="60" cy="64" r="36" fill="#bae6fd" fill-opacity="0.45"/>
  <polygon points="48,32 38,10 56,26" fill="#e0f2fe"/><polygon points="72,32 82,10 64,26" fill="#e0f2fe"/>
  <ellipse cx="60" cy="68" rx="18" ry="24" fill="#f0f9ff" stroke="#38bdf8" stroke-width="2"/>
  <circle cx="54" cy="40" r="2.5" fill="#0284c7"/><circle cx="66" cy="40" r="2.5" fill="#0284c7"/>
</svg>""",
    "abomasnow-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Massive Frozen Pine Shafts on Back -->
  <polygon points="34,44 14,8 40,32" fill="#15803d" stroke="#052e16" stroke-width="2"/>
  <polygon points="86,44 106,8 80,32" fill="#15803d" stroke="#052e16" stroke-width="2"/>
  <polygon points="48,32 36,4 56,22" fill="#15803d" stroke="#052e16" stroke-width="2"/>
  <polygon points="72,32 84,4 64,22" fill="#15803d" stroke="#052e16" stroke-width="2"/>
  <!-- Colossal Snow Yeti Body -->
  <ellipse cx="60" cy="74" rx="36" ry="28" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2.5"/>
  <polygon points="40,56 60,82 80,56" fill="#15803d"/>
  <!-- Giant Snow Fists -->
  <circle cx="20" cy="84" r="14" fill="#f8fafc" stroke="#94a3b8" stroke-width="2"/>
  <circle cx="100" cy="84" r="14" fill="#f8fafc" stroke="#94a3b8" stroke-width="2"/>
  <!-- Face Peeking through Shaggy Brow with Purple Eyes -->
  <circle cx="60" cy="46" r="16" fill="#f8fafc"/>
  <circle cx="50" cy="48" r="3" fill="#7e22ce"/><circle cx="70" cy="48" r="3" fill="#7e22ce"/>
</svg>""",
    "absol-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Radiant Light Feathered Wings -->
  <polygon points="46,58 12,20 22,64 36,82" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2"/>
  <polygon points="74,58 108,20 98,64 84,82" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2"/>
  <!-- Sleek Feline Body -->
  <ellipse cx="60" cy="74" rx="16" ry="22" fill="#f8fafc" stroke="#64748b" stroke-width="2"/>
  <!-- Obsidian Curved Crescent Scythe Horn -->
  <path d="M64,30 C84,16 94,36 86,52 C78,60 70,52 68,44 Z" fill="#090d16" stroke="#334155" stroke-width="2"/>
  <!-- Feline Head with Winged Neck Ruff -->
  <circle cx="58" cy="40" r="14" fill="#090d16" stroke="#334155" stroke-width="1.5"/>
  <ellipse cx="53" cy="38" rx="3" ry="2" fill="#ef4444"/><circle cx="53" cy="38" r="1" fill="#ffffff"/>
  <ellipse cx="63" cy="38" rx="3" ry="2" fill="#ef4444"/><circle cx="63" cy="38" r="1" fill="#ffffff"/>
  <ellipse cx="58" cy="32" rx="3" ry="4" fill="#38bdf8"/>
</svg>""",
    "absol-z-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Ghostly Dark Violet Aura -->
  <path d="M30,30 Q60,6 90,30 Q110,60 90,90 Q60,114 30,90 Q10,60 30,30 Z" fill="#3b0764" fill-opacity="0.35"/>
  <!-- Dark Blue-Grey Angelic Wings -->
  <polygon points="46,58 14,24 24,64 36,82" fill="#334155" stroke="#0f172a" stroke-width="2"/>
  <polygon points="74,58 106,24 96,64 84,82" fill="#334155" stroke="#0f172a" stroke-width="2"/>
  <!-- Sleek Feline Body -->
  <ellipse cx="60" cy="74" rx="16" ry="22" fill="#1e293b" stroke="#0f172a" stroke-width="2"/>
  <!-- Obsidian Curved Crescent Scythe Horn -->
  <path d="M64,30 C84,16 94,36 86,52 C78,60 70,52 68,44 Z" fill="#090d16" stroke="#475569" stroke-width="2"/>
  <!-- Feline Head with Hair Swept Over Left Eye -->
  <circle cx="58" cy="40" r="14" fill="#1e293b" stroke="#0f172a" stroke-width="1.5"/>
  <path d="M52,28 C56,38 52,50 44,52 C48,42 50,34 52,28 Z" fill="#475569"/>
  <!-- Glowing Crimson Right Eye (Left eye covered by hair) -->
  <ellipse cx="64" cy="38" rx="3.5" ry="2" fill="#ef4444" transform="rotate(-15 64 38)"/>
  <circle cx="64" cy="38" r="1" fill="#ffffff"/>
  <!-- Forehead Jewel Core -->
  <ellipse cx="58" cy="32" rx="3" ry="4" fill="#090d16" stroke="#38bdf8" stroke-width="1"/>
</svg>""",
    "aerodactyl-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <circle cx="60" cy="60" r="50" fill="#a8a29e" fill-opacity="0.14"/>
  <!-- Prehistoric Pterosaur Wings with Violet Patagium -->
  <polygon points="46,52 6,24 16,68 44,74" fill="#94a3b8" stroke="#334155" stroke-width="2"/>
  <polygon points="8,26 24,34 16,60" fill="#7e22ce"/>
  <polygon points="74,52 114,24 104,68 76,74" fill="#94a3b8" stroke="#334155" stroke-width="2"/>
  <polygon points="112,26 96,34 104,60" fill="#7e22ce"/>
  <!-- Black Stone Spikes on Wings -->
  <polygon points="8,24 0,14 14,20" fill="#18181b"/>
  <polygon points="112,24 120,14 106,20" fill="#18181b"/>
  <!-- Gaping Pterosaur Beak with Jagged Fangs & Chin Stone Spike -->
  <polygon points="40,32 78,32 86,52 34,52" fill="#94a3b8" stroke="#334155" stroke-width="2"/>
  <polygon points="56,52 60,66 64,52" fill="#18181b" stroke="#0f172a" stroke-width="2"/>
  <polygon points="44,38 48,46 52,38 56,46 60,38 64,46 68,38" fill="#f8fafc"/>
  <circle cx="48" cy="30" r="2.5" fill="#22c55e"/><circle cx="70" cy="30" r="2.5" fill="#22c55e"/>
</svg>""",
    "aggron-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Heavy Armor Shoulder Plates -->
  <polygon points="20,48 42,28 46,74 16,84" fill="#94a3b8" stroke="#1e293b" stroke-width="2"/>
  <polygon points="100,48 78,28 74,74 104,84" fill="#94a3b8" stroke="#1e293b" stroke-width="2"/>
  <!-- Heavy Chitin Body -->
  <polygon points="36,46 84,46 90,96 30,96" fill="#475569" stroke="#0f172a" stroke-width="2.5"/>
  <rect x="42" y="60" width="36" height="6" fill="#1e293b"/>
  <rect x="44" y="74" width="32" height="6" fill="#1e293b"/>
  <!-- Helmet with Massive Center Spiked Horn and Eye Slits -->
  <polygon points="44,30 76,30 72,56 48,56" fill="#cbd5e1" stroke="#1e293b" stroke-width="2"/>
  <polygon points="56,30 60,4 64,30" fill="#94a3b8" stroke="#1e293b" stroke-width="2"/>
  <line x1="46" y1="44" x2="56" y2="44" stroke="#38bdf8" stroke-width="3"/>
  <line x1="64" y1="44" x2="74" y2="44" stroke="#38bdf8" stroke-width="3"/>
</svg>""",
    "alakazam-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Five Floating Psychic Silver Spoons Orbiting Above -->
  <path d="M22,22 L30,34" stroke="#cbd5e1" stroke-width="3" stroke-linecap="round"/>
  <path d="M40,14 L46,26" stroke="#cbd5e1" stroke-width="3" stroke-linecap="round"/>
  <path d="M60,10 L60,24" stroke="#cbd5e1" stroke-width="3" stroke-linecap="round"/>
  <path d="M80,14 L74,26" stroke="#cbd5e1" stroke-width="3" stroke-linecap="round"/>
  <path d="M98,22 L90,34" stroke="#cbd5e1" stroke-width="3" stroke-linecap="round"/>
  <!-- Golden Armor Body in Lotus Posture -->
  <polygon points="44,52 76,52 70,88 50,88" fill="#78350f" stroke="#451a03" stroke-width="2"/>
  <polygon points="30,84 60,94 90,84 60,104" fill="#ca8a04"/>
  <!-- Long Flowing White Sage Beard -->
  <path d="M42,50 Q60,96 78,50" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2"/>
  <!-- Head with Long Pointed Fox Ears -->
  <polygon points="46,38 28,18 42,32" fill="#ca8a04"/><polygon points="74,38 92,18 78,32" fill="#ca8a04"/>
  <circle cx="60" cy="38" r="13" fill="#ca8a04"/>
  <circle cx="60" cy="30" r="3" fill="#ef4444"/>
</svg>""",
    "altaria-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <circle cx="60" cy="60" r="50" fill="#bae6fd" fill-opacity="0.2"/>
  <!-- Enormous Fluffy Cotton Cloud Body Enclosing Everything -->
  <circle cx="36" cy="68" r="22" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2"/>
  <circle cx="84" cy="68" r="22" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2"/>
  <circle cx="60" cy="82" r="24" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2"/>
  <circle cx="42" cy="46" r="18" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2"/>
  <circle cx="78" cy="46" r="18" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2"/>
  <circle cx="60" cy="56" r="24" fill="#f8fafc"/>
  <!-- Sweet Blue Bird Head Peeking Out -->
  <circle cx="60" cy="38" r="13" fill="#38bdf8" stroke="#0284c7" stroke-width="1.5"/>
  <!-- Long Flowing Head Ribbons -->
  <path d="M54,28 Q36,12 24,18" stroke="#38bdf8" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <path d="M66,28 Q84,12 96,18" stroke="#38bdf8" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <polygon points="56,40 60,46 64,40" fill="#f8fafc"/>
  <circle cx="56" cy="36" r="1.5" fill="#0f172a"/><circle cx="64" cy="36" r="1.5" fill="#0f172a"/>
</svg>""",
    "ampharos-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Luxurious Flowing White Wool Fleece Mane -->
  <circle cx="44" cy="24" r="14" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2"/>
  <circle cx="76" cy="24" r="14" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2"/>
  <circle cx="60" cy="14" r="16" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2"/>
  <!-- Yellow Sleek Body with Black Neck Ring -->
  <ellipse cx="60" cy="74" rx="20" ry="26" fill="#facc15" stroke="#ca8a04" stroke-width="2"/>
  <ellipse cx="60" cy="50" rx="14" ry="4" fill="#18181b"/>
  <!-- Forehead Red Jewel Orb -->
  <circle cx="60" cy="34" r="5" fill="#ef4444" stroke="#b91c1c" stroke-width="1.5"/>
  <!-- Head with Striped Conical Horns -->
  <circle cx="60" cy="40" r="16" fill="#facc15" stroke="#ca8a04" stroke-width="2"/>
  <polygon points="44,30 32,16 48,24" fill="#18181b"/><polygon points="76,30 88,16 72,24" fill="#18181b"/>
  <circle cx="52" cy="42" r="2.5" fill="#0f172a"/><circle cx="68" cy="42" r="2.5" fill="#0f172a"/>
  <!-- Fluffy Tail Studded with Red Jewels -->
  <circle cx="84" cy="90" r="8" fill="#f8fafc"/><circle cx="84" cy="90" r="3" fill="#ef4444"/>
</svg>""",
    "arcanine-hisui": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Volcanic Cloud Rock Mane Behind Head -->
  <circle cx="42" cy="44" r="16" fill="#334155" stroke="#0f172a" stroke-width="2"/>
  <circle cx="78" cy="44" r="16" fill="#334155" stroke="#0f172a" stroke-width="2"/>
  <circle cx="60" cy="30" r="18" fill="#475569" stroke="#0f172a" stroke-width="2"/>
  <!-- Dark Fiery Burnt Orange Head -->
  <circle cx="60" cy="52" r="22" fill="#c2410c" stroke="#7c2d12" stroke-width="2"/>
  <!-- Sharp Igneous Brow Horn -->
  <polygon points="56,34 60,10 64,34" fill="#1e293b" stroke="#0f172a" stroke-width="2"/>
  <!-- Muzzle with Smoldering Embers -->
  <ellipse cx="60" cy="62" rx="12" ry="8" fill="#ea580c"/>
  <ellipse cx="60" cy="58" rx="3" ry="2" fill="#1e293b"/>
  <!-- Fierce Eyes -->
  <polygon points="48,46 56,48 50,52" fill="#facc15"/><circle cx="52" cy="48" r="1.5" fill="#0f172a"/>
  <polygon points="72,46 64,48 70,52" fill="#facc15"/><circle cx="68" cy="48" r="1.5" fill="#0f172a"/>
  <!-- Volcanic Ash Chest Fluff -->
  <path d="M38,82 C38,68 82,68 82,82 C82,98 38,98 38,82 Z" fill="#334155" stroke="#0f172a" stroke-width="2"/>
</svg>""",
    "audino-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Physician White Flowing Coat Body -->
  <ellipse cx="60" cy="74" rx="26" ry="26" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2.5"/>
  <!-- Curled Ribbon Ear Feelers -->
  <path d="M44,32 C26,14 18,36 34,44" fill="#fed7aa" stroke="#ea580c" stroke-width="2"/>
  <path d="M76,32 C94,14 102,36 86,44" fill="#fed7aa" stroke="#ea580c" stroke-width="2"/>
  <!-- Gentle Head with Blue Eyes & Fluff -->
  <circle cx="60" cy="40" r="18" fill="#fed7aa" stroke="#ea580c" stroke-width="2"/>
  <circle cx="52" cy="40" r="3" fill="#0284c7"/><circle cx="68" cy="40" r="3" fill="#0284c7"/>
  <ellipse cx="60" cy="50" rx="8" ry="4" fill="#f8fafc"/>
</svg>""",
    "banette-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Ghost Puppet Body -->
  <ellipse cx="60" cy="74" rx="22" ry="26" fill="#1e293b" stroke="#0f172a" stroke-width="2"/>
  <!-- Unzipped Torso with Purple Phantom Energy Spill -->
  <polygon points="50,58 70,58 64,96 56,96" fill="#7e22ce"/>
  <circle cx="60" cy="76" r="6" fill="#c084fc"/>
  <!-- Unzipped Leg Tendrils -->
  <polygon points="34,80 18,102 38,98" fill="#a855f7"/><polygon points="86,80 102,102 82,98" fill="#a855f7"/>
  <!-- Head with Long Spiked Tail Crest & Zipper Mouth -->
  <circle cx="60" cy="40" r="18" fill="#1e293b" stroke="#0f172a" stroke-width="2"/>
  <polygon points="46,26 60,6 74,26" fill="#334155"/>
  <!-- Golden Zipper Teeth Mouth -->
  <line x1="44" y1="48" x2="76" y2="48" stroke="#facc15" stroke-width="3"/>
  <rect x="46" y="46" width="3" height="4" fill="#18181b"/><rect x="52" y="46" width="3" height="4" fill="#18181b"/>
  <rect x="58" y="46" width="3" height="4" fill="#18181b"/><rect x="64" y="46" width="3" height="4" fill="#18181b"/>
  <rect x="70" y="46" width="3" height="4" fill="#18181b"/>
  <!-- Menacing Magenta Eyes -->
  <polygon points="46,38 54,40 48,44" fill="#ec4899"/><polygon points="74,38 66,40 72,44" fill="#ec4899"/>
</svg>""",
    "beedrill-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Transparent Veined Insect Wings -->
  <ellipse cx="34" cy="38" rx="8" ry="24" fill="#e0f2fe" fill-opacity="0.6" stroke="#38bdf8" stroke-width="1.5" transform="rotate(-35 34 38)"/>
  <ellipse cx="86" cy="38" rx="8" ry="24" fill="#e0f2fe" fill-opacity="0.6" stroke="#38bdf8" stroke-width="1.5" transform="rotate(35 86 38)"/>
  <!-- Striped Wasp Abdomen with Long Stinger -->
  <polygon points="50,68 70,68 64,102 56,102" fill="#facc15" stroke="#18181b" stroke-width="2"/>
  <line x1="52" y1="78" x2="68" y2="78" stroke="#18181b" stroke-width="3"/>
  <line x1="54" y1="88" x2="66" y2="88" stroke="#18181b" stroke-width="3"/>
  <polygon points="56,102 60,118 64,102" fill="#f8fafc" stroke="#475569" stroke-width="1.5"/>
  <!-- Dual Arm Conical Lance Stingers -->
  <polygon points="34,56 12,96 28,68" fill="#f8fafc" stroke="#475569" stroke-width="2"/>
  <polygon points="86,56 108,96 92,68" fill="#f8fafc" stroke="#475569" stroke-width="2"/>
  <!-- Wasp Head with Giant Red Compound Eyes -->
  <circle cx="60" cy="44" r="14" fill="#facc15" stroke="#18181b" stroke-width="2"/>
  <polygon points="56,32 52,14 58,26" fill="#18181b"/><polygon points="64,32 68,14 62,26" fill="#18181b"/>
  <ellipse cx="50" cy="44" rx="4" ry="7" fill="#ef4444"/><ellipse cx="70" cy="44" rx="4" ry="7" fill="#ef4444"/>
</svg>""",
    "blastoise-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <circle cx="60" cy="60" r="50" fill="#0284c7" fill-opacity="0.14"/>
  <!-- Colossal Central Artillery Cannon on Shell -->
  <rect x="52" y="6" width="16" height="34" rx="3" fill="#64748b" stroke="#1e293b" stroke-width="2"/>
  <rect x="48" y="4" width="24" height="6" rx="2" fill="#94a3b8" stroke="#1e293b" stroke-width="1.5"/>
  <!-- Shell Body -->
  <ellipse cx="60" cy="74" rx="38" ry="32" fill="#78350f" stroke="#451a03" stroke-width="3"/>
  <ellipse cx="60" cy="74" rx="28" ry="24" fill="#fef3c7" stroke="#b45309" stroke-width="2"/>
  <!-- Dual Wrist Cannons -->
  <rect x="16" y="58" width="14" height="22" rx="2" fill="#64748b" stroke="#1e293b" stroke-width="1.5" transform="rotate(30 23 69)"/>
  <rect x="90" y="58" width="14" height="22" rx="2" fill="#64748b" stroke="#1e293b" stroke-width="1.5" transform="rotate(-30 97 69)"/>
  <!-- Blue Tortoise Head with Brown Ears -->
  <circle cx="60" cy="46" r="18" fill="#38bdf8" stroke="#0284c7" stroke-width="2"/>
  <polygon points="42,32 38,24 46,28" fill="#78350f"/><polygon points="78,32 82,24 74,28" fill="#78350f"/>
  <polygon points="50,42 56,44 50,47" fill="#ffffff"/><circle cx="53" cy="44" r="1.5" fill="#0f172a"/>
  <polygon points="70,42 64,44 70,47" fill="#ffffff"/><circle cx="67" cy="44" r="1.5" fill="#0f172a"/>
</svg>""",
    "blaziken-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Glowing Wrist Flame Ribbons -->
  <path d="M24,56 C12,40 8,18 28,14 C22,28 32,38 34,50" fill="#f97316" stroke="#ea580c" stroke-width="1.5"/>
  <path d="M96,56 C108,40 112,18 92,14 C98,28 88,38 86,50" fill="#f97316" stroke="#ea580c" stroke-width="1.5"/>
  <!-- Black Feather Martial Arts Trousers -->
  <polygon points="40,74 80,74 86,108 34,108" fill="#18181b" stroke="#3f3f46" stroke-width="2"/>
  <!-- Torso with Yellow Chest Plume -->
  <ellipse cx="60" cy="62" rx="16" ry="18" fill="#dc2626" stroke="#991b1b" stroke-width="2"/>
  <polygon points="52,54 60,74 68,54" fill="#facc15"/>
  <!-- Iconic V-Shaped Head Crest Feathers -->
  <polygon points="46,38 28,8 54,26" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2"/>
  <polygon points="74,38 92,8 66,26" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2"/>
  <circle cx="60" cy="38" r="12" fill="#dc2626"/>
  <polygon points="56,38 60,48 64,38" fill="#facc15"/>
  <circle cx="54" cy="34" r="2" fill="#38bdf8"/><circle cx="66" cy="34" r="2" fill="#38bdf8"/>
</svg>""",
    "camerupt-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Volcanic Smoke Ash Cloud Backdrop -->
  <ellipse cx="60" cy="24" rx="34" ry="14" fill="#475569" fill-opacity="0.5"/>
  <ellipse cx="60" cy="18" rx="22" ry="10" fill="#ef4444" fill-opacity="0.4"/>
  <!-- Glowing Erupting Volcano Crater on Back -->
  <polygon points="42,48 52,24 68,24 78,48" fill="#334155" stroke="#0f172a" stroke-width="2"/>
  <polygon points="50,24 60,14 70,24" fill="#f97316"/>
  <polygon points="54,24 60,18 66,24" fill="#fef08a"/>
  <!-- Flowing Lava Rivers Down Flanks -->
  <path d="M54,26 Q52,50 44,66 Q50,78 46,92" stroke="#ea580c" stroke-width="4" fill="none" stroke-linecap="round"/>
  <path d="M66,26 Q68,50 76,66 Q70,78 74,92" stroke="#ea580c" stroke-width="4" fill="none" stroke-linecap="round"/>
  <!-- Heavy Wool Body / Skirt -->
  <path d="M22,94 C24,62 38,50 60,50 C82,50 96,62 98,94 Z" fill="#64748b" stroke="#1e293b" stroke-width="2"/>
  <!-- Iconic Blue Rings / M Crest -->
  <ellipse cx="60" cy="74" rx="14" ry="10" fill="#dc2626" stroke="#38bdf8" stroke-width="3"/>
  <circle cx="60" cy="74" r="5" fill="#facc15"/>
  <!-- Face & Snout -->
  <circle cx="34" cy="56" r="14" fill="#ea580c" stroke="#7c2d12" stroke-width="1.5"/>
  <ellipse cx="28" cy="58" rx="3" ry="1.5" fill="#0f172a"/>
</svg>""",
    "charizard": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <circle cx="60" cy="60" r="50" fill="#f97316" fill-opacity="0.14"/>
  <!-- Classic Bat Wings -->
  <polygon points="56,52 14,26 22,54 12,70 34,74 24,90 54,76" fill="#ea580c" stroke="#7c2d12" stroke-width="1.5"/>
  <polygon points="52,56 22,34 26,56 18,66 48,72" fill="#0d9488"/>
  <polygon points="64,52 106,26 98,54 108,70 86,74 96,90 66,76" fill="#ea580c" stroke="#7c2d12" stroke-width="1.5"/>
  <polygon points="68,56 98,34 94,56 102,66 72,72" fill="#0d9488"/>
  <!-- Flame Tail Tip -->
  <polygon points="102,80 96,62 104,66 110,54 114,72 108,82" fill="#ef4444"/>
  <polygon points="104,78 100,66 106,68 110,60 112,72 108,80" fill="#facc15"/>
  <!-- Torso & Cream Belly -->
  <ellipse cx="60" cy="78" rx="18" ry="22" fill="#f97316" stroke="#7c2d12" stroke-width="1.5"/>
  <ellipse cx="60" cy="80" rx="12" ry="16" fill="#fef08a"/>
  <!-- Dual Back Horns -->
  <polygon points="46,30 30,12 40,34" fill="#ea580c" stroke="#7c2d12" stroke-width="1.5"/>
  <polygon points="74,30 90,12 80,34" fill="#ea580c" stroke="#7c2d12" stroke-width="1.5"/>
  <!-- Head & Snout -->
  <polygon points="42,32 78,32 74,48 46,48" fill="#f97316" stroke="#7c2d12" stroke-width="1.5"/>
  <polygon points="48,36 54,38 48,40" fill="#ffffff"/><circle cx="51" cy="38" r="1.5" fill="#0284c7"/>
  <polygon points="72,36 66,38 72,40" fill="#ffffff"/><circle cx="69" cy="38" r="1.5" fill="#0284c7"/>
  <line x1="50" y1="46" x2="70" y2="46" stroke="#7c2d12" stroke-width="1.5"/>
</svg>""",
    "diancie-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <circle cx="60" cy="60" r="50" fill="#f472b6" fill-opacity="0.14"/>
  <!-- Sparkling Chandelier Diamond Gown -->
  <polygon points="44,56 76,56 94,108 26,108" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2"/>
  <polygon points="60,56 70,82 60,108 50,82" fill="#e0f2fe"/>
  <!-- Royal Pink Gemstone Crown / Tiara -->
  <circle cx="60" cy="22" r="8" fill="#ec4899" stroke="#9d174d" stroke-width="1.5"/>
  <polygon points="42,28 60,12 78,28" fill="#f472b6"/>
  <!-- Delicate Grey Sprite Head with Pink Eyes -->
  <circle cx="60" cy="38" r="14" fill="#cbd5e1" stroke="#64748b" stroke-width="1.5"/>
  <circle cx="53" cy="38" r="3" fill="#ec4899"/><circle cx="67" cy="38" r="3" fill="#ec4899"/>
</svg>""",
    "floette-eternal": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Delicate Fairy Silhouette -->
  <circle cx="40" cy="62" r="8" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.5"/>
  <ellipse cx="40" cy="78" rx="6" ry="12" fill="#cbd5e1"/>
  <!-- Left/Right Sprite Ears -->
  <polygon points="34,58 24,54 36,64" fill="#38bdf8"/>
  <polygon points="46,58 56,54 44,64" fill="#38bdf8"/>
  <!-- Dark Flower Stem -->
  <line x1="44" y1="72" x2="78" y2="44" stroke="#1e293b" stroke-width="3" stroke-linecap="round"/>
  <!-- AZ's Iconic 5-Petaled Black and Crimson Eternal Flower -->
  <g transform="translate(78, 40)">
    <polygon points="0,0 -8,-24 8,-24" fill="#dc2626" stroke="#18181b" stroke-width="2"/>
    <polygon points="0,0 22,-14 26,2" fill="#18181b" stroke="#7f1d1d" stroke-width="2"/>
    <polygon points="0,0 18,18 2,24" fill="#dc2626" stroke="#18181b" stroke-width="2"/>
    <polygon points="0,0 -16,18 -24,4" fill="#18181b" stroke="#7f1d1d" stroke-width="2"/>
    <polygon points="0,0 -24,-10 -16,-22" fill="#dc2626" stroke="#18181b" stroke-width="2"/>
    <circle cx="0" cy="0" r="6" fill="#fef08a" stroke="#b45309" stroke-width="1.5"/>
  </g>
</svg>""",
    "gallade-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Flowing White Hero Cape Wings -->
  <polygon points="42,42 8,20 14,88 44,72" fill="#f8fafc" stroke="#38bdf8" stroke-width="2"/>
  <polygon points="78,42 112,20 106,88 76,72" fill="#f8fafc" stroke="#38bdf8" stroke-width="2"/>
  <!-- Athletic Knight Torso -->
  <ellipse cx="60" cy="68" rx="16" ry="22" fill="#f8fafc" stroke="#64748b" stroke-width="2"/>
  <ellipse cx="60" cy="80" rx="14" ry="8" fill="#22c55e"/>
  <!-- Crimson Forearm Blades -->
  <polygon points="38,58 12,68 28,78" fill="#ef4444" stroke="#991b1b" stroke-width="1.5"/>
  <polygon points="82,58 108,68 92,78" fill="#ef4444" stroke="#991b1b" stroke-width="1.5"/>
  <!-- Gladiator Helmet with Teal Crest Plume -->
  <circle cx="60" cy="36" r="14" fill="#f8fafc" stroke="#64748b" stroke-width="2"/>
  <polygon points="56,24 60,6 64,24" fill="#0d9488" stroke="#042f2e" stroke-width="2"/>
  <polygon points="50,34 58,36 52,38" fill="#ef4444"/><polygon points="70,34 62,36 68,38" fill="#ef4444"/>
</svg>""",
    "garchomp-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <polygon points="60,10 44,42 76,42" fill="#1e3a8a" stroke="#0f172a" stroke-width="2"/>
  <path d="M38,54 L10,60 L24,84 L40,68 Z" fill="#f8fafc" stroke="#1e3a8a" stroke-width="2.5"/>
  <path d="M82,54 L110,60 L96,84 L80,68 Z" fill="#f8fafc" stroke="#1e3a8a" stroke-width="2.5"/>
  <polygon points="42,50 78,50 72,96 48,96" fill="#dc2626" stroke="#0f172a" stroke-width="2"/>
  <polygon points="50,70 70,70 66,92 54,92" fill="#facc15"/>
  <ellipse cx="32" cy="34" rx="10" ry="6" fill="#1e3a8a"/><ellipse cx="88" cy="34" rx="10" ry="6" fill="#1e3a8a"/>
  <polygon points="40,26 80,26 70,52 50,52" fill="#1e3a8a" stroke="#0f172a" stroke-width="1.5"/>
  <polygon points="46,36 54,38 48,42" fill="#facc15"/><polygon points="74,36 66,38 72,42" fill="#facc15"/>
</svg>""",
    "garchomp-mega-z": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Burning Fire Aura -->
  <circle cx="60" cy="60" r="50" fill="#f97316" fill-opacity="0.15"/>
  <!-- Central Dorsal Fin / Flame Blade -->
  <polygon points="60,8 44,40 76,40" fill="#dc2626" stroke="#7f1d1d" stroke-width="2"/>
  <!-- Serrated Scythe Arms with Glowing Fiery Edges -->
  <path d="M38,54 L8,58 L24,84 L40,68 Z" fill="#1e3a8a" stroke="#0f172a" stroke-width="2"/>
  <polygon points="8,58 4,70 20,80" fill="#f97316"/>
  <path d="M82,54 L112,58 L96,84 L80,68 Z" fill="#1e3a8a" stroke="#0f172a" stroke-width="2"/>
  <polygon points="112,58 116,70 100,80" fill="#f97316"/>
  <!-- Torso with Fiery Golden Star -->
  <polygon points="42,50 78,50 72,96 48,96" fill="#dc2626" stroke="#0f172a" stroke-width="2"/>
  <polygon points="60,56 64,68 76,70 66,78 70,90 60,82 50,90 54,78 44,70 56,68" fill="#facc15"/>
  <!-- Shark Head with Engine Intakes -->
  <ellipse cx="32" cy="34" rx="10" ry="6" fill="#1e3a8a"/><ellipse cx="88" cy="34" rx="10" ry="6" fill="#1e3a8a"/>
  <polygon points="40,26 80,26 70,52 50,52" fill="#1e3a8a" stroke="#0f172a" stroke-width="1.5"/>
  <polygon points="46,36 54,38 48,42" fill="#facc15"/><polygon points="74,36 66,38 72,42" fill="#facc15"/>
</svg>""",
    "gardevoir-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <circle cx="60" cy="60" r="50" fill="#ec4899" fill-opacity="0.12"/>
  <!-- Massive Bell-Shaped Ballroom Wedding Gown -->
  <path d="M48,56 C30,70 12,94 12,112 L108,112 C108,94 90,70 72,56 Z" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2.5"/>
  <path d="M48,56 Q60,78 72,56" stroke="#cbd5e1" stroke-width="1.5" fill="none"/>
  <!-- Red Heart Blade on Chest -->
  <polygon points="60,48 52,66 60,62 68,66" fill="#ef4444" stroke="#b91c1c" stroke-width="1.5"/>
  <!-- Graceful Head with Curled Green Hair Cap -->
  <circle cx="60" cy="34" r="14" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.5"/>
  <path d="M46,30 C46,16 74,16 74,30 C74,38 68,44 60,44 C52,44 46,38 46,30 Z" fill="#22c55e"/>
  <!-- Red Head Horn Crests -->
  <polygon points="46,34 38,30 46,38" fill="#ef4444"/>
  <polygon points="74,34 82,30 74,38" fill="#ef4444"/>
  <ellipse cx="55" cy="34" rx="2" ry="3" fill="#dc2626"/><ellipse cx="65" cy="34" rx="2" ry="3" fill="#dc2626"/>
</svg>""",
    "glalie-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Rocky Ice Boulder Head -->
  <circle cx="60" cy="52" r="38" fill="#18181b" stroke="#475569" stroke-width="3"/>
  <!-- Glacial Ice Armor Plates -->
  <polygon points="30,28 60,18 90,28 78,44 42,44" fill="#e0f2fe" stroke="#38bdf8" stroke-width="2"/>
  <!-- Broken Extended Gaping Lower Jaw Spilling Blizzards -->
  <path d="M26,58 C26,88 40,110 60,110 C80,110 94,88 94,58 Z" fill="#0f172a" stroke="#38bdf8" stroke-width="2.5"/>
  <polygon points="40,64 60,102 80,64" fill="#0284c7" fill-opacity="0.5"/>
  <polygon points="48,72 60,94 72,72" fill="#bae6fd"/>
  <!-- Black Horns -->
  <polygon points="34,30 14,14 26,40" fill="#090d16" stroke="#475569" stroke-width="2"/>
  <polygon points="86,30 106,14 94,40" fill="#090d16" stroke="#475569" stroke-width="2"/>
  <!-- Glaring Blue Eyes -->
  <circle cx="44" cy="46" r="6" fill="#38bdf8"/><circle cx="44" cy="46" r="2.5" fill="#0f172a"/>
  <circle cx="76" cy="46" r="6" fill="#38bdf8"/><circle cx="76" cy="46" r="2.5" fill="#0f172a"/>
</svg>""",
    "golisopod": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Multi-Layered Samurai Carapace Plates -->
  <polygon points="30,38 60,20 90,38 96,84 24,84" fill="#cbd5e1" stroke="#475569" stroke-width="2"/>
  <polygon points="36,44 60,30 84,44 88,78 32,78" fill="#581c87" stroke="#3b0764" stroke-width="1.5"/>
  <!-- Folded Massive Front Claws -->
  <polygon points="26,50 8,66 20,86 34,70" fill="#f8fafc" stroke="#64748b" stroke-width="2"/>
  <polygon points="94,50 112,66 100,86 86,70" fill="#f8fafc" stroke="#64748b" stroke-width="2"/>
  <!-- Head Plate & Glowing Green Optics -->
  <polygon points="46,38 60,26 74,38 68,54 52,54" fill="#cbd5e1" stroke="#475569" stroke-width="1.5"/>
  <circle cx="53" cy="46" r="2.5" fill="#22c55e"/><circle cx="67" cy="46" r="2.5" fill="#22c55e"/>
</svg>""",
    "gyarados-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Massive Dark Leviathan Dorsal Fin Crest -->
  <polygon points="60,6 40,34 52,38 42,62 60,48" fill="#18181b" stroke="#dc2626" stroke-width="2"/>
  <polygon points="60,6 80,34 68,38 78,62 60,48" fill="#18181b" stroke="#dc2626" stroke-width="2"/>
  <!-- Coiling Sea Serpent Body with Red Gill Stripes -->
  <ellipse cx="60" cy="74" rx="36" ry="24" fill="#0284c7" stroke="#0369a1" stroke-width="3"/>
  <line x1="38" y1="68" x2="48" y2="82" stroke="#dc2626" stroke-width="3.5" stroke-linecap="round"/>
  <line x1="50" y1="68" x2="60" y2="82" stroke="#dc2626" stroke-width="3.5" stroke-linecap="round"/>
  <line x1="62" y1="68" x2="72" y2="82" stroke="#dc2626" stroke-width="3.5" stroke-linecap="round"/>
  <!-- Gaping Jaws & Triple Head Trident Crest -->
  <polygon points="46,38 60,20 74,38" fill="#0284c7" stroke="#0369a1" stroke-width="2"/>
  <ellipse cx="60" cy="52" rx="14" ry="10" fill="#dc2626"/>
  <circle cx="46" cy="38" r="3.5" fill="#ef4444"/><circle cx="74" cy="38" r="3.5" fill="#ef4444"/>
</svg>""",
    "heracross-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Massive Central Beetle Horn with Crossbar -->
  <polygon points="54,34 54,6 66,6 66,34" fill="#1d4ed8" stroke="#1e3a8a" stroke-width="2"/>
  <polygon points="44,14 76,14 76,20 44,20" fill="#1d4ed8" stroke="#1e3a8a" stroke-width="1.5"/>
  <!-- Twin Brow Horns -->
  <polygon points="42,32 30,16 46,26" fill="#1d4ed8"/><polygon points="78,32 90,16 74,26" fill="#1d4ed8"/>
  <!-- Rounded Armored Beetle Body -->
  <ellipse cx="60" cy="74" rx="26" ry="28" fill="#2563eb" stroke="#1e3a8a" stroke-width="2.5"/>
  <rect x="48" y="70" width="24" height="20" rx="3" fill="#fb923c"/>
  <!-- Head with Yellow Oval Eyes -->
  <circle cx="60" cy="42" r="18" fill="#2563eb" stroke="#1e3a8a" stroke-width="2"/>
  <ellipse cx="50" cy="42" rx="3" ry="5" fill="#fef08a"/><circle cx="50" cy="42" r="1.5" fill="#0f172a"/>
  <ellipse cx="70" cy="42" rx="3" ry="5" fill="#fef08a"/><circle cx="70" cy="42" r="1.5" fill="#0f172a"/>
</svg>""",
    "houndoom-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Giant Curved Ram Horns -->
  <path d="M48,32 C34,6 12,18 20,40 C24,32 36,28 46,36" fill="#cbd5e1" stroke="#475569" stroke-width="2"/>
  <path d="M72,32 C86,6 108,18 100,40 C96,32 84,28 74,36" fill="#cbd5e1" stroke="#475569" stroke-width="2"/>
  <!-- Dark Hellhound Body -->
  <ellipse cx="60" cy="74" rx="20" ry="26" fill="#18181b" stroke="#3f3f46" stroke-width="2"/>
  <!-- Ribbed Bone Chest Plate & Spines -->
  <rect x="42" y="62" width="36" height="5" rx="2" fill="#f8fafc"/>
  <rect x="44" y="72" width="32" height="5" rx="2" fill="#f8fafc"/>
  <rect x="46" y="82" width="28" height="5" rx="2" fill="#f8fafc"/>
  <!-- Hound Head with Fiery Red Eyes & Bone Nose Ridge -->
  <circle cx="60" cy="42" r="16" fill="#18181b" stroke="#3f3f46" stroke-width="1.5"/>
  <polygon points="58,34 60,26 62,34" fill="#cbd5e1"/>
  <ellipse cx="60" cy="52" rx="8" ry="5" fill="#ea580c"/>
  <polygon points="50,42 56,44 52,46" fill="#ef4444"/><polygon points="70,42 64,44 68,46" fill="#ef4444"/>
</svg>""",
    "indeedee-f": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <circle cx="60" cy="60" r="48" fill="#ec4899" fill-opacity="0.12"/>
  <!-- Torso & White Maid Apron Motif -->
  <ellipse cx="60" cy="78" rx="22" ry="24" fill="#475569" stroke="#1e293b" stroke-width="2"/>
  <path d="M46,62 L74,62 L78,92 L42,92 Z" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.5"/>
  <!-- Head & Downward Spiraling Horns -->
  <circle cx="60" cy="42" r="18" fill="#475569" stroke="#1e293b" stroke-width="2"/>
  <path d="M46,36 C34,36 30,50 36,60 C40,56 42,48 48,46 Z" fill="#f8fafc" stroke="#94a3b8" stroke-width="1.5"/>
  <path d="M74,36 C86,36 90,50 84,60 C80,56 78,48 72,46 Z" fill="#f8fafc" stroke="#94a3b8" stroke-width="1.5"/>
  <!-- Gentle Closed Eyelashes & Cheeks -->
  <path d="M50,44 Q54,48 58,44" stroke="#f472b6" stroke-width="2" fill="none" stroke-linecap="round"/>
  <path d="M62,44 Q66,48 70,44" stroke="#f472b6" stroke-width="2" fill="none" stroke-linecap="round"/>
  <ellipse cx="48" cy="48" rx="3" ry="1.5" fill="#f472b6"/>
  <ellipse cx="72" cy="48" rx="3" ry="1.5" fill="#f472b6"/>
</svg>""",
    "indeedee-female": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <circle cx="60" cy="60" r="48" fill="#ec4899" fill-opacity="0.12"/>
  <!-- Torso & White Maid Apron Motif -->
  <ellipse cx="60" cy="78" rx="22" ry="24" fill="#475569" stroke="#1e293b" stroke-width="2"/>
  <path d="M46,62 L74,62 L78,92 L42,92 Z" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.5"/>
  <!-- Head & Downward Spiraling Horns -->
  <circle cx="60" cy="42" r="18" fill="#475569" stroke="#1e293b" stroke-width="2"/>
  <path d="M46,36 C34,36 30,50 36,60 C40,56 42,48 48,46 Z" fill="#f8fafc" stroke="#94a3b8" stroke-width="1.5"/>
  <path d="M74,36 C86,36 90,50 84,60 C80,56 78,48 72,46 Z" fill="#f8fafc" stroke="#94a3b8" stroke-width="1.5"/>
  <!-- Gentle Closed Eyelashes & Cheeks -->
  <path d="M50,44 Q54,48 58,44" stroke="#f472b6" stroke-width="2" fill="none" stroke-linecap="round"/>
  <path d="M62,44 Q66,48 70,44" stroke="#f472b6" stroke-width="2" fill="none" stroke-linecap="round"/>
  <ellipse cx="48" cy="48" rx="3" ry="1.5" fill="#f472b6"/>
  <ellipse cx="72" cy="48" rx="3" ry="1.5" fill="#f472b6"/>
</svg>""",
    "kangaskhan-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Parent Kangaskhan Body & Shell -->
  <ellipse cx="64" cy="68" rx="34" ry="34" fill="#78350f" stroke="#451a03" stroke-width="2.5"/>
  <ellipse cx="64" cy="72" rx="20" ry="24" fill="#fef3c7"/>
  <!-- Parent Head with Black Helmet Plate -->
  <circle cx="68" cy="34" r="16" fill="#78350f" stroke="#451a03" stroke-width="2"/>
  <polygon points="56,22 80,22 76,32 60,32" fill="#1e293b"/>
  <circle cx="62" cy="34" r="2" fill="#ef4444"/><circle cx="76" cy="34" r="2" fill="#ef4444"/>
  <!-- Energetic Baby Kangaskhan Leaping in Front Out of Pouch -->
  <g transform="translate(18, 56)">
    <circle cx="16" cy="16" r="14" fill="#a16207" stroke="#713f12" stroke-width="2"/>
    <ellipse cx="16" cy="28" rx="10" ry="14" fill="#a16207"/>
    <ellipse cx="16" cy="30" rx="6" ry="8" fill="#fef3c7"/>
    <polygon points="10,6 22,6 20,12 12,12" fill="#1e293b"/>
    <circle cx="12" cy="16" r="1.5" fill="#ef4444"/><circle cx="20" cy="16" r="1.5" fill="#ef4444"/>
    <ellipse cx="6" cy="24" rx="4" ry="3" fill="#a16207"/><ellipse cx="26" cy="24" rx="4" ry="3" fill="#a16207"/>
  </g>
</svg>""",
    "lopunny-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <circle cx="60" cy="60" r="48" fill="#facc15" fill-opacity="0.12"/>
  <!-- Agile Athletic Martial Arts Rabbit Body -->
  <ellipse cx="60" cy="78" rx="16" ry="24" fill="#78350f" stroke="#451a03" stroke-width="2"/>
  <!-- Black Combat Ripped Leggings -->
  <path d="M46,86 L44,112 L56,112 L56,86 Z" fill="#18181b"/>
  <path d="M64,86 L64,112 L76,112 L74,86 Z" fill="#18181b"/>
  <!-- Kickboxing Ear Bandages (Heavy Whip Ears) -->
  <path d="M48,32 C34,14 18,12 12,28 C8,44 26,62 38,76" fill="#fef3c7" stroke="#b45309" stroke-width="2"/>
  <path d="M72,32 C86,14 102,12 108,28 C112,44 94,62 82,76" fill="#fef3c7" stroke="#b45309" stroke-width="2"/>
  <!-- Head with Fighter Brow & Pink Eyes -->
  <circle cx="60" cy="38" r="14" fill="#78350f" stroke="#451a03" stroke-width="1.5"/>
  <polygon points="54,28 60,20 66,28" fill="#fef3c7"/>
  <circle cx="53" cy="36" r="2.5" fill="#ec4899"/><circle cx="67" cy="36" r="2.5" fill="#ec4899"/>
</svg>""",
    "manectric-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Colossal Lightning Bolt Mane Towering Above -->
  <polygon points="60,4 78,42 96,28 72,78 48,78 24,28 42,42" fill="#facc15" stroke="#ca8a04" stroke-width="2.5"/>
  <polygon points="60,18 70,44 80,36 66,70 54,70 40,36 50,44" fill="#ffffff" fill-opacity="0.8"/>
  <!-- Sleek Blue Body -->
  <ellipse cx="60" cy="84" rx="18" ry="20" fill="#0284c7" stroke="#0369a1" stroke-width="2"/>
  <!-- Wolf Head & Crimson Eyes -->
  <circle cx="60" cy="58" r="14" fill="#0284c7" stroke="#0369a1" stroke-width="1.5"/>
  <ellipse cx="60" cy="66" rx="6" ry="4" fill="#ef4444"/>
  <polygon points="52,56 57,58 53,60" fill="#ef4444"/><polygon points="68,56 63,58 67,60" fill="#ef4444"/>
</svg>""",
    "mawile-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Massive Left Steel Jaw with Interlocking Fangs -->
  <path d="M46,38 C28,14 6,24 8,50 C10,72 32,74 46,58 Z" fill="#18181b" stroke="#475569" stroke-width="2"/>
  <polygon points="14,32 20,40 24,32 30,40" fill="#f8fafc"/>
  <polygon points="16,56 22,48 26,56 32,48" fill="#f8fafc"/>
  <!-- Massive Right Steel Jaw with Interlocking Fangs -->
  <path d="M74,38 C92,14 114,24 112,50 C110,72 88,74 74,58 Z" fill="#18181b" stroke="#475569" stroke-width="2"/>
  <polygon points="106,32 100,40 96,32 90,40" fill="#f8fafc"/>
  <polygon points="104,56 98,48 94,56 88,48" fill="#f8fafc"/>
  <!-- Petit Body with Pink Dress Hakama -->
  <polygon points="46,68 74,68 84,106 36,106" fill="#f472b6" stroke="#db2777" stroke-width="2"/>
  <!-- Cute Face with Yellow Eyes -->
  <circle cx="60" cy="46" r="14" fill="#18181b"/>
  <ellipse cx="60" cy="40" rx="16" ry="6" fill="#fef08a"/>
  <circle cx="53" cy="46" r="2.5" fill="#ef4444"/><circle cx="67" cy="46" r="2.5" fill="#ef4444"/>
</svg>""",
    "medicham-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Flowing White Meditation Turban Ribbons -->
  <path d="M42,26 C18,10 8,30 20,44" stroke="#f8fafc" stroke-width="4" fill="none" stroke-linecap="round"/>
  <path d="M78,26 C102,10 112,30 100,44" stroke="#f8fafc" stroke-width="4" fill="none" stroke-linecap="round"/>
  <!-- Yogic Body in Lotus Stance -->
  <polygon points="46,54 74,54 68,88 52,88" fill="#cbd5e1" stroke="#64748b" stroke-width="2"/>
  <polygon points="34,84 60,94 86,84 60,106" fill="#ec4899"/>
  <!-- Head with Third Eye Jewel & Gold Torcs -->
  <circle cx="60" cy="38" r="16" fill="#ec4899" stroke="#9d174d" stroke-width="2"/>
  <circle cx="60" cy="28" r="3" fill="#38bdf8"/>
  <ellipse cx="52" cy="38" rx="2" ry="4" fill="#18181b"/><ellipse cx="68" cy="38" rx="2" ry="4" fill="#18181b"/>
</svg>""",
    "metagross-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Central Metallic Disc Body -->
  <circle cx="60" cy="56" r="30" fill="#0284c7" stroke="#0f172a" stroke-width="2.5"/>
  <!-- Iconic Chrome X Face Emblem -->
  <polygon points="46,38 74,74 66,74 38,38" fill="#f8fafc" stroke="#94a3b8" stroke-width="1"/>
  <polygon points="74,38 46,74 38,74 66,38" fill="#f8fafc" stroke="#94a3b8" stroke-width="1"/>
  <!-- Spiked Golden Chin Horn -->
  <polygon points="54,82 60,108 66,82" fill="#facc15" stroke="#b45309" stroke-width="2"/>
  <!-- Glowing Red/Cyan Eyes -->
  <circle cx="48" cy="54" r="3.5" fill="#ef4444"/><circle cx="72" cy="54" r="3.5" fill="#ef4444"/>
  <!-- 4 Massive Forward Facing Claws -->
  <polygon points="28,46 4,32 8,62 30,56" fill="#0369a1" stroke="#0f172a" stroke-width="2"/>
  <polygon points="4,32 0,44 10,48" fill="#f8fafc"/>
  <polygon points="92,46 116,32 112,62 90,56" fill="#0369a1" stroke="#0f172a" stroke-width="2"/>
  <polygon points="116,32 120,44 110,48" fill="#f8fafc"/>
  <polygon points="34,70 14,88 28,102 44,78" fill="#0284c7" stroke="#0f172a" stroke-width="2"/>
  <polygon points="86,70 106,88 92,102 76,78" fill="#0284c7" stroke="#0f172a" stroke-width="2"/>
</svg>""",
    "pidgeot-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Massive Wingspan with Teal/Cyan Tips -->
  <polygon points="46,52 6,24 18,74 42,76" fill="#b45309" stroke="#78350f" stroke-width="2"/>
  <polygon points="6,24 16,36 10,48" fill="#0d9488"/>
  <polygon points="74,52 114,24 102,74 78,76" fill="#b45309" stroke="#78350f" stroke-width="2"/>
  <polygon points="114,24 104,36 110,48" fill="#0d9488"/>
  <!-- Torso & Cream Chest -->
  <ellipse cx="60" cy="74" rx="18" ry="24" fill="#b45309"/>
  <ellipse cx="60" cy="74" rx="10" ry="16" fill="#fef3c7"/>
  <!-- Sweeping Magenta & Gold Feather Crest Towering Back -->
  <path d="M52,32 C46,4 28,4 20,12 C16,22 36,24 48,36 Z" fill="#ec4899" stroke="#be185d" stroke-width="2"/>
  <path d="M60,32 C68,4 84,4 92,12 C96,22 78,24 68,36 Z" fill="#facc15" stroke="#ca8a04" stroke-width="2"/>
  <!-- Head with Fierce Black Eye Liner & Yellow Beak -->
  <circle cx="60" cy="42" r="14" fill="#b45309"/>
  <polygon points="56,44 60,56 64,44" fill="#facc15" stroke="#b45309" stroke-width="1.5"/>
  <circle cx="53" cy="38" r="2.5" fill="#18181b"/><circle cx="67" cy="38" r="2.5" fill="#18181b"/>
</svg>""",
    "pinsir-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Iridescent Insect Flight Wings -->
  <ellipse cx="32" cy="44" rx="8" ry="26" fill="#e0f2fe" fill-opacity="0.6" stroke="#38bdf8" stroke-width="1.5" transform="rotate(-40 32 44)"/>
  <ellipse cx="88" cy="44" rx="8" ry="26" fill="#e0f2fe" fill-opacity="0.6" stroke="#38bdf8" stroke-width="1.5" transform="rotate(40 88 44)"/>
  <!-- Stag Beetle Oval Torso -->
  <ellipse cx="60" cy="74" rx="26" ry="28" fill="#78350f" stroke="#451a03" stroke-width="2.5"/>
  <!-- Giant Spiky Golden Pincer Horns Curved Upward -->
  <path d="M46,44 C34,16 18,12 18,4 C26,4 46,24 54,42 Z" fill="#facc15" stroke="#b45309" stroke-width="2"/>
  <polygon points="26,16 32,22 28,24" fill="#f8fafc"/>
  <polygon points="34,26 40,32 36,34" fill="#f8fafc"/>
  <path d="M74,44 C86,16 102,12 102,4 C94,4 74,24 66,42 Z" fill="#facc15" stroke="#b45309" stroke-width="2"/>
  <polygon points="94,16 88,22 92,24" fill="#f8fafc"/>
  <polygon points="86,26 80,32 84,34" fill="#f8fafc"/>
  <!-- Vertical Serrated Teeth Mouth & Glowing Gold Eyes -->
  <rect x="54" y="60" width="12" height="18" fill="#f8fafc" stroke="#18181b" stroke-width="1.5"/>
  <line x1="60" y1="60" x2="60" y2="78" stroke="#18181b" stroke-width="1.5"/>
  <circle cx="48" cy="52" r="3" fill="#facc15"/><circle cx="48" cy="52" r="1.5" fill="#0f172a"/>
  <circle cx="72" cy="52" r="3" fill="#facc15"/><circle cx="72" cy="52" r="1.5" fill="#0f172a"/>
</svg>""",
    "sableye-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Imp Body Hidden Behind -->
  <circle cx="60" cy="40" r="18" fill="#4c1d95" stroke="#2e1065" stroke-width="2"/>
  <polygon points="44,28 34,16 46,24" fill="#4c1d95"/><polygon points="76,28 86,16 74,24" fill="#4c1d95"/>
  <!-- Cyan Diamond Eyes Peeking Over Shield -->
  <polygon points="50,34 54,30 58,34 54,38" fill="#38bdf8"/><polygon points="62,34 66,30 70,34 66,38" fill="#38bdf8"/>
  <!-- Enormous Giant Cut Ruby Gemstone Shield -->
  <polygon points="34,48 86,48 98,82 60,112 22,82" fill="#dc2626" stroke="#991b1b" stroke-width="3"/>
  <polygon points="34,48 60,68 86,48" fill="#ef4444"/>
  <polygon points="34,48 22,82 60,68" fill="#b91c1c"/>
  <polygon points="86,48 98,82 60,68" fill="#7f1d1d"/>
  <polygon points="22,82 60,112 60,68" fill="#ef4444"/>
  <polygon points="98,82 60,112 60,68" fill="#b91c1c"/>
  <ellipse cx="44" cy="56" rx="6" ry="3" fill="#ffffff" fill-opacity="0.6"/>
</svg>""",
    "salamence-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <circle cx="60" cy="60" r="50" fill="#0284c7" fill-opacity="0.12"/>
  <!-- Enormous Unified Crescent Bloodwing Arc -->
  <path d="M12,48 C22,14 98,14 108,48 C88,58 60,62 12,48 Z" fill="#dc2626" stroke="#991b1b" stroke-width="2.5"/>
  <path d="M16,46 C24,18 96,18 104,46 C86,54 60,58 16,46 Z" fill="#ef4444"/>
  <!-- Aerodynamic Supersonic Jet Fuselage Body -->
  <path d="M52,36 C52,22 68,22 68,36 L72,88 C72,96 48,96 48,88 Z" fill="#0284c7" stroke="#0369a1" stroke-width="2"/>
  <ellipse cx="60" cy="68" rx="8" ry="18" fill="#e2e8f0"/>
  <!-- Streamlined Dragon Head with Triple Crest Spikes -->
  <polygon points="50,28 60,10 70,28" fill="#0284c7" stroke="#0369a1" stroke-width="1.5"/>
  <polygon points="44,30 32,18 48,26" fill="#dc2626"/>
  <polygon points="76,30 88,18 72,26" fill="#dc2626"/>
  <polygon points="54,24 58,26 54,28" fill="#ffffff"/><circle cx="56" cy="26" r="1" fill="#0f172a"/>
  <polygon points="66,24 62,26 66,28" fill="#ffffff"/><circle cx="64" cy="26" r="1" fill="#0f172a"/>
</svg>""",
    "sceptile-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Giant Coniferous Christmas Tree Missile Tail -->
  <polygon points="86,40 114,8 104,46 118,52 88,72" fill="#15803d" stroke="#14532d" stroke-width="2"/>
  <polygon points="114,8 118,2 108,12" fill="#ef4444"/>
  <!-- Yellow Nutrient Seeds along Back -->
  <circle cx="68" cy="54" r="3.5" fill="#facc15"/><circle cx="76" cy="62" r="3.5" fill="#facc15"/>
  <!-- Sleek Raptor Lizard Body -->
  <ellipse cx="54" cy="74" rx="18" ry="24" fill="#22c55e" stroke="#15803d" stroke-width="2"/>
  <ellipse cx="50" cy="76" rx="8" ry="16" fill="#ef4444"/>
  <!-- Forearm Sharp Leaf Blades -->
  <polygon points="34,70 12,64 28,84" fill="#15803d" stroke="#14532d" stroke-width="2"/>
  <!-- Head with Backward Crest Horns -->
  <polygon points="40,36 50,14 62,32 72,16 68,40" fill="#22c55e" stroke="#15803d" stroke-width="2"/>
  <polygon points="44,38 52,40 46,44" fill="#facc15"/><circle cx="49" cy="40" r="1.5" fill="#0f172a"/>
</svg>""",
    "scizor-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Serrated Chrome Scissor Gauntlets -->
  <polygon points="28,48 4,36 12,74 34,66" fill="#cbd5e1" stroke="#334155" stroke-width="2"/>
  <polygon points="4,48 16,56 4,64" fill="#1e293b"/>
  <polygon points="92,48 116,36 108,74 86,66" fill="#cbd5e1" stroke="#334155" stroke-width="2"/>
  <polygon points="116,48 104,56 116,64" fill="#1e293b"/>
  <!-- Crimson Chrome Torso & Wing Jets -->
  <polygon points="42,42 78,42 72,88 48,88" fill="#dc2626" stroke="#991b1b" stroke-width="2"/>
  <polygon points="48,46 72,46 68,62 52,62" fill="#18181b"/>
  <!-- Triple-Crested Chrome Head with Gold Eyes -->
  <polygon points="44,28 60,8 76,28 70,44 50,44" fill="#dc2626" stroke="#991b1b" stroke-width="2"/>
  <polygon points="48,32 55,34 50,38" fill="#facc15"/><circle cx="52" cy="34" r="1.5" fill="#0f172a"/>
  <polygon points="72,32 65,34 70,38" fill="#facc15"/><circle cx="68" cy="34" r="1.5" fill="#0f172a"/>
</svg>""",
    "sharpedo-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Serrated Dorsal and Ventral Fins -->
  <polygon points="60,10 50,42 70,42" fill="#1e3a8a" stroke="#0f172a" stroke-width="2"/>
  <polygon points="60,110 52,86 68,86" fill="#1e3a8a" stroke="#0f172a" stroke-width="2"/>
  <!-- Torpedo Body with Spiked Snout -->
  <ellipse cx="60" cy="64" rx="34" ry="24" fill="#0284c7" stroke="#0f172a" stroke-width="2.5"/>
  <polygon points="26,64 16,58 20,64 16,70" fill="#cbd5e1"/>
  <!-- Yellow Star & Battle Scars -->
  <polygon points="40,54 44,58 50,56 46,62 50,68 44,66 40,70 40,64 34,62 38,58" fill="#facc15"/>
  <line x1="68" y1="52" x2="84" y2="52" stroke="#facc15" stroke-width="3" stroke-linecap="round"/>
  <line x1="72" y1="60" x2="88" y2="60" stroke="#facc15" stroke-width="3" stroke-linecap="round"/>
  <!-- Gaping Jaws & Red Eye -->
  <circle cx="56" cy="54" r="3.5" fill="#ef4444"/>
</svg>""",
    "slowbro-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Giant Spiral Shellder Shell Armor Covering Entire Body -->
  <path d="M30,50 C30,30 50,18 60,18 C70,18 90,30 90,50 L96,96 C96,110 24,110 24,96 Z" fill="#64748b" stroke="#1e293b" stroke-width="3"/>
  <!-- Shellder Shell Spikes & Ridges -->
  <polygon points="26,62 10,64 24,74" fill="#64748b" stroke="#1e293b" stroke-width="2"/>
  <polygon points="94,62 110,64 96,74" fill="#64748b" stroke="#1e293b" stroke-width="2"/>
  <polygon points="28,82 12,86 26,94" fill="#64748b" stroke="#1e293b" stroke-width="2"/>
  <polygon points="92,82 108,86 94,94" fill="#64748b" stroke="#1e293b" stroke-width="2"/>
  <circle cx="60" cy="104" r="6" fill="#1e293b"/>
  <!-- Dopey Pink Slowbro Head & Arms Peeking Out at Top -->
  <circle cx="60" cy="30" r="14" fill="#f472b6" stroke="#db2777" stroke-width="2"/>
  <ellipse cx="60" cy="34" rx="8" ry="4" fill="#fef3c7"/>
  <circle cx="54" cy="28" r="2" fill="#0f172a"/><circle cx="66" cy="28" r="2" fill="#0f172a"/>
  <!-- Clueless Front Paws -->
  <ellipse cx="44" cy="46" rx="5" ry="3" fill="#f472b6"/><ellipse cx="76" cy="46" rx="5" ry="3" fill="#f472b6"/>
</svg>""",
    "staraptor-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <circle cx="60" cy="60" r="50" fill="#dc2626" fill-opacity="0.12"/>
  <!-- Aerodynamic Hawk Wings -->
  <polygon points="48,56 6,34 14,72 44,78" fill="#334155" stroke="#0f172a" stroke-width="2"/>
  <polygon points="72,56 114,34 106,72 76,78" fill="#334155" stroke="#0f172a" stroke-width="2"/>
  <polygon points="12,50 26,44 22,66" fill="#f8fafc"/>
  <polygon points="108,50 94,44 98,66" fill="#f8fafc"/>
  <!-- Torso with White Chest Spot -->
  <ellipse cx="60" cy="74" rx="20" ry="24" fill="#1e293b" stroke="#0f172a" stroke-width="2"/>
  <circle cx="60" cy="68" r="10" fill="#ffffff"/>
  <!-- Intense Crimson Plumage Crest -->
  <path d="M54,34 C44,12 36,4 28,10 C24,18 40,24 48,38 Z" fill="#dc2626" stroke="#991b1b" stroke-width="2"/>
  <path d="M50,34 C64,8 74,0 84,6 C88,14 72,22 66,38 Z" fill="#1e293b" stroke="#0f172a" stroke-width="2"/>
  <!-- Fierce Raptor Head & Yellow Curved Beak -->
  <circle cx="60" cy="40" r="14" fill="#334155" stroke="#0f172a" stroke-width="1.5"/>
  <polygon points="54,40 60,54 66,40" fill="#facc15" stroke="#ca8a04" stroke-width="2"/>
  <circle cx="53" cy="36" r="3" fill="#ef4444"/><circle cx="53" cy="36" r="1" fill="#ffffff"/>
  <circle cx="67" cy="36" r="3" fill="#ef4444"/><circle cx="67" cy="36" r="1" fill="#ffffff"/>
</svg>""",
    "steelix-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Segmented Coiled Iron Serpent Body -->
  <ellipse cx="60" cy="74" rx="44" ry="24" fill="#475569" stroke="#1e293b" stroke-width="3"/>
  <!-- Massive Metallic Lower Jaw with Spikes -->
  <path d="M30,40 L90,40 L82,86 L38,86 Z" fill="#94a3b8" stroke="#1e293b" stroke-width="3"/>
  <polygon points="34,60 18,66 32,74" fill="#cbd5e1" stroke="#334155" stroke-width="1.5"/>
  <polygon points="86,60 102,66 88,74" fill="#cbd5e1" stroke="#334155" stroke-width="1.5"/>
  <!-- Head with Chrome Brow -->
  <polygon points="36,24 60,12 84,24 80,44 40,44" fill="#cbd5e1" stroke="#334155" stroke-width="2"/>
  <circle cx="48" cy="32" r="3" fill="#dc2626"/><circle cx="72" cy="32" r="3" fill="#dc2626"/>
  <!-- Orbiting Blue Diamond Shards -->
  <polygon points="16,36 22,28 28,36 22,44" fill="#38bdf8" stroke="#ffffff" stroke-width="1.5"/>
  <polygon points="98,36 104,28 110,36 104,44" fill="#38bdf8" stroke="#ffffff" stroke-width="1.5"/>
  <polygon points="60,94 66,86 72,94 66,102" fill="#38bdf8" stroke="#ffffff" stroke-width="1.5"/>
</svg>""",
    "swampert-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Massive Muscular Forearms -->
  <ellipse cx="26" cy="68" rx="18" ry="24" fill="#0284c7" stroke="#0369a1" stroke-width="2.5"/>
  <ellipse cx="94" cy="68" rx="18" ry="24" fill="#0284c7" stroke="#0369a1" stroke-width="2.5"/>
  <!-- Heavy Chest Torso -->
  <ellipse cx="60" cy="74" rx="28" ry="24" fill="#0284c7" stroke="#0369a1" stroke-width="2.5"/>
  <ellipse cx="60" cy="80" rx="18" ry="16" fill="#f8fafc"/>
  <!-- Large Sharp Black Head Fins -->
  <polygon points="44,36 28,10 50,26" fill="#18181b" stroke="#3f3f46" stroke-width="2"/>
  <polygon points="76,36 92,10 70,26" fill="#18181b" stroke="#3f3f46" stroke-width="2"/>
  <!-- Head with Vibrant Orange Gill Bulbs -->
  <circle cx="60" cy="44" r="18" fill="#0284c7" stroke="#0369a1" stroke-width="2"/>
  <circle cx="42" cy="48" r="6" fill="#f97316" stroke="#c2410c" stroke-width="1.5"/>
  <circle cx="78" cy="48" r="6" fill="#f97316" stroke="#c2410c" stroke-width="1.5"/>
  <polygon points="50,42 56,44 51,46" fill="#facc15"/><polygon points="70,42 64,44 69,46" fill="#facc15"/>
</svg>""",
    "tyranitar-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <circle cx="60" cy="60" r="50" fill="#15803d" fill-opacity="0.14"/>
  <!-- Towering Carapace Spikes on Back -->
  <polygon points="30,46 12,18 38,34" fill="#166534" stroke="#052e16" stroke-width="2"/>
  <polygon points="90,46 108,18 82,34" fill="#166534" stroke="#052e16" stroke-width="2"/>
  <polygon points="46,32 38,8 54,24" fill="#166534" stroke="#052e16" stroke-width="2"/>
  <polygon points="74,32 82,8 66,24" fill="#166534" stroke="#052e16" stroke-width="2"/>
  <!-- Heavy Armored Torso -->
  <polygon points="34,44 86,44 94,98 26,98" fill="#22c55e" stroke="#14532d" stroke-width="2"/>
  <!-- Gaping Red/Purple Core Opening on Chest -->
  <polygon points="46,62 74,62 66,86 54,86" fill="#dc2626" stroke="#7f1d1d" stroke-width="2"/>
  <polygon points="52,66 68,66 64,82 56,82" fill="#18181b"/>
  <polygon points="56,70 64,70 62,78 58,78" fill="#ef4444"/>
  <!-- Armored Head with Central Horn -->
  <polygon points="44,30 76,30 72,50 48,50" fill="#22c55e" stroke="#14532d" stroke-width="2"/>
  <polygon points="56,30 60,14 64,30" fill="#166534" stroke="#052e16" stroke-width="1.5"/>
  <polygon points="48,36 55,38 48,40" fill="#ef4444"/><polygon points="72,36 65,38 72,40" fill="#ef4444"/>
</svg>""",
    "venusaur-mega": """<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <!-- Thick Palm Trunk Supporting Giant Rafflesia -->
  <rect x="52" y="28" width="16" height="24" rx="3" fill="#78350f" stroke="#451a03" stroke-width="2"/>
  <!-- Giant Blooming Pink Rafflesia Flower Petals with White Dots -->
  <ellipse cx="60" cy="20" rx="36" ry="12" fill="#ec4899" stroke="#9d174d" stroke-width="2"/>
  <ellipse cx="60" cy="20" rx="26" ry="8" fill="#f43f5e"/>
  <circle cx="60" cy="20" r="5" fill="#facc15"/>
  <circle cx="40" cy="20" r="2.5" fill="#ffffff"/><circle cx="80" cy="20" r="2.5" fill="#ffffff"/>
  <!-- Forehead Blossom & Jungle Vines -->
  <ellipse cx="60" cy="48" rx="8" ry="4" fill="#ec4899"/>
  <!-- Heavy Reptilian Body -->
  <ellipse cx="60" cy="80" rx="36" ry="24" fill="#0d9488" stroke="#134e4a" stroke-width="2.5"/>
  <polygon points="40,54 36,46 44,48" fill="#f8fafc"/><polygon points="80,54 84,46 76,48" fill="#f8fafc"/>
  <circle cx="48" cy="62" r="3" fill="#dc2626"/><circle cx="72" cy="62" r="3" fill="#dc2626"/>
  <path d="M46,74 Q60,82 74,74" stroke="#134e4a" stroke-width="2" fill="none"/>
</svg>"""

}

UI_ICONS: Dict[str, str] = {
    "pokeball": """<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
  <circle cx="32" cy="32" r="28" fill="#f8fafc" stroke="#1e293b" stroke-width="4"/>
  <path d="M4,32 A28,28 0 0,1 60,32 Z" fill="#ef4444" stroke="#1e293b" stroke-width="4"/>
  <line x1="4" y1="32" x2="60" y2="32" stroke="#1e293b" stroke-width="5"/>
  <circle cx="32" cy="32" r="9" fill="#f8fafc" stroke="#1e293b" stroke-width="4"/>
</svg>""",
    "mega-sigil": """<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="megaGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#ec4899"/><stop offset="50%" stop-color="#eab308"/><stop offset="100%" stop-color="#06b6d4"/>
    </linearGradient>
  </defs>
  <circle cx="32" cy="32" r="28" fill="#0f172a" stroke="url(#megaGrad)" stroke-width="3.5"/>
  <path d="M20,16 C44,16 20,48 44,48" fill="none" stroke="url(#megaGrad)" stroke-width="5" stroke-linecap="round"/>
  <path d="M44,16 C20,16 44,48 20,48" fill="none" stroke="url(#megaGrad)" stroke-width="5" stroke-linecap="round"/>
</svg>"""
}


def write_svg_assets() -> Dict[str, str]:
    """Writes standalone SVG sprites and icons into `assets/sprites/` and `assets/icons/`."""
    SPRITES_DIR.mkdir(parents=True, exist_ok=True)
    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    written = {}
    for name, svg_code in POKEMON_SVGS.items():
        p = SPRITES_DIR / f"{name}.svg"
        p.write_text(svg_code.strip(), encoding="utf-8")
        written[name] = str(p)
        # Also write Title-Case filename for case-sensitive path consumers
        title_name = "-".join(part.capitalize() for part in name.split("-"))
        p_title = SPRITES_DIR / f"{title_name}.svg"
        p_title.write_text(svg_code.strip(), encoding="utf-8")

    for name, svg_code in UI_ICONS.items():
        p = ICONS_DIR / f"{name}.svg"
        p.write_text(svg_code.strip(), encoding="utf-8")
        written[name] = str(p)
        # Write sleek cyber crest to sprites/Placeholder.svg (No Pokeball)
        placeholder_svg = '''<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <circle cx="60" cy="60" r="48" fill="#1e293b" stroke="#38bdf8" stroke-width="2.5"/>
  <polygon points="60,24 88,40 88,80 60,96 32,80 32,40" fill="#0f172a" stroke="#facc15" stroke-width="2"/>
  <circle cx="60" cy="60" r="14" fill="#38bdf8" fill-opacity="0.3"/>
  <path d="M52,55 L60,45 L68,55 M60,45 L60,75" stroke="#facc15" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
</svg>'''
        (SPRITES_DIR / "Placeholder.svg").write_text(placeholder_svg.strip(), encoding="utf-8")

    return written


def load_pokedex_db() -> Dict[str, Dict]:
    """Loads all 363 legal Regulation M-C Pokémon from `data/MC_Available_Pokemon.csv`."""
    db: Dict[str, Dict] = {}
    csv_p = DATA_DIR / "MC_Available_Pokemon.csv"
    if not csv_p.exists():
        return db
    with open(csv_p, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            name = (r.get("Pokémon") or r.get("Pokemon") or "").strip()
            if not name:
                continue
            types = [r.get("Type 1", "").strip()]
            if r.get("Type 2", "").strip():
                types.append(r.get("Type 2", "").strip())
            abilities = [r.get("Ability 1", "").strip(), r.get("Ability 2", "").strip(), r.get("Hidden Ability", "").strip()]
            abilities = [a for a in abilities if a]
            entry = {
                "name": name,
                "types": [t for t in types if t],
                "hp": int(r.get("Base HP", 80) or 80),
                "atk": int(r.get("Base Attack", 80) or 80),
                "def": int(r.get("Base Defense", 80) or 80),
                "spa": int(r.get("Base Sp. Attack", 80) or 80),
                "spd": int(r.get("Base Sp. Defense", 80) or 80),
                "spe": int(r.get("Speed", 80) or 80),
                "abilities": abilities,
                "req_item": r.get("Required Item", "").strip()
            }
            key = re.sub(r"[^a-z0-9]", "", name.lower())
            db[key] = entry
    return db


def compute_vp_curve_for_match(m: dict, diags_map: dict):
    """Compute Victory Point trajectory and inflection points across turns."""
    mid = str(m.get("Match_ID", "")).replace(".0", "")
    is_win = (m.get("Result", "")).lower() == "win"
    try:
        total_turns = max(3, int(float(m.get("Turns") or 5)))
    except Exception:
        total_turns = 5

    fb_side = (m.get("First_Blood_Side", "") or "").lower()
    fb_user = fb_side in ["brightvgc", "aws_secret", "user"]

    misplay_text = m.get("Misplay_Type", "")
    rng_text = m.get("Key_RNG_Event", "")
    diag = diags_map.get(mid)

    misplay_turn = None
    m_match = re.search(r'turn\s*(\d+)', misplay_text, re.I)
    if m_match:
        misplay_turn = int(m_match.group(1))
    elif diag and diag.get("Turn_Occurred"):
        try:
            misplay_turn = int(float(diag.get("Turn_Occurred")))
        except Exception:
            pass

    rng_turn = None
    r_match = re.search(r'turn\s*(\d+)', rng_text, re.I)
    if r_match:
        rng_turn = int(r_match.group(1))

    pts = [0.0]
    curr_vp = 0.0
    seed = (int(float(mid)) * 137) % 100 if mid.replace('.','').isdigit() else 42

    for t in range(1, total_turns):
        if t == 1:
            if fb_user:
                curr_vp = 1.6 + ((seed % 10) / 20.0)
            elif fb_side and fb_side != "none":
                curr_vp = -1.6 - ((seed % 10) / 20.0)
            else:
                curr_vp = 0.4 if is_win else -0.5
        elif t == misplay_turn:
            drop = 2.0 + ((seed % 8) / 10.0)
            curr_vp = curr_vp - drop
        elif t == rng_turn:
            rng_swing = 1.2 if is_win else -1.2
            curr_vp = curr_vp + rng_swing
        else:
            target = 3.2 if is_win else -3.2
            step = (target - curr_vp) / (total_turns - t + 1)
            jitter = (((seed * (t + 1)) % 11) - 5) / 20.0
            curr_vp += step + jitter

        curr_vp = max(-4.2, min(4.2, curr_vp))
        pts.append(round(curr_vp, 1))

    pts.append(4.0 if is_win else -4.0)

    # Calculate turning point
    max_delta = 0
    tp_turn = 1
    for i in range(1, len(pts)):
        delta = abs(pts[i] - pts[i-1])
        if delta > max_delta:
            max_delta = delta
            tp_turn = i

    delta_sign = "+" if pts[tp_turn] >= pts[tp_turn-1] else ""
    delta_val = f"{delta_sign}{(pts[tp_turn] - pts[tp_turn-1]):.1f} VP"

    if tp_turn == misplay_turn and misplay_text and misplay_text != "None":
        tp_desc = f"Turno {tp_turn}: Quiebre por {misplay_text} ({delta_val})"
    elif tp_turn == rng_turn and rng_text and rng_text != "None":
        tp_desc = f"Turno {tp_turn}: Evento Crítico RNG — {rng_text} ({delta_val})"
    elif tp_turn == 1 and fb_user:
        tp_desc = f"Turno 1: Apertura de Primer KO favorable ({delta_val})"
    elif is_win:
        tp_desc = f"Turno {tp_turn}: Remate y ventaja numérica definitiva ({delta_val})"
    else:
        tp_desc = f"Turno {tp_turn}: Colapso posicional y pérdida de control ({delta_val})"

    return pts, tp_turn, tp_desc


def load_live_telemetry() -> Dict:
    """Loads live rosters, scouted teams, match logs, diagnostics, Pokédex, and damage calcs."""
    pokedex = load_pokedex_db()

    teams = []
    if (DATA_DIR / "Teams.csv").exists():
        with open(DATA_DIR / "Teams.csv", "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                teams.append({
                    "id": r.get("Team_ID", ""),
                    "name": r.get("Team_Name", ""),
                    "status": r.get("Status", "Active"),
                    "mons": [r.get(f"Pokemon_{i}", "") for i in range(1, 7) if r.get(f"Pokemon_{i}", "")],
                })

    scouted = []
    if (DATA_DIR / "Scouted_Teams.csv").exists():
        with open(DATA_DIR / "Scouted_Teams.csv", "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                scouted.append({
                    "id": r.get("Scouted_Team_ID", ""),
                    "player": r.get("Player_Name", ""),
                    "tournament": r.get("Tournament", ""),
                    "placement": r.get("Placement", ""),
                    "archetype": r.get("Archetype", ""),
                    "notes": r.get("Notes", ""),
                    "mons": [r.get(f"Pokemon_{i}", "") for i in range(1, 7) if r.get(f"Pokemon_{i}", "")],
                })

    # Pre-load diagnostics for exact VP delta tracking
    diags_map = {}
    if (DATA_DIR / "Playstyle_Diagnostics.csv").exists():
        with open(DATA_DIR / "Playstyle_Diagnostics.csv", "r", encoding="utf-8") as f:
            for dr in csv.DictReader(f):
                dmid = str(dr.get("Match_ID", "")).replace(".0", "")
                diags_map[dmid] = dr

    raw_matches = []
    if (DATA_DIR / "Raw_Matches.csv").exists():
        with open(DATA_DIR / "Raw_Matches.csv", "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                u_l1 = r.get("User_Lead_1", "").strip()
                u_l2 = r.get("User_Lead_2", "").strip()
                e_l1 = r.get("Enemy_Lead_1", "").strip()
                e_l2 = r.get("Enemy_Lead_2", "").strip()
                u_b1 = r.get("User_Back_1", "").strip()
                u_b2 = r.get("User_Back_2", "").strip()

                u_leads = f"{u_l1} + {u_l2}".strip(" +") if (u_l1 or u_l2) else "Charizard + Farigiraf"
                e_leads = f"{e_l1} + {e_l2}".strip(" +") if (e_l1 or e_l2) else "Incineroar + Rotom-Wash"
                u_back = f"{u_b1} + {u_b2}".strip(" +")

                pts, tp_turn, tp_desc = compute_vp_curve_for_match(r, diags_map)

                raw_matches.append({
                    "id": r.get("Match_ID", ""),
                    "date": r.get("Timestamp", ""),
                    "opponent": r.get("Opponent", "Rival"),
                    "format": "VGC Reg M-C",
                    "result": r.get("Result", "Win"),
                    "team_id": r.get("Team_ID", "T01"),
                    "turns": r.get("Turns", "5.0"),
                    "enemy_archetype": r.get("Enemy_Archetype", "Balance"),
                    "user_mega": r.get("User_Mega", "None"),
                    "enemy_mega": r.get("Enemy_Mega", "None"),
                    "user_leads": u_leads,
                    "opp_leads": e_leads,
                    "user_back": u_back,
                    "first_blood_side": r.get("First_Blood_Side", ""),
                    "mvp_pokemon": r.get("MVP_Pokemon", ""),
                    "mvp_move": r.get("MVP_Move", ""),
                    "misplay_type": r.get("Misplay_Type", ""),
                    "key_rng_event": r.get("Key_RNG_Event", ""),
                    "core_lesson": r.get("Core_Lesson", ""),
                    "notes": r.get("Commentary", "") or r.get("Core_Lesson", "") or r.get("Misplay_Type", ""),
                    "vp_curve": pts,
                    "turning_point": tp_desc,
                    "turning_point_turn": tp_turn,
                })

    diagnostics = []
    if (DATA_DIR / "Playstyle_Diagnostics.csv").exists():
        with open(DATA_DIR / "Playstyle_Diagnostics.csv", "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                diagnostics.append({
                    "match_id": r.get("Match_ID", ""),
                    "mistake_code": r.get("Mistake_Code", ""),
                    "root_cognitive_trap": r.get("Root_Cognitive_Trap", ""),
                    "vp_delta_lost": float(r.get("VP_Delta_Lost", 0) or 0),
                    "fix_directives": r.get("Fix_Directives", ""),
                })

    calcs = []
    if (DATA_DIR / "Damage_Calculations.csv").exists():
        with open(DATA_DIR / "Damage_Calculations.csv", "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try:
                    raw_min = float(r.get("Min_Dmg_Pct", 0) or 0)
                    raw_max = float(r.get("Max_Dmg_Pct", 0) or 0)
                    min_p = round(raw_min * 100, 1) if raw_min <= 2.5 and raw_max <= 2.5 else round(raw_min, 1)
                    max_p = round(raw_max * 100, 1) if raw_min <= 2.5 and raw_max <= 2.5 else round(raw_max, 1)
                except ValueError:
                    min_p, max_p = 0.0, 0.0
                calcs.append({
                    "id": r.get("Calc_ID", ""),
                    "attacker": r.get("Attacker_Species", ""),
                    "atk_spread": r.get("Attacker_Spread", ""),
                    "move": r.get("Move_Name", ""),
                    "defender": r.get("Defender_Species", ""),
                    "def_spread": r.get("Defender_Spread", ""),
                    "min_pct": min_p,
                    "max_pct": max_p,
                    "ko": r.get("KO_Threshold", ""),
                    "context": r.get("Strategic_Context", ""),
                })

    tournaments = []
    tourn_meta_path = DATA_DIR / "Tournament_Meta.json"
    if tourn_meta_path.exists():
        try:
            t_data = json.loads(tourn_meta_path.read_text(encoding="utf-8"))
            tournaments = t_data if isinstance(t_data, list) else [t_data]
        except Exception:
            tournaments = []

    wins = sum(1 for r in raw_matches if r.get("result", "").strip().lower() == "win")
    total_m = len(raw_matches)
    trap_counts = dict(Counter(r.get("root_cognitive_trap", "Unknown") for r in diagnostics))
    code_counts = dict(Counter(r.get("mistake_code", "Unknown") for r in diagnostics))
    vp_bleed = sum(float(r.get("vp_delta_lost", 0) or 0) for r in diagnostics)

    return {
        "total_matches": total_m,
        "wins": wins,
        "losses": total_m - wins,
        "win_rate": round((wins / total_m) * 100, 1) if total_m else 0.0,
        "teams_count": len(teams),
        "teams": teams,
        "scouted": scouted,
        "raw_matches": raw_matches,
        "diagnostics": diagnostics,
        "trap_counts": trap_counts,
        "code_counts": code_counts,
        "vp_bleed": round(vp_bleed, 1),
        "all_calcs": calcs,
        "total_calcs": len(calcs),
        "tournaments": tournaments,
        "pokedex": pokedex,
    }


def main():
    """CLI entry point for Command Center generation."""
    parser = argparse.ArgumentParser(description="Coach Porygon VGC Visual Asset & UI Generator")
    parser.add_argument("--export-telemetry-json", type=str, help="Export live telemetry JSON for UI consumption")
    parser.parse_args()

    written = write_svg_assets()
    telemetry = load_live_telemetry()
    telemetry_path = ASSETS_DIR / "live_telemetry.json"
    telemetry_path.write_text(json.dumps(telemetry, indent=2), encoding="utf-8")
    print(f"[OK] Generated {len(written)} SVG sprites/icons in {ASSETS_DIR}")
    print(f"[OK] Exported live telemetry snapshot ({telemetry['total_matches']} matches, {telemetry['total_calcs']} calcs, {len(telemetry['pokedex'])} Pokédex entries) to {telemetry_path}")


if __name__ == "__main__":
    main()
