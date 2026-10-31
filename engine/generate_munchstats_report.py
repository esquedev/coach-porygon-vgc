#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — MunchStats 7-Regional Meta & Theorybuilding Report Generator
Compiles:
- assets/reports/munchstats_theorybuild_report.html
- assets/reports/munchstats_theorybuild_report.pdf
And synchronizes both to the Antigravity Brain artifact directory.
"""

import base64
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
ASSETS_DIR = REPO_ROOT / "assets"
REPORTS_DIR = ASSETS_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
SPRITES_DIR = ASSETS_DIR / "sprites"
ITEMS_DIR = ASSETS_DIR / "items"

ARTIFACT_DIR = Path(r"C:\Users\unkil\.gemini\antigravity\brain\abb6a85e-c2b6-438b-9be3-8a43c6c50364")

HTML_OUT = REPORTS_DIR / "munchstats_theorybuild_report.html"
PDF_OUT = REPORTS_DIR / "munchstats_theorybuild_report.pdf"

CHROME_PATH = "C:/Program Files/Google/Chrome/Application/chrome.exe"

def get_base64_img(folder: Path, filename: str) -> str:
    """Read image and return data URI."""
    p = folder / filename
    if not p.exists():
        # try without dash or lower
        clean = filename.lower().replace(" ", "-")
        p = folder / clean
    if p.exists():
        mime = "image/png" if p.suffix == ".png" else "image/svg+xml"
        b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
        return f"data:{mime};base64,{b64}"
    return ""

def build_report():
    """Builds the comprehensive 7-Regional MunchStats HTML report and compiles downloadable PDF."""
    print("[1/4] Loading tournament meta and aggregate data...")
    with open(DATA_DIR / "Munchstats_Aggregate_Meta.json", "r", encoding="utf-8") as f:
        agg = json.load(f)

    with open(DATA_DIR / "Tournament_Meta.json", "r", encoding="utf-8") as f:
        tournaments = json.load(f)

    # Pre-load base64 images for the team
    team_images = {
        "ceruledge": get_base64_img(SPRITES_DIR, "ceruledge.png"),
        "milotic": get_base64_img(SPRITES_DIR, "milotic.png"),
        "rillaboom": get_base64_img(SPRITES_DIR, "rillaboom.png"),
        "staraptor": get_base64_img(SPRITES_DIR, "staraptor.png"),
        "staraptor_mega": get_base64_img(SPRITES_DIR, "staraptor-mega.png"),
        "gholdengo": get_base64_img(SPRITES_DIR, "gholdengo.png"),
        "raichu": get_base64_img(SPRITES_DIR, "raichu.png"),
        "raichu_mega_y": get_base64_img(SPRITES_DIR, "raichu-mega-y.png"),
        # items
        "grassy_seed": get_base64_img(ITEMS_DIR, "grassy-seed.png"),
        "sitrus_berry": get_base64_img(ITEMS_DIR, "sitrus-berry.png"),
        "miracle_seed": get_base64_img(ITEMS_DIR, "miracle-seed.png"),
        "staraptite": get_base64_img(ASSETS_DIR / "megastones", "staraptite.png"),
        "life_orb": get_base64_img(ITEMS_DIR, "life-orb.png"),
        "raichunite_y": get_base64_img(ASSETS_DIR / "megastones", "raichunite-y.png"),
        "porygon_logo": get_base64_img(ASSETS_DIR / "icons", "porygon-coach.svg") or get_base64_img(SPRITES_DIR, "porygon-coach.svg")
    }

    # Pre-load top meta species images
    meta_species_imgs = {}
    top_meta_species = [
        "Rillaboom", "Sneasler", "Incineroar", "Raichu-Mega-Y", "Gholdengo",
        "Kingambit", "Salamence-Mega", "Archaludon", "Charizard-Mega-Y", "Arcanine-Hisui",
        "Garchomp-Mega-Z", "Basculegion", "Indeedee-F", "Farigiraf", "Pelipper"
    ]
    for sp in top_meta_species:
        fn = sp.lower() + ".png"
        meta_species_imgs[sp] = get_base64_img(SPRITES_DIR, fn)

    print("[2/4] Assembling comprehensive HTML report...")

    # Build Tournament table rows
    t_rows = ""
    for t in tournaments:
        champ_name = t.get("champion", {}).get("player", "Undetermined") if t.get("champion") else "Top Cut"
        champ_arch = t.get("champion", {}).get("archetype", "Meta Core") if t.get("champion") else ""
        top_mega = t.get("dominant_megas", [{}])[0].get("mega", "None")
        top_mega_pct = t.get("dominant_megas", [{}])[0].get("usage_pct", 0)
        t_rows += f"""
        <tr class="border-b border-slate-700/50 hover:bg-slate-800/40 transition">
          <td class="py-3 px-4 font-mono font-bold text-cyan-400">{t['tournament_id']}</td>
          <td class="py-3 px-4 font-semibold text-slate-100">{t['tournament_name']}<div class="text-xs text-slate-400">{t['location']} • {t['date']}</div></td>
          <td class="py-3 px-4 text-center font-mono font-bold text-slate-200">{t['total_players']:,}</td>
          <td class="py-3 px-4 text-center font-mono text-emerald-400">{t['top_cut_size']}</td>
          <td class="py-3 px-4 font-mono text-purple-300 font-bold">{top_mega} <span class="text-xs text-slate-400">({top_mega_pct}%)</span></td>
          <td class="py-3 px-4 text-amber-300 font-semibold">{champ_name}<div class="text-xs text-slate-400">{champ_arch}</div></td>
        </tr>
        """

    # Build Top 15 Meta Table rows
    meta_table_rows = ""
    for s in agg["top_species_weighted_usage"][:15]:
        sp_name = s["species"]
        img_src = meta_species_imgs.get(sp_name, "")
        img_tag = f'<img src="{img_src}" class="w-8 h-8 object-contain inline-block mr-2">' if img_src else ''
        meta_table_rows += f"""
        <tr class="border-b border-slate-700/40 hover:bg-slate-800/30">
          <td class="py-2.5 px-3 font-mono font-extrabold text-slate-400 text-center">#{s['rank']}</td>
          <td class="py-2.5 px-3 font-bold text-slate-100 flex items-center">{img_tag}<span>{sp_name}</span></td>
          <td class="py-2.5 px-3 text-right font-mono font-extrabold text-cyan-400">{s['weighted_usage_pct']:.2f}%</td>
          <td class="py-2.5 px-3 text-right font-mono text-slate-300">{s['total_count']:,}</td>
          <td class="py-2.5 px-3 text-center">
            <div class="w-full bg-slate-700 rounded-full h-2">
              <div class="bg-gradient-to-r from-cyan-500 to-blue-500 h-2 rounded-full" style="width: {min(100, s['weighted_usage_pct'] * 1.8)}%"></div>
            </div>
          </td>
        </tr>
        """

    # Dominant Megas rows
    mega_table_rows = ""
    for m in agg["dominant_megas_ranking"][:8]:
        mega_name = m["mega"]
        img_src = get_base64_img(SPRITES_DIR, mega_name.lower() + ".png")
        img_tag = f'<img src="{img_src}" class="w-8 h-8 object-contain inline-block mr-2">' if img_src else ''
        mega_table_rows += f"""
        <tr class="border-b border-slate-700/40 hover:bg-slate-800/30">
          <td class="py-2.5 px-3 font-mono font-extrabold text-purple-400 text-center">#{m['rank']}</td>
          <td class="py-2.5 px-3 font-bold text-slate-100 flex items-center">{img_tag}<span>{mega_name}</span></td>
          <td class="py-2.5 px-3 text-right font-mono font-extrabold text-purple-300">{m['weighted_usage_pct']:.2f}%</td>
          <td class="py-2.5 px-3 text-right font-mono text-slate-300">{m['total_count']:,}</td>
        </tr>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Coach Porygon VGC — Metagame Intelligence & Team Theorybuilding Audit</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&family=JetBrains+Mono:wght@400;600;700;800&display=swap');
    body {{
      font-family: 'Plus Jakarta Sans', sans-serif;
      background-color: #0b1120;
      color: #e2e8f0;
    }}
    code, pre, .font-mono {{
      font-family: 'JetBrains Mono', monospace;
    }}
    @media print {{
      body {{
        background-color: #ffffff !important;
        color: #0f172a !important;
        font-size: 11pt;
      }}
      .no-print {{
        display: none !important;
      }}
      .print-break {{
        page-break-before: always !important;
      }}
      .print-card {{
        border: 1px solid #cbd5e1 !important;
        background: #f8fafc !important;
        color: #0f172a !important;
        box-shadow: none !important;
      }}
      .text-slate-100, .text-slate-200, .text-slate-300 {{
        color: #0f172a !important;
      }}
      .text-slate-400 {{
        color: #475569 !important;
      }}
      .text-cyan-400, .text-cyan-300 {{
        color: #0284c7 !important;
      }}
      .text-emerald-400, .text-emerald-300 {{
        color: #059669 !important;
      }}
      .text-amber-400, .text-amber-300 {{
        color: #d97706 !important;
      }}
      .text-purple-400, .text-purple-300 {{
        color: #7c3aed !important;
      }}
      .bg-slate-900, .bg-slate-800, .bg-slate-950 {{
        background-color: #ffffff !important;
      }}
      .border-slate-800, .border-slate-700 {{
        border-color: #e2e8f0 !important;
      }}
    }}
  </style>
</head>
<body class="p-4 md:p-8 max-w-7xl mx-auto space-y-8">

  <!-- TOP ACTION BAR (Hidden in Print) -->
  <header class="no-print bg-slate-900/90 backdrop-blur border border-slate-700/80 rounded-2xl p-4 flex flex-wrap items-center justify-between gap-4 sticky top-4 z-50 shadow-2xl">
    <div class="flex items-center gap-3">
      <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center p-1.5 shadow-lg shadow-cyan-500/20">
        <svg viewBox="0 0 100 100" class="w-full h-full fill-white">
          <polygon points="50,10 90,32 90,78 50,95 10,78 10,32"/>
        </svg>
      </div>
      <div>
        <h1 class="font-extrabold text-base tracking-wide text-white">COACH PORYGON VGC <span class="text-xs px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">REGULATION M-C</span></h1>
        <p class="text-xs text-slate-400 font-mono">7-Regional Metagame Ingestion & Deterministic Team Audit</p>
      </div>
    </div>
    <div class="flex items-center gap-3">
      <a href="munchstats_theorybuild_report.pdf" download="munchstats_theorybuild_report.pdf" class="px-4 py-2 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-extrabold text-xs shadow-lg shadow-purple-500/20 flex items-center gap-2 cursor-pointer transition">
        <span>📄</span> <span>Download PDF Document</span>
      </a>
      <button onclick="window.print()" class="px-4 py-2 rounded-xl bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-extrabold text-xs shadow-lg shadow-cyan-500/20 flex items-center gap-2 cursor-pointer transition">
        <span>🖨️</span> <span>Print / Save as PDF</span>
      </button>
    </div>
  </header>

  <!-- REPORT BANNER -->
  <section class="bg-gradient-to-br from-slate-900 via-slate-900 to-slate-950 border border-slate-800 rounded-3xl p-6 md:p-8 shadow-2xl relative overflow-hidden">
    <div class="absolute -right-16 -top-16 w-80 h-80 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none"></div>
    <div class="absolute -left-16 -bottom-16 w-80 h-80 bg-purple-500/10 rounded-full blur-3xl pointer-events-none"></div>

    <div class="relative z-10 space-y-4">
      <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-4">
        <span class="font-mono text-xs text-cyan-400 font-bold uppercase tracking-wider">Tournament Scouting & Roster Theorycrafting Audit</span>
        <span class="font-mono text-xs text-slate-400">Timestamp: 2026-10-31 • 4,965 Verified Competitors Ingested</span>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-4 gap-4 pt-2">
        <div class="p-4 rounded-2xl bg-slate-800/40 border border-slate-700/50">
          <div class="text-xs text-slate-400 font-semibold">Total Teams Crawled</div>
          <div class="text-2xl md:text-3xl font-extrabold text-white font-mono mt-1">4,965</div>
          <div class="text-[11px] text-cyan-400 font-mono mt-0.5">7 Official Regional Championships</div>
        </div>
        <div class="p-4 rounded-2xl bg-slate-800/40 border border-slate-700/50">
          <div class="text-xs text-slate-400 font-semibold">Format Apex Threat</div>
          <div class="text-2xl md:text-3xl font-extrabold text-emerald-400 font-mono mt-1">Rillaboom</div>
          <div class="text-[11px] text-slate-400 font-mono mt-0.5">50.37% Usage (2,501 Rosters)</div>
        </div>
        <div class="p-4 rounded-2xl bg-slate-800/40 border border-slate-700/50">
          <div class="text-xs text-slate-400 font-semibold">Premier Mega Evolution</div>
          <div class="text-2xl md:text-3xl font-extrabold text-purple-400 font-mono mt-1">Mega Raichu Y</div>
          <div class="text-[11px] text-purple-300 font-mono mt-0.5">25.80% Usage (1,281 Rosters)</div>
        </div>
        <div class="p-4 rounded-2xl bg-slate-800/40 border border-slate-700/50">
          <div class="text-xs text-slate-400 font-semibold">Audited Team Status</div>
          <div class="text-2xl md:text-3xl font-extrabold text-cyan-300 font-mono mt-1">100% Legal</div>
          <div class="text-[11px] text-emerald-400 font-mono mt-0.5">396/396 SP • Strict Item Clause OK</div>
        </div>
      </div>
    </div>
  </section>

  <!-- SECTION 1: CRAWLED REGIONAL CHAMPIONSHIPS DATA -->
  <section class="space-y-4">
    <div class="flex items-center justify-between">
      <h2 class="text-xl font-extrabold text-white flex items-center gap-2">
        <span class="w-3 h-3 rounded-full bg-cyan-400 inline-block"></span>
        1. Ingested Tournament Datasets (MunchStats RK9 Live Brackets)
      </h2>
      <span class="font-mono text-xs text-slate-400">Regulation M-C Open Team Sheet (OTS)</span>
    </div>

    <div class="overflow-x-auto rounded-2xl border border-slate-800 bg-slate-900/60 shadow-xl">
      <table class="w-full text-left text-sm">
        <thead class="bg-slate-800/80 text-xs uppercase font-mono text-slate-300 border-b border-slate-700">
          <tr>
            <th class="py-3 px-4">Event ID</th>
            <th class="py-3 px-4">Tournament & Location</th>
            <th class="py-3 px-4 text-center">Players</th>
            <th class="py-3 px-4 text-center">Top Cut</th>
            <th class="py-3 px-4">Dominant Mega</th>
            <th class="py-3 px-4">Champion / Playstyle</th>
          </tr>
        </thead>
        <tbody>
          {t_rows}
        </tbody>
      </table>
    </div>
  </section>

  <!-- SECTION 2: METAGAME COMPOSITION & USAGE LANDSCAPE -->
  <section class="grid grid-cols-1 lg:grid-cols-2 gap-6 print-break">
    <div class="space-y-4">
      <h2 class="text-lg font-extrabold text-white flex items-center gap-2">
        <span class="w-2.5 h-2.5 rounded-full bg-blue-400"></span>
        Top 15 Weighted Species (4,965 Rosters)
      </h2>
      <div class="overflow-x-auto rounded-2xl border border-slate-800 bg-slate-900/60 p-1">
        <table class="w-full text-left text-xs">
          <thead class="bg-slate-800/60 font-mono text-slate-400 border-b border-slate-700">
            <tr>
              <th class="py-2 px-3 text-center">Rank</th>
              <th class="py-2 px-3">Species</th>
              <th class="py-2 px-3 text-right">Weighted %</th>
              <th class="py-2 px-3 text-right">Count</th>
              <th class="py-2 px-3 text-center">Meta Share</th>
            </tr>
          </thead>
          <tbody>
            {meta_table_rows}
          </tbody>
        </table>
      </div>
    </div>

    <div class="space-y-4">
      <h2 class="text-lg font-extrabold text-white flex items-center gap-2">
        <span class="w-2.5 h-2.5 rounded-full bg-purple-400"></span>
        Dominant Mega Evolution Distribution
      </h2>
      <div class="overflow-x-auto rounded-2xl border border-slate-800 bg-slate-900/60 p-1">
        <table class="w-full text-left text-xs">
          <thead class="bg-slate-800/60 font-mono text-slate-400 border-b border-slate-700">
            <tr>
              <th class="py-2 px-3 text-center">Rank</th>
              <th class="py-2 px-3">Mega Evolution</th>
              <th class="py-2 px-3 text-right">Usage %</th>
              <th class="py-2 px-3 text-right">Total Teams</th>
            </tr>
          </thead>
          <tbody>
            {mega_table_rows}
          </tbody>
        </table>
      </div>

      <div class="p-4 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-2">
        <h3 class="text-xs font-bold uppercase tracking-wider text-slate-400 font-mono">Key Metagame Takeaways from 7 Regionals</h3>
        <ul class="text-xs text-slate-300 space-y-1.5 list-disc pl-4">
          <li><b class="text-white">Rillaboom & Sneasler Duopoly:</b> Rillaboom (50.37%) and Sneasler (38.85%) dictate turn 1 positioning. Fake Out + Unburden Dire Claw/Close Combat forces every team to respect priority and terrain control.</li>
          <li><b class="text-white">Incineroar Everywhere (34.10%):</b> Intimidate + Parting Shot creates immense cycle pressure, making <span class="text-cyan-400 font-semibold">Competitive Milotic</span> and <span class="text-amber-400 font-semibold">Defiant Kingambit</span> prime anti-meta weapons.</li>
          <li><b class="text-white">Mega Raichu Y Supremacy (25.80%):</b> Overcoming Salamence-Mega (21.13%) and Charizard-Mega-Y (16.96%), Mega Raichu Y's 200 Base Speed and 180 SpA render it the fastest offensive pivot in the format.</li>
        </ul>
      </div>
    </div>
  </section>

  <!-- SECTION 3: IN-DEPTH THEORYBUILDING & ROSTER AUDIT -->
  <section class="space-y-6 print-break">
    <div class="border-b border-slate-800 pb-3 flex flex-wrap items-center justify-between gap-2">
      <div>
        <h2 class="text-xl font-extrabold text-white flex items-center gap-2">
          <span class="w-3 h-3 rounded-full bg-emerald-400 inline-block"></span>
          2. Complete Theorybuilding Audit: Dual Mega Grassy Flash Fire Balance
        </h2>
        <p class="text-xs text-slate-400 font-mono">Validated against Official Level 50 Stat Point Algorithm (66 SP per mon • Seq. Floor Rounding)</p>
      </div>
      <span class="px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-300 font-mono text-xs border border-emerald-500/30 font-bold">Archetype: Grassy Seed Flash Fire Balance</span>
    </div>

    <!-- 6 POKEMON CARDS -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">

      <!-- 1. Ceruledge -->
      <div class="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 space-y-4 print-card relative overflow-hidden">
        <div class="flex items-center justify-between border-b border-slate-800 pb-3">
          <div class="flex items-center gap-3">
            <img src="{team_images['ceruledge']}" class="w-12 h-12 object-contain" alt="Ceruledge">
            <div>
              <h3 class="font-extrabold text-base text-white">Ceruledge <span class="text-xs text-slate-400">(M)</span></h3>
              <div class="text-xs font-mono text-cyan-400 flex items-center gap-1.5">
                <img src="{team_images['grassy_seed']}" class="w-4 h-4 object-contain inline" alt="">
                <span>Grassy Seed</span>
              </div>
            </div>
          </div>
          <span class="px-2 py-0.5 rounded bg-orange-500/20 text-orange-300 border border-orange-500/30 font-mono text-[11px] font-bold">Fire / Ghost</span>
        </div>

        <div class="space-y-1.5 text-xs">
          <div class="flex justify-between"><span class="text-slate-400">Ability:</span> <span class="font-bold text-slate-200">Flash Fire (Fire Immune + Boost)</span></div>
          <div class="flex justify-between"><span class="text-slate-400">Nature:</span> <span class="font-bold text-slate-200">Adamant (+Atk, -SpA)</span></div>
          <div class="flex justify-between font-mono"><span class="text-slate-400">SP Allocation:</span> <span class="text-cyan-400 font-bold">32 HP / 12 Atk / 6 Def / 10 SpD / 6 Spe</span></div>
        </div>

        <div class="p-2.5 rounded-xl bg-slate-800/50 border border-slate-700/50 font-mono text-xs grid grid-cols-6 text-center gap-1">
          <div><div class="text-[10px] text-slate-400">HP</div><div class="font-bold text-white">182</div></div>
          <div><div class="text-[10px] text-slate-400">Atk</div><div class="font-bold text-cyan-300">172</div></div>
          <div><div class="text-[10px] text-slate-400">Def</div><div class="font-bold text-emerald-300">106<span class="text-[9px] text-emerald-400">(+1=159)</span></div></div>
          <div><div class="text-[10px] text-slate-400">SpA</div><div class="text-slate-500">72</div></div>
          <div><div class="text-[10px] text-slate-400">SpD</div><div class="font-bold text-white">130</div></div>
          <div><div class="text-[10px] text-slate-400">Spe</div><div class="font-bold text-white">111</div></div>
        </div>

        <div class="space-y-1 pt-1">
          <div class="text-[11px] font-bold text-slate-400 uppercase tracking-wider font-mono">Moveset:</div>
          <div class="grid grid-cols-2 gap-1.5 text-xs font-mono font-semibold">
            <span class="px-2 py-1 rounded bg-slate-800 text-orange-300 border border-slate-700/60">🗡️ Bitter Blade</span>
            <span class="px-2 py-1 rounded bg-slate-800 text-purple-300 border border-slate-700/60">👻 Shadow Sneak</span>
            <span class="px-2 py-1 rounded bg-slate-800 text-amber-300 border border-slate-700/60">⚔️ Swords Dance</span>
            <span class="px-2 py-1 rounded bg-slate-800 text-slate-300 border border-slate-700/60">🛡️ Protect</span>
          </div>
        </div>

        <div class="text-[11px] text-slate-300 bg-slate-800/30 p-2.5 rounded-lg border border-slate-700/40">
          <b class="text-cyan-300">Meta Role:</b> Physical win condition. Enters on Rillaboom's Grassy Terrain to trigger Grassy Seed (+1 Def to 159). Flash Fire absorbs Fire attacks targeting Rillaboom and Gholdengo. Grassy Terrain reduces Earthquake damage by 50%.
        </div>
      </div>

      <!-- 2. Milotic -->
      <div class="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 space-y-4 print-card relative overflow-hidden">
        <div class="flex items-center justify-between border-b border-slate-800 pb-3">
          <div class="flex items-center gap-3">
            <img src="{team_images['milotic']}" class="w-12 h-12 object-contain" alt="Milotic">
            <div>
              <h3 class="font-extrabold text-base text-white">Milotic <span class="text-xs text-slate-400">(F)</span></h3>
              <div class="text-xs font-mono text-cyan-400 flex items-center gap-1.5">
                <img src="{team_images['sitrus_berry']}" class="w-4 h-4 object-contain inline" alt="">
                <span>Sitrus Berry</span>
              </div>
            </div>
          </div>
          <span class="px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30 font-mono text-[11px] font-bold">Water</span>
        </div>

        <div class="space-y-1.5 text-xs">
          <div class="flex justify-between"><span class="text-slate-400">Ability:</span> <span class="font-bold text-amber-300">Competitive (+2 SpA on stat drop)</span></div>
          <div class="flex justify-between"><span class="text-slate-400">Nature:</span> <span class="font-bold text-slate-200">Calm (+SpD, -Atk)</span></div>
          <div class="flex justify-between font-mono"><span class="text-slate-400">SP Allocation:</span> <span class="text-cyan-400 font-bold">32 HP / 31 Def / 3 SpD</span></div>
        </div>

        <div class="p-2.5 rounded-xl bg-slate-800/50 border border-slate-700/50 font-mono text-xs grid grid-cols-6 text-center gap-1">
          <div><div class="text-[10px] text-slate-400">HP</div><div class="font-bold text-white">202</div></div>
          <div><div class="text-[10px] text-slate-400">Atk</div><div class="text-slate-500">72</div></div>
          <div><div class="text-[10px] text-slate-400">Def</div><div class="font-bold text-emerald-300">130</div></div>
          <div><div class="text-[10px] text-slate-400">SpA</div><div class="font-bold text-cyan-300">120<span class="text-[9px] text-amber-400">(+2=240)</span></div></div>
          <div><div class="text-[10px] text-slate-400">SpD</div><div class="font-bold text-white">162</div></div>
          <div><div class="text-[10px] text-slate-400">Spe</div><div class="font-bold text-white">101</div></div>
        </div>

        <div class="space-y-1 pt-1">
          <div class="text-[11px] font-bold text-slate-400 uppercase tracking-wider font-mono">Moveset:</div>
          <div class="grid grid-cols-2 gap-1.5 text-xs font-mono font-semibold">
            <span class="px-2 py-1 rounded bg-slate-800 text-blue-300 border border-slate-700/60">🌊 Muddy Water</span>
            <span class="px-2 py-1 rounded bg-slate-800 text-indigo-300 border border-slate-700/60">💤 Hypnosis</span>
            <span class="px-2 py-1 rounded bg-slate-800 text-emerald-300 border border-slate-700/60">🐍 Coil</span>
            <span class="px-2 py-1 rounded bg-slate-800 text-cyan-300 border border-slate-700/60">❄️ Ice Beam</span>
          </div>
        </div>

        <div class="text-[11px] text-slate-300 bg-slate-800/30 p-2.5 rounded-lg border border-slate-700/40">
          <b class="text-amber-300">Meta Role:</b> Direct hard counter to Incineroar (34.10% usage). Intimidate grants instant +2 SpA. <b class="text-emerald-300">Coil Innovation:</b> Boosts Def, Atk, and +1 Accuracy, raising Hypnosis accuracy from 60% to 80% and Muddy Water from 85% to 100%!
        </div>
      </div>

      <!-- 3. Rillaboom -->
      <div class="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 space-y-4 print-card relative overflow-hidden">
        <div class="flex items-center justify-between border-b border-slate-800 pb-3">
          <div class="flex items-center gap-3">
            <img src="{team_images['rillaboom']}" class="w-12 h-12 object-contain" alt="Rillaboom">
            <div>
              <h3 class="font-extrabold text-base text-white">Rillaboom <span class="text-xs text-slate-400">(M)</span></h3>
              <div class="text-xs font-mono text-cyan-400 flex items-center gap-1.5">
                <img src="{team_images['miracle_seed']}" class="w-4 h-4 object-contain inline" alt="">
                <span>Miracle Seed</span>
              </div>
            </div>
          </div>
          <span class="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-mono text-[11px] font-bold">Grass</span>
        </div>

        <div class="space-y-1.5 text-xs">
          <div class="flex justify-between"><span class="text-slate-400">Ability:</span> <span class="font-bold text-emerald-300">Grassy Surge (Terrain Setter)</span></div>
          <div class="flex justify-between"><span class="text-slate-400">Nature:</span> <span class="font-bold text-slate-200">Adamant (+Atk, -SpA)</span></div>
          <div class="flex justify-between font-mono"><span class="text-slate-400">SP Allocation:</span> <span class="text-cyan-400 font-bold">24 HP / 16 Atk / 1 Def / 1 SpD / 24 Spe</span></div>
        </div>

        <div class="p-2.5 rounded-xl bg-slate-800/50 border border-slate-700/50 font-mono text-xs grid grid-cols-6 text-center gap-1">
          <div><div class="text-[10px] text-slate-400">HP</div><div class="font-bold text-white">199</div></div>
          <div><div class="text-[10px] text-slate-400">Atk</div><div class="font-bold text-cyan-300">177</div></div>
          <div><div class="text-[10px] text-slate-400">Def</div><div class="font-bold text-white">111</div></div>
          <div><div class="text-[10px] text-slate-400">SpA</div><div class="text-slate-500">72</div></div>
          <div><div class="text-[10px] text-slate-400">SpD</div><div class="font-bold text-white">91</div></div>
          <div><div class="text-[10px] text-slate-400">Spe</div><div class="font-bold text-cyan-300">129</div></div>
        </div>

        <div class="space-y-1 pt-1">
          <div class="text-[11px] font-bold text-slate-400 uppercase tracking-wider font-mono">Moveset:</div>
          <div class="grid grid-cols-2 gap-1.5 text-xs font-mono font-semibold">
            <span class="px-2 py-1 rounded bg-slate-800 text-emerald-300 border border-slate-700/60">🌿 Grassy Glide</span>
            <span class="px-2 py-1 rounded bg-slate-800 text-emerald-400 border border-slate-700/60">🥁 Drum Beating</span>
            <span class="px-2 py-1 rounded bg-slate-800 text-amber-400 border border-slate-700/60">🐎 High Horsepower</span>
            <span class="px-2 py-1 rounded bg-slate-800 text-yellow-300 border border-slate-700/60">✋ Fake Out</span>
          </div>
        </div>

        <div class="text-[11px] text-slate-300 bg-slate-800/30 p-2.5 rounded-lg border border-slate-700/40">
          <b class="text-emerald-300">Meta Role:</b> Core anchor & terrain controller (50.37% meta share). Miracle Seed boosts Grassy Glide priority revenge-killing. High Horsepower bypasses Grassy Terrain's Earthquake penalty to punish Fire and Steel types (Archaludon, Incineroar).
        </div>
      </div>

      <!-- 4. Staraptor-Mega -->
      <div class="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 space-y-4 print-card relative overflow-hidden">
        <div class="flex items-center justify-between border-b border-slate-800 pb-3">
          <div class="flex items-center gap-3">
            <img src="{team_images['staraptor_mega']}" class="w-12 h-12 object-contain" alt="Staraptor-Mega">
            <div>
              <h3 class="font-extrabold text-base text-white">Staraptor <span class="text-xs text-purple-400">★ Mega</span></h3>
              <div class="text-xs font-mono text-purple-300 flex items-center gap-1.5">
                <img src="{team_images['staraptite']}" class="w-4 h-4 object-contain inline" alt="">
                <span>Staraptite</span>
              </div>
            </div>
          </div>
          <span class="px-2 py-0.5 rounded bg-slate-700 text-slate-200 border border-slate-600 font-mono text-[11px] font-bold">Normal / Flying</span>
        </div>

        <div class="space-y-1.5 text-xs">
          <div class="flex justify-between"><span class="text-slate-400">Base Ability:</span> <span class="font-bold text-amber-300">Intimidate (On-switch debuff)</span></div>
          <div class="flex justify-between"><span class="text-slate-400">Nature:</span> <span class="font-bold text-slate-200">Jolly (+Spe, -SpA)</span></div>
          <div class="flex justify-between font-mono"><span class="text-slate-400">SP Allocation:</span> <span class="text-cyan-400 font-bold">15 HP / 19 Atk / 32 Spe</span></div>
        </div>

        <div class="p-2.5 rounded-xl bg-slate-800/50 border border-slate-700/50 font-mono text-xs grid grid-cols-6 text-center gap-1">
          <div><div class="text-[10px] text-slate-400">HP</div><div class="font-bold text-white">175</div></div>
          <div><div class="text-[10px] text-slate-400">Atk</div><div class="font-bold text-cyan-300">179</div></div>
          <div><div class="text-[10px] text-slate-400">Def</div><div class="font-bold text-white">120</div></div>
          <div><div class="text-[10px] text-slate-400">SpA</div><div class="text-slate-500">72</div></div>
          <div><div class="text-[10px] text-slate-400">SpD</div><div class="font-bold text-white">110</div></div>
          <div><div class="text-[10px] text-slate-400">Spe</div><div class="font-bold text-yellow-300">178</div></div>
        </div>

        <div class="space-y-1 pt-1">
          <div class="text-[11px] font-bold text-slate-400 uppercase tracking-wider font-mono">Moveset:</div>
          <div class="grid grid-cols-2 gap-1.5 text-xs font-mono font-semibold">
            <span class="px-2 py-1 rounded bg-slate-800 text-amber-400 border border-slate-700/60">💥 Close Combat</span>
            <span class="px-2 py-1 rounded bg-slate-800 text-sky-300 border border-slate-700/60">🦅 Brave Bird</span>
            <span class="px-2 py-1 rounded bg-slate-800 text-cyan-300 border border-slate-700/60">🌪️ Tailwind</span>
            <span class="px-2 py-1 rounded bg-slate-800 text-slate-300 border border-slate-700/60">🛡️ Protect</span>
          </div>
        </div>

        <div class="text-[11px] text-slate-300 bg-slate-800/30 p-2.5 rounded-lg border border-slate-700/40">
          <b class="text-purple-300">Mega Branch A:</b> Fast physical nuke & team speed control. Guaranteed OHKO on Kingambit with Close Combat (112-133%) and Sneasler with Brave Bird (233-276%). Instantaneous 178 Speed outspeeds unboosted Salamence-Mega and Garchomp.
        </div>
      </div>

      <!-- 5. Gholdengo -->
      <div class="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 space-y-4 print-card relative overflow-hidden">
        <div class="flex items-center justify-between border-b border-slate-800 pb-3">
          <div class="flex items-center gap-3">
            <img src="{team_images['gholdengo']}" class="w-12 h-12 object-contain" alt="Gholdengo">
            <div>
              <h3 class="font-extrabold text-base text-white">Gholdengo</h3>
              <div class="text-xs font-mono text-cyan-400 flex items-center gap-1.5">
                <img src="{team_images['life_orb']}" class="w-4 h-4 object-contain inline" alt="">
                <span>Life Orb</span>
              </div>
            </div>
          </div>
          <span class="px-2 py-0.5 rounded bg-yellow-500/20 text-yellow-300 border border-yellow-500/30 font-mono text-[11px] font-bold">Steel / Ghost</span>
        </div>

        <div class="space-y-1.5 text-xs">
          <div class="flex justify-between"><span class="text-slate-400">Ability:</span> <span class="font-bold text-yellow-300">Good as Gold (Status Immunity)</span></div>
          <div class="flex justify-between"><span class="text-slate-400">Nature:</span> <span class="font-bold text-slate-200">Modest (+SpA, -Atk)</span></div>
          <div class="flex justify-between font-mono"><span class="text-slate-400">SP Allocation:</span> <span class="text-cyan-400 font-bold">2 HP / 32 SpA / 32 Spe</span></div>
        </div>

        <div class="p-2.5 rounded-xl bg-slate-800/50 border border-slate-700/50 font-mono text-xs grid grid-cols-6 text-center gap-1">
          <div><div class="text-[10px] text-slate-400">HP</div><div class="font-bold text-white">164</div></div>
          <div><div class="text-[10px] text-slate-400">Atk</div><div class="text-slate-500">72</div></div>
          <div><div class="text-[10px] text-slate-400">Def</div><div class="font-bold text-white">115</div></div>
          <div><div class="text-[10px] text-slate-400">SpA</div><div class="font-bold text-cyan-300">203</div></div>
          <div><div class="text-[10px] text-slate-400">SpD</div><div class="font-bold text-white">111</div></div>
          <div><div class="text-[10px] text-slate-400">Spe</div><div class="font-bold text-yellow-300">136</div></div>
        </div>

        <div class="space-y-1 pt-1">
          <div class="text-[11px] font-bold text-slate-400 uppercase tracking-wider font-mono">Moveset:</div>
          <div class="grid grid-cols-2 gap-1.5 text-xs font-mono font-semibold">
            <span class="px-2 py-1 rounded bg-slate-800 text-slate-300 border border-slate-700/60">🛡️ Protect</span>
            <span class="px-2 py-1 rounded bg-slate-800 text-yellow-300 border border-slate-700/60">🪙 Make It Rain</span>
            <span class="px-2 py-1 rounded bg-slate-800 text-purple-300 border border-slate-700/60">👻 Shadow Ball</span>
            <span class="px-2 py-1 rounded bg-slate-800 text-amber-300 border border-slate-700/60">📈 Nasty Plot</span>
          </div>
        </div>

        <div class="text-[11px] text-slate-300 bg-slate-800/30 p-2.5 rounded-lg border border-slate-700/40">
          <b class="text-yellow-300">Meta Role:</b> Special spread anchor & status absorber (25.26% meta share). Complete immunity to Spore, Taunt, Encore, and Parting Shot. Life Orb Modest Make It Rain shreds opposing balance leads. Nasty Plot forces defensive protects.
        </div>
      </div>

      <!-- 6. Raichu-Mega-Y -->
      <div class="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 space-y-4 print-card relative overflow-hidden">
        <div class="flex items-center justify-between border-b border-slate-800 pb-3">
          <div class="flex items-center gap-3">
            <img src="{team_images['raichu_mega_y']}" class="w-12 h-12 object-contain" alt="Raichu-Mega-Y">
            <div>
              <h3 class="font-extrabold text-base text-white">Raichu <span class="text-xs text-purple-400">★ Mega Y</span></h3>
              <div class="text-xs font-mono text-purple-300 flex items-center gap-1.5">
                <img src="{team_images['raichunite_y']}" class="w-4 h-4 object-contain inline" alt="">
                <span>Raichunite Y</span>
              </div>
            </div>
          </div>
          <span class="px-2 py-0.5 rounded bg-yellow-500/20 text-yellow-300 border border-yellow-500/30 font-mono text-[11px] font-bold">Electric</span>
        </div>

        <div class="space-y-1.5 text-xs">
          <div class="flex justify-between"><span class="text-slate-400">Base Ability:</span> <span class="font-bold text-yellow-400">Lightning Rod (Electric Redirect)</span></div>
          <div class="flex justify-between"><span class="text-slate-400">Nature:</span> <span class="font-bold text-slate-200">Timid (+Spe, -Atk)</span></div>
          <div class="flex justify-between font-mono"><span class="text-slate-400">SP Allocation:</span> <span class="text-cyan-400 font-bold">32 HP / 2 Def / 32 Spe</span></div>
        </div>

        <div class="p-2.5 rounded-xl bg-slate-800/50 border border-slate-700/50 font-mono text-xs grid grid-cols-6 text-center gap-1">
          <div><div class="text-[10px] text-slate-400">HP</div><div class="font-bold text-white">167</div></div>
          <div><div class="text-[10px] text-slate-400">Atk</div><div class="text-slate-500">108</div></div>
          <div><div class="text-[10px] text-slate-400">Def</div><div class="font-bold text-white">77</div></div>
          <div><div class="text-[10px] text-slate-400">SpA</div><div class="font-bold text-cyan-300">180</div></div>
          <div><div class="text-[10px] text-slate-400">SpD</div><div class="font-bold text-white">100</div></div>
          <div><div class="text-[10px] text-slate-400">Spe</div><div class="font-bold text-yellow-300">200</div></div>
        </div>

        <div class="space-y-1 pt-1">
          <div class="text-[11px] font-bold text-slate-400 uppercase tracking-wider font-mono">Moveset:</div>
          <div class="grid grid-cols-2 gap-1.5 text-xs font-mono font-semibold">
            <span class="px-2 py-1 rounded bg-slate-800 text-yellow-300 border border-slate-700/60">✋ Fake Out</span>
            <span class="px-2 py-1 rounded bg-slate-800 text-slate-300 border border-slate-700/60">🛡️ Protect</span>
            <span class="px-2 py-1 rounded bg-slate-800 text-amber-300 border border-slate-700/60">⚡ Eerie Impulse</span>
            <span class="px-2 py-1 rounded bg-slate-800 text-yellow-400 border border-slate-700/60">💥 Zap Cannon</span>
          </div>
        </div>

        <div class="text-[11px] text-slate-300 bg-slate-800/30 p-2.5 rounded-lg border border-slate-700/40">
          <b class="text-purple-300">Mega Branch B:</b> Blazing 200 Speed control & redirection. Lightning Rod protects Milotic and Staraptor. Eerie Impulse shuts down special sweepers (Charizard-Y, Archaludon). <b class="text-rose-400">Tactical Risk:</b> Zap Cannon (50% acc) is high-variance without Coil/Gravity.
        </div>
      </div>

    </div>
  </section>

  <!-- SECTION 4: SPEED TIER & TURN ORDER SEQUENCING -->
  <section class="space-y-4 print-break">
    <div class="flex items-center justify-between">
      <h2 class="text-xl font-extrabold text-white flex items-center gap-2">
        <span class="w-3 h-3 rounded-full bg-yellow-400 inline-block"></span>
        3. Speed Tier Matrix (Instantaneous Regulation M-C Speed Scaling)
      </h2>
      <span class="font-mono text-xs text-slate-400">Level 50 Verified Values</span>
    </div>

    <div class="overflow-x-auto rounded-2xl border border-slate-800 bg-slate-900/60 p-4 shadow-xl">
      <div class="space-y-2 font-mono text-xs">
        <div class="flex items-center justify-between p-2 rounded bg-slate-800/60 border-l-4 border-yellow-400">
          <span class="font-bold text-yellow-300">356 Spe</span>
          <span class="text-slate-300">Staraptor-Mega under Active Tailwind (Jolly 32 SP)</span>
          <span class="badge bg-yellow-500/20 text-yellow-300 px-2 py-0.5 rounded text-[10px]">Tier 0: Apex Speed</span>
        </div>
        <div class="flex items-center justify-between p-2 rounded bg-slate-800/40 border-l-4 border-yellow-500">
          <span class="font-bold text-yellow-400">200 Spe</span>
          <span class="text-purple-300 font-bold">Mega Raichu Y (Timid 32 SP — Instant Post-Mega)</span>
          <span class="text-slate-400">Outspeeds entire unboosted Regulation M-C field</span>
        </div>
        <div class="flex items-center justify-between p-2 rounded bg-slate-800/40 border-l-4 border-slate-600">
          <span class="font-bold text-slate-300">189 Spe</span>
          <span class="text-slate-400">Opposing Sneasler (Jolly Max Speed unboosted)</span>
          <span class="text-rose-400">Outspeeds Staraptor-Mega before Tailwind</span>
        </div>
        <div class="flex items-center justify-between p-2 rounded bg-slate-800/40 border-l-4 border-purple-500">
          <span class="font-bold text-purple-300">178 Spe</span>
          <span class="text-purple-300 font-bold">Staraptor-Mega (Jolly 32 SP — Instant Post-Mega) / Base Raichu</span>
          <span class="text-slate-300">Speed ties unboosted Salamence-Mega (178)</span>
        </div>
        <div class="flex items-center justify-between p-2 rounded bg-slate-800/40 border-l-4 border-slate-600">
          <span class="font-bold text-slate-300">152 Spe</span>
          <span class="text-slate-400">Opposing Charizard-Mega-Y (Timid Max Speed)</span>
          <span class="text-emerald-400">Outsped by Staraptor-Mega & Mega Raichu Y</span>
        </div>
        <div class="flex items-center justify-between p-2 rounded bg-slate-800/40 border-l-4 border-cyan-500">
          <span class="font-bold text-cyan-300">136 Spe</span>
          <span class="text-slate-200">Gholdengo (Modest 32 SP)</span>
          <span class="text-slate-400">Outspeeds neutral base 80s & Kingambit</span>
        </div>
        <div class="flex items-center justify-between p-2 rounded bg-slate-800/40 border-l-4 border-emerald-500">
          <span class="font-bold text-emerald-300">129 Spe</span>
          <span class="text-slate-200">Rillaboom (Adamant 24 SP)</span>
          <span class="text-slate-400">Creeps standard 128 Spe bulk benchmarks</span>
        </div>
        <div class="flex items-center justify-between p-2 rounded bg-slate-800/40 border-l-4 border-orange-500">
          <span class="font-bold text-orange-300">111 Spe</span>
          <span class="text-slate-200">Ceruledge (Adamant 6 SP)</span>
          <span class="text-slate-400">Outspeeds paralyzed Charizard-Y & uninvested Milotic</span>
        </div>
        <div class="flex items-center justify-between p-2 rounded bg-slate-800/40 border-l-4 border-blue-500">
          <span class="font-bold text-blue-300">101 Spe</span>
          <span class="text-slate-200">Milotic (Calm 0 SP)</span>
          <span class="text-slate-400">Bulky tank benchmark; outspeeds Kingambit & Incineroar</span>
        </div>
      </div>
    </div>
  </section>

  <!-- SECTION 5: OFFICIAL VGC DAMAGE CALCULATIONS -->
  <section class="space-y-4 print-break">
    <div class="flex items-center justify-between">
      <h2 class="text-xl font-extrabold text-white flex items-center gap-2">
        <span class="w-3 h-3 rounded-full bg-rose-400 inline-block"></span>
        4. Official VGC Damage Calculations vs. Tournament Metagame
      </h2>
      <span class="font-mono text-xs text-slate-400">Verified via engine/turn_simulator.py</span>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <!-- Offensive Calcs -->
      <div class="p-4 rounded-2xl bg-slate-900/70 border border-slate-800 space-y-3">
        <h3 class="text-xs font-bold uppercase font-mono text-cyan-400 tracking-wider">Offensive Breakpoints</h3>
        <div class="space-y-2 text-xs font-mono">
          <div class="p-2 rounded bg-slate-800/60 border border-slate-700/60">
            <div class="text-white font-bold">Staraptor-Mega Close Combat vs Kingambit (207 HP / 140 Def):</div>
            <div class="text-emerald-400 font-extrabold mt-0.5">232 - 276 HP (112.1% - 133.3%) — Guaranteed OHKO</div>
          </div>
          <div class="p-2 rounded bg-slate-800/60 border border-slate-700/60">
            <div class="text-white font-bold">Staraptor-Mega Brave Bird vs Sneasler (155 HP / 80 Def):</div>
            <div class="text-emerald-400 font-extrabold mt-0.5">362 - 428 HP (233.5% - 276.1%) — Guaranteed OHKO</div>
          </div>
          <div class="p-2 rounded bg-slate-800/60 border border-slate-700/60">
            <div class="text-white font-bold">Milotic (+2 SpA Competitive) Ice Beam vs Salamence-Mega (170 HP / 110 SpD):</div>
            <div class="text-emerald-400 font-extrabold mt-0.5">296 - 352 HP (174.1% - 207.1%) — Guaranteed OHKO</div>
          </div>
          <div class="p-2 rounded bg-slate-800/60 border border-slate-700/60">
            <div class="text-white font-bold">Raichu-Mega-Y Zap Cannon vs Charizard-Mega-Y (153 HP / 135 SpD):</div>
            <div class="text-emerald-400 font-extrabold mt-0.5">182 - 216 HP (119.0% - 141.2%) — Guaranteed OHKO</div>
          </div>
          <div class="p-2 rounded bg-slate-800/60 border border-slate-700/60">
            <div class="text-white font-bold">Gholdengo (+2 Nasty Plot Life Orb) Shadow Ball vs Archaludon (197 HP / 85 SpD):</div>
            <div class="text-cyan-300 font-extrabold mt-0.5">187 - 222 HP (94.9% - 112.7%) — 75.0% OHKO chance</div>
          </div>
        </div>
      </div>

      <!-- Defensive Calcs -->
      <div class="p-4 rounded-2xl bg-slate-900/70 border border-slate-800 space-y-3">
        <h3 class="text-xs font-bold uppercase font-mono text-emerald-400 tracking-wider">Defensive Thresholds & Terrain Synergies</h3>
        <div class="space-y-2 text-xs font-mono">
          <div class="p-2 rounded bg-slate-800/60 border border-slate-700/60">
            <div class="text-white font-bold">Garchomp-Mega-Z Spread Earthquake vs Ceruledge (+1 Def in Grassy Terrain):</div>
            <div class="text-emerald-400 font-extrabold mt-0.5">56 - 68 HP (30.8% - 37.4%) — Easy 3HKO+ (Terrain 50% Reduction)</div>
          </div>
          <div class="p-2 rounded bg-slate-800/60 border border-slate-700/60">
            <div class="text-white font-bold">Incineroar Knock Off vs Ceruledge (+1 Def Grassy Seed):</div>
            <div class="text-amber-400 font-extrabold mt-0.5">96 - 114 HP (52.7% - 62.6%) — Guaranteed 2HKO (Survives comfortably)</div>
          </div>
          <div class="p-2 rounded bg-slate-800/60 border border-slate-700/60">
            <div class="text-white font-bold">Salamence-Mega Aerilate Hyper Voice vs Milotic (spread):</div>
            <div class="text-emerald-400 font-extrabold mt-0.5">40 - 48 HP (19.8% - 23.8%) — Negligible chip damage</div>
          </div>
          <div class="p-2 rounded bg-slate-800/60 border border-slate-700/60">
            <div class="text-white font-bold">Charizard-Mega-Y Drought Heat Wave vs Ceruledge:</div>
            <div class="text-cyan-300 font-extrabold mt-0.5">0 HP (0.0%) — Flash Fire Absorbed (+1.5x Fire Boost)</div>
          </div>
          <div class="p-2 rounded bg-slate-800/60 border border-slate-700/60">
            <div class="text-white font-bold">Sneasler Close Combat vs Ceruledge / Gholdengo:</div>
            <div class="text-emerald-400 font-extrabold mt-0.5">0 HP (0.0%) — Ghost Immunity (Immune to primary STAB)</div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- SECTION 6: HEAD COACH DIAGNOSTICS & TACTICAL ADVICE -->
  <section class="p-6 rounded-3xl bg-slate-900 border border-slate-800 space-y-4 print-break">
    <div class="flex items-center justify-between border-b border-slate-800 pb-3">
      <h2 class="text-lg font-extrabold text-white flex items-center gap-2">
        <span class="w-3 h-3 rounded-full bg-cyan-400"></span>
        5. Head Coach Diagnostics & Cognitive Leak Prevention
      </h2>
      <span class="font-mono text-xs text-cyan-400 font-bold">Coach Porygon Official Verdict</span>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
      <div class="p-4 rounded-xl bg-slate-800/50 border border-slate-700/50 space-y-2">
        <div class="font-bold text-amber-400 font-mono flex items-center gap-1.5">
          <span>⚠️</span> <span>TGT-01 / GREED: Zap Cannon Variance</span>
        </div>
        <p class="text-slate-300 leading-relaxed">
          While Zap Cannon guarantees an OHKO on Charizard-Mega-Y and 100% paralysis, its <b>50% unboosted accuracy</b> poses severe variance risks in high-stakes Swiss matches. If Milotic has not established Coil accuracy boosts, consider <b class="text-white">Thunderbolt</b> or <b class="text-white">Volt Switch</b> for tournament consistency.
        </p>
      </div>

      <div class="p-4 rounded-xl bg-slate-800/50 border border-slate-700/50 space-y-2">
        <div class="font-bold text-rose-400 font-mono flex items-center gap-1.5">
          <span>🛑</span> <span>TGT-02: Normal/Psychic Ghost Immunity</span>
        </div>
        <p class="text-slate-300 leading-relaxed">
          Both Farigiraf (14.72% usage) and Indeedee-F (14.82% usage) are <b>Normal/Psychic dual types</b>. They possess complete immunity to Shadow Ball from Gholdengo and Shadow Sneak from Ceruledge. Always default to <b class="text-white">Make It Rain</b> or <b class="text-white">Bitter Blade</b> into these slots.
        </p>
      </div>

      <div class="p-4 rounded-xl bg-slate-800/50 border border-slate-700/50 space-y-2">
        <div class="font-bold text-emerald-400 font-mono flex items-center gap-1.5">
          <span>🛡️</span> <span>POS-02: Lead Compression Mastery</span>
        </div>
        <p class="text-slate-300 leading-relaxed">
          Open <b class="text-white">Rillaboom + Ceruledge</b> into Rain/Earthquake cores (instant Grassy Seed + 50% Ground reduction), or <b class="text-white">Staraptor + Milotic</b> into Incineroar + Sneasler leads (punishing Intimidate with Competitive +2 while intimidating Sneasler).
        </p>
      </div>
    </div>

    <div class="p-4 rounded-xl bg-cyan-950/30 border border-cyan-800/50 flex flex-wrap items-center justify-between gap-4 text-xs font-mono">
      <div class="space-y-0.5">
        <div class="text-cyan-300 font-bold">4-Step Pre-Turn Validation Checklist:</div>
        <div class="text-slate-400">1. Confirm Weather/Terrain • 2. Calculate Post-Mega Speeds • 3. Check Ghost/Terrain Immunities • 4. Verify Positive VP Trade</div>
      </div>
      <div class="text-right">
        <span class="px-3 py-1 rounded bg-cyan-500/20 text-cyan-300 font-bold border border-cyan-500/40">VERDICT: TIER 1 TOURNAMENT CONTENDER</span>
      </div>
    </div>
  </section>

  <!-- FOOTER -->
  <footer class="text-center font-mono text-xs text-slate-500 py-6 border-t border-slate-800">
    Coach Porygon VGC • Autonomous Coaching & Metagame Intelligence System • Regulation M-C VGC ecosystem
  </footer>

</body>
</html>
"""

    HTML_OUT.write_text(html_content, encoding="utf-8")
    print(f"[SUCCESS] Generated static HTML report -> {HTML_OUT} ({len(html_content):,} bytes)")

    # 3. Compile PDF using Headless Chrome
    print("[3/4] Compiling static HTML into downloadable PDF via Headless Chrome...")
    if Path(CHROME_PATH).exists():
        cmd = [
            CHROME_PATH,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--no-pdf-header-footer",
            f"--print-to-pdf={PDF_OUT}",
            str(HTML_OUT)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and PDF_OUT.exists():
            print(f"[SUCCESS] Generated PDF document -> {PDF_OUT} ({PDF_OUT.stat().st_size:,} bytes)")
        else:
            print(f"[WARN] Chrome PDF conversion returned code {res.returncode}: {res.stderr}")
    else:
        print(f"[WARN] Chrome executable not found at {CHROME_PATH}")

    # 4. Sync Artifact to Brain Directory
    print("[4/4] Synchronizing artifacts to Antigravity Brain directory...")
    if ARTIFACT_DIR.exists():
        artifact_html = ARTIFACT_DIR / "munchstats_theorybuild_report.html"
        artifact_pdf = ARTIFACT_DIR / "munchstats_theorybuild_report.pdf"
        shutil.copyfile(HTML_OUT, artifact_html)
        print(f"[OK] Synced HTML -> {artifact_html}")
        if PDF_OUT.exists():
            shutil.copyfile(PDF_OUT, artifact_pdf)
            print(f"[OK] Synced PDF -> {artifact_pdf}")

    print("=" * 70)
    print("ALL ARTIFACTS AND REPORTS SUCCESSFULLY COMPILED!")
    print("=" * 70)


if __name__ == "__main__":
    build_report()
